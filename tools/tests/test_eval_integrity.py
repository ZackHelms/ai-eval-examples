"""The eval-integrity gate: structural checks over every folder in evals/.

Each check is a small function taking an eval directory (and the repo root
where it needs the shared prompt or the source script) and raising
AssertionError with a message that names the eval, the file and the problem.
The parametrized tests call them on every eval (ids = slugs); the failure
tests call the same functions on a broken copy of a generated case in tmp_path.

A *generated case* is an eval with grading/recipe.toml (built by
10-make-case.ps1). Checks 1-4 apply to every eval. Checks 5-10 apply to
generated cases only: they are parametrized over every eval but call
pytest.skip for the others. Eval 01 (the hand-made calibration case) has no
recipe, so it is not a generated case and checks 5-10 skip it. That is how
its known repo-path leak is exempt: its inputs/results.txt names the repo
path (.claude/standards/architecture.md, Learnings, "Evidence that points at
the answer key"). Any other check failing on Eval 01 is a real failure.

The checks:
 1. prompt.md, a non-empty inputs/ and grading/ exist; nothing under
    inputs/ is named "grading".
 2. Every inputs/... path in prompt.md exists; prompt.md has no $name
    placeholder (placeholders need a mapping, and none exists yet).
 3. No "grading/" or "grading\\" in prompt.md, any file under inputs/, or
    any text member of a .zip under inputs/.
 4. If grading/case.toml exists: load_case succeeds and fails_at is within
    inputs/script.py.
 5. prompt.md is byte-identical to rubrics/script-fix/prompt.md.
 6. The generated case's required files exist.
 7. build_scripts(load_recipe(eval)) equals the committed reference and input.
 8. No "ai-eval-examples" in prompt.md, inputs/ files or zip members.
 9. results.txt ends in a non-zero "exit code:" line and has a traceback
    frame at script.py line <fails_at>.
10. capture.toml has exactly the expected keys and values (1 user x 1
    iteration, reference exit 0, input exit non-zero, failing line ==
    fails_at).

Tests read files only: no browser, no site, no replays.
"""

from __future__ import annotations

import re
import shutil
import tomllib
import zipfile
from pathlib import Path

import pytest

from scriptfix.case import load_case
from scriptfix.makecase import build_scripts, load_recipe

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"
SHARED_PROMPT = REPO_ROOT / "rubrics" / "script-fix" / "prompt.md"
CASE_02 = EVALS_DIR / "02-docs-journey-a"

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
INPUT_PATH_RE = re.compile(r"inputs/[A-Za-z0-9_./-]*[A-Za-z0-9_]")
PLACEHOLDER_RE = re.compile(r"\$[A-Za-z_]\w*")
GRADING_RE = re.compile(r"grading[/\\]", re.IGNORECASE)
REPO_NAME_RE = re.compile(r"ai-eval-examples", re.IGNORECASE)
EXIT_LINE_RE = re.compile(r"exit code: [1-9]\d*")

CAPTURE_KEYS = (
    "date",
    "target",
    "users",
    "iterations",
    "python",
    "playwright",
    "reference_exit",
    "input_exit",
    "input_failing_line",
)
GENERATED_REQUIRED = (
    "grading/reference/script.py",
    "grading/corpus/corpus.toml",
    "grading/capture.toml",
    "inputs/script.py",
    "inputs/results.txt",
    "inputs/script.pwtrace.zip",
)


# --- helpers ---------------------------------------------------------------


def _eval_dirs() -> list:
    return [pytest.param(path, id=path.name) for path in sorted(EVALS_DIR.iterdir()) if path.is_dir()]


def is_generated(eval_dir: Path) -> bool:
    return (eval_dir / "grading" / "recipe.toml").is_file()


def _require_generated(eval_dir: Path) -> None:
    if not is_generated(eval_dir):
        pytest.skip(f"{eval_dir.name} has no grading/recipe.toml, so it is not a generated case (module docstring)")


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="ignore")


def _texts(eval_dir: Path):
    """Yield (label, text) for prompt.md, every non-zip file under inputs/, and,
    for every .zip under inputs/, each member's name and each non-image member's text."""
    prompt = eval_dir / "prompt.md"
    if prompt.is_file():
        yield "prompt.md", _decode(prompt.read_bytes())
    inputs = eval_dir / "inputs"
    if not inputs.is_dir():
        return
    for path in sorted(p for p in inputs.rglob("*") if p.is_file()):
        rel = path.relative_to(eval_dir).as_posix()
        if path.suffix.lower() != ".zip":
            yield rel, _decode(path.read_bytes())
            continue
        # A zip is scanned member by member (names, then text members), not as raw bytes.
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                yield f"{rel} (member name)", member.filename
                if member.is_dir() or member.filename.lower().endswith(IMAGE_SUFFIXES):
                    continue
                yield f"{rel}:{member.filename}", _decode(archive.read(member))


def _scan(eval_dir: Path, pattern: re.Pattern[str], what: str, check: str) -> None:
    for label, text in _texts(eval_dir):
        match = pattern.search(text)
        if match:
            raise AssertionError(
                f"{check}: {eval_dir.name}: {label} contains {what} ({match.group(0)!r})"
            )


def _read_text(eval_dir: Path, rel: str, check: str) -> str:
    path = eval_dir / rel
    if not path.is_file():
        raise AssertionError(f"{check}: {eval_dir.name}: {rel} is missing")
    return path.read_bytes().decode("utf-8")


def _capture(eval_dir: Path, check: str) -> dict:
    path = eval_dir / "grading" / "capture.toml"
    if not path.is_file():
        raise AssertionError(f"{check}: {eval_dir.name}: grading/capture.toml is missing")
    return tomllib.loads(path.read_text(encoding="utf-8"))


# --- the ten checks --------------------------------------------------------


def check_1_required_layout(eval_dir: Path) -> None:
    name = eval_dir.name
    if not (eval_dir / "prompt.md").is_file():
        raise AssertionError(f"check 1: {name}: prompt.md is missing")
    inputs = eval_dir / "inputs"
    if not inputs.is_dir() or not any(inputs.iterdir()):
        raise AssertionError(f"check 1: {name}: inputs/ is missing or empty")
    if not (eval_dir / "grading").is_dir():
        raise AssertionError(f"check 1: {name}: grading/ is missing")
    for path in inputs.rglob("*"):
        if path.name.lower() == "grading":
            raise AssertionError(
                f"check 1: {name}: {path.relative_to(eval_dir).as_posix()} is named 'grading' under inputs/"
            )


def check_2_prompt_paths(eval_dir: Path) -> None:
    name = eval_dir.name
    prompt = _read_text(eval_dir, "prompt.md", "check 2")
    for match in INPUT_PATH_RE.finditer(prompt):
        if not (eval_dir / match.group(0)).exists():
            raise AssertionError(f"check 2: {name}: prompt.md names {match.group(0)}, which does not exist")
    placeholder = PLACEHOLDER_RE.search(prompt)
    if placeholder:
        raise AssertionError(
            f"check 2: {name}: prompt.md has the placeholder {placeholder.group(0)}; "
            "placeholders need a mapping to inputs/ paths and none exists yet"
        )


def check_3_no_grading_paths(eval_dir: Path) -> None:
    _scan(eval_dir, GRADING_RE, "a grading/ path", "check 3")


def check_4_case_toml(eval_dir: Path) -> None:
    name = eval_dir.name
    if not (eval_dir / "grading" / "case.toml").is_file():
        return
    try:
        case = load_case(eval_dir)
    except ValueError as error:
        raise AssertionError(f"check 4: {name}: grading/case.toml does not load: {error}") from error
    script = eval_dir / "inputs" / "script.py"
    if not script.is_file():
        raise AssertionError(f"check 4: {name}: inputs/script.py is missing")
    line_count = len(script.read_text(encoding="utf-8").splitlines())
    if case.fails_at > line_count:
        raise AssertionError(
            f"check 4: {name}: grading/case.toml fails_at {case.fails_at} is past the end of "
            f"inputs/script.py ({line_count} lines)"
        )


def check_5_shared_prompt(eval_dir: Path, repo_root: Path) -> None:
    prompt = eval_dir / "prompt.md"
    shared = repo_root / "rubrics" / "script-fix" / "prompt.md"
    if not prompt.is_file() or prompt.read_bytes() != shared.read_bytes():
        raise AssertionError(
            f"check 5: {eval_dir.name}: prompt.md is not a byte copy of rubrics/script-fix/prompt.md"
        )


def check_6_required_files(eval_dir: Path) -> None:
    for rel in GENERATED_REQUIRED:
        if not (eval_dir / rel).is_file():
            raise AssertionError(f"check 6: {eval_dir.name}: {rel} is missing")


def check_7_rebuild_matches(eval_dir: Path, repo_root: Path) -> None:
    name = eval_dir.name
    try:
        reference, broken = build_scripts(load_recipe(eval_dir), repo_root)
    except ValueError as error:
        raise AssertionError(f"check 7: {name}: grading/recipe.toml does not build: {error}") from error
    for rel, built in (("grading/reference/script.py", reference), ("inputs/script.py", broken)):
        committed = _read_text(eval_dir, rel, "check 7")
        if committed != built:
            raise AssertionError(
                f"check 7: {name}: {rel} differs from what grading/recipe.toml builds; "
                "regenerate with 10-make-case.ps1"
            )


def check_8_no_repo_name(eval_dir: Path) -> None:
    _scan(eval_dir, REPO_NAME_RE, "the repo's name", "check 8")


def check_9_results_evidence(eval_dir: Path) -> None:
    name = eval_dir.name
    text = _read_text(eval_dir, "inputs/results.txt", "check 9")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not EXIT_LINE_RE.fullmatch(lines[-1].strip()):
        last = lines[-1] if lines else "(empty)"
        raise AssertionError(
            f"check 9: {name}: inputs/results.txt must end with a non-zero 'exit code: <n>' line, got {last!r}"
        )
    fails_at = load_case(eval_dir).fails_at
    frame = f'script.py", line {fails_at},'
    if frame not in text:
        raise AssertionError(
            f"check 9: {name}: inputs/results.txt has no traceback frame {frame!r} (case.toml fails_at)"
        )


def check_10_capture_toml(eval_dir: Path) -> None:
    name = eval_dir.name
    data = _capture(eval_dir, "check 10")
    keys = tuple(data)
    if sorted(keys) != sorted(CAPTURE_KEYS):
        missing = [k for k in CAPTURE_KEYS if k not in data]
        extra = [k for k in keys if k not in CAPTURE_KEYS]
        raise AssertionError(
            f"check 10: {name}: grading/capture.toml keys differ (missing {missing}, unexpected {extra})"
        )

    def int_value(key: str) -> int:
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise AssertionError(f"check 10: {name}: grading/capture.toml {key} must be an integer, got {value!r}")
        return value

    for key in ("date", "target", "python", "playwright"):
        if not isinstance(data[key], str) or not data[key]:
            raise AssertionError(
                f"check 10: {name}: grading/capture.toml {key} must be a non-empty string, got {data[key]!r}"
            )
    for key, wanted in (("users", 1), ("iterations", 1), ("reference_exit", 0)):
        if int_value(key) != wanted:
            raise AssertionError(
                f"check 10: {name}: grading/capture.toml {key} must be {wanted}, got {data[key]!r}"
            )
    if int_value("input_exit") == 0:
        raise AssertionError(f"check 10: {name}: grading/capture.toml input_exit must be non-zero")
    fails_at = load_case(eval_dir).fails_at
    if int_value("input_failing_line") != fails_at:
        raise AssertionError(
            f"check 10: {name}: grading/capture.toml input_failing_line {data['input_failing_line']} "
            f"!= case.toml fails_at {fails_at}"
        )


# --- the gate: every eval --------------------------------------------------


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_1_required_layout(eval_dir):
    check_1_required_layout(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_2_prompt_paths(eval_dir):
    check_2_prompt_paths(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_3_no_grading_paths(eval_dir):
    check_3_no_grading_paths(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_4_case_toml(eval_dir):
    check_4_case_toml(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_5_shared_prompt(eval_dir):
    _require_generated(eval_dir)
    check_5_shared_prompt(eval_dir, REPO_ROOT)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_6_required_files(eval_dir):
    _require_generated(eval_dir)
    check_6_required_files(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_7_rebuild_matches(eval_dir):
    _require_generated(eval_dir)
    check_7_rebuild_matches(eval_dir, REPO_ROOT)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_8_no_repo_name(eval_dir):
    _require_generated(eval_dir)
    check_8_no_repo_name(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_9_results_evidence(eval_dir):
    _require_generated(eval_dir)
    check_9_results_evidence(eval_dir)


@pytest.mark.parametrize("eval_dir", _eval_dirs())
def test_10_capture_toml(eval_dir):
    _require_generated(eval_dir)
    check_10_capture_toml(eval_dir)


# --- failure tests: each check fails on a broken copy of case 02 -----------


@pytest.fixture
def broken(tmp_path) -> Path:
    """A copy of case 02 in tmp_path (the folder name is kept: load_case needs the NN- prefix)."""
    copy = tmp_path / CASE_02.name
    shutil.copytree(CASE_02, copy)
    return copy


def _append(path: Path, text: str) -> None:
    path.write_bytes(path.read_bytes() + text.encode("utf-8"))


def _replace_in_toml(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def test_broken_copy_passes_every_check(broken):
    check_1_required_layout(broken)
    check_2_prompt_paths(broken)
    check_3_no_grading_paths(broken)
    check_4_case_toml(broken)
    check_5_shared_prompt(broken, REPO_ROOT)
    check_6_required_files(broken)
    check_7_rebuild_matches(broken, REPO_ROOT)
    check_8_no_repo_name(broken)
    check_9_results_evidence(broken)
    check_10_capture_toml(broken)


def test_1_fails_without_prompt(broken):
    (broken / "prompt.md").unlink()
    with pytest.raises(AssertionError, match="prompt.md is missing"):
        check_1_required_layout(broken)


def test_2_fails_on_missing_path_and_on_placeholder(broken):
    prompt = broken / "prompt.md"
    original = prompt.read_bytes()
    _append(prompt, " See also inputs/missing.txt.")
    with pytest.raises(AssertionError, match=r"inputs/missing\.txt.*does not exist"):
        check_2_prompt_paths(broken)
    prompt.write_bytes(original)
    _append(prompt, " Fix $script.")
    with pytest.raises(AssertionError, match=r"placeholder \$script.*mapping"):
        check_2_prompt_paths(broken)


def test_3_fails_on_grading_path_in_file_and_in_zip_member(broken):
    results = broken / "inputs" / "results.txt"
    original = results.read_bytes()
    _append(results, "see Grading/reference\n")
    with pytest.raises(AssertionError, match=r"inputs/results\.txt.*grading/ path"):
        check_3_no_grading_paths(broken)
    results.write_bytes(original)

    trace = broken / "inputs" / "script.pwtrace.zip"
    with zipfile.ZipFile(trace, "a") as archive:
        archive.writestr("extra.txt", "x = 'grading\\reference'")
    with pytest.raises(AssertionError, match=r"script\.pwtrace\.zip:extra\.txt.*grading/ path"):
        check_3_no_grading_paths(broken)


def test_4_fails_when_fails_at_is_past_the_script(broken):
    _replace_in_toml(broken / "grading" / "case.toml", "fails_at = 18", "fails_at = 999")
    with pytest.raises(AssertionError, match="fails_at 999 is past the end"):
        check_4_case_toml(broken)


def test_5_fails_when_prompt_differs_by_a_byte(broken):
    prompt = broken / "prompt.md"
    data = bytearray(prompt.read_bytes())
    data[0] = ord("d") if data[0] != ord("d") else ord("e")
    prompt.write_bytes(bytes(data))
    with pytest.raises(AssertionError, match="not a byte copy"):
        check_5_shared_prompt(broken, REPO_ROOT)


def test_6_fails_without_capture_toml(broken):
    (broken / "grading" / "capture.toml").unlink()
    with pytest.raises(AssertionError, match=r"grading/capture\.toml is missing"):
        check_6_required_files(broken)


def test_7_fails_when_committed_input_differs_from_the_build(broken):
    script = broken / "inputs" / "script.py"
    lines = script.read_bytes().decode("utf-8").split("\n")
    lines[2] = lines[2] + " "
    script.write_bytes("\n".join(lines).encode("utf-8"))
    with pytest.raises(AssertionError, match=r"inputs/script\.py differs"):
        check_7_rebuild_matches(broken, REPO_ROOT)


def test_8_fails_on_repo_name_in_inputs(broken):
    _append(broken / "inputs" / "results.txt", "D:\\gitrepos\\AI-Eval-Examples\\x.py\n")
    with pytest.raises(AssertionError, match=r"inputs/results\.txt.*repo's name"):
        check_8_no_repo_name(broken)


def test_9_fails_when_exit_code_is_zero(broken):
    results = broken / "inputs" / "results.txt"
    text = results.read_bytes().decode("utf-8")
    assert text.rstrip().endswith("exit code: 1")
    results.write_bytes((text.rstrip()[: -len("exit code: 1")] + "exit code: 0\n").encode("utf-8"))
    with pytest.raises(AssertionError, match="non-zero 'exit code"):
        check_9_results_evidence(broken)


def test_9_fails_without_the_failing_frame(broken):
    _replace_in_toml(broken / "grading" / "case.toml", "fails_at = 18", "fails_at = 19")
    with pytest.raises(AssertionError, match=r"no traceback frame"):
        check_9_results_evidence(broken)


def test_10_fails_with_two_users(broken):
    _replace_in_toml(broken / "grading" / "capture.toml", "users              = 1", "users              = 2")
    with pytest.raises(AssertionError, match="users must be 1"):
        check_10_capture_toml(broken)
