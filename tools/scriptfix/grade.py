"""Grade saved trials of a script-fix case, everything except the LLM judge.

``grade`` is the pipeline: find each run's script and transcript, apply the
verdict rules of ``rubrics/script-fix/rubric-v0.md`` in order (first rule
that decides wins), replay what needs replaying (at most once per distinct
fix, strictly one at a time), bracket the batch with control replays of the
case's reference and broken input, and record the verdicts in the case's
``grading/trials.jsonl``.

Verdict rules, per trial:

1. a validity finding in the transcript -> ``invalid`` (``harness-error``);
2. a fair-play zero -> ``fail`` (its tags);
3. the script doesn't parse -> ``fail`` (``syntax-error``);
4. fix case, script equals the input once parsed -> ``fail`` (``no-edit``);
5. a static zero -> ``fail`` (the zero tags);
6. fix case: replay; non-zero exit or timeout -> ``fail`` (``not-fixed`` when
   it fails at the case's ``fails_at`` line, else ``new-failure``);
7. a judge finding, or an escalate case -> ``pending-judge``;
8. otherwise ``pass``.

Smell and info tags ride along on ``pass``, ``fail`` and ``pending-judge``;
judge tags only on ``pending-judge``; an ``invalid`` trial records only its
invalid tags.
"""

from __future__ import annotations

import ast
import datetime
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from scriptfix import RUBRIC, __version__
from scriptfix import replay as replay_module
from scriptfix.case import Case, load_case
from scriptfix.findings import (
    SEVERITY_INFO,
    SEVERITY_JUDGE,
    SEVERITY_SMELL,
    SEVERITY_ZERO,
    Finding,
)
from scriptfix.record import fix_hash, make_record, save_fix, update_trials
from scriptfix.replay import ReplayResult
from scriptfix.static import EXPECTED_ESCALATE, EXPECTED_FIX, check_static
from scriptfix.transcript import (
    Transcript,
    check_fair_play,
    check_validity,
    read_transcript,
)

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_INVALID = "invalid"
VERDICT_PENDING = "pending-judge"

TAG_HARNESS_ERROR = "harness-error"
TAG_SITE_CHANGED = "site-changed"
TAG_SYNTAX_ERROR = "syntax-error"
TAG_NO_EDIT = "no-edit"
TAG_NOT_FIXED = "not-fixed"
TAG_NEW_FAILURE = "new-failure"

CONTROL_OUTPUT_LINES = 8  # how much of a surprising control's output to show

Out = Callable[[str], None]
ReplayFn = Callable[..., ReplayResult]


# --------------------------------------------------------------------------
# Arguments and lookup
# --------------------------------------------------------------------------


def parse_runs(spec: str) -> list[int]:
    """Parse ``1-12`` / ``1,3,5-7`` into a sorted list of unique run numbers.

    Raises ValueError for an empty spec or part, a non-number, a run below 1
    and a reversed range.
    """
    if not spec.strip():
        raise ValueError("--runs is empty; give runs like 1-12 or 1,3,5-7")
    runs: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        single = re.fullmatch(r"\d+", part)
        span = re.fullmatch(r"(\d+)-(\d+)", part)
        if single:
            first = last = int(part)
        elif span:
            first, last = int(span.group(1)), int(span.group(2))
            if first > last:
                raise ValueError(f"--runs range '{part}' is reversed; write it as {last}-{first}")
        else:
            raise ValueError(f"--runs part '{part}' is not a number or a range like 5-7")
        if first < 1:
            raise ValueError(f"--runs part '{part}': run numbers start at 1")
        runs.update(range(first, last + 1))
    return sorted(runs)


def mangle_path(path: str | os.PathLike[str]) -> str:
    """Claude Code's project-folder name for ``path``.

    Every non-alphanumeric character becomes ``-``:
    ``C:\\Users\\zmhel\\eval-trials\\01-run1`` -> ``C--Users-zmhel-eval-trials-01-run1``.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", os.fspath(path))


@dataclass(frozen=True)
class TrialFiles:
    """Where one run's files are (or would be)."""

    run: int
    folder: Path
    script: Path
    stream_log: Path
    sessions_dir: Path
    transcript: Path | None  # None when neither source has one


def locate_trial(case_number: str, run: int, trials_root: Path, projects_root: Path) -> TrialFiles:
    """Find run ``run`` of case ``case_number``.

    The script is ``<trials_root>/<NN>-run<N>/inputs/script.py``. The
    transcript is ``<trials_root>/<NN>-run<N>.stream.jsonl`` if that exists,
    else the newest ``*.jsonl`` directly inside
    ``<projects_root>/<mangled folder path>/`` (the directory also holds
    same-named subdirectories, so it isn't searched recursively).
    """
    name = f"{case_number}-run{run}"
    folder = Path(os.path.abspath(Path(trials_root) / name))
    stream_log = Path(trials_root) / f"{name}.stream.jsonl"
    sessions_dir = Path(projects_root) / mangle_path(folder)
    transcript: Path | None = None
    if stream_log.is_file():
        transcript = stream_log
    elif sessions_dir.is_dir():
        candidates = [path for path in sessions_dir.glob("*.jsonl") if path.is_file()]
        if candidates:
            transcript = max(candidates, key=lambda path: path.stat().st_mtime)
    return TrialFiles(
        run=run,
        folder=folder,
        script=folder / "inputs" / "script.py",
        stream_log=stream_log,
        sessions_dir=sessions_dir,
        transcript=transcript,
    )


# --------------------------------------------------------------------------
# Replays and controls
# --------------------------------------------------------------------------


def replay_summary(result: ReplayResult) -> str:
    """One short phrase for a replay's outcome."""
    if result.timed_out:
        return "timed out"
    where = f" at line {result.failing_line}" if result.failing_line is not None else ""
    return f"exit {result.exit_code}{where}"


def replay_record(result: ReplayResult | None) -> dict[str, object] | None:
    """The ``replay`` field of a trials.jsonl line."""
    if result is None:
        return None
    return {
        "exit_code": result.exit_code,
        "failing_line": result.failing_line,
        "timed_out": result.timed_out,
    }


class _Replays:
    """Runs replays one at a time, counting them and sharing results by fix hash."""

    def __init__(self, fn: ReplayFn | None, timeout_s: int, out: Out) -> None:
        self._fn = fn
        self._timeout_s = timeout_s
        self._out = out
        self.count = 0
        # fix hash -> (result, who ran it: "control" or a run number)
        self._cache: dict[str, tuple[ReplayResult, str]] = {}

    def fresh(self, script: Path) -> ReplayResult:
        """Replay ``script`` now, whatever has been replayed before."""
        # Resolved at call time so tests can monkeypatch scriptfix.replay.replay.
        fn = self._fn if self._fn is not None else replay_module.replay
        self.count += 1
        return fn(script, python=Path(sys.executable), timeout_s=self._timeout_s)

    def seed(self, key: str, result: ReplayResult) -> None:
        """Remember a control's result for trials with the same fix hash."""
        self._cache.setdefault(key, (result, "control"))

    def for_trial(self, key: str, script: Path, run: int) -> tuple[ReplayResult, str]:
        """Return ``(result, note)`` for a trial, replaying only if unseen."""
        if key in self._cache:
            result, origin = self._cache[key]
            note = "reused control" if origin == "control" else f"shared with run {origin}"
            return result, note
        self._out(f"  replaying run {run} ...")
        result = self.fresh(script)
        self._cache[key] = (result, str(run))
        return result, replay_summary(result)


def _surprise_reference(result: ReplayResult) -> str | None:
    if result.exit_code == 0 and not result.timed_out:
        return None
    return "the reference should exit 0"


def _surprise_input(result: ReplayResult, fails_at: int) -> str | None:
    if result.timed_out:
        return "the broken input timed out; it should fail"
    if result.exit_code in (0, None):
        return "the broken input should fail, but exited 0"
    if result.failing_line != fails_at:
        return f"the broken input should fail at line {fails_at}"
    return None


def _surprise_message(label: str, why: str, result: ReplayResult) -> str:
    tail = result.output.rstrip().splitlines()[-CONTROL_OUTPUT_LINES:]
    shown = "\n".join(f"    {line}" for line in tail) or "    (no output)"
    return (
        f"{label} control failed: {why} (exit code {result.exit_code}, "
        f"failing line {result.failing_line}, timed out {result.timed_out}).\n"
        f"  Last lines of output:\n{shown}"
    )


def _run_controls(
    replays: _Replays, case: Case, phase: str, out: Out
) -> tuple[str | None, ReplayResult | None, ReplayResult | None]:
    """Replay the reference, then the input; stop at the first surprise.

    Returns ``(failure message or None, reference result, input result)``.
    Stopping early spares the public site a replay it has no use for.
    """
    reference = replays.fresh(case.reference_script)
    out(f"{phase} control, reference: {replay_summary(reference)}")
    why = _surprise_reference(reference)
    if why:
        return _surprise_message(f"{phase} reference", why, reference), reference, None
    broken = replays.fresh(case.input_script)
    out(f"{phase} control, input: {replay_summary(broken)}")
    why = _surprise_input(broken, case.fails_at)
    if why:
        return _surprise_message(f"{phase} input", why, broken), reference, broken
    return None, reference, broken


# --------------------------------------------------------------------------
# Per-trial verdicts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialOutcome:
    """The graded result of one run, before it is recorded."""

    run: int
    verdict: str
    tags: tuple[str, ...]
    detail: str = ""
    fix: str | None = None
    script_data: bytes | None = None
    replay: ReplayResult | None = None
    replay_note: str = ""
    model: str | None = None
    cli: str | None = None
    session: str | None = None
    cost_usd: float | None = None


@dataclass
class _Loaded:
    """What was found for a run: script bytes, parsed transcript, problems."""

    data: bytes | None = None
    transcript: Transcript | None = None
    problems: list[str] = field(default_factory=list)


def _load(files: TrialFiles) -> _Loaded:
    loaded = _Loaded()
    if files.script.is_file():
        loaded.data = files.script.read_bytes()
    else:
        loaded.problems.append(f"missing script: {files.script}")
    if files.transcript is None:
        loaded.problems.append(
            f"missing transcript: no {files.stream_log.name} and no *.jsonl in {files.sessions_dir}"
        )
    else:
        try:
            loaded.transcript = read_transcript(files.transcript)
        except (OSError, ValueError) as exc:
            loaded.problems.append(f"unreadable transcript {files.transcript}: {exc}")
    return loaded


def _base(files: TrialFiles, loaded: _Loaded) -> TrialOutcome:
    """An outcome carrying only the metadata every verdict shares."""
    t = loaded.transcript
    return TrialOutcome(
        run=files.run,
        verdict=VERDICT_INVALID,
        tags=(),
        fix=fix_hash(loaded.data) if loaded.data is not None else None,
        script_data=loaded.data,
        model=t.model if t else None,
        cli=t.cli_version if t else None,
        session=t.session_id if t else None,
        cost_usd=t.cost_usd if t else None,
    )


def _tags(findings: list[Finding], *severities: str) -> set[str]:
    return {f.tag for f in findings if f.severity in severities}


def _parse(src: str) -> ast.Module | None:
    try:
        return ast.parse(src)
    except (SyntaxError, ValueError):
        return None


def _decide(
    case: Case,
    reference_src: str,
    input_src: str,
    files: TrialFiles,
    loaded: _Loaded,
    replays: _Replays,
) -> TrialOutcome:
    """Apply the verdict rules to one run."""
    base = _base(files, loaded)
    if loaded.problems or loaded.transcript is None or loaded.data is None:
        return replace(
            base,
            verdict=VERDICT_INVALID,
            tags=(TAG_HARNESS_ERROR,),
            detail="; ".join(loaded.problems),
        )

    # Rule 1. An invalid trial records only its invalid tags.
    validity = check_validity(loaded.transcript)
    if validity:
        return replace(
            base,
            verdict=VERDICT_INVALID,
            tags=tuple(sorted(_tags(validity, "invalid"))),
            detail="; ".join(f.detail for f in validity),
        )

    fair_play = check_fair_play(loaded.transcript)
    try:
        fix_src: str | None = loaded.data.decode("utf-8")
    except UnicodeDecodeError:
        fix_src = None
    fix_tree = _parse(fix_src) if fix_src is not None else None

    # Static checks run whenever the script parses, so smell and info tags
    # are recorded even when an earlier rule decides the verdict.
    static: list[Finding] = []
    if fix_src is not None and fix_tree is not None:
        static = check_static(
            reference_src, fix_src, input_src=input_src, expected=case.expected
        )
    soft = _tags(fair_play, SEVERITY_SMELL, SEVERITY_INFO) | _tags(
        static, SEVERITY_SMELL, SEVERITY_INFO
    )

    def outcome(verdict: str, deciding: set[str], **extra: object) -> TrialOutcome:
        return replace(base, verdict=verdict, tags=tuple(sorted(deciding | soft)), **extra)

    # Rule 2.
    fair_zero = _tags(fair_play, SEVERITY_ZERO)
    if fair_zero:
        detail = "; ".join(f.detail for f in fair_play if f.severity == SEVERITY_ZERO)
        return outcome(VERDICT_FAIL, fair_zero, detail=detail)

    # Rule 3.
    if fix_tree is None:
        return outcome(VERDICT_FAIL, {TAG_SYNTAX_ERROR}, detail="the script does not parse")

    # Rule 4. A script equal to the input once parsed changed nothing that matters.
    if case.expected == EXPECTED_FIX:
        input_tree = _parse(input_src)
        if input_tree is not None and ast.dump(input_tree) == ast.dump(fix_tree):
            return outcome(VERDICT_FAIL, {TAG_NO_EDIT}, detail="the script equals the input")

    # Rule 5.
    zero = _tags(static, SEVERITY_ZERO)
    if zero:
        detail = "; ".join(f.detail for f in static if f.severity == SEVERITY_ZERO)
        return outcome(VERDICT_FAIL, zero, detail=detail)

    # Rule 6. Escalate cases never replay.
    result: ReplayResult | None = None
    note = ""
    if case.expected == EXPECTED_FIX:
        result, note = replays.for_trial(base.fix or "", files.script, files.run)
        if result.timed_out or result.exit_code != 0:
            tag = TAG_NOT_FIXED if result.failing_line == case.fails_at else TAG_NEW_FAILURE
            return outcome(VERDICT_FAIL, {tag}, replay=result, replay_note=note)

    # Rule 7.
    judge = _tags(static, SEVERITY_JUDGE)
    if judge or case.expected == EXPECTED_ESCALATE:
        return outcome(VERDICT_PENDING, judge, replay=result, replay_note=note)

    # Rule 8.
    return outcome(VERDICT_PASS, set(), replay=result, replay_note=note)


def _site_changed(outcome: TrialOutcome, detail: str) -> TrialOutcome:
    """Void a trial because a control replay surprised us."""
    return replace(
        outcome,
        verdict=VERDICT_INVALID,
        tags=(TAG_SITE_CHANGED,),
        detail=detail,
        replay=None,
        replay_note="",
    )


# --------------------------------------------------------------------------
# The pipeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GradeResult:
    """What one ``grade`` call did."""

    outcomes: tuple[TrialOutcome, ...]
    control_failure: str | None  # the message, or None when both control sets passed
    replay_count: int
    trials_path: Path
    fixes_written: tuple[Path, ...]

    @property
    def exit_code(self) -> int:
        """0 when the controls held, 1 when one was surprising."""
        return 1 if self.control_failure else 0


def _trial_line(outcome: TrialOutcome) -> str:
    tags = ",".join(outcome.tags) or "-"
    parts = [f"run {outcome.run}: {outcome.verdict} [{tags}]"]
    if outcome.replay_note:
        parts.append(outcome.replay_note)
    if outcome.detail:
        parts.append(f"({outcome.detail})")
    return "  ".join(parts)


def grade(
    case_dir: Path,
    runs: list[int],
    *,
    trials_root: Path | None = None,
    projects_root: Path | None = None,
    effort: str = "default",
    context: str = "none",
    tools: str = "edit-only",
    timeout_s: int = 120,
    date: str | None = None,
    replay_fn: ReplayFn | None = None,
    out: Out = print,
) -> GradeResult:
    """Grade ``runs`` of the case at ``case_dir`` and record the verdicts.

    ``trials_root`` defaults to ``~/eval-trials`` and ``projects_root`` to
    ``~/.claude/projects``. ``replay_fn`` defaults to ``scriptfix.replay.replay``
    looked up at call time. Replays are strictly sequential. Nothing is
    written to the case until every verdict (and the closing controls) is
    in, so a crash leaves the case as it was; and when a control replay is
    surprising nothing is written at all (the batch is void, so earlier
    valid verdicts must survive), though the result still lists every trial
    as ``invalid`` / ``site-changed``.
    """
    case = load_case(Path(case_dir))
    if case.expected not in (EXPECTED_FIX, EXPECTED_ESCALATE):
        raise ValueError(f"unsupported expected value: {case.expected}")
    trials_root = Path(trials_root) if trials_root is not None else Path.home() / "eval-trials"
    projects_root = (
        Path(projects_root) if projects_root is not None else Path.home() / ".claude" / "projects"
    )
    when = date if date is not None else datetime.date.today().isoformat()
    reference_bytes = case.reference_script.read_bytes()
    input_bytes = case.input_script.read_bytes()
    reference_src = reference_bytes.decode("utf-8")
    input_src = input_bytes.decode("utf-8")

    replays = _Replays(replay_fn, timeout_s, out)
    files = [locate_trial(case.number, run, trials_root, projects_root) for run in runs]
    loads = [_load(item) for item in files]

    out(f"grading {case.slug} under {RUBRIC}: runs {', '.join(str(run) for run in runs)}")
    failure, reference_result, input_result = _run_controls(replays, case, "opening", out)
    outcomes: list[TrialOutcome] = []
    if failure:
        out(failure)
        out("opening controls failed: no trial replayed, closing controls skipped")
        outcomes = [
            _site_changed(_base(item, loaded), "the opening control failed")
            for item, loaded in zip(files, loads, strict=True)
        ]
    else:
        assert reference_result is not None and input_result is not None
        replays.seed(fix_hash(reference_bytes), reference_result)
        replays.seed(fix_hash(input_bytes), input_result)
        for item, loaded in zip(files, loads, strict=True):
            outcomes.append(_decide(case, reference_src, input_src, item, loaded, replays))
        failure, _closing_reference, _closing_input = _run_controls(replays, case, "closing", out)
        if failure:
            out(failure)
            out("closing controls failed: every trial of this invocation is invalid")
            outcomes = [_site_changed(item, "the closing control failed") for item in outcomes]

    for item in outcomes:
        out(_trial_line(item))

    trials_path = case.grading_dir / "trials.jsonl"
    fixes_written: list[Path] = []
    if failure:
        # A surprising control voids the batch (rubric-v0, Invalid trials):
        # record nothing, so earlier valid verdicts survive an outage.
        out("control failed: nothing recorded")
    else:
        # Fixes first: they are the evidence behind each line.
        for item in outcomes:
            if item.script_data is not None:
                digest, written = save_fix(case.grading_dir, item.script_data)
                if written:
                    fixes_written.append(case.grading_dir / "fixes" / f"{digest}.py")
        records = [
            make_record(
                run=item.run,
                date=when,
                rubric=RUBRIC,
                grader=__version__,
                subject={
                    "model": item.model,
                    "effort": effort,
                    "context": context,
                    "tools": tools,
                    "cli": item.cli,
                },
                verdict=item.verdict,
                tags=item.tags,
                fix=item.fix,
                session=item.session,
                cost_usd=item.cost_usd,
                replay=replay_record(item.replay),
            )
            for item in outcomes
        ]
        update_trials(trials_path, records)

    counts: dict[str, int] = {}
    for item in outcomes:
        counts[item.verdict] = counts.get(item.verdict, 0) + 1
    summary = ", ".join(f"{verdict} {count}" for verdict, count in sorted(counts.items()))
    out(f"summary: {summary or 'no runs'}")
    out(f"replays run: {replays.count}")
    if not failure:
        out(f"wrote {trials_path}")
        for path in fixes_written:
            out(f"wrote {path}")

    return GradeResult(
        outcomes=tuple(outcomes),
        control_failure=failure,
        replay_count=replays.count,
        trials_path=trials_path,
        fixes_written=tuple(fixes_written),
    )
