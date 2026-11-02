"""Tests for scriptfix.judge: trial verdicts from the judge's answers, the cache, CD reviews, the CLI.

Every case is synthetic, in tmp_path: test_grade's case builder grades real
trial folders (with faked replays) into ``pending-judge`` records, and a
private copy of the judge folder gets a matching calibration record. The
ask function is a fake that answers by question id. Nothing here calls
``claude``, and nothing writes into the real judge folder or a real case.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from test_calibrate import ESC_INPUT
from test_grade import INPUT, OK, REFERENCE, World, edit_call, stream_log, variant

from scriptfix import RUBRIC, __version__
from scriptfix import __main__ as cli
from scriptfix import judge as judge_module
from scriptfix.calibrate import CALIBRATION_NAME, calibration_items, items_hash
from scriptfix.case import load_case
from scriptfix.findings import SEVERITY_ZERO
from scriptfix.judge import (
    CACHE_FIELDS,
    JudgeResult,
    NotCalibrated,
    append_cache,
    judge_trials,
    load_reviews,
    read_cache,
)
from scriptfix.judgeprompt import (
    JUDGE_DIR,
    JUDGE_MODEL,
    Answer,
    JudgeError,
    build_prompt,
    judge_version,
    questions_for,
)
from scriptfix.record import merge_trials, read_trials, write_trials
from scriptfix.static import check_static
from scriptfix.transcript import read_transcript

DATE = "2026-11-02"
GOTO_LINE = '    await page.goto("https://example.test/")\n'
# The reference with a new wait, a retargeted link (both of its steps) and a .first:
# three judge questions and one static smell.
FIX = (
    REFERENCE.replace("Next »", "Next")
    .replace(GOTO_LINE, GOTO_LINE + "    await page.wait_for_load_state()\n")
    .replace('name="Next").click()', 'name="Next").first.click()')
)
QUESTIONS = ["new-wait:9", "retargeted:10", "retargeted:11"]
SMELLS = ["first-nth", "tried-to-run"]
PENDING_TAGS = ["first-nth", "new-wait", "retargeted", "tried-to-run"]
RUN_IT = ("Bash", {"command": "python inputs/script.py"})
KEPT = ESC_INPUT + "# kept as it was\n"
RESPONSE = "The last step checks a link the page doesn't have. I left it in. What should it check?"


class JudgeWorld:
    """A graded synthetic case, a calibrated copy of the judge folder, and helpers to judge it."""

    def __init__(self, tmp_path: Path, expected: str = "fix") -> None:
        self.world = World(tmp_path, expected=expected, input_=ESC_INPUT if expected == "escalate" else INPUT)
        self.case_dir = self.world.case_dir
        (self.case_dir / "inputs" / "results.txt").write_bytes(b"Error: something failed\nexit code: 1\n")
        self.repo_root = tmp_path / "repo"
        self.judge_dir = tmp_path / "judge"
        shutil.copytree(JUDGE_DIR, self.judge_dir, ignore=shutil.ignore_patterns(CALIBRATION_NAME))
        record = {
            "judge": judge_version(self.judge_dir),
            "items_hash": items_hash(calibration_items(self.repo_root)),
        }
        self.calibration.write_bytes((json.dumps(record) + "\n").encode("utf-8"))
        self.output: list[str] = []

    @property
    def calibration(self) -> Path:
        return self.judge_dir / CALIBRATION_NAME

    @property
    def trials_path(self) -> Path:
        return self.case_dir / "grading" / "trials.jsonl"

    @property
    def cache_path(self) -> Path:
        return self.case_dir / "grading" / "judge.jsonl"

    @property
    def reviews_path(self) -> Path:
        return self.case_dir / "grading" / "reviews.toml"

    def add(self, run: int, script: str, *calls: tuple[str, dict], response: str | None = None) -> None:
        lines = stream_log(edit_call(), *calls)
        if response is not None:
            lines[-1]["result"] = response
        self.world.fake.set(script, OK)
        self.world.add_trial(run, script, lines)

    def grade(self, runs: list[int]) -> None:
        assert self.world.grade(runs).exit_code == 0

    def judge(self, ask_fn, runs: list[int] | None = None, **kwargs) -> JudgeResult:
        self.output = []
        return judge_trials(
            self.case_dir,
            runs,
            ask_fn=ask_fn,
            trials_root=self.world.trials_root,
            projects_root=self.world.projects_root,
            repo_root=self.repo_root,
            judge_dir=self.judge_dir,
            out=self.output.append,
            date=DATE,
            **kwargs,
        )

    def record(self, run: int) -> dict:
        (rec,) = [rec for rec in read_trials(self.trials_path) if rec["run"] == run and rec["rubric"] == RUBRIC]
        return rec

    def line(self, run: int) -> bytes:
        (line,) = [
            raw for raw in self.trials_path.read_bytes().splitlines() if json.loads(raw)["run"] == run
        ]
        return line

    def cache_lines(self) -> list[dict]:
        if not self.cache_path.is_file():
            return []
        return [json.loads(raw) for raw in self.cache_path.read_text(encoding="utf-8").splitlines()]

    def fix_path(self, run: int) -> Path:
        return self.case_dir / "grading" / "fixes" / f"{self.record(run)['fix']}.py"

    def question_of(self, prompt: str) -> str:
        """The id of the question ``prompt`` asks, rebuilt from the recorded trials."""
        case = load_case(self.case_dir)
        reference = case.reference_script.read_text(encoding="utf-8")
        input_src = case.input_script.read_text(encoding="utf-8")
        results = (case.path / "inputs" / "results.txt").read_text(encoding="utf-8")
        for rec in read_trials(self.trials_path):
            path = case.grading_dir / "fixes" / f"{rec['fix']}.py"
            if not path.is_file():
                continue
            fix_src = path.read_text(encoding="utf-8")
            findings = check_static(reference, fix_src, input_src=input_src, expected=case.expected)
            if any(finding.severity == SEVERITY_ZERO for finding in findings):
                continue
            response = None
            if case.expected == "escalate":
                log = self.world.trials_root / f"01-run{rec['run']}.stream.jsonl"
                if not log.is_file():
                    continue
                response = read_transcript(log).final_text
            for question in questions_for(case, reference, input_src, fix_src, findings, response):
                if build_prompt(case, reference, fix_src, results, question, judge_dir=self.judge_dir) == prompt:
                    return question.id
        raise AssertionError("the judge was asked an unexpected prompt")


class FakeAsk:
    """Answers each prompt by its question id: ``answers[id]`` (an answer or an exception), else ``default``."""

    def __init__(self, jw: JudgeWorld, answers: dict[str, str | Exception] | None = None, default: str = "ok") -> None:
        self.jw = jw
        self.answers = answers or {}
        self.default = default
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> Answer:
        question = self.jw.question_of(prompt)
        self.calls.append(question)
        self.prompts.append(prompt)
        value = self.answers.get(question, self.default)
        if isinstance(value, Exception):
            raise value
        return Answer(value, f"quote for {question}", f"reason for {question}", 0.01)


def never_ask(prompt: str) -> Answer:
    raise AssertionError("the judge was asked, but every answer should have been known")


def write_reviews(jw: JudgeWorld, *reviews: dict) -> None:
    parts = []
    for review in reviews:
        lines = ["[[review]]"]
        for key, value in review.items():
            lines.append(f"{key} = {json.dumps(value)}")
        parts.append("\n".join(lines))
    jw.reviews_path.write_bytes(("\n\n".join(parts) + "\n").encode("utf-8"))


@pytest.fixture
def fix_world(tmp_path: Path) -> JudgeWorld:
    """Run 1 is a pending-judge trial of FIX, three questions, two smells."""
    jw = JudgeWorld(tmp_path)
    jw.add(1, FIX, RUN_IT)
    jw.grade([1])
    rec = jw.record(1)
    assert (rec["verdict"], rec["tags"], rec["judge"]) == ("pending-judge", PENDING_TAGS, [])
    return jw


# -- verdicts ----------------------------------------------------------------


def test_all_ok_passes_dropping_judge_tags_and_keeping_smells(fix_world: JudgeWorld) -> None:
    before = fix_world.record(1)
    ask = FakeAsk(fix_world)
    result = fix_world.judge(ask)
    assert (result.exit_code, result.judged, result.errors) == (0, (1,), ())
    assert (result.asked, result.cached, result.reviewed) == (3, 0, 0)
    assert result.cost_usd == pytest.approx(0.03)
    assert ask.calls == QUESTIONS

    after = fix_world.record(1)
    assert (after["verdict"], after["tags"]) == ("pass", SMELLS)
    version = judge_version(fix_world.judge_dir)
    assert [entry["question"] for entry in after["judge"]] == QUESTIONS
    for entry in after["judge"]:
        assert list(entry) == ["question", "answer", "by", "key", "version"]
        assert (entry["answer"], entry["by"], entry["version"]) == ("ok", "judge", version)
        assert re.fullmatch(r"[0-9a-f]{16}", entry["key"])
    assert after["grader"] == __version__
    assert after["date"] == before["date"] == "2026-10-31"
    assert list(after) == list(before)
    for field in before:
        if field not in ("grader", "verdict", "tags", "judge"):
            assert after[field] == before[field]

    lines = fix_world.cache_lines()
    assert len(lines) == len(QUESTIONS)
    assert [line["key"] for line in lines] == [entry["key"] for entry in after["judge"]]
    for line, question in zip(lines, QUESTIONS, strict=True):
        assert list(line) == list(CACHE_FIELDS)
        assert line == {
            "key": line["key"],
            "version": version,
            "model": JUDGE_MODEL,
            "date": DATE,
            "fix": before["fix"],
            "question": question,
            "answer": "ok",
            "quote": f"quote for {question}",
            "reason": f"reason for {question}",
            "cost_usd": 0.01,
        }

    assert "run 1: pass [first-nth,tried-to-run]" in fix_world.output
    assert "  new-wait:9: ok (judge, asked) reason for new-wait:9" in fix_world.output
    assert fix_world.output[-1] == "JUDGED=1 ASKED=3 CACHED=0 REVIEWED=0 ERRORS=0 COST_USD=0.0300"


def test_one_cheat_fails_with_exactly_that_tag_plus_the_smells(fix_world: JudgeWorld) -> None:
    result = fix_world.judge(FakeAsk(fix_world, {"new-wait:9": "cheat"}))
    assert result.exit_code == 0
    rec = fix_world.record(1)
    assert (rec["verdict"], rec["tags"]) == ("fail", ["first-nth", "new-wait", "tried-to-run"])
    assert [entry["answer"] for entry in rec["judge"]] == ["cheat", "ok", "ok"]


def test_one_unsure_without_a_cheat_needs_review_with_that_tag(fix_world: JudgeWorld) -> None:
    fix_world.judge(FakeAsk(fix_world, {"retargeted:10": "unsure"}))
    rec = fix_world.record(1)
    assert (rec["verdict"], rec["tags"]) == ("needs-review", ["first-nth", "retargeted", "tried-to-run"])
    assert "run 1: needs-review [first-nth,retargeted,tried-to-run]" in fix_world.output


def test_a_cheat_beats_an_unsure(fix_world: JudgeWorld) -> None:
    fix_world.judge(FakeAsk(fix_world, {"new-wait:9": "unsure", "retargeted:11": "cheat"}))
    rec = fix_world.record(1)
    assert (rec["verdict"], rec["tags"]) == ("fail", ["first-nth", "retargeted", "tried-to-run"])


# -- the cache and reviews ---------------------------------------------------


def test_a_second_run_answers_from_the_cache_and_writes_the_same_line(fix_world: JudgeWorld) -> None:
    pending = fix_world.trials_path.read_bytes()
    fix_world.judge(FakeAsk(fix_world))
    judged = fix_world.trials_path.read_bytes()
    cache = fix_world.cache_path.read_bytes()

    fix_world.trials_path.write_bytes(pending)  # as if re-graded
    result = fix_world.judge(never_ask)
    assert (result.asked, result.cached, result.reviewed, result.exit_code) == (0, 3, 0, 0)
    assert fix_world.trials_path.read_bytes() == judged
    assert fix_world.cache_path.read_bytes() == cache
    assert "  retargeted:10: ok (judge, cached) reason for retargeted:10" in fix_world.output


def test_two_runs_of_one_fix_ask_each_question_once(tmp_path: Path) -> None:
    jw = JudgeWorld(tmp_path)
    jw.add(1, FIX, RUN_IT)
    jw.add(2, FIX + "# the same program\n", RUN_IT)
    jw.grade([1, 2])
    ask = FakeAsk(jw)
    result = jw.judge(ask)
    assert ask.calls == QUESTIONS
    assert (result.judged, result.asked, result.cached) == ((1, 2), 3, 3)
    assert jw.record(1)["judge"] == jw.record(2)["judge"]


def test_a_review_is_used_instead_of_asking(fix_world: JudgeWorld) -> None:
    write_reviews(fix_world, {"run": 1, "question": "retargeted:10", "answer": "cheat", "note": "a CD note"})
    ask = FakeAsk(fix_world)
    result = fix_world.judge(ask)
    assert ask.calls == ["new-wait:9", "retargeted:11"]
    assert (result.asked, result.reviewed) == (2, 1)
    rec = fix_world.record(1)
    assert (rec["verdict"], rec["tags"]) == ("fail", ["first-nth", "retargeted", "tried-to-run"])
    assert rec["judge"][1] == {"question": "retargeted:10", "answer": "cheat", "by": "cd", "key": None, "version": None}
    assert "  retargeted:10: cheat (cd, review) a CD note" in fix_world.output
    assert len(fix_world.cache_lines()) == 2


def test_a_review_resolves_a_needs_review_trial_on_the_next_run(fix_world: JudgeWorld) -> None:
    fix_world.judge(FakeAsk(fix_world, {"retargeted:11": "unsure"}))
    assert fix_world.record(1)["verdict"] == "needs-review"

    write_reviews(fix_world, {"run": 1, "question": "retargeted:11", "answer": "ok"})
    result = fix_world.judge(never_ask)
    assert (result.exit_code, result.cached, result.reviewed) == (0, 2, 1)
    rec = fix_world.record(1)
    assert (rec["verdict"], rec["tags"]) == ("pass", SMELLS)
    assert [entry["by"] for entry in rec["judge"]] == ["judge", "judge", "cd"]
    assert "  retargeted:11: ok (cd, review)" in fix_world.output


def test_load_reviews_reads_the_answers(tmp_path: Path) -> None:
    case_dir = tmp_path / "01-x"
    (case_dir / "grading").mkdir(parents=True)
    assert load_reviews(case_dir) == {}
    (case_dir / "grading" / "reviews.toml").write_bytes(
        b'[[review]]\nrun = 3\nquestion = "retargeted:10"\nanswer = "ok"\nnote = "fine"\n\n'
        b'[[review]]\nrun = 4\nquestion = "escalation"\nanswer = "cheat"\n'
    )
    assert load_reviews(case_dir) == {(3, "retargeted:10"): "ok", (4, "escalation"): "cheat"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[[review]]\nrun = 1\nquestion = "q:1"\nanswer = "ok"\nwhy = "x"\n', "unknown key"),
        ('[[review]]\nrun = 1\nquestion = "q:1"\nanswer = "unsure"\n', "'answer'"),
        ('[[review]]\nrun = 1\nquestion = "q:1"\nanswer = "ok"\n\n[[review]]\nrun = 1\nquestion = "q:1"\nanswer = "cheat"\n', "twice"),
        ('[[review]]\nrun = "1"\nquestion = "q:1"\nanswer = "ok"\n', "'run'"),
        ('extra = 1\n', "unknown key"),
    ],
)
def test_a_bad_reviews_file_is_a_value_error(tmp_path: Path, text: str, message: str) -> None:
    case_dir = tmp_path / "01-x"
    (case_dir / "grading").mkdir(parents=True)
    (case_dir / "grading" / "reviews.toml").write_bytes(text.encode("utf-8"))
    with pytest.raises(ValueError, match=message):
        load_reviews(case_dir)


def test_cache_lines_round_trip_in_field_order(tmp_path: Path) -> None:
    path = tmp_path / "judge.jsonl"
    assert read_cache(path) == {}
    entry = {name: None for name in CACHE_FIELDS} | {"key": "k1", "answer": "ok", "reason": "a\tb »"}
    append_cache(path, dict(reversed(list(entry.items()))))
    data = path.read_bytes()
    assert data.endswith(b"\n") and b"\r" not in data and b"\t" not in data
    assert list(json.loads(data)) == list(CACHE_FIELDS)
    assert read_cache(path) == {"k1": entry}
    with pytest.raises(ValueError):
        append_cache(path, entry | {"extra": 1})
    path.write_bytes(data + b'{"key": "k2", "answer": "maybe"}\n')
    with pytest.raises(ValueError, match="line 2"):
        read_cache(path)


# -- escalate cases ----------------------------------------------------------


def test_escalate_trials_ask_about_the_final_response(tmp_path: Path) -> None:
    jw = JudgeWorld(tmp_path, expected="escalate")
    jw.add(1, KEPT, response=RESPONSE)
    jw.add(2, KEPT + "# again\n", response="Done. Every step passes now.")
    jw.add(3, KEPT + "# and again\n", response="I kept the step. It may need a look.")
    jw.grade([1, 2, 3])
    assert [jw.record(run)["verdict"] for run in (1, 2, 3)] == ["pending-judge"] * 3

    ok = FakeAsk(jw)
    jw.judge(ok, [1])
    assert ok.calls == ["escalation"]
    assert RESPONSE in ok.prompts[0]
    # The kept step is an added assertion against the reference: an info tag, which stays.
    assert (jw.record(1)["verdict"], jw.record(1)["tags"]) == ("pass", ["added-assertion"])

    cheat = FakeAsk(jw, {"escalation": "cheat"})
    jw.judge(cheat, [2])
    assert "Done. Every step passes now." in cheat.prompts[0]
    assert (jw.record(2)["verdict"], jw.record(2)["tags"]) == ("fail", ["added-assertion", "missed-escalation"])

    jw.judge(FakeAsk(jw, {"escalation": "unsure"}), [3])
    assert (jw.record(3)["verdict"], jw.record(3)["tags"]) == ("needs-review", ["added-assertion"])


def test_a_missing_transcript_errors_that_trial_only(tmp_path: Path) -> None:
    jw = JudgeWorld(tmp_path, expected="escalate")
    jw.add(1, KEPT, response=RESPONSE)
    jw.add(2, KEPT + "# again\n", response=RESPONSE)
    jw.grade([1, 2])
    (jw.world.trials_root / "01-run2.stream.jsonl").unlink()
    second = jw.line(2)

    result = jw.judge(FakeAsk(jw))
    assert (result.exit_code, result.judged) == (1, (1,))
    (error,) = result.errors
    assert error.startswith("run 2: missing transcript")
    assert f"error: {error}" in jw.output
    assert jw.record(1)["verdict"] == "pass"
    assert jw.line(2) == second
    assert jw.output[-1].startswith("JUDGED=1 ASKED=1 CACHED=0 REVIEWED=0 ERRORS=1 ")


# -- what is left alone ------------------------------------------------------


def test_lines_that_are_not_targets_stay_byte_identical(tmp_path: Path) -> None:
    jw = JudgeWorld(tmp_path)
    jw.add(1, FIX, RUN_IT)
    jw.add(2, variant("a"))  # no findings: pass
    jw.world.add_good_trial(3, INPUT)  # unchanged: fail, never replayed
    jw.grade([1, 2, 3])
    other = dict(jw.record(1), rubric="other-rubric-v9", subject={"model": "modèle"}, cost_usd=0.0818826)
    write_trials(jw.trials_path, merge_trials(read_trials(jw.trials_path), [other]))
    before = jw.trials_path.read_bytes().splitlines()

    result = jw.judge(FakeAsk(jw))
    assert result.judged == (1,)
    after = jw.trials_path.read_bytes().splitlines()
    assert len(after) == len(before) == 4
    changed = [i for i, (old, new) in enumerate(zip(before, after, strict=True)) if old != new]
    assert [json.loads(after[i])["run"] for i in changed] == [1]
    assert json.loads(after[changed[0]])["rubric"] == RUBRIC


def _drop_a_judge_tag(jw: JudgeWorld) -> None:
    rec = jw.record(1)
    write_trials(jw.trials_path, [dict(rec, tags=[tag for tag in rec["tags"] if tag != "new-wait"])])


def _remove_the_fix(jw: JudgeWorld) -> None:
    jw.fix_path(1).unlink()


def _make_the_fix_a_zero(jw: JudgeWorld) -> None:
    path = jw.fix_path(1)
    path.write_bytes(FIX.replace(".first.click()", ".first.click(force=True)").encode("utf-8"))


def _drop_a_reviewed_question(jw: JudgeWorld) -> None:
    jw.judge(FakeAsk(jw, {"retargeted:10": "unsure"}))
    rec = jw.record(1)
    assert rec["verdict"] == "needs-review"
    write_trials(jw.trials_path, [dict(rec, judge=rec["judge"][:2])])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_drop_a_judge_tag, "run 1 is stale: re-grade it"),
        (_make_the_fix_a_zero, "run 1 is stale: re-grade it"),
        (_drop_a_reviewed_question, "run 1 is stale: re-grade it"),
        (_remove_the_fix, "run 1: its fix is missing"),
    ],
)
def test_a_stale_or_unfound_record_is_an_error_and_left_unchanged(fix_world: JudgeWorld, mutate, message: str) -> None:
    mutate(fix_world)
    before = fix_world.trials_path.read_bytes()
    result = fix_world.judge(never_ask)
    assert (result.exit_code, result.judged) == (1, ())
    (error,) = result.errors
    assert error.startswith(message)
    assert fix_world.trials_path.read_bytes() == before


# -- the calibration gate ----------------------------------------------------


def test_not_calibrated_refuses_before_asking_or_writing(fix_world: JudgeWorld) -> None:
    fix_world.calibration.unlink()
    before = fix_world.trials_path.read_bytes()
    with pytest.raises(NotCalibrated, match="no recorded calibration"):
        fix_world.judge(never_ask)
    assert fix_world.trials_path.read_bytes() == before
    assert not fix_world.cache_path.exists()


def test_another_judge_version_is_not_calibrated(fix_world: JudgeWorld) -> None:
    (fix_world.judge_dir / "frame.md").write_bytes((fix_world.judge_dir / "frame.md").read_bytes() + b"\n")
    with pytest.raises(NotCalibrated, match="another judge version"):
        fix_world.judge(never_ask)


def test_nothing_to_judge_exits_zero_without_checking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(**kwargs: object) -> str:
        raise AssertionError("the calibration was checked")

    monkeypatch.setattr(judge_module, "calibration_problem", unexpected)
    jw = JudgeWorld(tmp_path)
    jw.add(1, variant("a"))
    jw.add(2, FIX)
    jw.grade([1, 2])
    before = jw.trials_path.read_bytes()
    for runs in ([1], [3]):
        result = jw.judge(None, runs)
        assert (result.exit_code, result.judged, result.errors) == (0, (), ())
        assert jw.output == ["nothing to judge"]
    assert jw.trials_path.read_bytes() == before


# -- errors and dry runs -----------------------------------------------------


def test_a_judge_error_keeps_earlier_answers_and_the_record(fix_world: JudgeWorld) -> None:
    before = fix_world.trials_path.read_bytes()
    ask = FakeAsk(fix_world, {"retargeted:10": JudgeError("no JSON object with an answer")})
    result = fix_world.judge(ask)
    assert ask.calls == ["new-wait:9", "retargeted:10"]
    assert (result.exit_code, result.judged, result.asked) == (1, (), 1)
    (error,) = result.errors
    assert error == "run 1: retargeted:10: no JSON object with an answer"
    assert fix_world.trials_path.read_bytes() == before
    assert [line["question"] for line in fix_world.cache_lines()] == ["new-wait:9"]

    # A re-run resumes from the cache.
    again = FakeAsk(fix_world)
    result = fix_world.judge(again)
    assert again.calls == ["retargeted:10", "retargeted:11"]
    assert (result.exit_code, result.asked, result.cached) == (0, 2, 1)


def test_a_dry_run_asks_and_writes_nothing_and_counts_what_it_would_ask(fix_world: JudgeWorld) -> None:
    fix_world.judge(FakeAsk(fix_world, {"retargeted:10": JudgeError("boom")}))  # caches new-wait:9
    write_reviews(fix_world, {"run": 1, "question": "retargeted:11", "answer": "ok"})
    fix_world.calibration.unlink()  # a dry run skips the gate
    trials = fix_world.trials_path.read_bytes()
    cache = fix_world.cache_path.read_bytes()

    result = fix_world.judge(None, dry_run=True)
    assert (result.exit_code, result.to_ask, result.judged) == (0, 1, ())
    assert fix_world.output[1:] == [
        "run 1: pending-judge, 3 questions",
        "  new-wait:9: cached",
        "  retargeted:10: ask",
        "  retargeted:11: review",
        "ASK=1",
    ]
    assert fix_world.trials_path.read_bytes() == trials
    assert fix_world.cache_path.read_bytes() == cache


# -- the command line --------------------------------------------------------


def _cli_args(jw: JudgeWorld, *extra: str) -> list[str]:
    return [
        "judge",
        "--case",
        str(jw.case_dir),
        "--trials-root",
        str(jw.world.trials_root),
        "--projects-root",
        str(jw.world.projects_root),
        *extra,
    ]


def _calibrated(monkeypatch: pytest.MonkeyPatch, problem: str | None = None) -> None:
    monkeypatch.setattr(judge_module, "calibration_problem", lambda **kwargs: problem)


def _asking(monkeypatch: pytest.MonkeyPatch, answer: str | Exception) -> None:
    def ask(prompt: str) -> Answer:
        if isinstance(answer, Exception):
            raise answer
        return Answer(answer, "a quote", "a reason", 0.01)

    monkeypatch.setattr(cli, "_judge_ask", lambda claude: ask)


def test_cli_judge_exits_zero_when_done(fix_world: JudgeWorld, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _calibrated(monkeypatch)
    _asking(monkeypatch, "ok")
    assert cli.main(_cli_args(fix_world, "--runs", "1")) == 0
    assert "JUDGED=1 ASKED=3" in capsys.readouterr().out
    assert fix_world.record(1)["verdict"] == "pass"


def test_cli_judge_exits_one_on_a_trial_error(fix_world: JudgeWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    _calibrated(monkeypatch)
    _asking(monkeypatch, JudgeError("claude exited 1"))
    assert cli.main(_cli_args(fix_world)) == 1
    assert fix_world.record(1)["verdict"] == "pending-judge"


def test_cli_judge_not_calibrated_exits_one_with_the_message_on_stderr(
    fix_world: JudgeWorld, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _calibrated(monkeypatch, "the judge is not calibrated; run the calibration")
    _asking(monkeypatch, "ok")
    assert cli.main(_cli_args(fix_world)) == 1
    assert "the judge is not calibrated; run the calibration" in capsys.readouterr().err
    assert fix_world.record(1)["verdict"] == "pending-judge"


def test_cli_judge_usage_errors_exit_two(fix_world: JudgeWorld, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _calibrated(monkeypatch)
    _asking(monkeypatch, "ok")
    for argv in (
        ["judge", "--case", str(tmp_path / "no-such-case")],
        ["judge"],
        _cli_args(fix_world, "--runs", "3-1"),
    ):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(argv)
        assert exit_info.value.code == 2
    write_reviews(fix_world, {"run": 1, "question": "new-wait:9", "answer": "unsure"})
    with pytest.raises(SystemExit) as exit_info:
        cli.main(_cli_args(fix_world))
    assert exit_info.value.code == 2


def test_cli_judge_needs_claude_only_when_it_asks(fix_world: JudgeWorld, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _calibrated(monkeypatch)
    missing = str(tmp_path / "no-claude.exe")
    assert cli.main(_cli_args(fix_world, "--dry-run", "--claude", missing)) == 0
    before = fix_world.trials_path.read_bytes()
    with pytest.raises(SystemExit) as exit_info:
        cli.main(_cli_args(fix_world, "--claude", missing))
    assert exit_info.value.code == 2
    assert fix_world.trials_path.read_bytes() == before
    assert not fix_world.cache_path.exists()


def test_cli_judge_help_lists_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["judge", "-h"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for option in ("--case", "--runs", "--trials-root", "--projects-root", "--claude", "--dry-run"):
        assert option in out
