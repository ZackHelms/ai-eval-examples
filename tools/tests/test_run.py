"""Tests for scriptfix.run: run numbers, trial folders, the child's environment, argv and sidecar."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from scriptfix import run
from scriptfix.run import (
    EFFORTS,
    STRIP_NAMES,
    allow_rule,
    check_free,
    claude_argv,
    next_runs,
    prepare_trial,
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
