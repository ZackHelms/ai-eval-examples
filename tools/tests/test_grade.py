"""Tests for scriptfix.grade: lookup, verdict paths, controls and dedupe.

Everything lives in tmp_path: a tiny synthetic case, trial folders and
synthetic stream-json transcripts. Replays are faked; no browser, no site,
and the real home folder is never read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath

from scriptfix.grade import GradeResult, grade, locate_trial, mangle_path
from scriptfix.record import fix_hash, read_trials, write_trials
from scriptfix.replay import ReplayResult

REFERENCE = '''import asyncio
from playwright.async_api import Playwright, async_playwright, expect


async def run(playwright: Playwright) -> None:
    browser = await playwright.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto("https://example.test/")
    await expect(page.get_by_role("link", name="Next \u00bb")).to_be_visible()
    await page.get_by_role("link", name="Next \u00bb").click()
    await browser.close()


async def main() -> None:
    async with async_playwright() as playwright:
        await run(playwright)


asyncio.run(main())
'''
INPUT = REFERENCE.replace("Next \u00bb", "Next >")
FAILS_AT = INPUT.splitlines().index('    await expect(page.get_by_role("link", name="Next >")).to_be_visible()') + 1

OK = ReplayResult(exit_code=0, timed_out=False, failing_line=None, output="")


def variant(tag: str) -> str:
    """The reference plus an unrelated assignment: a different program, no findings."""
    return REFERENCE + f"\nnote_{tag} = 1\n"


def failed_at(line: int | None) -> ReplayResult:
    return ReplayResult(exit_code=1, timed_out=False, failing_line=line, output="Traceback\nboom\n")


# -- synthetic transcripts ---------------------------------------------------


def stream_log(*calls: tuple[str, dict], is_error: bool = False, result: bool = True) -> list[dict]:
    """A clean stream-json log whose assistant makes the given (tool, input) calls."""
    items: list[dict] = [{"type": "text", "text": "working"}]
    for number, (name, tool_input) in enumerate(calls, start=1):
        items.append({"type": "tool_use", "id": f"t{number}", "name": name, "input": tool_input})
    lines: list[dict] = [
        {
            "type": "system",
            "subtype": "init",
            "model": "model-a",
            "claude_code_version": "9.9.9",
            "session_id": "sess-1",
        },
        {"type": "assistant", "message": {"role": "assistant", "content": items}},
    ]
    if result:
        lines.append(
            {
                "type": "result",
                "is_error": is_error,
                "api_error_status": None,
                "permission_denials": [],
                "result": "done",
                "session_id": "sess-1",
                "total_cost_usd": 0.25,
            }
        )
    return lines


def edit_call() -> tuple[str, dict]:
    return ("Edit", {"file_path": "C:/trials/01-run1/inputs/script.py"})


class FakeReplay:
    """A stand-in for scriptfix.replay.replay, keyed by the script's bytes."""

    def __init__(self) -> None:
        self.results: dict[bytes, ReplayResult | list[ReplayResult]] = {}
        self.calls: list[Path] = []

    def set(self, text: str, result: ReplayResult | list[ReplayResult]) -> None:
        self.results[text.encode("utf-8")] = result

    def __call__(self, script: Path, *, python: Path, timeout_s: int = 120) -> ReplayResult:
        data = Path(script).read_bytes()
        self.calls.append(Path(script))
        value = self.results[data]  # KeyError = an unexpected replay
        if isinstance(value, list):
            return value.pop(0)
        return value


class World:
    """A synthetic case plus its trials and a fake replay."""

    def __init__(self, tmp_path: Path, expected: str = "fix", reference: str = REFERENCE, input_: str = INPUT) -> None:
        self.case_dir = tmp_path / "repo" / "evals" / "01-x"
        grading = self.case_dir / "grading"
        (grading / "reference").mkdir(parents=True)
        (self.case_dir / "inputs").mkdir(parents=True)
        (grading / "case.toml").write_bytes(
            (
                'rubric = "script-fix-v0"\n'
                f'expected = "{expected}"\n'
                'issue = ["locator-text"]\n'
                'origin = "handmade"\n'
                'defect = "a link name is wrong"\n'
                f"fails_at = {FAILS_AT}\n"
                'target = "https://example.test/"\n'
            ).encode("utf-8")
        )
        (grading / "reference" / "script.py").write_bytes(reference.encode("utf-8"))
        (self.case_dir / "inputs" / "script.py").write_bytes(input_.encode("utf-8"))
        self.trials_root = tmp_path / "trials"
        self.projects_root = tmp_path / "projects"
        self.fake = FakeReplay()
        self.fake.set(reference, OK)
        self.fake.set(input_, failed_at(FAILS_AT))

    @property
    def trials_path(self) -> Path:
        return self.case_dir / "grading" / "trials.jsonl"

    def add_trial(self, run: int, script: str | None, lines: list[dict] | None = None) -> None:
        folder = self.trials_root / f"01-run{run}"
        (folder / "inputs").mkdir(parents=True, exist_ok=True)
        if script is not None:
            (folder / "inputs" / "script.py").write_bytes(script.encode("utf-8"))
        if lines is not None:
            log = self.trials_root / f"01-run{run}.stream.jsonl"
            log.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    def add_good_trial(self, run: int, script: str | None, *calls: tuple[str, dict]) -> None:
        self.add_trial(run, script, stream_log(edit_call(), *calls))

    def grade(self, runs: list[int], **kwargs) -> GradeResult:
        output: list[str] = []
        self.output = output
        return grade(
            self.case_dir,
            runs,
            trials_root=self.trials_root,
            projects_root=self.projects_root,
            date="2026-10-31",
            replay_fn=self.fake,
            out=output.append,
            **kwargs,
        )

    def seed_prior_record(self) -> bytes:
        """Write a prior valid verdict for run 1 and return the file's bytes."""
        prior = {"run": 1, "rubric": "script-fix-v0", "verdict": "pass", "tags": [], "fix": "abc"}
        write_trials(self.trials_path, [prior])
        return self.trials_path.read_bytes()

    def fix_files(self) -> list[Path]:
        return sorted((self.case_dir / "grading" / "fixes").glob("*.py"))

    def records(self) -> list[dict]:
        return read_trials(self.trials_path)

    def trial_replays(self) -> list[Path]:
        return [call for call in self.fake.calls if self.trials_root in call.parents]


def only(result: GradeResult):
    (outcome,) = result.outcomes
    return outcome


# -- lookup ------------------------------------------------------------------


def test_mangle_path_example() -> None:
    expected = "C--Users-zmhel-eval-trials-01-run1"
    assert mangle_path(r"C:\Users\zmhel\eval-trials\01-run1") == expected
    assert mangle_path(PureWindowsPath(r"C:\Users\zmhel\eval-trials\01-run1")) == expected


def test_locate_prefers_the_stream_log(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE, stream_log())
    files = locate_trial("01", 1, world.trials_root, world.projects_root)
    assert files.transcript == world.trials_root / "01-run1.stream.jsonl"
    assert files.script == files.folder / "inputs" / "script.py"


def test_locate_falls_back_to_the_newest_session_file_not_recursively(tmp_path: Path) -> None:
    trials_root, projects_root = tmp_path / "trials", tmp_path / "projects"
    folder = Path(os.path.abspath(trials_root / "01-run2"))
    sessions = projects_root / mangle_path(folder)
    (sessions / "sess-dir").mkdir(parents=True)
    old, new = sessions / "old.jsonl", sessions / "new.jsonl"
    deep = sessions / "sess-dir" / "deep.jsonl"
    for path, stamp in ((old, 1_000_000), (new, 2_000_000), (deep, 3_000_000)):
        path.write_text("{}\n", encoding="utf-8")
        os.utime(path, (stamp, stamp))
    assert locate_trial("01", 2, trials_root, projects_root).transcript == new


def test_locate_with_no_transcript(tmp_path: Path) -> None:
    files = locate_trial("01", 3, tmp_path / "trials", tmp_path / "projects")
    assert files.transcript is None


def test_session_transcript_is_used_for_grading(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE + "# tidy\n", None)
    folder = Path(os.path.abspath(world.trials_root / "01-run1"))
    sessions = world.projects_root / mangle_path(folder)
    sessions.mkdir(parents=True)
    assistant = {
        "type": "assistant",
        "version": "8.8.8",
        "sessionId": "s-9",
        "message": {"model": "model-b", "content": [{"type": "tool_use", "id": "t1", "name": "Edit", "input": {}}]},
    }
    (sessions / "s-9.jsonl").write_text(json.dumps(assistant) + "\n", encoding="utf-8")
    result = world.grade([1], effort="high", tools="interactive")
    assert only(result).verdict == "pass"
    (rec,) = world.records()
    assert rec["subject"] == {"model": "model-b", "effort": "high", "context": "none", "tools": "interactive", "cli": "8.8.8"}
    assert rec["session"] == "s-9"


# -- verdict paths -----------------------------------------------------------


def test_invalid_when_transcript_missing(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE, None)
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",))
    assert "missing transcript" in outcome.detail
    assert world.trial_replays() == []


def test_invalid_when_script_missing(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, None, stream_log(edit_call()))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",))
    assert "missing script" in outcome.detail
    (rec,) = world.records()
    assert rec["fix"] is None and rec["replay"] is None
    assert not (world.case_dir / "grading" / "fixes").exists()


def test_invalid_when_result_line_is_error(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE, stream_log(edit_call(), is_error=True))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",))
    assert world.trial_replays() == []


def test_invalid_records_only_its_invalid_tags_even_with_tried_to_run(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE, stream_log(edit_call(), ("Bash", {"command": "python inputs/script.py"}), is_error=True))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",))


def test_fair_play_zero_fails_with_answer_key(tmp_path: Path) -> None:
    world = World(tmp_path)
    read = ("Read", {"file_path": r"D:\gitrepos\ai-eval-examples\evals\01-x\grading\rubric.md"})
    world.add_trial(1, REFERENCE + "# peeked\n", stream_log(read, edit_call()))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("answer-key",))
    assert world.trial_replays() == []


def test_searching_above_the_cases_repo_is_answer_key_by_default(tmp_path: Path) -> None:
    # The case is <tmp>/repo/evals/01-x, so the repo is <tmp>/repo and <tmp> is above it.
    world = World(tmp_path)
    above = str(world.case_dir.resolve().parents[2])
    grep = ("Grep", {"pattern": "rubric", "path": above})
    world.add_trial(1, REFERENCE + "# peeked\n", stream_log(grep, edit_call()))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("answer-key",))
    assert outcome.detail.startswith("searched above the repo: ")
    assert world.trial_replays() == []


def test_the_case_repo_itself_and_its_neighbours_are_not_above_it(tmp_path: Path) -> None:
    world = World(tmp_path)
    repo = world.case_dir.resolve().parents[1]
    calls = [
        ("Grep", {"pattern": "rubric", "path": str(repo)}),  # the repo, not an ancestor
        ("Grep", {"pattern": "rubric", "path": str(world.trials_root)}),  # a sibling folder
    ]
    world.add_trial(1, REFERENCE, stream_log(edit_call(), *calls))
    assert "answer-key" not in only(world.grade([1])).tags


def test_an_explicit_repo_root_reaches_the_fair_play_check(tmp_path: Path) -> None:
    world = World(tmp_path)
    elsewhere = tmp_path / "other"
    grep = ("Grep", {"pattern": "rubric", "path": str(elsewhere.resolve())})
    world.add_trial(1, REFERENCE + "# peeked\n", stream_log(grep, edit_call()))
    world.fake.set(REFERENCE + "# peeked\n", OK)
    # The default repo is <tmp>/repo, so <tmp>/other is not above it ...
    assert "answer-key" not in only(world.grade([1])).tags
    # ... but it is above an explicit root inside it.
    outcome = only(world.grade([1], repo_root=elsewhere / "repo"))
    assert (outcome.verdict, outcome.tags) == ("fail", ("answer-key",))


def test_unparsable_script_is_a_syntax_error(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, "def (:\n")
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("syntax-error",))
    assert world.trial_replays() == []
    assert (world.case_dir / "grading" / "fixes" / f"{outcome.fix}.py").read_bytes() == b"def (:\n"


def test_unchanged_script_is_no_edit(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, INPUT + "# looked at it\n")
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("no-edit",))
    assert world.trial_replays() == []


def test_static_zero_fails_without_replaying(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE.replace("    await page.goto", "    await asyncio.sleep(2)\n    await page.goto"))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("sleep",))
    assert world.trial_replays() == []


def test_replay_failing_at_the_same_line_is_not_fixed(tmp_path: Path) -> None:
    world = World(tmp_path)
    fix = variant("a")
    world.fake.set(fix, failed_at(FAILS_AT))
    world.add_good_trial(1, fix)
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("fail", ("not-fixed",))
    (rec,) = world.records()
    assert rec["replay"] == {"exit_code": 1, "failing_line": FAILS_AT, "timed_out": False}


def test_replay_failing_elsewhere_or_timing_out_is_a_new_failure(tmp_path: Path) -> None:
    world = World(tmp_path)
    elsewhere, hung = variant("a"), variant("b")
    world.fake.set(elsewhere, failed_at(FAILS_AT + 1))
    world.fake.set(hung, ReplayResult(exit_code=None, timed_out=True, failing_line=None, output=""))
    world.add_good_trial(1, elsewhere)
    world.add_good_trial(2, hung)
    first, second = world.grade([1, 2]).outcomes
    assert (first.verdict, first.tags) == ("fail", ("new-failure",))
    assert (second.verdict, second.tags) == ("fail", ("new-failure",))
    assert world.records()[1]["replay"] == {"exit_code": None, "failing_line": None, "timed_out": True}


def test_retargeted_locator_is_pending_judge(tmp_path: Path) -> None:
    world = World(tmp_path)
    fix = REFERENCE.replace("Next \u00bb", "Next")
    world.fake.set(fix, OK)
    world.add_good_trial(1, fix)
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("pending-judge", ("retargeted",))
    assert world.trial_replays() == [world.trials_root / "01-run1" / "inputs" / "script.py"]


def test_pass_records_info_and_smell_tags(tmp_path: Path) -> None:
    world = World(tmp_path)
    extra = '    await expect(page.get_by_role("heading", name="Title")).to_be_visible()\n'
    fix = REFERENCE.replace('    await page.get_by_role("link", name="Next \u00bb").click()', extra + '    await page.get_by_role("link", name="Next \u00bb").click()')
    world.fake.set(fix, OK)
    world.add_good_trial(1, fix, ("Bash", {"command": "python inputs/script.py"}))
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("pass", ("added-assertion", "tried-to-run"))
    (rec,) = world.records()
    assert rec["judge"] == [] and rec["cost_usd"] == 0.25 and rec["session"] == "sess-1"
    assert rec["subject"] == {"model": "model-a", "effort": "default", "context": "none", "tools": "edit-only", "cli": "9.9.9"}
    assert (rec["date"], rec["grader"], rec["rubric"], rec["run"]) == ("2026-10-31", "0.1.0", "script-fix-v0", 1)
    assert rec["replay"] == {"exit_code": 0, "failing_line": None, "timed_out": False}


def test_judge_tags_are_dropped_from_a_fail(tmp_path: Path) -> None:
    # A retargeted locator that then fails the replay is a fail without the judge tag.
    world = World(tmp_path)
    fix = REFERENCE.replace("Next \u00bb", "Next")
    world.fake.set(fix, failed_at(FAILS_AT))
    world.add_good_trial(1, fix)
    assert only(world.grade([1])).tags == ("not-fixed",)


def test_escalate_case_is_pending_judge_and_never_replays_a_trial(tmp_path: Path) -> None:
    reference = INPUT.replace(
        '    await expect(page.get_by_role("link", name="Next >")).to_be_visible()\n'
        '    await page.get_by_role("link", name="Next >").click()\n',
        "",
    )
    world = World(tmp_path, expected="escalate", reference=reference)
    world.add_good_trial(1, INPUT + "# left alone\n")  # kept as is: allowed in an escalate case
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("pending-judge", ())
    assert world.trial_replays() == []
    assert outcome.replay is None


# -- records -----------------------------------------------------------------


def test_regrading_replaces_the_line_and_keeps_other_rubrics(tmp_path: Path) -> None:
    world = World(tmp_path)
    other = {"run": 1, "rubric": "other-rubric", "verdict": "pass"}
    keep = {"run": 2, "rubric": "script-fix-v0", "verdict": "fail", "tags": ["old"]}
    write_trials(world.trials_path, [other, keep])
    world.add_trial(1, REFERENCE, None)  # invalid first time
    world.grade([1])
    assert [(r["run"], r["rubric"], r["verdict"]) for r in world.records()] == [
        (1, "other-rubric", "pass"),
        (1, "script-fix-v0", "invalid"),
        (2, "script-fix-v0", "fail"),
    ]
    world.add_good_trial(1, REFERENCE + "# redo\n")
    world.grade([1])
    rows = [(r["run"], r["rubric"], r["verdict"]) for r in world.records()]
    assert rows == [(1, "other-rubric", "pass"), (1, "script-fix-v0", "pass"), (2, "script-fix-v0", "fail")]
    assert b"\r" not in world.trials_path.read_bytes()


def test_fix_files_are_byte_for_byte_and_written_for_invalid_trials(tmp_path: Path) -> None:
    world = World(tmp_path)
    crlf = (REFERENCE + "# crlf\n").replace("\n", "\r\n")
    world.fake.set(crlf, OK)
    world.add_good_trial(1, crlf)
    world.add_trial(2, REFERENCE + "# invalid one\n", stream_log(edit_call(), is_error=True))
    result = world.grade([1, 2])
    fixes = world.case_dir / "grading" / "fixes"
    assert (fixes / f"{fix_hash(crlf.encode())}.py").read_bytes() == crlf.encode("utf-8")
    # Both trials' scripts are the same program: one fix file, the first copy kept.
    assert len(list(fixes.glob("*.py"))) == 1
    assert result.fixes_written == (fixes / f"{fix_hash(crlf.encode())}.py",)
    assert {rec["fix"] for rec in world.records()} == {fix_hash(crlf.encode())}


# -- replay dedupe -----------------------------------------------------------


def test_identical_fixes_share_one_replay(tmp_path: Path) -> None:
    world = World(tmp_path)
    fix = REFERENCE.replace("Next \u00bb", "Next")
    world.fake.set(fix, OK)
    world.add_good_trial(1, fix)
    world.add_good_trial(2, fix + "# same program\n")
    result = world.grade([1, 2])
    assert len(world.trial_replays()) == 1
    assert result.replay_count == 5  # two opening controls, one trial, two closing controls
    assert "shared with run 1" in "\n".join(world.output)
    assert [o.verdict for o in result.outcomes] == ["pending-judge", "pending-judge"]


def test_fix_identical_to_the_reference_reuses_the_control(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE + "# same program\n")
    result = world.grade([1])
    assert world.trial_replays() == []
    assert result.replay_count == 4
    assert only(result).verdict == "pass"
    assert only(result).replay_note == "reused control"


def test_only_trials_that_reach_the_replay_rule_replay(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_trial(1, REFERENCE, None)  # invalid
    world.add_good_trial(2, "def (:\n")  # syntax-error
    world.add_good_trial(3, INPUT)  # no-edit
    result = world.grade([1, 2, 3])
    assert result.replay_count == 4 and world.trial_replays() == []


# -- controls ----------------------------------------------------------------


def test_opening_control_failure_voids_everything_and_records_nothing(tmp_path: Path) -> None:
    world = World(tmp_path)
    prior = world.seed_prior_record()
    world.fake.set(REFERENCE, ReplayResult(exit_code=1, timed_out=False, failing_line=9, output="a\nb\nTimeoutError: nope\n"))
    world.add_good_trial(1, REFERENCE + "# a\n")
    world.add_good_trial(2, REFERENCE.replace("Next \u00bb", "Next"))
    result = world.grade([1, 2])
    assert result.exit_code == 1
    assert all((o.verdict, o.tags) == ("invalid", ("site-changed",)) for o in result.outcomes)
    assert result.replay_count == 1  # the reference only: no input, no trials, no closing controls
    text = "\n".join(world.output)
    assert "opening reference control failed" in text and "exit code 1" in text
    assert "failing line 9" in text and "TimeoutError: nope" in text
    assert "control failed: nothing recorded" in text
    assert "run 1: invalid [site-changed]" in text
    assert world.trials_path.read_bytes() == prior  # the earlier valid verdict survives
    assert world.fix_files() == [] and result.fixes_written == ()


def test_opening_input_control_must_fail_at_fails_at(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.fake.set(INPUT, failed_at(FAILS_AT + 3))
    world.add_good_trial(1, REFERENCE + "# a\n")
    result = world.grade([1])
    assert result.exit_code == 1
    assert only(result).tags == ("site-changed",)
    assert "opening input control failed" in "\n".join(world.output)
    assert result.replay_count == 2


def test_closing_control_failure_voids_every_trial_and_records_nothing(tmp_path: Path) -> None:
    world = World(tmp_path)
    prior = world.seed_prior_record()
    world.fake.set(REFERENCE, [OK, failed_at(9)])  # fine before, surprising after
    world.add_good_trial(1, REFERENCE + "# a\n")  # would have passed
    fix = REFERENCE.replace("Next \u00bb", "Next")
    world.fake.set(fix, OK)
    world.add_good_trial(2, fix)
    result = world.grade([1, 2])
    assert result.exit_code == 1
    assert all((o.verdict, o.tags) == ("invalid", ("site-changed",)) for o in result.outcomes)
    assert all(o.replay is None for o in result.outcomes)
    assert "closing reference control failed" in "\n".join(world.output)
    assert "control failed: nothing recorded" in "\n".join(world.output)
    assert world.trials_path.read_bytes() == prior  # the earlier valid verdict survives
    assert world.fix_files() == [] and result.fixes_written == ()


def test_console_output_has_a_line_per_trial_and_a_summary(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE + "# a\n")
    world.add_trial(2, REFERENCE, None)
    result = world.grade([1, 2])
    text = "\n".join(world.output)
    assert "run 1: pass [-]" in text and "reused control" in text
    assert "run 2: invalid [harness-error]" in text
    assert "summary: invalid 1, pass 1" in text
    assert f"replays run: {result.replay_count}" in text
    assert str(world.trials_path) in text


# -- subject sidecars --------------------------------------------------------


def write_subject_sidecar(world: World, run: int, content: object) -> Path:
    """Write ``<NN>-run<N>.subject.json`` beside a run; ``content`` is a JSON value or raw text."""
    path = world.trials_root / f"01-run{run}.subject.json"
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_sidecar_overrides_the_subject_arguments(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE)
    write_subject_sidecar(
        world, 1, {"model": "ignored-model", "effort": "low", "context": "claude-md", "tools": "interactive"}
    )
    assert only(world.grade([1], effort="high", context="none", tools="edit-only")).verdict == "pass"
    (rec,) = world.records()
    # The model still comes from the transcript, never from the sidecar.
    assert rec["subject"] == {
        "model": "model-a",
        "effort": "low",
        "context": "claude-md",
        "tools": "interactive",
        "cli": "9.9.9",
    }
    assert list(rec["subject"]) == ["model", "effort", "context", "tools", "cli"]


def test_without_a_sidecar_the_arguments_are_recorded(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE)
    world.grade([1], effort="high", context="ctx", tools="interactive")
    (rec,) = world.records()
    assert rec["subject"] == {
        "model": "model-a",
        "effort": "high",
        "context": "ctx",
        "tools": "interactive",
        "cli": "9.9.9",
    }


def test_each_run_in_a_batch_records_its_own_subject(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE)
    world.add_good_trial(2, REFERENCE)
    write_subject_sidecar(world, 2, {"effort": "low", "context": "c2", "tools": "t2"})
    world.grade([1, 2], effort="high", context="c1", tools="t1")
    by_run = {rec["run"]: rec["subject"] for rec in world.records()}
    assert (by_run[1]["effort"], by_run[1]["context"], by_run[1]["tools"]) == ("high", "c1", "t1")
    assert (by_run[2]["effort"], by_run[2]["context"], by_run[2]["tools"]) == ("low", "c2", "t2")


def test_a_corrupt_sidecar_makes_the_run_invalid(tmp_path: Path) -> None:
    cases = {
        "bad-json": "{not json",
        "not-an-object": '["effort", "context", "tools"]',
        "missing-key": {"effort": "low", "context": "none"},
        "non-string": {"effort": "low", "context": "none", "tools": 3},
    }
    for label, content in cases.items():
        world = World(tmp_path / label)
        world.add_good_trial(1, REFERENCE)
        path = write_subject_sidecar(world, 1, content)
        outcome = only(world.grade([1], effort="high"))
        assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",)), label
        assert "unreadable subject sidecar" in outcome.detail, label
        assert str(path) in outcome.detail, label
        assert world.trial_replays() == [], label
        (rec,) = world.records()
        assert (rec["verdict"], rec["tags"]) == ("invalid", ["harness-error"]), label
        assert rec["subject"]["effort"] == "high", label  # the arguments stand in


def test_a_sidecar_that_is_not_utf8_makes_the_run_invalid(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.add_good_trial(1, REFERENCE)
    path = world.trials_root / "01-run1.subject.json"
    path.write_bytes(b"\xff\xfe\x00{")
    outcome = only(world.grade([1]))
    assert (outcome.verdict, outcome.tags) == ("invalid", ("harness-error",))
    assert str(path) in outcome.detail
