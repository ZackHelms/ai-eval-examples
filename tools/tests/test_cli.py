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
