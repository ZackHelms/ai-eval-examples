"""Re-grade a case's recorded trials without replaying anything.

A grader change (a new detector, a new rubric) should leave old verdicts alone
unless the rubric says otherwise. ``regrade`` checks that: it grades the saved
trial scripts again with a *fake* replay that answers from evidence already on
record, then compares each result with what the trial's record said.

The fake replay never runs a script. The reference and the broken input
answer as their controls do; any other fix answers with the replay result an
earlier record stored for the same fix hash. A fix with no stored result
raises ``NeedsReplay``, and nothing is written. So the check is free, needs
no site, and cannot touch the case: it grades a temporary copy of it.

``write=True`` then records every run under the current rubric by running the
same grade calls on the real case (older rubrics' lines are left alone).
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scriptfix import RUBRIC
from scriptfix.case import Case, load_case
from scriptfix.grade import Out, ReplayFn, TrialOutcome, grade
from scriptfix.judge import BY_CD, JUDGE_TAGS, TAG_MISSED_ESCALATION
from scriptfix.judgeprompt import QUESTION_ESCALATION
from scriptfix.record import fix_hash, read_trials
from scriptfix.replay import ReplayResult

STATUS_SAME = "same"
STATUS_CHANGED = "changed"
STATUS_NEEDS_REPLAY = "needs-replay"

# What ``grade`` records for a run whose record has no (or a partial) subject.
_DEFAULT_SUBJECT = ("default", "none", "edit-only")

Form = tuple[str, tuple[str, ...]]


class NeedsReplay(Exception):
    """A fix has no replay result on record, so re-grading it would need a replay."""

    def __init__(self, script: Path, fix: str) -> None:
        super().__init__(f"{script}: no replay on record for fix {fix}")
        self.script = script
        self.fix = fix

    @property
    def run(self) -> int | None:
        """The run number, read from the script's ``<NN>-run<N>`` trial folder (None if it isn't one)."""
        match = re.fullmatch(r"\d+-run(\d+)", self.script.parent.parent.name)
        return int(match.group(1)) if match else None


@dataclass(frozen=True)
class RegradeRow:
    """One run: what its record said and what the re-grade says."""

    run: int
    was: Form
    now: Form
    was_fix: str | None
    now_fix: str | None
    recorded_verdict: str | None = None  # the record's verdict, when the judge decided it
    recorded_by: str | None = None  # "the judge", "the CD" or both

    @property
    def same(self) -> bool:
        return self.was == self.now and self.was_fix == self.now_fix


@dataclass(frozen=True)
class RegradeResult:
    """What one ``regrade`` call found (and, with ``write``, did)."""

    status: str
    rows: tuple[RegradeRow, ...] = ()
    needs_replay: NeedsReplay | None = None
    written: Path | None = None  # the trials.jsonl written, or None
    pending_runs: tuple[int, ...] = ()  # written runs that now wait for the judge

    @property
    def changed(self) -> int:
        return sum(1 for row in self.rows if not row.same)

    @property
    def exit_code(self) -> int:
        """0 when every row is the same or a write succeeded, 1 otherwise."""
        return 0 if self.status == STATUS_SAME or self.written is not None else 1


def static_form(record: dict) -> Form:
    """The verdict and tags the record had before the judge decided it."""
    questions = [entry["question"] for entry in record.get("judge") or []]
    tags = set(record.get("tags") or [])
    if not questions:
        return str(record["verdict"]), tuple(sorted(tags))
    kept = {tag for tag in tags if tag not in JUDGE_TAGS and tag != TAG_MISSED_ESCALATION}
    prefixes = (question.split(":", 1)[0] for question in questions)
    asked = {tag for tag in prefixes if tag != QUESTION_ESCALATION}
    return "pending-judge", tuple(sorted(kept | asked))


def format_runs(runs: Sequence[int]) -> str:
    """``[1, 2, 3, 5]`` as ``1-3,5``: spans of three or more collapse."""
    ordered = sorted(runs)
    parts: list[str] = []
    start = 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        if end - start >= 2:
            parts.append(f"{ordered[start]}-{ordered[end]}")
        else:
            parts.extend(str(run) for run in ordered[start : end + 1])
        start = end + 1
    return ",".join(parts)


def _fake_replay(case: Case, sources: Sequence[dict]) -> ReplayFn:
    """A replay function that answers from the controls and the stored results, never running a script."""
    reference = fix_hash(case.reference_script.read_bytes())
    broken = fix_hash(case.input_script.read_bytes())
    stored: dict[str, ReplayResult] = {}
    for record in sorted(sources, key=lambda rec: int(rec["run"])):  # the lowest run's result wins
        fix, replay = record.get("fix"), record.get("replay")
        if isinstance(fix, str) and isinstance(replay, dict):
            stored.setdefault(
                fix,
                ReplayResult(
                    exit_code=replay.get("exit_code"),
                    timed_out=bool(replay.get("timed_out")),
                    failing_line=replay.get("failing_line"),
                    output="",
                ),
            )

    def fake(script: Path, **_ignored: object) -> ReplayResult:
        digest = fix_hash(Path(script).read_bytes())
        if digest == reference:
            return ReplayResult(exit_code=0, timed_out=False, failing_line=None, output="")
        if digest == broken:
            return ReplayResult(exit_code=1, timed_out=False, failing_line=case.fails_at, output="")
        if digest in stored:
            return stored[digest]
        raise NeedsReplay(Path(script), digest)

    return fake


def _subject_of(record: dict) -> tuple[str, str, str]:
    subject = record.get("subject")
    subject = subject if isinstance(subject, dict) else {}
    effort, context, tools = (
        subject.get(name) if isinstance(subject.get(name), str) else default
        for name, default in zip(("effort", "context", "tools"), _DEFAULT_SUBJECT, strict=True)
    )
    return effort, context, tools


def _groups(sources: Sequence[dict]) -> list[tuple[tuple[str, str, str], list[int]]]:
    """The runs grouped by recorded subject, in ascending order of each group's first run."""
    groups: dict[tuple[str, str, str], list[int]] = {}
    for record in sorted(sources, key=lambda rec: int(rec["run"])):
        groups.setdefault(_subject_of(record), []).append(int(record["run"]))
    return list(groups.items())


def _grade_all(
    case_dir: Path,
    groups: Sequence[tuple[tuple[str, str, str], list[int]]],
    *,
    trials_root: Path | None,
    projects_root: Path | None,
    repo_root: Path,
    date: str | None,
    replay_fn: ReplayFn,
) -> list[TrialOutcome]:
    """One ``grade`` call per subject group. Grade's own lines (its control lines claim replays) are dropped."""
    outcomes: list[TrialOutcome] = []
    for (effort, context, tools), runs in groups:
        lines: list[str] = []
        result = grade(
            case_dir,
            runs,
            trials_root=trials_root,
            projects_root=projects_root,
            effort=effort,
            context=context,
            tools=tools,
            date=date,
            replay_fn=replay_fn,
            out=lines.append,
            repo_root=repo_root,
        )
        outcomes.extend(result.outcomes)
    return outcomes


def _form_text(form: Form) -> str:
    return f"{form[0]}[{','.join(form[1])}]"


def _row_line(row: RegradeRow) -> str:
    parts = [f"RUN={row.run}", f"WAS={_form_text(row.was)}", f"NOW={_form_text(row.now)}"]
    if row.was_fix != row.now_fix:
        parts.append(f"FIX={row.was_fix or '-'}->{row.now_fix or '-'}")
    parts.append("SAME" if row.same else "CHANGED")
    line = " ".join(parts)
    if row.recorded_verdict is not None:
        line += f" (recorded: {row.recorded_verdict}, by {row.recorded_by})"
    return line


def _judged_by(record: dict) -> str | None:
    entries = [entry for entry in record.get("judge") or [] if isinstance(entry, dict)]
    if not entries:
        return None
    by_cd = {entry.get("by") == BY_CD for entry in entries}
    if by_cd == {True}:
        return "the CD"
    return "the judge and the CD" if by_cd == {True, False} else "the judge"


def _row(record: dict, outcome: TrialOutcome) -> RegradeRow:
    judged = bool(record.get("judge"))
    return RegradeRow(
        run=outcome.run,
        was=static_form(record),
        now=(outcome.verdict, tuple(sorted(outcome.tags))),
        was_fix=record.get("fix"),
        now_fix=outcome.fix,
        recorded_verdict=str(record["verdict"]) if judged else None,
        recorded_by=_judged_by(record) if judged else None,
    )


def regrade(
    case_dir: Path,
    runs: list[int],
    *,
    source_rubric: str = RUBRIC,
    write: bool = False,
    trials_root: Path | None = None,
    projects_root: Path | None = None,
    repo_root: Path | None = None,
    date: str | None = None,
    out: Out = print,
) -> RegradeResult:
    """Re-grade ``runs`` of the case at ``case_dir`` against their ``source_rubric`` records, replaying nothing.

    The check always runs first, on a temporary copy of the case, so the case
    itself is untouched. ``repo_root`` defaults to the repo that holds the
    real case (never the copy). With ``write=True`` and no run needing a
    replay, the same grading is then done on the real case, recording every
    run under the current rubric; changed rows don't block that. Raises
    ``ValueError`` for ``write`` from the current rubric (re-grading in place
    would overwrite the judge's answers), for a run with no ``source_rubric``
    record, and for a bad case or ``trials.jsonl``.
    """
    case_dir = Path(case_dir)
    if write and source_rubric == RUBRIC:
        raise ValueError(
            f"--write needs --from an older rubric than {RUBRIC}: "
            "re-grading in place would overwrite the judge's answers with pending-judge"
        )
    case = load_case(case_dir)
    trials_path = case.grading_dir / "trials.jsonl"
    records = read_trials(trials_path)
    sources: list[dict] = []
    for run in sorted(set(runs)):
        found = [rec for rec in records if rec["run"] == run and rec["rubric"] == source_rubric]
        if not found:
            raise ValueError(f"run {run} has no record under rubric {source_rubric} in {trials_path}")
        sources.append(found[0])
    by_run = {int(rec["run"]): rec for rec in sources}
    repo_root = Path(repo_root) if repo_root is not None else case.path.resolve().parents[1]
    groups = _groups(sources)
    replay_fn = _fake_replay(case, sources)
    shown = sorted(by_run)

    out(f"regrading {case.slug} under {RUBRIC} from {source_rubric}: runs {format_runs(shown)}, no replays")
    options = {
        "trials_root": trials_root,
        "projects_root": projects_root,
        "repo_root": repo_root,
        "date": date,
        "replay_fn": replay_fn,
    }
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
            copy = Path(scratch) / case_dir.name
            shutil.copytree(case_dir, copy)
            outcomes = _grade_all(copy, groups, **options)
    except NeedsReplay as exc:
        out(f"REGRADE={STATUS_NEEDS_REPLAY} RUN={exc.run if exc.run is not None else '?'} FIX={exc.fix}")
        return RegradeResult(status=STATUS_NEEDS_REPLAY, needs_replay=exc)

    rows = tuple(_row(by_run[outcome.run], outcome) for outcome in sorted(outcomes, key=lambda item: item.run))
    for row in rows:
        out(_row_line(row))
    changed = sum(1 for row in rows if not row.same)
    status = STATUS_CHANGED if changed else STATUS_SAME
    out(f"REGRADE={status} RUNS={len(rows)} CHANGED={changed}")
    if not write:
        return RegradeResult(status=status, rows=rows)

    written = _grade_all(case_dir, groups, **options)
    pending = tuple(sorted(item.run for item in written if item.verdict == "pending-judge"))
    out(f"wrote {trials_path}")
    if pending:
        out(rf"NEXT=.\30-grade-trials.ps1 -Judge -Case {case_dir} -Runs {','.join(str(run) for run in pending)}")
    return RegradeResult(status=status, rows=rows, written=trials_path, pending_runs=pending)
