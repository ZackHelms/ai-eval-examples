"""Tests for the command line: run parsing, help, usage errors, wiring.

The end-to-end tests monkeypatch scriptfix.replay.replay, so no browser or
site is involved. They reuse test_grade's synthetic case builder.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_grade import REFERENCE, World, failed_at
from test_report import rec

from scriptfix import __main__ as cli
from scriptfix import replay as replay_module
from scriptfix.grade import parse_runs
from scriptfix.record import write_trials


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("1-12", list(range(1, 13))),
        ("1,3,5-7", [1, 3, 5, 6, 7]),
        ("7", [7]),
        ("5-5", [5]),
        (" 3 , 1 ", [1, 3]),
        ("2,2,1-2", [1, 2]),
    ],
)
def test_parse_runs_accepts(spec: str, expected: list[int]) -> None:
    assert parse_runs(spec) == expected


@pytest.mark.parametrize("spec", ["", "  ", "1,,2", "5-3", "a", "1-x", "1-", "-3", "0", "0-2", "1.5"])
def test_parse_runs_rejects(spec: str) -> None:
    with pytest.raises(ValueError, match="--runs"):
        parse_runs(spec)


def test_help_exits_zero_and_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["-h"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "grade" in out and "report" in out
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["grade", "--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--case", "--runs", "--trials-root", "--projects-root", "--effort", "--context", "--tools", "--timeout"):
        assert option in out


@pytest.mark.parametrize(
    "argv",
    [
        ["--bogus"],
        ["grade", "--bogus"],
        ["report", "--bogus"],
        ["grade", "--case", "x"],  # --runs is required
        ["grade", "--case", "x", "--runs", "5-3"],
        ["grade", "--case", "x", "--runs", "a"],
        ["make-case", "--bogus"],
        ["make-case"],  # --case and --python are required
        ["run", "--bogus"],
        ["run", "--effort", "ludicrous"],
        ["run", "--count", "1", "--runs", "1"],  # mutually exclusive
        ["run", "--count", "x"],
        ["run", "--context", "bundle"],
        ["run", "--tools", "all"],
        ["run", "--runs", "5-3"],
        [],
    ],
)
def test_usage_errors_exit_two_with_a_pointer_to_help(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2
    assert "-h" in capsys.readouterr().err


def test_make_case_help_lists_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["make-case", "-h"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--case", "--python", "--timeout", "--dry-run"):
        assert option in out
    with pytest.raises(SystemExit):
        cli.main(["-h"])
    assert "make-case" in capsys.readouterr().out


def test_make_case_usage_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case = tmp_path / "02-x"
    case.mkdir()
    python = tmp_path / "python.exe"
    for argv in (
        ["make-case", "--case", str(tmp_path / "nope"), "--python", str(python)],  # no such directory
        ["make-case", "--case", str(case), "--python", str(python), "--timeout", "0"],
        ["make-case", "--case", str(case), "--python", str(python)],  # python missing, not a dry run
        ["make-case", "--case", str(case), "--python", str(python), "--dry-run"],  # no case.toml
    ):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
        assert exit_info.value.code == 2
        assert "-h" in capsys.readouterr().err


def test_make_case_wires_the_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_make_case(case_dir: Path, **kwargs: object) -> int:
        seen["case"] = case_dir
        seen.update(kwargs)
        return 1

    monkeypatch.setattr(cli, "make_case", fake_make_case)
    case = tmp_path / "02-x"
    case.mkdir()
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    code = cli.main(["make-case", "--case", str(case), "--python", str(python), "--timeout", "30"])
    assert code == 1  # make_case's exit code is passed through
    assert seen["case"] == case and seen["python"] == python
    assert seen["timeout_s"] == 30 and seen["dry_run"] is False
    assert seen["repo_root"] == Path(cli.__file__).resolve().parents[2]
    # --dry-run does not check --python.
    code = cli.main(["make-case", "--case", str(case), "--python", str(tmp_path / "gone.exe"), "--dry-run"])
    assert code == 1 and seen["dry_run"] is True


def test_run_help_lists_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["run", "-h"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for option in (
        "--case", "--model", "--count", "--runs", "--effort", "--context", "--tools",
        "--trials-root", "--claude", "--pwsh", "--timeout", "--dry-run", "--self-test",
    ):  # fmt: skip
        assert option in out
    with pytest.raises(SystemExit):
        cli.main(["-h"])
    assert "{grade,calibrate,report,make-case,run}" in capsys.readouterr().out


class RunWorld:
    """Real files for --case, --claude and --pwsh, and a recorder in place of the launcher."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.case = tmp_path / "evals" / "02-x"
        self.case.mkdir(parents=True)
        self.claude = tmp_path / "claude.exe"
        self.claude.write_bytes(b"")
        self.pwsh = tmp_path / "pwsh.exe"
        self.pwsh.write_bytes(b"")
        self.root = tmp_path / "trials"
        self.trials: dict[str, object] = {}
        self.selftests: dict[str, object] = {}
        self.result = 0
        monkeypatch.setattr(cli, "run_trials", self._run_trials)
        monkeypatch.setattr(cli, "self_test", self._self_test)

    def _run_trials(self, case_dir: Path, **kwargs: object) -> int:
        self.trials.clear()
        self.trials.update(kwargs, case=case_dir)
        return self.result

    def _self_test(self, **kwargs: object) -> int:
        self.selftests.clear()
        self.selftests.update(kwargs)
        return self.result

    def argv(self, *extra: str) -> list[str]:
        return ["run", "--claude", str(self.claude), "--pwsh", str(self.pwsh), "--trials-root", str(self.root), *extra]


@pytest.fixture
def run_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunWorld:
    return RunWorld(tmp_path, monkeypatch)


def test_run_wires_the_arguments(run_world: RunWorld) -> None:
    code = cli.main(run_world.argv("--case", str(run_world.case), "--model", "claude-haiku-5-5", "--count", "3"))
    assert code == 0
    seen = run_world.trials
    assert seen["case"] == run_world.case and seen["model"] == "claude-haiku-5-5"
    assert seen["count"] == 3 and seen["runs"] is None
    assert seen["effort"] == "default" and seen["context"] == "none" and seen["tools"] == "edit-only"
    assert seen["timeout_s"] == 1800 and seen["dry_run"] is False
    assert seen["trials_root"] == run_world.root
    assert seen["claude_cmd"] == [str(run_world.claude)] and seen["pwsh"] == run_world.pwsh
    assert run_world.selftests == {}


def test_run_wires_runs_effort_timeout_and_dry_run(run_world: RunWorld) -> None:
    code = cli.main(
        run_world.argv(
            "--case", str(run_world.case), "--model", "m", "--runs", "1,3-4",
            "--effort", "high", "--timeout", "60", "--dry-run",
        )
    )  # fmt: skip
    assert code == 0
    seen = run_world.trials
    assert seen["runs"] == [1, 3, 4] and seen["count"] is None
    assert seen["effort"] == "high" and seen["timeout_s"] == 60 and seen["dry_run"] is True


def test_run_passes_the_exit_code_through(run_world: RunWorld) -> None:
    run_world.result = 1
    assert cli.main(run_world.argv("--case", str(run_world.case), "--model", "m", "--count", "1")) == 1


def test_run_self_test_wiring_and_defaults(run_world: RunWorld) -> None:
    run_world.result = 1
    assert cli.main(run_world.argv("--self-test")) == 1
    seen = run_world.selftests
    assert seen["model"] == "claude-haiku-5-5" and seen["timeout_s"] == 600
    assert seen["trials_root"] == run_world.root
    assert seen["claude_cmd"] == [str(run_world.claude)] and seen["pwsh"] == run_world.pwsh
    assert run_world.trials == {}
    cli.main(run_world.argv("--self-test", "--model", "other", "--timeout", "30"))
    assert run_world.selftests["model"] == "other" and run_world.selftests["timeout_s"] == 30


@pytest.mark.parametrize(
    "extra",
    [
        [],  # no --case
        ["--case", "{case}"],  # no --model
        ["--case", "{case}", "--model", "m"],  # neither --count nor --runs
        ["--case", "{case}/nope", "--model", "m", "--count", "1"],  # not a directory
        ["--case", "{case}", "--model", "m", "--count", "1", "--timeout", "0"],
        ["--self-test", "--case", "{case}"],
        ["--self-test", "--count", "1"],
        ["--self-test", "--runs", "1"],
        ["--self-test", "--dry-run"],
        ["--self-test", "--timeout", "0"],
    ],
)
def test_run_usage_errors(run_world: RunWorld, extra: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    args = [part.replace("{case}", str(run_world.case)) for part in extra]
    with pytest.raises(SystemExit) as exit_info:
        cli.main(run_world.argv(*args))
    assert exit_info.value.code == 2
    assert "-h" in capsys.readouterr().err
    assert run_world.trials == {} and run_world.selftests == {}


def test_run_rejects_a_missing_claude_or_pwsh_or_the_alias(run_world: RunWorld, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    alias = tmp_path / "Microsoft" / "WindowsApps" / "pwsh.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"")
    base = ["--case", str(run_world.case), "--model", "m", "--count", "1"]
    for flag, bad, message in (
        ("--claude", tmp_path / "gone.exe", "--claude"),
        ("--pwsh", tmp_path / "gone.exe", "--pwsh"),
        ("--pwsh", alias, "alias"),
    ):
        argv = run_world.argv(*base)
        argv[argv.index(flag) + 1] = str(bad)
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
        assert exit_info.value.code == 2
        assert message in capsys.readouterr().err
    assert run_world.trials == {}


def test_run_turns_a_launcher_value_error_into_a_usage_error(
    run_world: RunWorld, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(case_dir: Path, **kwargs: object) -> int:
        raise ValueError("run 3 of case 02 already exists: somewhere")

    monkeypatch.setattr(cli, "run_trials", refuse)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(run_world.argv("--case", str(run_world.case), "--model", "m", "--runs", "3"))
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "already exists" in err and "-h" in err


def test_missing_case_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["grade", "--case", str(tmp_path / "nope"), "--runs", "1"])
    assert exit_info.value.code == 2


def test_grade_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    world = World(tmp_path)
    fix = REFERENCE + "# edited\n"
    world.add_good_trial(1, fix)
    monkeypatch.setattr(replay_module, "replay", world.fake)
    code = cli.main(
        [
            "grade",
            "--case", str(world.case_dir),
            "--runs", "1",
            "--trials-root", str(world.trials_root),
            "--projects-root", str(world.projects_root),
            "--effort", "high",
            "--timeout", "30",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "run 1: pass" in out and "replays run: 4" in out
    (record,) = world.records()
    assert record["verdict"] == "pass" and record["subject"]["effort"] == "high"


def test_grade_exits_one_when_a_control_is_surprising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    world = World(tmp_path)
    world.fake.set(REFERENCE, failed_at(9))
    world.add_good_trial(1, REFERENCE + "# a\n")
    monkeypatch.setattr(replay_module, "replay", world.fake)
    code = cli.main(
        ["grade", "--case", str(world.case_dir), "--runs", "1", "--trials-root", str(world.trials_root), "--projects-root", str(world.projects_root)]
    )
    assert code == 1
    assert "control failed" in capsys.readouterr().out


def test_console_output_survives_a_non_utf8_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    # An ascii stdout would raise on the guillemet if main() did not reconfigure it.
    cli.main(["report", "--case", str(tmp_path)])  # no trials: prints a plain line
    print("»")
    stream.flush()


def test_report_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case = tmp_path / "evals" / "01-x"
    write_trials(case / "grading" / "trials.jsonl", [rec(1, "pass"), rec(2, "fail", ["not-fixed"])])
    assert cli.main(["report", "--case", str(case)]) == 0
    out = capsys.readouterr().out
    assert "01-x" in out and "1/2" in out
    empty = tmp_path / "evals" / "02-y"
    empty.mkdir(parents=True)
    assert cli.main(["report", "--case", str(empty)]) == 0
    assert "no trials recorded" in capsys.readouterr().out
