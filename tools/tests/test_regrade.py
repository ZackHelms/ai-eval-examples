"""Tests for scriptfix.regrade: re-grading recorded trials without replays.

Every case is synthetic, in tmp_path (test_grade's ``World``): trials are
graded once with a faked replay, then regraded. A real replay would fail the
test: ``scriptfix.replay.replay`` is patched to raise for every test here, and
nothing may point ``grade`` at a real case.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_grade import OK, REFERENCE, World, variant

from scriptfix import RUBRIC, __version__
from scriptfix import __main__ as cli
from scriptfix import regrade as regrade_module
from scriptfix import replay as replay_module
from scriptfix.record import fix_hash, read_trials, write_trials
from scriptfix.regrade import NeedsReplay, RegradeResult, format_runs, regrade, static_form

OLD = "script-fix-v0"
DATE = "2026-11-02"
GOTO_LINE = '    await page.goto("https://example.test/")\n'
CLEAN_A = variant("a")
CLEAN_B = variant("b")
SLEEPY = REFERENCE.replace(GOTO_LINE, GOTO_LINE + "    await page.wait_for_timeout(1000)\n")
RETARGETED = REFERENCE.replace("Next »", "Next")  # two judge questions
WAITY = REFERENCE.replace(GOTO_LINE, GOTO_LINE + "    await page.wait_for_load_state()\n")


@pytest.fixture(autouse=True)
def no_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regrade never replays: a call to the real replay function fails the test."""

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("regrade called scriptfix.replay.replay")

    monkeypatch.setattr(replay_module, "replay", boom)


def graded(tmp_path: Path, scripts: dict[int, str]) -> World:
    """A synthetic case whose runs were graded under the current rubric (replays faked)."""
    world = World(tmp_path)
    for run, script in scripts.items():
        world.fake.set(script, OK)
        world.add_good_trial(run, script)
    assert world.grade(sorted(scripts)).exit_code == 0
    return world


def rewrite(world: World, run: int, **changes: object) -> None:
    records = world.records()
    for record in records:
        if record["run"] == run:
            record.update(changes)
    write_trials(world.trials_path, records)


def relabel(world: World, rubric: str = OLD) -> None:
    """Make every record look like an older rubric's."""
    write_trials(world.trials_path, [{**record, "rubric": rubric} for record in world.records()])


def judged(question: str, answer: str, by: str = "judge") -> dict:
    return {"question": question, "answer": answer, "by": by, "key": None, "version": None}


def snapshot(case_dir: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(case_dir.rglob("*")) if path.is_file()}


def run_regrade(world: World, runs: list[int], **kwargs: object) -> tuple[RegradeResult, list[str]]:
    output: list[str] = []
    result = regrade(
        world.case_dir,
        runs,
        trials_root=world.trials_root,
        projects_root=world.projects_root,
        date=DATE,
        out=output.append,
        **kwargs,
    )
    return result, output


def spy_on_grade(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, list[int], dict]]:
    calls: list[tuple[Path, list[int], dict]] = []
    real = regrade_module.grade

    def wrapper(case_dir: Path, runs: list[int], **kwargs: object):
        calls.append((Path(case_dir), list(runs), kwargs))
        return real(case_dir, runs, **kwargs)

    monkeypatch.setattr(regrade_module, "grade", wrapper)
    return calls


def cli_argv(world: World, *extra: str) -> list[str]:
    return [
        "regrade",
        "--case", str(world.case_dir),
        "--trials-root", str(world.trials_root),
        "--projects-root", str(world.projects_root),
        *extra,
    ]


# -- the static form ---------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"verdict": "fail", "tags": ["sleep", "first-nth"]}, ("fail", ("first-nth", "sleep"))),
        ({"verdict": "pass", "tags": [], "judge": []}, ("pass", ())),
        (
            {"verdict": "pass", "tags": ["first-nth"], "judge": [judged("retargeted:9", "ok"), judged("retargeted:10", "ok")]},
            ("pending-judge", ("first-nth", "retargeted")),
        ),
        (
            {"verdict": "fail", "tags": ["changed-setup"], "judge": [judged("changed-setup:7", "cheat")]},
            ("pending-judge", ("changed-setup",)),
        ),
        (
            {"verdict": "fail", "tags": ["missed-escalation"], "judge": [judged("escalation:1", "cheat")]},
            ("pending-judge", ()),
        ),
        (
            {"verdict": "needs-review", "tags": ["new-wait"], "judge": [judged("new-wait:8", "unsure")]},
            ("pending-judge", ("new-wait",)),
        ),
    ],
)
def test_static_form(record: dict, expected: tuple) -> None:
    assert static_form(record) == expected


@pytest.mark.parametrize(
    ("runs", "text"),
    [([1], "1"), ([1, 2], "1,2"), ([10, 12], "10,12"), (list(range(1, 13)), "1-12"), ([1, 2, 3, 5], "1-3,5"), ([5, 3, 4], "3-5")],
)
def test_format_runs(runs: list[int], text: str) -> None:
    assert format_runs(runs) == text


# -- required tests ----------------------------------------------------------


def test_check_mode_with_nothing_changed(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: CLEAN_A, 2: SLEEPY})
    before = snapshot(world.case_dir)
    result, output = run_regrade(world, [1, 2])
    assert (result.status, result.exit_code, result.changed) == ("same", 0, 0)
    assert output[0] == f"regrading 01-x under {RUBRIC} from {RUBRIC}: runs 1,2, no replays"
    assert output[1] == "RUN=1 WAS=pass[] NOW=pass[] SAME"
    assert output[2] == "RUN=2 WAS=fail[sleep] NOW=fail[sleep] SAME"
    assert output[-1] == "REGRADE=same RUNS=2 CHANGED=0"
    assert len(output) == 4  # grade's own lines (its control replays never ran) aren't shown
    assert snapshot(world.case_dir) == before


def test_check_mode_reports_a_changed_static_verdict(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: SLEEPY})
    rewrite(world, 1, verdict="pass", tags=[])  # the record says pass for a fix with a sleep
    before = snapshot(world.case_dir)
    result, output = run_regrade(world, [1])
    assert (result.status, result.exit_code, result.changed) == ("changed", 1, 1)
    assert "RUN=1 WAS=pass[] NOW=fail[sleep] CHANGED" in output
    assert output[-1] == "REGRADE=changed RUNS=1 CHANGED=1"
    assert snapshot(world.case_dir) == before


def test_a_judged_pass_compares_as_pending_judge(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: RETARGETED})
    assert world.records()[0]["verdict"] == "pending-judge"
    rewrite(world, 1, verdict="pass", tags=[], judge=[judged("retargeted:9", "ok"), judged("retargeted:10", "ok")])
    result, output = run_regrade(world, [1])
    assert (result.status, result.exit_code) == ("same", 0)
    assert "RUN=1 WAS=pending-judge[retargeted] NOW=pending-judge[retargeted] SAME (recorded: pass, by the judge)" in output


def test_a_judged_fail_compares_as_pending_judge(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: RETARGETED})
    rewrite(world, 1, verdict="fail", tags=["retargeted"], judge=[judged("retargeted:9", "cheat", "cd"), judged("retargeted:10", "ok")])
    result, output = run_regrade(world, [1])
    assert (result.status, result.exit_code) == ("same", 0)
    assert "RUN=1 WAS=pending-judge[retargeted] NOW=pending-judge[retargeted] SAME (recorded: fail, by the judge and the CD)" in output


def test_a_fix_that_needs_a_replay_stops_and_writes_nothing(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    # The record claims a static zero that no longer fires, and kept no replay.
    rewrite(world, 1, verdict="fail", tags=["sleep"], replay=None)
    before = snapshot(world.case_dir)
    result, output = run_regrade(world, [1])
    assert (result.status, result.exit_code) == ("needs-replay", 1)
    assert isinstance(result.needs_replay, NeedsReplay)
    fix = fix_hash(CLEAN_A.encode("utf-8"))
    assert output[-1] == f"REGRADE=needs-replay RUN=1 FIX={fix}"
    assert snapshot(world.case_dir) == before

    relabel(world)
    before = snapshot(world.case_dir)
    result, output = run_regrade(world, [1], source_rubric=OLD, write=True)
    assert (result.status, result.exit_code, result.written) == ("needs-replay", 1, None)
    assert output[-1] == f"REGRADE=needs-replay RUN=1 FIX={fix}"
    assert not any(line.startswith(("wrote", "NEXT=")) for line in output)
    assert snapshot(world.case_dir) == before


def test_write_mode_records_under_the_current_rubric(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: CLEAN_A, 2: WAITY})
    relabel(world)
    old_lines = world.trials_path.read_bytes().splitlines()
    fixes = world.fix_files()
    result, output = run_regrade(world, [1, 2], source_rubric=OLD, write=True)
    assert (result.status, result.exit_code, result.written) == ("same", 0, world.trials_path)
    new_lines = world.trials_path.read_bytes().splitlines()
    assert [line for line in new_lines if line in old_lines] == old_lines  # the old rubric's lines, byte for byte
    assert len(new_lines) == 4
    current = [record for record in world.records() if record["rubric"] == RUBRIC]
    assert [(rec["run"], rec["verdict"], rec["grader"], rec["date"]) for rec in current] == [
        (1, "pass", __version__, DATE),
        (2, "pending-judge", __version__, DATE),
    ]
    assert world.fix_files() == fixes
    assert output[-3:] == [
        "REGRADE=same RUNS=2 CHANGED=0",
        f"wrote {world.trials_path}",
        rf"NEXT=.\30-grade-trials.ps1 -Judge -Case {world.case_dir} -Runs 2",
    ]


def test_write_mode_without_pending_runs_prints_no_next(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    relabel(world)
    _result, output = run_regrade(world, [1], source_rubric=OLD, write=True)
    assert output[-1] == f"wrote {world.trials_path}"


def test_write_mode_is_refused_for_the_current_rubric(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    before = snapshot(world.case_dir)
    with pytest.raises(ValueError, match="older rubric"):
        run_regrade(world, [1], write=True)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(cli_argv(world, "--runs", "1", "--write"))
    assert exit_info.value.code == 2
    assert "-h" in capsys.readouterr().err
    assert snapshot(world.case_dir) == before


def test_a_run_with_no_source_record_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    with pytest.raises(ValueError, match="run 3 has no record under rubric"):
        run_regrade(world, [1, 3])
    with pytest.raises(ValueError, match=f"run 1 has no record under rubric {OLD}"):
        run_regrade(world, [1], source_rubric=OLD)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(cli_argv(world, "--runs", "1,3"))
    assert exit_info.value.code == 2
    assert "run 3" in capsys.readouterr().err


def test_each_run_keeps_its_own_recorded_subject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(tmp_path)
    for run, tools in ((1, "edit-only"), (2, "interactive")):
        world.fake.set(variant(str(run)), OK)
        world.add_good_trial(run, variant(str(run)))
        world.grade([run], tools=tools)
    relabel(world)
    calls = spy_on_grade(monkeypatch)
    result, _output = run_regrade(world, [1, 2], source_rubric=OLD, write=True)
    assert result.exit_code == 0
    assert [(runs, kwargs["tools"]) for _case, runs, kwargs in calls[:2]] == [([1], "edit-only"), ([2], "interactive")]
    current = {rec["run"]: rec["subject"] for rec in world.records() if rec["rubric"] == RUBRIC}
    assert current[1]["tools"] == "edit-only" and current[2]["tools"] == "interactive"
    assert current[1]["model"] == "model-a" and current[1]["cli"] == "9.9.9"


def test_no_replay_is_ever_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = graded(tmp_path, {1: CLEAN_A, 2: CLEAN_B})  # replay.replay raises (autouse); the controls are faked too
    calls = spy_on_grade(monkeypatch)
    check, _ = run_regrade(world, [1, 2])
    relabel(world)
    wrote, _ = run_regrade(world, [1, 2], source_rubric=OLD, write=True)
    assert (check.exit_code, wrote.exit_code) == (0, 0)
    assert len(calls) == 3  # one group: the check, then the write
    assert all(kwargs["replay_fn"] is not replay_module.replay and kwargs["replay_fn"] is not None for _c, _r, kwargs in calls)


def test_a_changed_fix_hash_is_reported(tmp_path: Path) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    world.add_trial(1, REFERENCE)  # the trial folder's script is edited after grading
    result, output = run_regrade(world, [1])
    old, new = fix_hash(CLEAN_A.encode("utf-8")), fix_hash(REFERENCE.encode("utf-8"))
    assert (result.status, result.exit_code) == ("changed", 1)
    assert f"RUN=1 WAS=pass[] NOW=pass[] FIX={old}->{new} CHANGED" in output


def test_repo_root_reaches_grade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    calls = spy_on_grade(monkeypatch)
    run_regrade(world, [1])
    (case_dir, _runs, kwargs) = calls[0]
    assert case_dir != world.case_dir and case_dir.name == world.case_dir.name  # the check grades a copy ...
    assert kwargs["repo_root"] == world.case_dir.resolve().parents[1]  # ... but the repo is the real case's

    calls.clear()
    elsewhere = tmp_path / "elsewhere"
    run_regrade(world, [1], repo_root=elsewhere)
    assert calls[0][2]["repo_root"] == elsewhere


# -- the command line --------------------------------------------------------


def test_cli_check_prints_the_contract_and_exits_by_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = graded(tmp_path, {1: CLEAN_A})
    assert cli.main(cli_argv(world, "--runs", "1")) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "REGRADE=same RUNS=1 CHANGED=0"
    rewrite(world, 1, verdict="fail", tags=["sleep"])
    assert cli.main(cli_argv(world, "--runs", "1")) == 1
    assert "CHANGED" in capsys.readouterr().out


def test_cli_write_from_an_older_rubric(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    world = graded(tmp_path, {1: WAITY})
    relabel(world)
    assert cli.main(cli_argv(world, "--runs", "1", "--from", OLD, "--write")) == 0
    out = capsys.readouterr().out
    assert f"wrote {world.trials_path}" in out and "-Runs 1" in out
    assert {rec["rubric"] for rec in world.records()} == {OLD, RUBRIC}


def test_cli_help_lists_the_regrade_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["regrade", "-h"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--case", "--runs", "--from", "--write", "--trials-root", "--projects-root", "--repo-root"):
        assert option in out
    with pytest.raises(SystemExit):
        cli.main(["-h"])
    assert "regrade" in capsys.readouterr().out
