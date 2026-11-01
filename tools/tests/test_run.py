"""Tests for scriptfix.run: run numbers, trial folders, the child's environment, argv, sidecar and launching.

The launching tests use a fake ``claude``: a stdlib-only Python script in
tmp_path that records its argv, cwd and environment, prints canned
stream-json and edits the allowed file. Nothing here touches the real home
folder or the real ``claude``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest
from test_grade import World, edit_call, stream_log

from scriptfix import __version__, run
from scriptfix.run import (
    EFFORTS,
    SELF_TEST_MODEL,
    SELF_TEST_PROMPT,
    STRIP_NAMES,
    allow_rule,
    check_free,
    claude_argv,
    is_windowsapps_alias,
    next_command,
    next_runs,
    prepare_trial,
    resolve_claude,
    resolve_pwsh,
    run_trials,
    self_test,
    stripped_names,
    trial_env,
    write_sidecar,
)


def touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------
# next_runs
# --------------------------------------------------------------------------


def test_next_runs_with_nothing_starts_at_one(tmp_path: Path) -> None:
    assert next_runs("01", 3, tmp_path / "missing-root", tmp_path / "missing.jsonl") == [1, 2, 3]


def test_next_runs_counts_folders_logs_and_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "01-run4").mkdir(parents=True)
    touch(root / "01-run7.stream.jsonl")
    touch(root / "01-run9.subject.json")
    assert next_runs("01", 2, root, tmp_path / "none.jsonl") == [10, 11]


def test_next_runs_counts_a_leftover_stderr_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    touch(root / "01-run5.stderr.txt")
    assert next_runs("01", 1, root, tmp_path / "none.jsonl") == [6]


def test_next_runs_counts_trials_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    jsonl = touch(
        tmp_path / "trials.jsonl",
        json.dumps({"run": 12, "rubric": "v0"}) + "\n" + json.dumps({"run": 3, "rubric": "v0"}) + "\n",
    )
    assert next_runs("01", 1, root, jsonl) == [13]


def test_next_runs_takes_the_highest_across_sources(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "01-run2").mkdir(parents=True)
    jsonl = touch(tmp_path / "trials.jsonl", json.dumps({"run": 8, "rubric": "v0"}) + "\n")
    assert next_runs("01", 1, root, jsonl) == [9]


def test_next_runs_matches_the_case_number_exactly(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "11-run50").mkdir(parents=True)
    (root / "011-run60").mkdir()
    touch(root / "01-run12.stream.jsonl")
    touch(root / "02-run99.stream.jsonl")
    assert next_runs("01", 1, root, tmp_path / "none.jsonl") == [13]


def test_next_runs_ignores_unrelated_names(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "01-runx").mkdir(parents=True)
    (root / "01-run30.stream.jsonl.bak").mkdir()
    touch(root / "01-run40.txt")
    touch(root / "01-run50")  # a plain file with the folder's name is not a trial folder
    assert next_runs("01", 1, root, tmp_path / "none.jsonl") == [1]


@pytest.mark.parametrize("count", [0, -1])
def test_next_runs_rejects_a_count_below_one(tmp_path: Path, count: int) -> None:
    with pytest.raises(ValueError, match="--count"):
        next_runs("01", count, tmp_path, tmp_path / "none.jsonl")


# --------------------------------------------------------------------------
# check_free
# --------------------------------------------------------------------------


def test_check_free_passes_when_nothing_exists(tmp_path: Path) -> None:
    check_free("01", [1, 2], tmp_path / "root")


def test_check_free_ignores_other_cases_and_runs(tmp_path: Path) -> None:
    (tmp_path / "02-run1").mkdir()
    (tmp_path / "01-run2").mkdir()
    check_free("01", [1], tmp_path)


def test_check_free_rejects_an_existing_folder(tmp_path: Path) -> None:
    (tmp_path / "01-run3").mkdir()
    with pytest.raises(ValueError, match="01-run3"):
        check_free("01", [3], tmp_path)


@pytest.mark.parametrize("suffix", [".stream.jsonl", ".subject.json", ".stderr.txt"])
def test_check_free_rejects_each_kind_of_existing_file(tmp_path: Path, suffix: str) -> None:
    touch(tmp_path / f"01-run3{suffix}")
    with pytest.raises(ValueError, match=rf"01-run3{suffix.replace('.', r'\.')}"):
        check_free("01", [3], tmp_path)


def test_check_free_names_the_first_run_that_exists(tmp_path: Path) -> None:
    (tmp_path / "01-run5").mkdir()
    (tmp_path / "01-run6").mkdir()
    with pytest.raises(ValueError, match="01-run5"):
        check_free("01", [4, 5, 6], tmp_path)


# --------------------------------------------------------------------------
# prepare_trial
# --------------------------------------------------------------------------


def make_case_dir(tmp_path: Path) -> Path:
    case = tmp_path / "evals" / "09-demo"
    case.mkdir(parents=True)
    (case / "prompt.md").write_bytes(b"Fix `inputs/script.py`.\r\nSecond \xc2\xbb line\n")
    (case / "inputs" / "results").mkdir(parents=True)
    (case / "inputs" / "script.py").write_bytes(b"print('a')\r\n")
    (case / "inputs" / "results" / "log.txt").write_bytes(b"\x00\x01binary\xff")
    (case / "grading" / "reference").mkdir(parents=True)
    (case / "grading" / "reference" / "script.py").write_text("print('fixed')\n", encoding="utf-8")
    (case / "grading" / "case.toml").write_text("x = 1\n", encoding="utf-8")
    (case / "notes.md").write_text("not part of the trial\n", encoding="utf-8")
    return case


def test_prepare_trial_copies_exactly_the_prompt_and_inputs(tmp_path: Path) -> None:
    case = make_case_dir(tmp_path)
    folder = tmp_path / "trials" / "09-run1"
    script = prepare_trial(case, folder)

    assert script == folder / "inputs" / "script.py"
    copied = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
    assert copied == ["inputs", "inputs/results", "inputs/results/log.txt", "inputs/script.py", "prompt.md"]


def test_prepare_trial_copies_bytes_unchanged(tmp_path: Path) -> None:
    case = make_case_dir(tmp_path)
    folder = tmp_path / "09-run1"
    prepare_trial(case, folder)
    assert (folder / "prompt.md").read_bytes() == (case / "prompt.md").read_bytes()
    assert (folder / "inputs" / "script.py").read_bytes() == b"print('a')\r\n"
    assert (folder / "inputs" / "results" / "log.txt").read_bytes() == b"\x00\x01binary\xff"


def test_prepare_trial_never_copies_grading(tmp_path: Path) -> None:
    case = make_case_dir(tmp_path)
    folder = tmp_path / "09-run1"
    prepare_trial(case, folder)
    assert not (folder / "grading").exists()
    assert not (folder / "notes.md").exists()


def test_prepare_trial_refuses_an_existing_folder(tmp_path: Path) -> None:
    case = make_case_dir(tmp_path)
    folder = tmp_path / "09-run1"
    folder.mkdir()
    (folder / "keep.txt").write_text("mine\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        prepare_trial(case, folder)
    assert sorted(p.name for p in folder.iterdir()) == ["keep.txt"]


def test_prepare_trial_reports_a_case_without_a_prompt(tmp_path: Path) -> None:
    case = make_case_dir(tmp_path)
    (case / "prompt.md").unlink()
    with pytest.raises(ValueError, match="prompt.md"):
        prepare_trial(case, tmp_path / "09-run1")
    assert not (tmp_path / "09-run1").exists()


def test_prepare_trial_reports_a_case_without_inputs(tmp_path: Path) -> None:
    case = tmp_path / "09-bare"
    case.mkdir()
    (case / "prompt.md").write_text("hi\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inputs"):
        prepare_trial(case, tmp_path / "09-run1")
    assert not (tmp_path / "09-run1").exists()


# --------------------------------------------------------------------------
# trial_env
# --------------------------------------------------------------------------


def paths(*entries: Path | str) -> str:
    return os.pathsep.join(os.fspath(entry) for entry in entries)


def test_trial_env_strips_every_listed_name(tmp_path: Path) -> None:
    environ = {name: "x" for name in STRIP_NAMES}
    environ.update({"KEEP_ME": "1", "PATH": paths(tmp_path / "bin")})
    env = trial_env(environ, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert set(env) == {"KEEP_ME", "PATH"}


def test_trial_env_strips_names_case_insensitively(tmp_path: Path) -> None:
    environ = {
        "ai_agent": "1",
        "No_Color": "1",
        "psexecutionpolicypreference": "x",
        "NODEFAULTCURRENTDIRECTORYINEXEPATH": "1",
        "virtual_env": "x",
        "PythonPath": "x",
        "HOME": "h",
    }
    env = trial_env(environ, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert set(env) - {"PATH"} == {"HOME"}


def test_trial_env_strips_claude_and_plugin_prefixes(tmp_path: Path) -> None:
    environ = {
        "CLAUDECODE": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "claude_code_something": "x",
        "ZMH3D_ROOT": "x",
        "zmh3d_cache": "x",
        "ZMH3D": "no underscore: kept",
        "NOT_CLAUDE": "kept",
    }
    env = trial_env(environ, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert set(env) - {"PATH"} == {"ZMH3D", "NOT_CLAUDE"}


def test_trial_env_leaves_its_input_alone(tmp_path: Path) -> None:
    environ = {"CLAUDECODE": "1", "PATH": paths(tmp_path / "bin")}
    before = dict(environ)
    trial_env(environ, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert environ == before


def test_trial_env_puts_the_pwsh_directory_first(tmp_path: Path) -> None:
    other = tmp_path / "other"
    pwsh = tmp_path / "pwsh"
    env = trial_env({"PATH": paths(other)}, pwsh_dir=pwsh, repo_root=tmp_path / "repo")
    assert env["PATH"].split(os.pathsep) == [os.fspath(pwsh), os.fspath(other)]


def test_trial_env_drops_path_entries_under_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    keep = tmp_path / "tools"
    path = paths(repo / ".venv" / "Scripts", keep, repo, repo / "sub" / "dir", tmp_path / "repo2")
    env = trial_env({"PATH": path}, pwsh_dir=tmp_path / "pwsh", repo_root=repo)
    assert env["PATH"].split(os.pathsep) == [
        os.fspath(tmp_path / "pwsh"),
        os.fspath(keep),
        os.fspath(tmp_path / "repo2"),  # a sibling that merely shares the prefix is kept
    ]


def test_trial_env_drops_the_removed_virtual_envs_script_dirs(tmp_path: Path) -> None:
    venv = tmp_path / "elsewhere" / "venv"
    keep = tmp_path / "keep"
    path = paths(venv / "Scripts", venv / "bin", keep)
    env = trial_env(
        {"PATH": path, "VIRTUAL_ENV": os.fspath(venv)},
        pwsh_dir=tmp_path / "pwsh",
        repo_root=tmp_path / "repo",
    )
    assert env["PATH"].split(os.pathsep) == [os.fspath(tmp_path / "pwsh"), os.fspath(keep)]
    assert "VIRTUAL_ENV" not in env


def test_trial_env_drops_empty_entries(tmp_path: Path) -> None:
    keep = tmp_path / "keep"
    env = trial_env(
        {"PATH": os.pathsep + os.fspath(keep) + os.pathsep + os.pathsep},
        pwsh_dir=tmp_path / "pwsh",
        repo_root=tmp_path / "repo",
    )
    assert env["PATH"].split(os.pathsep) == [os.fspath(tmp_path / "pwsh"), os.fspath(keep)]


def test_trial_env_keeps_the_path_key_spelling_and_a_single_key(tmp_path: Path) -> None:
    env = trial_env(
        {"Path": paths(tmp_path / "bin"), "HOME": "h"},
        pwsh_dir=tmp_path / "pwsh",
        repo_root=tmp_path / "repo",
    )
    assert [key for key in env if key.upper() == "PATH"] == ["Path"]
    assert env["Path"].split(os.pathsep)[0] == os.fspath(tmp_path / "pwsh")


def test_trial_env_without_a_path_still_gets_the_pwsh_directory(tmp_path: Path) -> None:
    env = trial_env({"HOME": "h"}, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert env["PATH"] == os.fspath(tmp_path / "pwsh")


@pytest.mark.skipif(os.name != "nt", reason="path comparison is case-insensitive on Windows only")
def test_trial_env_compares_paths_case_insensitively_on_windows(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shouting = os.fspath(repo / ".venv" / "Scripts").upper()
    env = trial_env({"PATH": paths(shouting)}, pwsh_dir=tmp_path / "pwsh", repo_root=repo)
    assert env["PATH"] == os.fspath(tmp_path / "pwsh")


def test_stripped_names_lists_what_trial_env_removes(tmp_path: Path) -> None:
    environ = {"CLAUDECODE": "1", "virtual_env": "x", "HOME": "h", "PATH": "p", "ZMH3D_A": "1"}
    assert stripped_names(environ) == ["CLAUDECODE", "ZMH3D_A", "virtual_env"]


# --------------------------------------------------------------------------
# allow_rule
# --------------------------------------------------------------------------


def test_allow_rule_on_a_windows_path() -> None:
    path = PureWindowsPath(r"C:\Users\a\eval-trials\02-run3\inputs\script.py")
    assert allow_rule("Edit", path) == "Edit(//c/Users/a/eval-trials/02-run3/inputs/script.py)"


def test_allow_rule_on_a_windows_path_with_forward_slashes() -> None:
    path = PureWindowsPath("D:/x/y.py")
    assert allow_rule("Write", path) == "Write(//d/x/y.py)"


def test_allow_rule_on_a_posix_path() -> None:
    assert allow_rule("Edit", PurePosixPath("/home/a/x.py")) == "Edit(//home/a/x.py)"


def test_allow_rule_on_a_concrete_absolute_path(tmp_path: Path) -> None:
    rule = allow_rule("Edit", tmp_path / "inputs" / "script.py")
    assert rule.startswith("Edit(//")
    assert "\\" not in rule
    assert not rule.startswith("Edit(///")
    assert rule.endswith("/inputs/script.py)")


@pytest.mark.parametrize("bad", [PurePosixPath("inputs/script.py"), PureWindowsPath(r"inputs\script.py")])
def test_allow_rule_rejects_a_relative_path(bad: PurePosixPath | PureWindowsPath) -> None:
    with pytest.raises(ValueError, match="absolute"):
        allow_rule("Edit", bad)  # type: ignore[arg-type]


def test_allow_rule_rejects_a_drive_relative_path() -> None:
    with pytest.raises(ValueError, match="absolute"):
        allow_rule("Edit", PureWindowsPath("C:script.py"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# claude_argv
# --------------------------------------------------------------------------


def argv_for(effort: str, tmp_path: Path, claude_cmd: list[str] | None = None) -> list[str]:
    return claude_argv(
        claude_cmd or ["claude"],
        prompt="Fix the script.\nThen stop.",
        model="claude-haiku-5-5",
        effort=effort,
        allowed_file=tmp_path / "09-run1" / "inputs" / "script.py",
    )


def test_claude_argv_without_effort(tmp_path: Path) -> None:
    argv = argv_for("default", tmp_path)
    rule_path = allow_rule("Edit", tmp_path / "09-run1" / "inputs" / "script.py")[len("Edit(") : -1]
    assert argv == [
        "claude",
        "-p",
        "Fix the script.\nThen stop.",
        "--safe-mode",
        "--strict-mcp-config",
        "--model",
        "claude-haiku-5-5",
        "--permission-mode",
        run.PERMISSION_MODE,
        "--allowedTools",
        f"Edit({rule_path})",
        f"Write({rule_path})",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    assert "--effort" not in argv


def test_claude_argv_with_effort(tmp_path: Path) -> None:
    argv = argv_for("high", tmp_path)
    at = argv.index("--effort")
    assert argv[at + 1] == "high"
    assert argv[at - 2 : at] == ["--model", "claude-haiku-5-5"]
    assert argv[at + 2] == "--permission-mode"


def test_claude_argv_puts_the_prompt_right_after_dash_p(tmp_path: Path) -> None:
    argv = argv_for("max", tmp_path, claude_cmd=["python", "fake.py"])
    assert argv[:4] == ["python", "fake.py", "-p", "Fix the script.\nThen stop."]
    # The variadic --allowedTools holds exactly the two rules, then the next flag.
    start = argv.index("--allowedTools")
    assert argv[start + 3] == "--output-format"


def test_claude_argv_defaults_to_the_default_permission_mode() -> None:
    assert run.PERMISSION_MODE == "default"


def test_claude_argv_rejects_an_unknown_effort(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="effort"):
        argv_for("ludicrous", tmp_path)


@pytest.mark.parametrize("effort", EFFORTS)
def test_claude_argv_accepts_every_listed_effort(tmp_path: Path, effort: str) -> None:
    assert ("--effort" in argv_for(effort, tmp_path)) == (effort != "default")


def test_constants_match_the_supported_choices() -> None:
    assert run.TOOLS == ("edit-only",)
    assert run.CONTEXTS == ("none",)
    assert run.DEFAULT_TRIAL_TIMEOUT_S == 1800
    assert run.SELF_TEST_MODEL == "claude-haiku-5-5"


# --------------------------------------------------------------------------
# write_sidecar
# --------------------------------------------------------------------------


SIDECAR = {
    "run": 13,
    "case": "01-playwright-python-basic",
    "model": "claude-haiku-5-5",
    "effort": "default",
    "context": "none",
    "tools": "edit-only",
    "runner": "0.1.0",
    "started": "2026-11-01T10:00:00",
    "seconds": 74.2,
    "exit_code": 0,
    "timed_out": False,
}


def test_write_sidecar_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "01-run13.subject.json"
    write_sidecar(path, dict(SIDECAR))
    assert json.loads(path.read_text(encoding="utf-8")) == SIDECAR


def test_write_sidecar_is_indented_lf_json_with_a_final_newline(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    write_sidecar(path, dict(SIDECAR))
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.endswith(b"}\n")
    assert data.decode("utf-8") == json.dumps(SIDECAR, indent=2) + "\n"


def test_write_sidecar_keeps_the_key_order_and_null(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    record = {**SIDECAR, "exit_code": None, "timed_out": True}
    write_sidecar(path, record)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert list(loaded) == list(record)
    assert loaded["exit_code"] is None


# --------------------------------------------------------------------------
# resolve_pwsh / resolve_claude
# --------------------------------------------------------------------------

REAL_PWSH = r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.9.0_x64__8wekyb3d8bbwe\pwsh.exe"
ALIAS_PWSH = r"C:\Users\a\AppData\Local\Microsoft\WindowsApps\pwsh.exe"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (ALIAS_PWSH, True),
        (ALIAS_PWSH.lower(), True),
        (ALIAS_PWSH.replace("\\", "/"), True),
        (PureWindowsPath(ALIAS_PWSH), True),
        (REAL_PWSH, False),  # the store package under Program Files is the real thing
        (PureWindowsPath(REAL_PWSH), False),
        (r"C:\Program Files\PowerShell\7\pwsh.exe", False),
        ("/usr/bin/pwsh", False),
    ],
)
def test_is_windowsapps_alias(path: str | PureWindowsPath, expected: bool) -> None:
    assert is_windowsapps_alias(path) is expected


def test_resolve_pwsh_accepts_an_existing_file(tmp_path: Path) -> None:
    pwsh = tmp_path / "pwsh.exe"
    pwsh.write_bytes(b"")
    assert resolve_pwsh(pwsh) == pwsh


def test_resolve_pwsh_rejects_the_alias_even_when_it_exists(tmp_path: Path) -> None:
    alias = tmp_path / "Microsoft" / "WindowsApps" / "pwsh.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"")
    with pytest.raises(ValueError, match=r"--pwsh.*alias.*Get-Process -Id \$PID"):
        resolve_pwsh(alias)


def test_resolve_pwsh_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a file"):
        resolve_pwsh(tmp_path / "nope" / "pwsh.exe")


def test_resolve_pwsh_uses_which_and_rejects_its_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pwsh = tmp_path / "pwsh.exe"
    pwsh.write_bytes(b"")
    monkeypatch.setattr(run.shutil, "which", lambda name: str(pwsh) if name == "pwsh" else None)
    assert resolve_pwsh(None) == pwsh
    monkeypatch.setattr(run.shutil, "which", lambda name: ALIAS_PWSH)
    with pytest.raises(ValueError, match="alias"):
        resolve_pwsh(None)
    monkeypatch.setattr(run.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="--pwsh"):
        resolve_pwsh(None)


def test_resolve_claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    claude = tmp_path / "claude.exe"
    claude.write_bytes(b"")
    assert resolve_claude(claude) == claude
    with pytest.raises(ValueError, match="--claude is not a file"):
        resolve_claude(tmp_path / "missing.exe")
    monkeypatch.setattr(run.shutil, "which", lambda name: str(claude))
    assert resolve_claude(None) == claude
    monkeypatch.setattr(run.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="--claude"):
        resolve_claude(None)


# --------------------------------------------------------------------------
# next_command
# --------------------------------------------------------------------------


def test_next_command_for_a_case_inside_the_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run, "REPO_ROOT", tmp_path / "repo")
    case = tmp_path / "repo" / "evals" / "02-docs-journey-a"
    default_root = Path.home() / "eval-trials"
    assert next_command(case, [13], default_root) == r".\30-grade-trials.ps1 -Case evals\02-docs-journey-a -Runs 13"


def test_next_command_for_a_case_outside_the_repo_is_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run, "REPO_ROOT", tmp_path / "repo")
    case = tmp_path / "elsewhere" / "02-x"
    command = next_command(case, [1, 2], Path.home() / "eval-trials")
    assert f"-Case {case} " in command and command.endswith("-Runs 1-2")


def test_next_command_run_specs(tmp_path: Path) -> None:
    case, root = tmp_path / "02-x", Path.home() / "eval-trials"
    assert next_command(case, [3, 4, 5], root).endswith("-Runs 3-5")
    assert next_command(case, [3, 7, 9], root).endswith("-Runs 3,7,9")
    assert next_command(case, [9, 3], root).endswith("-Runs 3,9")


def test_next_command_adds_a_non_default_trials_root(tmp_path: Path) -> None:
    command = next_command(tmp_path / "02-x", [1], tmp_path / "trials")
    assert command.endswith(f"-Runs 1 -TrialsRoot {tmp_path / 'trials'}")
    assert "-TrialsRoot" not in next_command(tmp_path / "02-x", [1], Path("~/eval-trials"))


def test_next_command_quotes_a_path_with_spaces(tmp_path: Path) -> None:
    command = next_command(tmp_path / "my cases" / "02-x", [1], tmp_path / "a b")
    assert f"-Case '{tmp_path / 'my cases' / '02-x'}'" in command
    assert f"-TrialsRoot '{tmp_path / 'a b'}'" in command


# --------------------------------------------------------------------------
# A fake claude
# --------------------------------------------------------------------------

# Stdlib only, and it finds its settings beside itself: the child's environment
# is stripped, so nothing can be passed through PYTHONPATH.
FAKE_CLAUDE = '''
import json, os, sys, time

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "fake_claude.json"), encoding="utf-8") as handle:
    cfg = json.load(handle)
with open(cfg["record"], "a", encoding="utf-8", newline="\\n") as handle:
    handle.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}) + "\\n")
for line in cfg.get("stdout", []):
    sys.stdout.buffer.write((json.dumps(line) + "\\n").encode("utf-8"))
sys.stdout.buffer.flush()
sys.stderr.write(cfg.get("stderr", ""))
edit = cfg.get("edit")
if edit:
    with open(os.path.join(os.getcwd(), edit["file"]), "w", encoding="utf-8", newline="\\n") as handle:
        handle.write(edit["text"])
time.sleep(cfg.get("sleep", 0))
sys.exit(cfg.get("exit", 0))
'''

PROMPT = "Fix `inputs/script.py` so the run passes.\n\nReply when you are done.\n"
FIXED_NOW = datetime(2026, 11, 1, 10, 0, 0)


class FakeClaude:
    """A ``claude`` stand-in launched as ``[python, fake_claude.py]``."""

    def __init__(self, tmp_path: Path) -> None:
        self.dir = tmp_path / "fake"
        self.dir.mkdir()
        self.script = self.dir / "fake_claude.py"
        self.script.write_text(FAKE_CLAUDE, encoding="utf-8", newline="\n")
        self.record = self.dir / "record.jsonl"
        self.pwsh = self.dir / "pwsh" / "pwsh.exe"
        self.pwsh.parent.mkdir()
        self.pwsh.write_bytes(b"")
        self.configure()

    @property
    def cmd(self) -> list[str]:
        return [sys.executable, str(self.script)]

    def configure(self, **settings: Any) -> None:
        settings["record"] = str(self.record)
        (self.dir / "fake_claude.json").write_text(json.dumps(settings), encoding="utf-8", newline="\n")

    def calls(self) -> list[dict[str, Any]]:
        if not self.record.exists():
            return []
        lines = self.record.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture
def fake(tmp_path: Path) -> FakeClaude:
    return FakeClaude(tmp_path)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setattr(run, "_now", lambda: FIXED_NOW)
    case = World(tmp_path)
    (case.case_dir / "prompt.md").write_text(PROMPT, encoding="utf-8", newline="\n")
    return case


def good_trial(fake: FakeClaude, **extra: Any) -> None:
    fake.configure(
        stdout=stream_log(edit_call()),
        edit={"file": "inputs/script.py", "text": "# fixed\n"},
        **extra,
    )


def go(world: World, fake: FakeClaude, out: list[str], **over: Any) -> int:
    kwargs: dict[str, Any] = {
        "model": "claude-haiku-5-5",
        "effort": "default",
        "runs": None,
        "count": 1,
        "trials_root": world.trials_root,
        "claude_cmd": fake.cmd,
        "pwsh": fake.pwsh,
        "timeout_s": 60,
        "dry_run": False,
        "out": out.append,
    }
    kwargs.update(over)
    return run_trials(world.case_dir, **kwargs)


def line_with(out: list[str], prefix: str) -> str:
    (found,) = [line for line in out if line.startswith(prefix)]
    return found


# --------------------------------------------------------------------------
# launch_trial
# --------------------------------------------------------------------------


def test_launch_trial_captures_raw_bytes_into_files_and_runs_in_the_folder(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    code = (
        "import os, sys; sys.stdout.buffer.write(b'\\xff\\xfe\\r\\n'); "
        "sys.stderr.write('oops'); open('cwd.txt', 'w').write(os.getcwd()); sys.exit(3)"
    )
    exit_code, timed_out, seconds = run.launch_trial(
        [sys.executable, "-c", code],
        folder=folder,
        log=tmp_path / "out.jsonl",
        stderr=tmp_path / "err.txt",
        env=dict(os.environ),
        timeout_s=60,
    )
    assert (exit_code, timed_out) == (3, False)
    assert seconds >= 0
    assert (tmp_path / "out.jsonl").read_bytes() == b"\xff\xfe\r\n"  # never decoded or re-encoded
    assert (tmp_path / "err.txt").read_text(encoding="utf-8") == "oops"
    assert Path((folder / "cwd.txt").read_text(encoding="utf-8")).samefile(folder)


def test_launch_trial_kills_a_process_that_outlives_the_timeout(tmp_path: Path) -> None:
    started = time.monotonic()
    exit_code, timed_out, seconds = run.launch_trial(
        [sys.executable, "-c", "import time; print('hi', flush=True); time.sleep(60)"],
        folder=tmp_path,
        log=tmp_path / "out.txt",
        stderr=tmp_path / "err.txt",
        env=dict(os.environ),
        timeout_s=2,
    )
    assert exit_code is None and timed_out is True
    assert 2 <= seconds < 30 and time.monotonic() - started < 30
    assert (tmp_path / "out.txt").read_text(encoding="utf-8").strip() == "hi"


# --------------------------------------------------------------------------
# run_trials: a good trial
# --------------------------------------------------------------------------


def test_a_good_trial(world: World, fake: FakeClaude) -> None:
    good_trial(fake)
    out: list[str] = []
    assert go(world, fake, out) == 0

    root = world.trials_root
    folder = root / "01-run1"
    assert sorted(p.name for p in folder.iterdir()) == ["inputs", "prompt.md"]
    assert (folder / "inputs" / "script.py").read_text(encoding="utf-8") == "# fixed\n"
    assert sorted(p.name for p in root.iterdir()) == [
        "01-run1",
        "01-run1.stderr.txt",
        "01-run1.stream.jsonl",
        "01-run1.subject.json",
    ]
    expected_log = "".join(json.dumps(line) + "\n" for line in stream_log(edit_call()))
    assert (root / "01-run1.stream.jsonl").read_text(encoding="utf-8") == expected_log

    sidecar = json.loads((root / "01-run1.subject.json").read_text(encoding="utf-8"))
    assert list(sidecar) == [
        "run", "case", "model", "effort", "context", "tools", "runner", "started", "seconds", "exit_code", "timed_out",
    ]  # fmt: skip
    assert sidecar | {"seconds": 0} == {
        "run": 1,
        "case": "01-x",
        "model": "claude-haiku-5-5",
        "effort": "default",
        "context": "none",
        "tools": "edit-only",
        "runner": __version__,
        "started": "2026-11-01T10:00:00",
        "seconds": 0,
        "exit_code": 0,
        "timed_out": False,
    }
    assert isinstance(sidecar["seconds"], float) and sidecar["seconds"] == round(sidecar["seconds"], 1)
    assert (root / "01-run1.subject.json").read_bytes().endswith(b"}\n")

    log = root / "01-run1.stream.jsonl"
    assert line_with(out, "RUN=") == (
        f"RUN=1 EXIT=0 TIMED_OUT=False COST_USD=0.25 IS_ERROR=False DENIALS=0 LOG={log}"
    )
    assert line_with(out, "NEXT=") == f"NEXT={next_command(world.case_dir, [1], root)}"
    assert "-Runs 1 -TrialsRoot " in line_with(out, "NEXT=")
    assert not any(line.startswith("HARNESS=") for line in out)


def test_the_child_sees_the_documented_argv_cwd_and_env(
    world: World, fake: FakeClaude, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("ZMH3D_ROOT", "x")
    monkeypatch.setenv("VIRTUAL_ENV", str(world.case_dir))
    monkeypatch.setenv("PYTHONPATH", str(world.case_dir))
    monkeypatch.setenv("KEEP_ME", "yes")
    good_trial(fake)
    assert go(world, fake, [], effort="high") == 0

    (call,) = fake.calls()
    folder = world.trials_root / "01-run1"
    script = folder / "inputs" / "script.py"
    argv = call["argv"]
    assert argv[:2] == ["-p", PROMPT.strip()]  # the prompt, stripped, right after -p
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--effort") + 1] == "high"
    start = argv.index("--allowedTools")
    assert argv[start + 1 : start + 3] == [allow_rule("Edit", script), allow_rule("Write", script)]
    assert argv[start + 1].startswith("Edit(//") and ":" not in argv[start + 1]
    assert "--safe-mode" in argv and "--strict-mcp-config" in argv and argv[-1] == "--verbose"
    assert Path(call["cwd"]).samefile(folder)

    env = call["env"]
    assert not any(key.upper().startswith(("CLAUDE", "ZMH3D_")) for key in env)
    assert not {"VIRTUAL_ENV", "PYTHONPATH"} & {key.upper() for key in env}
    assert env["KEEP_ME"] == "yes"
    first = env["PATH"].split(os.pathsep)[0]
    assert os.path.normcase(first) == os.path.normcase(str(fake.pwsh.parent))


def test_default_effort_omits_the_flag(world: World, fake: FakeClaude) -> None:
    good_trial(fake)
    assert go(world, fake, []) == 0
    assert "--effort" not in fake.calls()[0]["argv"]


# --------------------------------------------------------------------------
# run_trials: numbering and the never-overwrite rule
# --------------------------------------------------------------------------


def test_count_numbers_after_the_existing_runs(world: World, fake: FakeClaude) -> None:
    (world.trials_root / "01-run4").mkdir(parents=True)
    (world.trials_root / "01-run5.subject.json").write_text("{}", encoding="utf-8")
    good_trial(fake)
    out: list[str] = []
    assert go(world, fake, out, count=2) == 0
    assert (world.trials_root / "01-run6.subject.json").is_file()
    assert (world.trials_root / "01-run7.subject.json").is_file()
    assert not (world.trials_root / "01-run8").exists()
    assert len(fake.calls()) == 2
    assert [line.split()[0] for line in out if line.startswith("RUN=")] == ["RUN=6", "RUN=7"]
    assert "-Runs 6-7 " in line_with(out, "NEXT=") + " "


def test_count_numbers_after_trials_jsonl(world: World, fake: FakeClaude) -> None:
    world.trials_path.write_text(json.dumps({"run": 12, "rubric": "script-fix-v0"}) + "\n", encoding="utf-8")
    good_trial(fake)
    assert go(world, fake, []) == 0
    assert (world.trials_root / "01-run13.subject.json").is_file()


def test_runs_names_exact_numbers_and_next_lists_them(world: World, fake: FakeClaude) -> None:
    good_trial(fake)
    out: list[str] = []
    assert go(world, fake, out, runs=[3, 7], count=None) == 0
    assert (world.trials_root / "01-run3").is_dir() and (world.trials_root / "01-run7").is_dir()
    assert "-Runs 3,7" in line_with(out, "NEXT=")


@pytest.mark.parametrize("existing", ["01-run2", "01-run2.stream.jsonl", "01-run2.subject.json", "01-run2.stderr.txt"])
def test_runs_naming_an_existing_run_is_rejected_before_anything_happens(
    world: World, fake: FakeClaude, existing: str
) -> None:
    world.trials_root.mkdir(parents=True)
    path = world.trials_root / existing
    if existing == "01-run2":
        path.mkdir()
    else:
        path.write_text("keep\n", encoding="utf-8")
    before = sorted(p.name for p in world.trials_root.iterdir())
    good_trial(fake)
    with pytest.raises(ValueError, match=existing.replace(".", r"\.")):
        go(world, fake, [], runs=[1, 2], count=None)
    assert sorted(p.name for p in world.trials_root.iterdir()) == before  # run 1 was not started either
    assert fake.calls() == []


def test_exactly_one_of_runs_and_count(world: World, fake: FakeClaude) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        go(world, fake, [], runs=None, count=None)
    with pytest.raises(ValueError, match="exactly one"):
        go(world, fake, [], runs=[1], count=1)
    assert not world.trials_root.exists() and fake.calls() == []


@pytest.mark.parametrize(
    "bad",
    [{"effort": "ludicrous"}, {"context": "bundle"}, {"tools": "all"}, {"timeout_s": 0}, {"runs": [0], "count": None}, {"runs": [2, 2], "count": None}, {"count": 0}],
)
def test_bad_arguments_fail_before_anything_is_created(world: World, fake: FakeClaude, bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        go(world, fake, [], **bad)
    assert not world.trials_root.exists() and fake.calls() == []


def test_a_case_without_a_prompt_fails_before_anything_is_created(world: World, fake: FakeClaude) -> None:
    (world.case_dir / "prompt.md").unlink()
    with pytest.raises(ValueError, match="prompt.md"):
        go(world, fake, [])
    assert not world.trials_root.exists()


# --------------------------------------------------------------------------
# run_trials: harness problems stop the batch
# --------------------------------------------------------------------------


def test_a_non_zero_exit_stops_the_batch_after_the_first_trial(world: World, fake: FakeClaude) -> None:
    good_trial(fake, exit=1, stderr="boom\n")
    out: list[str] = []
    assert go(world, fake, out, count=2) == 1

    assert len(fake.calls()) == 1
    assert not (world.trials_root / "01-run2").exists()
    assert sorted(p.name for p in world.trials_root.glob("*.subject.json")) == ["01-run1.subject.json"]
    sidecar = json.loads((world.trials_root / "01-run1.subject.json").read_text(encoding="utf-8"))
    assert sidecar["exit_code"] == 1 and sidecar["timed_out"] is False
    assert (world.trials_root / "01-run1.stderr.txt").read_text(encoding="utf-8") == "boom\n"
    assert line_with(out, "RUN=").startswith("RUN=1 EXIT=1 TIMED_OUT=False")
    assert "exited with code 1" in line_with(out, "HARNESS=")
    assert "-Runs 1" in line_with(out, "NEXT=") and "-Runs 1-2" not in line_with(out, "NEXT=")
    assert out.index(line_with(out, "HARNESS=")) < out.index(line_with(out, "NEXT="))


def test_a_log_without_a_result_line_stops_the_batch(world: World, fake: FakeClaude) -> None:
    fake.configure(stdout=stream_log(edit_call(), result=False))
    out: list[str] = []
    assert go(world, fake, out, count=2) == 1
    assert len(fake.calls()) == 1
    assert "COST_USD=None" in line_with(out, "RUN=") and "EXIT=0" in line_with(out, "RUN=")
    assert "no result line" in line_with(out, "HARNESS=")
    sidecar = json.loads((world.trials_root / "01-run1.subject.json").read_text(encoding="utf-8"))
    assert sidecar["exit_code"] == 0


def test_an_empty_log_counts_as_no_result_line(world: World, fake: FakeClaude) -> None:
    fake.configure()
    out: list[str] = []
    assert go(world, fake, out) == 1
    assert "no result line" in line_with(out, "HARNESS=")


def test_a_timeout_kills_the_trial_and_stops_the_batch(world: World, fake: FakeClaude) -> None:
    good_trial(fake, sleep=60)
    out: list[str] = []
    started = time.monotonic()
    assert go(world, fake, out, count=2, timeout_s=2) == 1
    assert time.monotonic() - started < 40  # it did not wait for the sleep

    assert len(fake.calls()) == 1
    run_line = line_with(out, "RUN=")
    assert "EXIT=None" in run_line and "TIMED_OUT=True" in run_line
    assert "timed out" in line_with(out, "HARNESS=")
    sidecar = json.loads((world.trials_root / "01-run1.subject.json").read_text(encoding="utf-8"))
    assert sidecar["exit_code"] is None and sidecar["timed_out"] is True
    assert not (world.trials_root / "01-run2").exists()


def test_a_result_with_denials_is_reported_but_is_not_a_harness_problem(world: World, fake: FakeClaude) -> None:
    lines = stream_log(edit_call())
    lines[-1]["permission_denials"] = [{"tool_name": "Bash", "tool_use_id": "t9", "tool_input": {"command": "ls"}}]
    lines[-1]["is_error"] = True
    fake.configure(stdout=lines, edit={"file": "inputs/script.py", "text": "x\n"})
    out: list[str] = []
    assert go(world, fake, out) == 0
    assert "IS_ERROR=True DENIALS=1" in line_with(out, "RUN=")


# --------------------------------------------------------------------------
# run_trials: --dry-run
# --------------------------------------------------------------------------


def test_dry_run_prints_the_plan_and_creates_nothing(
    world: World, fake: FakeClaude, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    out: list[str] = []
    assert go(world, fake, out, count=2, dry_run=True, effort="low") == 0

    assert not world.trials_root.exists()
    assert fake.calls() == []
    text = "\n".join(out)
    assert "RUNS=1-2" in text
    assert f"RUN=1 FOLDER={world.trials_root / '01-run1'}" in text
    assert f"RUN=2 FOLDER={world.trials_root / '01-run2'}" in text
    assert f"<prompt.md: {len(PROMPT.strip())} chars>" in text
    assert PROMPT.strip() not in text
    assert "--effort low" in text and "--allowedTools" in text
    assert "CLAUDECODE" in line_with(out, "STRIP=")


def test_dry_run_still_rejects_an_existing_run(world: World, fake: FakeClaude) -> None:
    (world.trials_root / "01-run1").mkdir(parents=True)
    with pytest.raises(ValueError, match="01-run1"):
        go(world, fake, [], runs=[1], count=None, dry_run=True)


# --------------------------------------------------------------------------
# self_test
# --------------------------------------------------------------------------


def selftest_log(
    *,
    ps_text: str = r"C:\trial\01",
    ps_error: bool = False,
    bash_error: bool = False,
    denials: tuple[str, ...] = (),
    result: bool = True,
    result_error: bool = False,
) -> list[dict[str, Any]]:
    uses = [
        {"type": "tool_use", "id": "t1", "name": "PowerShell", "input": {"command": "Get-Location"}},
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "cd inputs && ls"}},
        {"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": "inputs/dummy.txt"}},
    ]
    answers = [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": ps_error, "content": ps_text},
        {"type": "tool_result", "tool_use_id": "t2", "is_error": bash_error, "content": "dummy.txt"},
        {"type": "tool_result", "tool_use_id": "t3", "is_error": False, "content": "edited"},
    ]
    lines: list[dict[str, Any]] = [
        {"type": "system", "subtype": "init", "model": "m", "claude_code_version": "9", "session_id": "s"},
        {"type": "assistant", "message": {"role": "assistant", "content": uses}},
        {"type": "user", "message": {"role": "user", "content": answers}},
    ]
    if result:
        lines.append(
            {
                "type": "result",
                "is_error": result_error,
                "permission_denials": [{"tool_name": name, "tool_use_id": "t3", "tool_input": {}} for name in denials],
                "result": "done",
                "session_id": "s",
                "total_cost_usd": 0.01,
            }
        )
    return lines


def good_selftest(fake: FakeClaude, **log_options: Any) -> None:
    fake.configure(
        stdout=selftest_log(**log_options),
        edit={"file": "inputs/dummy.txt", "text": "after\n"},
    )


def selftest(world: World, fake: FakeClaude, out: list[str], **over: Any) -> int:
    kwargs: dict[str, Any] = {
        "model": SELF_TEST_MODEL,
        "trials_root": world.trials_root,
        "claude_cmd": fake.cmd,
        "pwsh": fake.pwsh,
        "timeout_s": 60,
        "out": out.append,
    }
    kwargs.update(over)
    return self_test(**kwargs)


def test_self_test_passes(world: World, fake: FakeClaude) -> None:
    good_selftest(fake)
    out: list[str] = []
    assert selftest(world, fake, out) == 0

    folder = world.trials_root / "selftest-20261101-100000"
    log = world.trials_root / "selftest-20261101-100000.stream.jsonl"
    assert out == ["SELFTEST=pass", f"FOLDER={folder}", f"LOG={log}"]
    assert [p.name for p in folder.rglob("*") if p.is_file()] == ["dummy.txt"]  # the folder is kept
    assert (folder / "inputs" / "dummy.txt").read_text(encoding="utf-8") == "after\n"
    assert log.is_file()

    (call,) = fake.calls()
    argv = call["argv"]
    dummy = folder / "inputs" / "dummy.txt"
    assert argv[:2] == ["-p", SELF_TEST_PROMPT]
    assert argv[argv.index("--model") + 1] == SELF_TEST_MODEL and "--effort" not in argv
    start = argv.index("--allowedTools")
    assert argv[start + 1 : start + 3] == [allow_rule("Edit", dummy), allow_rule("Write", dummy)]
    assert Path(call["cwd"]).samefile(folder)


def test_self_test_runs_through_the_trial_environment(
    world: World, fake: FakeClaude, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    good_selftest(fake)
    assert selftest(world, fake, []) == 0
    env = fake.calls()[0]["env"]
    assert "CLAUDECODE" not in {key.upper() for key in env}
    assert os.path.normcase(env["PATH"].split(os.pathsep)[0]) == os.path.normcase(str(fake.pwsh.parent))


def test_self_test_prompt_is_the_plans_text() -> None:
    assert SELF_TEST_PROMPT == (
        "This is a harness check. Do exactly these three things and nothing else. "
        "1. With the PowerShell tool, run: Get-Location "
        "2. With the Bash tool, run: cd inputs && ls "
        "3. With the Edit tool, change the word before to after in inputs/dummy.txt. "
        "Then reply with the three results."
    )


def test_self_test_fails_on_the_command_line_is_too_long(world: World, fake: FakeClaude) -> None:
    good_selftest(fake, ps_error=True, ps_text="The command line is too long.")
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert out[0] == "SELFTEST=fail"
    reasons = [line for line in out if line.startswith("REASON=")]
    assert any(line.startswith("REASON=powershell: ") for line in reasons)
    assert any(line.startswith("REASON=too-long: ") for line in reasons)
    assert not any(line.startswith("REASON=bash") for line in reasons)
    assert out[-2].startswith("FOLDER=") and out[-1].startswith("LOG=")


def test_self_test_fails_on_a_bash_error(world: World, fake: FakeClaude) -> None:
    good_selftest(fake, bash_error=True)
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert [line.split(":")[0] for line in out if line.startswith("REASON=")] == ["REASON=bash"]


def test_self_test_fails_when_the_edit_was_not_made(world: World, fake: FakeClaude) -> None:
    fake.configure(stdout=selftest_log())
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert any(line.startswith("REASON=edit: dummy.txt reads 'before'") for line in out)


def test_self_test_fails_on_an_edit_denial(world: World, fake: FakeClaude) -> None:
    good_selftest(fake, denials=("Edit",))
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert any(line.startswith("REASON=denial: ") for line in out)


def test_self_test_fails_on_an_error_result(world: World, fake: FakeClaude) -> None:
    good_selftest(fake, result_error=True)
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert "REASON=result: the result line reports is_error" in out


def test_self_test_fails_on_a_missing_result_line(world: World, fake: FakeClaude) -> None:
    good_selftest(fake, result=False)
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert "REASON=result: the log has no result line" in out


def test_self_test_fails_on_a_non_zero_exit(world: World, fake: FakeClaude) -> None:
    fake.configure(
        stdout=selftest_log(), edit={"file": "inputs/dummy.txt", "text": "after\n"}, exit=3
    )
    out: list[str] = []
    assert selftest(world, fake, out) == 1
    assert "REASON=exit: claude exited with code 3" in out


def test_self_test_fails_on_a_timeout(world: World, fake: FakeClaude) -> None:
    fake.configure(
        stdout=selftest_log(), edit={"file": "inputs/dummy.txt", "text": "after\n"}, sleep=60
    )
    out: list[str] = []
    started = time.monotonic()
    assert selftest(world, fake, out, timeout_s=2) == 1
    assert time.monotonic() - started < 40
    assert any(line.startswith("REASON=timeout: ") for line in out)


def test_self_test_refuses_to_reuse_a_folder(world: World, fake: FakeClaude) -> None:
    good_selftest(fake)
    assert selftest(world, fake, []) == 0
    with pytest.raises(ValueError, match="selftest-20261101-100000"):
        selftest(world, fake, [])
    assert len(fake.calls()) == 1


def test_self_test_rejects_a_bad_timeout(world: World, fake: FakeClaude) -> None:
    with pytest.raises(ValueError, match="timeout"):
        selftest(world, fake, [], timeout_s=0)
    assert not world.trials_root.exists()
