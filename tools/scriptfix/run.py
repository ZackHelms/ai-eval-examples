"""The trial runner: launch a script-fix case's one-shot headless trials, one at a time.

Each trial runs in a fresh ``<trials_root>/<NN>-run<N>/`` holding only
``prompt.md`` and ``inputs/``; its stream log and a subject sidecar land beside
that folder, where ``scriptfix.grade`` already looks. The module encodes the
launcher gotchas of ``.claude/skills/trial-runs.md``: absolute allow rules, the
parent session's variables stripped from the child's environment, and the real
``pwsh.exe`` first on ``PATH``.

This part is pure: run numbering and the never-overwrite check, preparing a
trial folder, the child's environment, the allow rules, the ``claude``
argument list and the sidecar file. Nothing here starts a process.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path, PurePath

from scriptfix.record import read_trials

TOOLS = ("edit-only",)
CONTEXTS = ("none",)
EFFORTS = ("default", "low", "medium", "high", "xhigh", "max")
DEFAULT_TRIAL_TIMEOUT_S = 1800
SELF_TEST_MODEL = "claude-haiku-5-5"

# Runs 3-12 of Eval 01 used "default"; the live self-test decides whether the
# installed Claude Code needs "manual" instead (its help lists that name).
PERMISSION_MODE = "default"

# Variables of the parent session that must not reach a trial. Keys are
# compared case-insensitively. The last three name the repo or its venv: the
# evidence must not, and neither may the environment.
STRIP_PREFIXES = ("CLAUDE", "ZMH3D_")
STRIP_NAMES = (
    "AI_AGENT",
    "NO_COLOR",
    "PYTHONIOENCODING",
    "GIT_ASKPASS",
    "GIT_EDITOR",
    "GIT_TERMINAL_PROMPT",
    "GCM_INTERACTIVE",
    "COREPACK_ENABLE_AUTO_PIN",
    "PSExecutionPolicyPreference",
    "NoDefaultCurrentDirectoryInExePath",
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "PYTHONSTARTUP",
)

# What a run leaves beside its folder, as suffixes of "<NN>-run<N>".
STREAM_SUFFIX = ".stream.jsonl"
SIDECAR_SUFFIX = ".subject.json"
STDERR_SUFFIX = ".stderr.txt"
_SIDE_SUFFIXES = (STREAM_SUFFIX, SIDECAR_SUFFIX, STDERR_SUFFIX)


# --------------------------------------------------------------------------
# Run numbers
# --------------------------------------------------------------------------


def _highest_run(case_number: str, trials_root: Path, trials_jsonl: Path) -> int:
    """The highest run number of the case found on disk or in trials.jsonl (0 if none)."""
    pattern = re.compile(rf"{re.escape(case_number)}-run(\d+)")
    highest = 0
    root = Path(trials_root)
    if root.is_dir():
        for entry in root.iterdir():
            name = entry.name
            if entry.is_dir():
                match = pattern.fullmatch(name)
            else:
                match = next(
                    (
                        found
                        for suffix in _SIDE_SUFFIXES
                        if name.endswith(suffix)
                        and (found := pattern.fullmatch(name[: -len(suffix)]))
                    ),
                    None,
                )
            if match:
                highest = max(highest, int(match.group(1)))
    for record in read_trials(trials_jsonl):
        run = record["run"]
        if isinstance(run, int) and not isinstance(run, bool):
            highest = max(highest, run)
    return highest


def next_runs(case_number: str, count: int, trials_root: Path, trials_jsonl: Path) -> list[int]:
    """The next ``count`` run numbers of case ``case_number``, after the highest existing one.

    "Existing" means a folder ``<NN>-run<N>``, its stream log, sidecar or
    stderr file in ``trials_root``, or a ``run`` in ``trials_jsonl``; a missing
    root or file counts as none. Raises ValueError when ``count`` is below 1.
    """
    if count < 1:
        raise ValueError(f"--count must be at least 1, got {count}")
    start = _highest_run(case_number, trials_root, trials_jsonl) + 1
    return list(range(start, start + count))


def check_free(case_number: str, runs: list[int], trials_root: Path) -> None:
    """Raise ValueError naming the first path a run would overwrite; trials are never overwritten."""
    root = Path(trials_root)
    for run in runs:
        name = f"{case_number}-run{run}"
        for path in (root / name, *(root / f"{name}{suffix}" for suffix in _SIDE_SUFFIXES)):
            if path.exists():
                raise ValueError(f"run {run} of case {case_number} already exists: {path}")


# --------------------------------------------------------------------------
# The trial folder
# --------------------------------------------------------------------------


def prepare_trial(case_dir: Path, folder: Path) -> Path:
    """Copy exactly ``prompt.md`` and ``inputs/`` of the case into the new ``folder``.

    The bytes are copied as they are. Nothing else of the case is copied,
    never ``grading/``. Raises ValueError when ``folder`` already exists or
    the case lacks either piece. Returns ``folder/inputs/script.py``.
    """
    case_dir, folder = Path(case_dir), Path(folder)
    if folder.exists():
        raise ValueError(f"trial folder already exists: {folder}")
    prompt, inputs = case_dir / "prompt.md", case_dir / "inputs"
    if not prompt.is_file():
        raise ValueError(f"the case has no prompt.md: {prompt}")
    if not inputs.is_dir():
        raise ValueError(f"the case has no inputs/ folder: {inputs}")
    folder.mkdir(parents=True)
    shutil.copy2(prompt, folder / "prompt.md")
    shutil.copytree(inputs, folder / "inputs")
    return folder / "inputs" / "script.py"


# --------------------------------------------------------------------------
# The child's environment
# --------------------------------------------------------------------------


def _is_stripped(key: str) -> bool:
    upper = key.upper()
    return upper.startswith(STRIP_PREFIXES) or upper in {name.upper() for name in STRIP_NAMES}


def stripped_names(environ: Mapping[str, str]) -> list[str]:
    """The keys of ``environ`` that ``trial_env`` removes, sorted."""
    return sorted(key for key in environ if _is_stripped(key))


def _norm(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_inside(entry: str, directory: str) -> bool:
    """Whether the normalized ``entry`` is ``directory`` or below it."""
    return entry == directory or entry.startswith(directory.rstrip(os.sep) + os.sep)


def trial_env(environ: Mapping[str, str], *, pwsh_dir: Path, repo_root: Path) -> dict[str, str]:
    """The environment a trial's ``claude`` runs in, built from a copy of ``environ``.

    Removes the parent session's variables (``STRIP_PREFIXES``,
    ``STRIP_NAMES``). Rebuilds ``PATH``, keeping its key's spelling: drops
    empty entries, entries inside ``repo_root`` (the repo's venv included) and
    inside the removed ``VIRTUAL_ENV``'s ``Scripts``/``bin``, then puts
    ``pwsh_dir`` first. Stripping variables does not fix a WindowsApps
    ``pwsh`` alias ("The command line is too long"); only the ``PATH`` change
    does.
    """
    env = dict(environ)
    venv = next((value for key, value in env.items() if key.upper() == "VIRTUAL_ENV"), "")
    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
    old_path = next((value for key, value in env.items() if key.upper() == "PATH"), "")

    for key in [key for key in env if _is_stripped(key) or key.upper() == "PATH"]:
        del env[key]

    avoid = [_norm(repo_root)]
    if venv:
        avoid += [_norm(Path(venv) / "Scripts"), _norm(Path(venv) / "bin")]
    kept = [
        entry
        for entry in old_path.split(os.pathsep)
        if entry and not any(_is_inside(_norm(entry), directory) for directory in avoid)
    ]
    env[path_key] = os.pathsep.join([os.fspath(pwsh_dir), *kept])
    return env


# --------------------------------------------------------------------------
# The claude command
# --------------------------------------------------------------------------


def allow_rule(tool: str, path: Path) -> str:
    """A permission rule for ``tool`` on the absolute ``path``: ``Edit(//c/Users/a/x.py)``.

    The path has forward slashes and, on Windows, a lowercase drive letter
    with no colon. It is absolute so that a later ``cd`` can't stop it
    matching. Raises ValueError for a relative (or UNC) path.
    """
    text = path.as_posix() if isinstance(path, PurePath) else str(path).replace("\\", "/")
    drive = re.fullmatch(r"([A-Za-z]):/(.*)", text)
    if drive:
        rule_path = f"{drive.group(1).lower()}/{drive.group(2)}"
    elif text.startswith("/") and not text.startswith("//"):
        rule_path = text[1:]
    else:
        raise ValueError(f"an allow rule needs an absolute path, got {os.fspath(path)!r}")
    return f"{tool}(//{rule_path})"


def claude_argv(
    claude_cmd: list[str],
    *,
    prompt: str,
    model: str,
    effort: str,
    allowed_file: Path,
) -> list[str]:
    """The ``claude`` argument list for one headless trial that may edit only ``allowed_file``.

    The prompt is the positional right after ``-p``: ``--allowedTools`` is
    variadic and would swallow anything after it. ``--effort`` is omitted for
    ``default``. Raises ValueError for an effort not in ``EFFORTS``.
    """
    if effort not in EFFORTS:
        raise ValueError(f"unknown effort {effort!r}; choose one of {', '.join(EFFORTS)}")
    argv = [
        *claude_cmd,
        "-p",
        prompt,
        "--safe-mode",
        "--strict-mcp-config",
        "--model",
        model,
    ]
    if effort != "default":
        argv += ["--effort", effort]
    argv += [
        "--permission-mode",
        PERMISSION_MODE,
        "--allowedTools",
        allow_rule("Edit", allowed_file),
        allow_rule("Write", allowed_file),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    return argv


# --------------------------------------------------------------------------
# The sidecar
# --------------------------------------------------------------------------


def write_sidecar(path: Path, record: dict[str, object]) -> None:
    """Write the subject sidecar as indented JSON, UTF-8 with LF line endings."""
    text = json.dumps(record, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")
