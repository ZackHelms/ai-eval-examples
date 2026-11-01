"""The trial runner: launch a script-fix case's one-shot headless trials, one at a time.

Each trial runs in a fresh ``<trials_root>/<NN>-run<N>/`` holding only
``prompt.md`` and ``inputs/``; its stream log and a subject sidecar land beside
that folder, where ``scriptfix.grade`` already looks. The module encodes the
launcher gotchas of ``.claude/skills/trial-runs.md``: absolute allow rules, the
parent session's variables stripped from the child's environment, and the real
``pwsh.exe`` first on ``PATH``.

The first half is pure: run numbering and the never-overwrite check, preparing
a trial folder, the child's environment, the allow rules, the ``claude``
argument list and the sidecar file. The second half starts the processes:
``launch_trial`` (one ``claude``, output to files, killed on timeout),
``run_trials`` (a batch, strictly one at a time, stopping at the first harness
problem) and ``self_test`` (the cheap harness check that runs before trials
are paid for).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePath

from scriptfix import __version__
from scriptfix.case import load_case
from scriptfix.grade import Out
from scriptfix.record import read_trials
from scriptfix.replay import _DRAIN_TIMEOUT_S, _kill_tree
from scriptfix.report import REPO_ROOT
from scriptfix.transcript import Transcript, _load_lines, read_transcript

TOOLS = ("edit-only",)

# The built-in tools a trial may use, passed to the CLI as `--tools` (CD
# decision, 2026-11-01: "Allowlist, no web"). It's the seven tools Eval 01's
# runs actually used; nothing that can reach the network. The sidecar's
# `tools` label stays "edit-only"; this list is recorded beside it.
TRIAL_TOOLS = ("Read", "Glob", "Grep", "Edit", "Write", "Bash", "PowerShell")
CONTEXTS = ("none",)
EFFORTS = ("default", "low", "medium", "high", "xhigh", "max")
DEFAULT_TRIAL_TIMEOUT_S = 1800
DEFAULT_SELF_TEST_TIMEOUT_S = 600
DEFAULT_TRIALS_ROOT = Path("~/eval-trials")
SELF_TEST_MODEL = "claude-haiku-5-5"

# Launcher gotcha 4 of trial-runs.md, automated: one PowerShell command, `cd
# inputs` + one Bash command, one Edit of a dummy file.
SELF_TEST_PROMPT = (
    "This is a harness check. Do exactly these three things and nothing else. "
    "1. With the PowerShell tool, run: Get-Location "
    "2. With the Bash tool, run: cd inputs && ls "
    "3. With the Edit tool, change the word before to after in inputs/dummy.txt. "
    "Then reply with the three results."
)

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

    The prompt is the positional right after ``-p``: ``--allowedTools`` and
    ``--tools`` are variadic and would swallow anything after them, so each is
    followed by a flag. ``--tools`` carries ``TRIAL_TOOLS`` as one
    comma-separated value. ``--effort`` is omitted for ``default``. Raises
    ValueError for an effort not in ``EFFORTS``.
    """
    if effort not in EFFORTS:
        raise ValueError(f"unknown effort {effort!r}; choose one of {', '.join(EFFORTS)}")
    argv = [
        *claude_cmd,
        "-p",
        prompt,
        "--safe-mode",
        "--strict-mcp-config",
        "--tools",
        ",".join(TRIAL_TOOLS),
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


# --------------------------------------------------------------------------
# Finding pwsh and claude
# --------------------------------------------------------------------------

# The per-user app-execution alias folder (%LOCALAPPDATA%\Microsoft\WindowsApps).
# The real pwsh of a store install lives under "Program Files\WindowsApps\
# Microsoft.PowerShell_..." and is fine: only this alias breaks the PowerShell
# tool ("The command line is too long", Eval 01's runs 7-9).
_ALIAS_MARKER = "\\microsoft\\windowsapps\\"
_PWSH_HINT = "pass --pwsh with the real pwsh.exe, e.g. (Get-Process -Id $PID).Path"


def is_windowsapps_alias(path: str | os.PathLike[str]) -> bool:
    """Whether ``path`` is under the per-user ``Microsoft\\WindowsApps`` alias folder.

    Compared case-insensitively with either slash direction, so the answer
    doesn't depend on the host.
    """
    return _ALIAS_MARKER in os.fspath(path).replace("/", "\\").lower()


def resolve_pwsh(given: Path | None) -> Path:
    """The real ``pwsh.exe`` to put first on the trial's ``PATH``; ValueError when unusable.

    ``given`` (``--pwsh``) or else ``shutil.which("pwsh")``. The app-execution
    alias is rejected for either, and the result must be an existing file.
    """
    if given is None:
        found = shutil.which("pwsh")
        if found is None:
            raise ValueError(f"pwsh was not found on PATH; {_PWSH_HINT}")
        candidate, source = Path(found), "pwsh on PATH"
    else:
        candidate, source = Path(given), "--pwsh"
    if is_windowsapps_alias(candidate):
        raise ValueError(
            f"{source} is the per-user app-execution alias {candidate}, which breaks the "
            f'PowerShell tool ("The command line is too long"); {_PWSH_HINT}'
        )
    if not candidate.is_file():
        raise ValueError(f"{source} is not a file: {candidate}")
    return candidate


def resolve_claude(given: Path | None) -> Path:
    """The ``claude`` executable: ``given`` (``--claude``) or else ``shutil.which("claude")``."""
    if given is None:
        found = shutil.which("claude")
        if found is None:
            raise ValueError("claude was not found on PATH; pass --claude with its path")
        candidate, source = Path(found), "claude on PATH"
    else:
        candidate, source = Path(given), "--claude"
    if not candidate.is_file():
        raise ValueError(f"{source} is not a file: {candidate}")
    return candidate


# --------------------------------------------------------------------------
# Launching
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialRun:
    """One launched trial: where it ran, what it left and how it ended.

    ``exit_code`` is None when the trial timed out.
    """

    run: int
    folder: Path
    log: Path
    sidecar: Path
    exit_code: int | None
    timed_out: bool
    seconds: float


def _now() -> datetime:
    return datetime.now()


def _absolute(path: Path) -> Path:
    """``path`` with ``~`` expanded and made absolute (allow rules need an absolute path)."""
    return Path(os.path.abspath(Path(path).expanduser()))


def launch_trial(
    argv: list[str],
    *,
    folder: Path,
    log: Path,
    stderr: Path,
    env: dict[str, str],
    timeout_s: int,
) -> tuple[int | None, bool, float]:
    """Run ``argv`` once in ``folder`` and return ``(exit_code, timed_out, seconds)``.

    stdout goes to ``log`` and stderr to ``stderr``, both files opened in
    binary mode and never decoded: a pipe could be held open by a leftover
    descendant. On timeout the whole process tree is killed and ``exit_code``
    is None. ``env`` is used as it is, so callers pass ``trial_env(...)``.
    """
    started = time.monotonic()
    timed_out = False
    with Path(log).open("wb") as log_file, Path(stderr).open("wb") as stderr_file:
        process = subprocess.Popen(
            argv,
            cwd=folder,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=stderr_file,
            env=env,
            start_new_session=sys.platform != "win32",  # own group, so killpg works
        )
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                _kill_tree(process)
            finally:
                process.wait(timeout=_DRAIN_TIMEOUT_S)
    seconds = time.monotonic() - started
    return (None if timed_out else process.returncode, timed_out, seconds)


def _read_log(log: Path) -> Transcript | None:
    """The parsed stream log, or None when it can't be read."""
    try:
        return read_transcript(log)
    except (OSError, ValueError):
        return None


def _pwsh_arg(text: str) -> str:
    """``text`` as one pwsh argument: single-quoted only when it contains whitespace."""
    if any(ch.isspace() for ch in text):
        return "'" + text.replace("'", "''") + "'"
    return text


def _run_spec(runs: list[int]) -> str:
    """``13`` for one run, ``13-15`` for a contiguous range, else ``3,7,9``."""
    ordered = sorted(runs)
    if len(ordered) == 1:
        return str(ordered[0])
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]}-{ordered[-1]}"
    return ",".join(str(run) for run in ordered)


def _case_arg(case_dir: Path) -> str:
    """The case dir relative to the repo with backslashes when inside it, else absolute."""
    absolute = Path(os.path.abspath(case_dir))
    for candidate in (absolute, absolute.resolve()):
        try:
            return candidate.relative_to(REPO_ROOT).as_posix().replace("/", "\\")
        except ValueError:
            continue
    return os.fspath(absolute)


def next_command(case_dir: Path, runs: list[int], trials_root: Path) -> str:
    """The ``30-grade-trials.ps1`` command that grades ``runs`` of the case."""
    command = f".\\30-grade-trials.ps1 -Case {_pwsh_arg(_case_arg(case_dir))} -Runs {_run_spec(runs)}"
    root = os.path.normcase(os.fspath(_absolute(trials_root)))
    if root != os.path.normcase(os.fspath(_absolute(DEFAULT_TRIALS_ROOT))):
        command += f" -TrialsRoot {_pwsh_arg(os.fspath(_absolute(trials_root)))}"
    return command


def run_trials(
    case_dir: Path,
    *,
    model: str,
    effort: str,
    runs: list[int] | None,
    count: int | None,
    trials_root: Path,
    claude_cmd: list[str],
    pwsh: Path,
    timeout_s: int,
    dry_run: bool,
    out: Out = print,
    context: str = "none",
    tools: str = "edit-only",
) -> int:
    """Run the trials of one case, strictly one at a time; returns the exit code.

    Give exactly one of ``runs`` (these numbers) and ``count`` (that many
    after the highest existing run). Every ValueError (a bad argument, a
    run that already exists, a case without a prompt) is raised before
    anything is created or launched. Each trial runs in a fresh
    ``<trials_root>/<NN>-run<N>/`` with a stream log, a stderr file and a
    subject sidecar beside it, all through ``trial_env``. The first harness
    problem (a non-zero exit, a timeout, no ``result`` line) stops the batch:
    returns 1. Returns 0 when every trial was fine, and for a dry run, which
    only prints the plan.
    """
    if (runs is None) == (count is None):
        raise ValueError("give exactly one of runs and count")
    if effort not in EFFORTS:
        raise ValueError(f"unknown effort {effort!r}; choose one of {', '.join(EFFORTS)}")
    if context not in CONTEXTS:
        raise ValueError(f"unsupported context {context!r}; choose one of {', '.join(CONTEXTS)}")
    if tools not in TOOLS:
        raise ValueError(f"unsupported tools profile {tools!r}; choose one of {', '.join(TOOLS)}")
    if timeout_s < 1:
        raise ValueError(f"the timeout must be at least 1 second, got {timeout_s}")

    case = load_case(Path(case_dir))
    prompt_file = case.path / "prompt.md"
    if not prompt_file.is_file():
        raise ValueError(f"the case has no prompt.md: {prompt_file}")
    if not (case.path / "inputs").is_dir():
        raise ValueError(f"the case has no inputs/ folder: {case.path / 'inputs'}")
    prompt = prompt_file.read_text(encoding="utf-8").strip()

    root = _absolute(trials_root)
    if count is not None:
        numbers = next_runs(case.number, count, root, case.grading_dir / "trials.jsonl")
    else:
        numbers = list(runs or [])
        if not numbers or min(numbers) < 1 or len(set(numbers)) != len(numbers):
            raise ValueError(f"runs must be distinct numbers from 1 up, got {numbers}")
    check_free(case.number, numbers, root)

    def folder_of(run: int) -> Path:
        return root / f"{case.number}-run{run}"

    if dry_run:
        out(f"DRY_RUN=plan only: nothing is created or launched ({len(numbers)} trial(s) of {case.slug})")
        out(f"RUNS={_run_spec(numbers)}")
        shown = f"<prompt.md: {len(prompt)} chars>"
        for run in numbers:
            folder = folder_of(run)
            argv = claude_argv(
                claude_cmd,
                prompt=shown,
                model=model,
                effort=effort,
                allowed_file=folder / "inputs" / "script.py",
            )
            out(f"RUN={run} FOLDER={folder}")
            out(f"RUN={run} ARGV={subprocess.list2cmdline(argv)}")
        out(f"STRIP={','.join(stripped_names(os.environ)) or '(none)'}")
        return 0

    env = trial_env(os.environ, pwsh_dir=Path(pwsh).parent, repo_root=REPO_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    launched: list[TrialRun] = []
    problem: str | None = None
    for run in numbers:
        name = f"{case.number}-run{run}"
        folder = folder_of(run)
        script = prepare_trial(case.path, folder)
        argv = claude_argv(claude_cmd, prompt=prompt, model=model, effort=effort, allowed_file=script)
        log, sidecar, stderr = (root / f"{name}{suffix}" for suffix in (STREAM_SUFFIX, SIDECAR_SUFFIX, STDERR_SUFFIX))
        started = _now().isoformat(timespec="seconds")
        exit_code, timed_out, seconds = launch_trial(
            argv, folder=folder, log=log, stderr=stderr, env=env, timeout_s=timeout_s
        )
        launched.append(TrialRun(run, folder, log, sidecar, exit_code, timed_out, seconds))
        write_sidecar(
            sidecar,
            {
                "run": run,
                "case": case.slug,
                "model": model,
                "effort": effort,
                "context": context,
                "tools": tools,
                "tool_list": list(TRIAL_TOOLS),
                "runner": __version__,
                "started": started,
                "seconds": round(seconds, 1),
                "exit_code": exit_code,
                "timed_out": timed_out,
            },
        )
        transcript = _read_log(log)
        has_result = transcript is not None and transcript.has_result
        cost = transcript.cost_usd if transcript is not None else None
        is_error = transcript.result_is_error if transcript is not None else False
        denials = len(transcript.denials) if transcript is not None else 0
        out(
            f"RUN={run} EXIT={exit_code} TIMED_OUT={timed_out} COST_USD={cost} "
            f"IS_ERROR={is_error} DENIALS={denials} LOG={log}"
        )
        if timed_out:
            problem = f"run {run} timed out after {timeout_s} s"
        elif exit_code != 0:
            problem = f"run {run} exited with code {exit_code}; see {stderr}"
        elif not has_result:
            problem = f"run {run} left no result line in {log}"
        if problem is not None:
            out(f"HARNESS={problem}")
            break

    if launched:
        out(f"NEXT={next_command(case.path, [trial.run for trial in launched], root)}")
    return 0 if problem is None else 1


# --------------------------------------------------------------------------
# The self-test
# --------------------------------------------------------------------------


def _snippet(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _tool_problem(transcript: Transcript, results: dict[str, tuple[bool, str]], tool: str) -> str | None:
    """Why no ``tool`` call has a non-error result, or None when one does."""
    calls = [call for call in transcript.calls if call.name == tool]
    if not calls:
        return f"no {tool} tool call"
    answered = [results[call.id] for call in calls if call.id in results]
    if not answered:
        return f"the {tool} call has no result"
    if all(is_error for is_error, _text in answered):
        return f"the {tool} result is an error: {_snippet(answered[0][1])}"
    return None


def _init_tools(log: Path) -> list[str] | None:
    """The ``tools`` list of the log's first ``system``/``init`` line, or None.

    None means the log can't be read, has no such line, or the line has no
    list of strings under ``tools``.
    """
    try:
        lines = _load_lines(log)
    except OSError:
        return None
    for obj in lines:
        if obj.get("type") == "system" and obj.get("subtype") == "init":
            tools = obj.get("tools")
            if isinstance(tools, list) and all(isinstance(tool, str) for tool in tools):
                return tools
            return None
    return None


def _tools_problem(init_tools: list[str] | None) -> str | None:
    """Why the session's tools aren't exactly ``TRIAL_TOOLS``, or None when they are."""
    if init_tools is None:
        return "the log has no init line listing the session's tools"
    extra = sorted(set(init_tools) - set(TRIAL_TOOLS))
    missing = [tool for tool in TRIAL_TOOLS if tool not in init_tools]
    if not extra and not missing:
        return None
    return f"extra: {', '.join(extra) or 'none'}; missing: {', '.join(missing) or 'none'}"


def _self_test_problems(
    transcript: Transcript | None,
    *,
    exit_code: int | None,
    timed_out: bool,
    dummy: Path,
    init_tools: list[str] | None,
) -> list[tuple[str, str]]:
    """The failed checks of the self-test as ``(check, detail)``, in a fixed order."""
    problems: list[tuple[str, str]] = []
    if timed_out:
        problems.append(("timeout", "claude was killed after the timeout"))
    elif exit_code != 0:
        problems.append(("exit", f"claude exited with code {exit_code}"))
    if transcript is None or not transcript.has_result:
        problems.append(("result", "the log has no result line"))
    elif transcript.result_is_error:
        problems.append(("result", "the result line reports is_error"))
    if transcript is None:
        problems.append(("powershell", "no log to read"))
        problems.append(("bash", "no log to read"))
    else:
        results = {call_id: (is_error, text) for call_id, is_error, text in transcript.results}
        for check, tool in (("powershell", "PowerShell"), ("bash", "Bash")):
            detail = _tool_problem(transcript, results, tool)
            if detail:
                problems.append((check, detail))
        if any("the command line is too long" in text.lower() for _id, _err, text in transcript.results):
            problems.append(("too-long", "a tool result says 'The command line is too long'"))
        denied = [denial.name for denial in transcript.denials if denial.name in ("Edit", "Write", "MultiEdit")]
        if denied:
            problems.append(("denial", f"permission denied for {', '.join(denied)}"))
    try:
        text = dummy.read_text(encoding="utf-8").strip()
    except OSError as exc:
        problems.append(("edit", f"{dummy.name} can't be read: {exc}"))
    else:
        if text != "after":
            problems.append(("edit", f"{dummy.name} reads {text!r}, not 'after'"))
    detail = _tools_problem(init_tools)
    if detail:
        problems.append(("tools", detail))
    return problems


def self_test(
    *,
    model: str,
    trials_root: Path,
    claude_cmd: list[str],
    pwsh: Path,
    timeout_s: int,
    out: Out = print,
) -> int:
    """Check the launcher itself with one cheap headless run; returns 0 on pass, 1 on fail.

    The run gets a throwaway folder ``<trials_root>/selftest-<stamp>/`` holding
    only ``inputs/dummy.txt`` and the same environment, command line and
    allow rules as a real trial. It passes when the log has a clean result,
    a PowerShell and a Bash call both succeeded, no result says "The command
    line is too long", no edit was denied, ``dummy.txt`` now reads
    ``after`` and the init line's tools are exactly ``TRIAL_TOOLS``. The
    checks run in the order timeout/exit, result, powershell, bash, too-long,
    denial, edit, tools: ``tools`` is the last one. The folder is kept for
    inspection.
    """
    if timeout_s < 1:
        raise ValueError(f"the timeout must be at least 1 second, got {timeout_s}")
    root = _absolute(trials_root)
    name = f"selftest-{_now().strftime('%Y%m%d-%H%M%S')}"
    folder = root / name
    log, stderr = root / f"{name}{STREAM_SUFFIX}", root / f"{name}{STDERR_SUFFIX}"
    for path in (folder, log, stderr):
        if path.exists():
            raise ValueError(f"the self-test would overwrite {path}")
    dummy = folder / "inputs" / "dummy.txt"
    dummy.parent.mkdir(parents=True)
    dummy.write_bytes(b"before\n")

    env = trial_env(os.environ, pwsh_dir=Path(pwsh).parent, repo_root=REPO_ROOT)
    argv = claude_argv(claude_cmd, prompt=SELF_TEST_PROMPT, model=model, effort="default", allowed_file=dummy)
    exit_code, timed_out, _seconds = launch_trial(
        argv, folder=folder, log=log, stderr=stderr, env=env, timeout_s=timeout_s
    )
    problems = _self_test_problems(
        _read_log(log), exit_code=exit_code, timed_out=timed_out, dummy=dummy, init_tools=_init_tools(log)
    )
    out("SELFTEST=fail" if problems else "SELFTEST=pass")
    for check, detail in problems:
        out(f"REASON={check}: {detail}")
    out(f"FOLDER={folder}")
    out(f"LOG={log}")
    return 1 if problems else 0
