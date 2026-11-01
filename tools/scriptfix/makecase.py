"""Case recipes: build a script-fix case's reference and broken input from grading/recipe.toml.

A recipe names a source script (repo-relative), an optional cut of it, and a
list of one-line edits. The cut source is the case's reference; the reference
with the edits applied is the case's input. ``load_recipe`` and
``build_scripts`` are pure: the only I/O is reading the recipe and the source.

``make_case`` then captures the case: it replays the reference and the input
once each (strictly one at a time, never retried) and, only if both behave as
the case says, writes the case's scripts, prompt, evidence and
``grading/capture.toml``. The input is replayed in a neutral folder
(``<temp>/pwrun``) with a venv outside the repo, so the evidence never names
the repo. Any surprise returns 1 having written nothing.
"""

from __future__ import annotations

import datetime
import difflib
import json
import re
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from scriptfix import replay as replay_module
from scriptfix.case import Case, load_case
from scriptfix.grade import Out, ReplayFn, replay_summary
from scriptfix.replay import ReplayResult

RECIPE_KEYS = ("source", "cut", "edit")
EDIT_KEYS = ("line", "old", "new", "delete", "insert")
KINDS = ("replace", "delete", "insert")


@dataclass(frozen=True)
class Edit:
    line: int  # a line of the reference (after the cut), 1-based
    kind: str  # "replace" | "delete" | "insert"
    old: str = ""  # replace: occurs exactly once on the line
    new: str = ""  # replace
    text: str = ""  # insert (indented like `line`)


@dataclass(frozen=True)
class Recipe:
    path: Path  # the recipe.toml
    source: str  # repo-relative, forward slashes
    cut: tuple[int, int] | None  # source lines [first, last], inclusive
    edits: tuple[Edit, ...]


def _fail(path: Path, message: str) -> ValueError:
    return ValueError(f"{message}: {path}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_source_path(source: str, path: Path) -> None:
    windows = PureWindowsPath(source)
    if source.startswith(("/", "\\")) or windows.drive or windows.is_absolute():
        raise _fail(path, f"recipe key 'source' must be repo-relative, not absolute ({source!r})")
    if ".." in re.split(r"[\\/]", source):
        raise _fail(path, f"recipe key 'source' must not contain '..' ({source!r})")


def _single_line(path: Path, label: str, key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise _fail(path, f"recipe {label}: '{key}' must be a single line (no newline)")


def _load_edit(index: int, raw: object, path: Path) -> Edit:
    """Validate one [[edit]] table; the label names its line once that is known."""
    label = f"edit #{index}"
    if not isinstance(raw, dict):
        raise _fail(path, f"recipe [[edit]] #{index} must be a table, got {raw!r}")
    for key in raw:
        if key not in EDIT_KEYS:
            raise _fail(path, f"recipe {label} has unknown key '{key}'")
    if "line" not in raw:
        raise _fail(path, f"recipe {label} is missing key 'line'")
    line = raw["line"]
    if not _is_int(line):
        raise _fail(path, f"recipe {label} key 'line' must be an integer, got {line!r}")
    label = f"edit at line {line}"
    if line < 1:
        raise _fail(path, f"recipe {label}: 'line' must be at least 1")

    replace = "old" in raw or "new" in raw
    delete = "delete" in raw
    insert = "insert" in raw
    if replace + delete + insert != 1:
        raise _fail(
            path,
            f"recipe {label} needs exactly one of 'old' + 'new', 'delete = true' or 'insert'",
        )

    for key in ("old", "new", "insert"):
        if key in raw:
            if not isinstance(raw[key], str):
                raise _fail(path, f"recipe {label} key '{key}' must be a string, got {raw[key]!r}")
            _single_line(path, label, key, raw[key])

    if replace:
        for key in ("old", "new"):
            if key not in raw:
                raise _fail(path, f"recipe {label} has 'old' or 'new' without '{key}'")
        if raw["old"] == "":
            raise _fail(path, f"recipe {label} key 'old' must not be empty")
        return Edit(line=line, kind="replace", old=raw["old"], new=raw["new"])
    if delete:
        value = raw["delete"]
        if not isinstance(value, bool):
            raise _fail(path, f"recipe {label} key 'delete' must be true, got {value!r}")
        if not value:
            raise _fail(path, f"recipe {label} has 'delete = false'; omit the edit instead")
        return Edit(line=line, kind="delete")
    return Edit(line=line, kind="insert", text=raw["insert"])


def load_recipe(case_dir: Path) -> Recipe:
    """Read <case_dir>/grading/recipe.toml; raise ValueError naming the bad key or line."""
    path = Path(case_dir) / "grading" / "recipe.toml"
    if not path.is_file():
        raise ValueError(f"recipe.toml not found: {path}")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise _fail(path, f"recipe.toml is not valid TOML ({error})") from error

    for key in data:
        if key not in RECIPE_KEYS:
            raise _fail(path, f"recipe has unknown key '{key}'")
    if "source" not in data:
        raise _fail(path, "recipe is missing required key 'source'")
    source = data["source"]
    if not isinstance(source, str) or not source:
        raise _fail(path, f"recipe key 'source' must be a non-empty string, got {source!r}")
    _check_source_path(source, path)

    cut: tuple[int, int] | None = None
    if "cut" in data:
        raw_cut = data["cut"]
        if not isinstance(raw_cut, list) or len(raw_cut) != 2 or not all(map(_is_int, raw_cut)):
            raise _fail(path, f"recipe key 'cut' must be a list of two integers, got {raw_cut!r}")
        first, last = raw_cut
        if not 1 <= first <= last:
            raise _fail(path, f"recipe key 'cut' needs 1 <= first <= last, got {raw_cut!r}")
        cut = (first, last)

    raw_edits = data.get("edit", [])
    if not isinstance(raw_edits, list):
        raise _fail(path, f"recipe key 'edit' must be an array of tables, got {raw_edits!r}")
    edits = tuple(_load_edit(index, raw, path) for index, raw in enumerate(raw_edits, start=1))
    seen: set[int] = set()
    for edit in edits:
        if edit.line in seen:
            raise _fail(path, f"recipe has two edits on line {edit.line}")
        seen.add(edit.line)

    return Recipe(path=path, source=source, cut=cut, edits=edits)


def _split_lines(text: str) -> list[str]:
    """Split on \\n only, keeping each line's ending (\\n or \\r\\n) on the line."""
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def _split_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _read_source(recipe: Recipe, repo_root: Path) -> str:
    source = Path(repo_root) / recipe.source
    if not source.is_file():
        raise _fail(recipe.path, f"recipe key 'source' does not exist ({recipe.source!r})")
    try:
        return source.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise _fail(
            recipe.path, f"recipe key 'source' is not valid UTF-8 ({recipe.source!r}: {error})"
        ) from error


def _apply(edit: Edit, lines: list[str], recipe: Recipe) -> None:
    """Apply one edit to `lines` in place (callers go from the highest line down)."""
    index = edit.line - 1
    body, ending = _split_ending(lines[index])
    if edit.kind == "replace":
        count = body.count(edit.old)
        if count != 1:
            raise _fail(
                recipe.path,
                f"recipe edit at line {edit.line}: 'old' {edit.old!r} must occur exactly once"
                f" on the line, found {count} times",
            )
        lines[index] = body.replace(edit.old, edit.new, 1) + ending
    elif edit.kind == "delete":
        del lines[index]
    elif edit.kind == "insert":
        indent = body[: len(body) - len(body.lstrip(" \t"))]
        inserted = (indent + edit.text if edit.text else "") + (ending or "\n")
        lines.insert(index, inserted)
    else:
        raise _fail(recipe.path, f"recipe edit at line {edit.line} has unknown kind {edit.kind!r}")


def build_scripts(recipe: Recipe, repo_root: Path) -> tuple[str, str]:
    """Return (reference, input): the cut source, and that with the edits applied."""
    lines = _split_lines(_read_source(recipe, repo_root))
    if recipe.cut is not None:
        first, last = recipe.cut
        if last > len(lines):
            raise _fail(
                recipe.path,
                f"recipe key 'cut' {[first, last]} is past the end of the source"
                f" ({len(lines)} lines)",
            )
        lines = lines[: first - 1] + lines[last:]
    reference_lines = list(lines)
    for edit in recipe.edits:
        if not 1 <= edit.line <= len(reference_lines):
            raise _fail(
                recipe.path,
                f"recipe edit at line {edit.line} is outside the reference"
                f" ({len(reference_lines)} lines)",
            )
    for edit in sorted(recipe.edits, key=lambda item: item.line, reverse=True):
        _apply(edit, lines, recipe)
    reference, broken = "".join(reference_lines), "".join(lines)
    if broken == reference:
        raise _fail(recipe.path, "recipe edits leave the input identical to the reference")
    return reference, broken


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------

SHARED_PROMPT = "rubrics/script-fix/prompt.md"
PROBE_CODE = (
    "import sys, importlib.metadata as m; "
    "print(sys.version.split()[0]); print(m.version('playwright'))"
)
PROBE_TIMEOUT_S = 60
CAPTURE_COMMENT = "# Written by 10-make-case.ps1 from recipe.toml; regenerate, don't edit."


@dataclass(frozen=True)
class CaptureResult:
    """What a good capture saw: both replays, the evidence and the tool versions."""

    reference: ReplayResult
    input: ReplayResult
    results_txt: bytes
    trace: bytes
    python_version: str
    playwright_version: str


class _Surprise(Exception):
    """The capture did not go as the case says; nothing gets written."""


def probe_versions(python: Path) -> tuple[str, str]:
    """Return (python version, playwright version) of the capture venv's ``python``.

    Raises ``RuntimeError("version probe failed: ...")`` when the probe can't
    run, exits non-zero or doesn't print exactly two lines.
    """
    try:
        done = subprocess.run(
            [str(python), "-c", PROBE_CODE],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"version probe failed: {error}") from error
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"version probe failed: exit {done.returncode}: {detail[0]}")
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise RuntimeError(f"version probe failed: expected two lines, got {done.stdout!r}")
    return lines[0], lines[1]


def _line_ending(output: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in output else b"\n"


def _results_txt(output: bytes, exit_code: int) -> bytes:
    """The replay's raw output, a final ``exit code: <n>`` line, the output's line ending."""
    ending = _line_ending(output)
    if not output.endswith(b"\n"):
        output += ending
    return output + b"exit code: " + str(exit_code).encode("ascii") + ending


def _input_surprise(result: ReplayResult, case: Case) -> str | None:
    if result.timed_out:
        return "input replay timed out; it should fail"
    if result.exit_code in (0, None):
        return "input replay exited 0; it should fail"
    if result.failing_line != case.fails_at:
        actual = (
            f"line {result.failing_line}" if result.failing_line is not None else "no failing line"
        )
        return f"input replay failed at {actual}; case.toml says fails_at = {case.fails_at}"
    return None


def _capture(
    case: Case,
    reference: str,
    broken: str,
    *,
    python: Path,
    timeout_s: int,
    replay_fn: ReplayFn | None,
    out: Out,
) -> CaptureResult:
    """Probe, replay the reference then the input, and gather the evidence.

    Raises ``_Surprise``. A surprising reference stops the capture before the
    input is replayed; each replay happens at most once.
    """
    try:
        python_version, playwright_version = probe_versions(python)
    except RuntimeError as error:
        raise _Surprise(str(error)) from error
    out(f"capture venv: python {python_version}, playwright {playwright_version}")

    # Resolved at call time so tests can monkeypatch scriptfix.replay.replay.
    fn = replay_fn if replay_fn is not None else replay_module.replay
    pwrun = Path(tempfile.gettempdir()) / "pwrun"
    with tempfile.TemporaryDirectory() as scratch:
        reference_file = Path(scratch) / "reference.py"
        reference_file.write_bytes(reference.encode("utf-8"))
        input_file = Path(scratch) / "input.py"
        input_file.write_bytes(broken.encode("utf-8"))

        out("replaying the reference ...")
        reference_result = fn(reference_file, python=python, timeout_s=timeout_s)
        out(f"reference replay: {replay_summary(reference_result)}")
        if reference_result.timed_out or reference_result.exit_code != 0:
            raise _Surprise(f"reference replay failed: {replay_summary(reference_result)}")

        out(f"replaying the input in {pwrun} ...")
        input_result = fn(input_file, python=python, timeout_s=timeout_s, workdir=pwrun)
        out(f"input replay: {replay_summary(input_result)}")
        why = _input_surprise(input_result, case)
        if why:
            raise _Surprise(why)

    assert input_result.exit_code is not None  # _input_surprise ruled out a timeout
    output_file = pwrun / "output.txt"
    trace_file = pwrun / "script.pwtrace.zip"
    for needed in (output_file, trace_file):
        if not needed.is_file():
            raise _Surprise(f"input replay left no {needed.name} in {pwrun}")
    return CaptureResult(
        reference=reference_result,
        input=input_result,
        results_txt=_results_txt(output_file.read_bytes(), input_result.exit_code),
        trace=trace_file.read_bytes(),
        python_version=python_version,
        playwright_version=playwright_version,
    )


def _capture_toml(case: Case, result: CaptureResult) -> bytes:
    """``grading/capture.toml``: fixed key order, LF, UTF-8."""
    rows = [
        ("date", json.dumps(datetime.date.today().isoformat())),
        ("target", json.dumps(case.target)),
        ("users", "1"),
        ("iterations", "1"),
        ("python", json.dumps(result.python_version)),
        ("playwright", json.dumps(result.playwright_version)),
        ("reference_exit", str(result.reference.exit_code)),
        ("input_exit", str(result.input.exit_code)),
        ("input_failing_line", str(result.input.failing_line)),
    ]
    width = max(len(key) for key, _ in rows)
    lines = [CAPTURE_COMMENT] + [f"{key:<{width}} = {value}" for key, value in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _display(path: Path, repo_root: Path) -> str:
    """``path`` relative to the repo root with forward slashes when it is inside it."""
    try:
        return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def make_case(
    case_dir: Path,
    *,
    repo_root: Path,
    python: Path,
    timeout_s: int = 120,
    dry_run: bool = False,
    replay_fn: ReplayFn | None = None,
    out: Out = print,
) -> int:
    """Capture one case from its recipe; return 0, or 1 on a surprise (nothing written).

    Order: load the case and recipe, build the scripts; (not on a dry run)
    probe the capture venv, replay the reference (a surprise stops here, so
    the site never sees the input), replay the input; compute the evidence;
    only then write. ``dry_run`` prints the diff and the planned replays and
    does none of the rest. Raises ``ValueError`` for a bad case.toml or recipe.
    """
    case_dir = Path(case_dir)
    repo_root = Path(repo_root)
    case = load_case(case_dir)
    recipe = load_recipe(case_dir)
    reference, broken = build_scripts(recipe, repo_root)
    prompt_file = repo_root / SHARED_PROMPT
    if not prompt_file.is_file():
        raise ValueError(f"shared prompt not found: {prompt_file}")
    prompt = prompt_file.read_bytes()

    if dry_run:
        out(f"dry run: {case.slug} from {recipe.source}")
        for line in difflib.unified_diff(
            reference.splitlines(),
            broken.splitlines(),
            fromfile="grading/reference/script.py",
            tofile="inputs/script.py",
            lineterm="",
        ):
            out(line)
        pwrun = Path(tempfile.gettempdir()) / "pwrun"
        out("would replay the reference in a temp copy (it must exit 0)")
        out(f"would replay the input in {pwrun} (it must fail at line {case.fails_at})")
        out("dry run: nothing replayed, nothing written")
        return 0

    try:
        result = _capture(
            case,
            reference,
            broken,
            python=Path(python),
            timeout_s=timeout_s,
            replay_fn=replay_fn,
            out=out,
        )
    except _Surprise as surprise:
        out(f"surprise: {surprise}")
        out("nothing written")
        return 1

    files = [
        (case.reference_script, reference.encode("utf-8")),
        (case.input_script, broken.encode("utf-8")),
        (case.path / "prompt.md", prompt),
        (case.path / "inputs" / "results.txt", result.results_txt),
        (case.path / "inputs" / "script.pwtrace.zip", result.trace),
        (case.grading_dir / "capture.toml", _capture_toml(case, result)),
    ]
    for path, data in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        out(f"wrote {_display(path, repo_root)}")
    return 0
