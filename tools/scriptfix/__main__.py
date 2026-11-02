"""Command line: ``python -m scriptfix grade ...``, ``judge``, ``calibrate``, ``report``, ``make-case`` and ``run``.

Wiring only: argument parsing here, the work in ``grade.py``, ``judge.py``,
``calibrate.py``, ``report.py``, ``makecase.py`` and ``run.py``. Exit codes:
0 success, 1 a control replay was surprising (the batch is void), a
make-case capture was (nothing written), a trial run hit a harness problem
(or the self-test failed), a judged trial erred, the judge is not
calibrated, or a calibration missed, erred or ran out of budget, 2 usage
errors (a bad ``reviews.toml`` included).
"""

from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

from scriptfix import RUBRIC, __version__
from scriptfix.calibrate import CALIBRATION_SAMPLES, DEFAULT_MAX_TOTAL_USD, calibrate
from scriptfix.grade import grade, parse_runs
from scriptfix.judge import NotCalibrated, judge_trials
from scriptfix.judgeprompt import JUDGE_DIR, Answer, AskFn, ask_claude
from scriptfix.makecase import make_case
from scriptfix.report import REPO_ROOT, report
from scriptfix.run import (
    CONTEXTS,
    DEFAULT_SELF_TEST_TIMEOUT_S,
    DEFAULT_TRIAL_TIMEOUT_S,
    DEFAULT_TRIALS_ROOT,
    EFFORTS,
    SELF_TEST_MODEL,
    TOOLS,
    resolve_claude,
    resolve_pwsh,
    run_trials,
    self_test,
)

PROG = "python -m scriptfix"


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors point at -h."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\nTry '{self.prog} -h' for usage.\n")


def _runs_arg(text: str) -> list[int]:
    try:
        return parse_runs(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (help text is generated from here)."""
    parser = _Parser(
        prog=PROG,
        description=(
            f"Deterministic grader for rubric {RUBRIC} (grader {__version__}): "
            "grade saved trials of a script-fix case, judge what the static checks "
            "leave to the LLM judge, and report pass rates."
        ),
        epilog=(
            "Exit codes: 0 ok, 1 a control replay or a make-case capture was "
            "surprising, a trial run hit a harness problem (or the self-test "
            "failed), a judged trial erred or the judge is not calibrated, or a "
            "calibration did not pass, 2 usage error."
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="{grade,judge,calibrate,report,make-case,run}", required=True)

    grader = sub.add_parser(
        "grade",
        help="grade saved trials of one case and record them in its trials.jsonl",
        description=(
            "Grade saved trials of one case: transcript validity and fair play, "
            "static checks, one replay per distinct fix (plus control replays of the "
            "reference and the broken input before and after), then record the verdicts "
            "in <case>/grading/trials.jsonl. Replays go one at a time against the "
            "case's target; run only single replays against public sites."
        ),
    )
    grader.add_argument("--case", required=True, type=Path, help="the eval directory, e.g. evals/01-playwright-python-basic")
    grader.add_argument("--runs", required=True, type=_runs_arg, help="runs to grade: 1-12 or 1,3,5-7")
    grader.add_argument(
        "--trials-root",
        type=Path,
        default=None,
        help="folder holding <NN>-run<N>/ trial folders (default: ~/eval-trials)",
    )
    grader.add_argument(
        "--projects-root",
        type=Path,
        default=None,
        help="Claude Code projects folder to find session transcripts (default: ~/.claude/projects)",
    )
    grader.add_argument("--effort", default="default", help="subject effort to record for runs without a <NN>-run<N>.subject.json sidecar (default: default)")
    grader.add_argument("--context", default="none", help="subject context files to record for runs without a <NN>-run<N>.subject.json sidecar (default: none)")
    grader.add_argument("--tools", default="edit-only", help="subject tool profile to record for runs without a <NN>-run<N>.subject.json sidecar (default: edit-only)")
    grader.add_argument("--timeout", type=int, default=120, help="seconds before a replay is killed (default: 120)")

    judger = sub.add_parser(
        "judge",
        help="ask the LLM judge about one case's pending-judge and needs-review trials",
        description=(
            "Judge one case's pending-judge and needs-review trials: one question per judge "
            "flag (plus the escalation question on an escalate case), each answered by the CD's "
            "grading/reviews.toml, else the grading/judge.jsonl cache, else one claude -p call "
            "(a paid Sonnet call, appended to the cache at once). Any cheat makes the trial a "
            "fail, else any unsure makes it needs-review, else it passes. No retries: a re-run "
            "resumes from the cache. Refuses to ask while the recorded calibration doesn't match "
            "the judge. Never replays a script; a record whose judge flags no longer match a "
            "fresh static check is stale and left alone."
        ),
        epilog=(
            "Prints run N: <verdict> [<tags>] per trial and one line per question, then "
            "JUDGED= ASKED= CACHED= REVIEWED= ERRORS= COST_USD= (with --dry-run, ASK=<n>). "
            "Exit codes: 0 done or nothing to judge, 1 a trial erred or the judge is not "
            "calibrated, 2 usage error (a bad reviews.toml, or no claude when one is needed)."
        ),
    )
    judger.add_argument("--case", required=True, type=Path, help="the eval directory, e.g. evals/01-playwright-python-basic")
    judger.add_argument("--runs", type=_runs_arg, default=None, help="runs to judge: 1-12 or 1,3,5-7 (default: every pending-judge or needs-review run)")
    judger.add_argument(
        "--trials-root",
        type=Path,
        default=None,
        help="folder holding the trials' stream logs, for escalate cases' responses (default: ~/eval-trials)",
    )
    judger.add_argument(
        "--projects-root",
        type=Path,
        default=None,
        help="Claude Code projects folder to find session transcripts (default: ~/.claude/projects)",
    )
    judger.add_argument("--claude", type=Path, default=None, help="the claude executable (default: claude on PATH; looked up only when a question is asked)")
    judger.add_argument("--dry-run", action="store_true", help="list each trial's questions and how many would be asked; ask nothing, write nothing, skip the calibration check")

    calibrator = sub.add_parser(
        "calibrate",
        help="ask the judge every labeled corpus item and check it agrees",
        description=(
            "Calibrate the judge: ask it every item labeled in the cases' "
            "grading/corpus/judge.toml files, SAMPLES times each, one call at a time, "
            "with the prompt a real trial would get. It passes only when every answer "
            "equals its label (unsure is a miss). A full pass with at least "
            f"{CALIBRATION_SAMPLES} samples is recorded in the judge folder's calibration.json. "
            "Never reads or writes a judge.jsonl. Each call costs money; --dry-run asks nothing."
        ),
        epilog=(
            "Prints ITEM=<id> LABEL=<answer> GOT=<answers> OK|MISS per item, then CALLS=, "
            "COST_USD=, CALIBRATION=pass|fail|error|budget and RECORDED=<path>|no. "
            "Exit codes: 0 a pass or a dry run, 1 a miss, an error or the budget, 2 usage error."
        ),
    )
    calibrator.add_argument("--samples", type=int, default=CALIBRATION_SAMPLES, help=f"times to ask each item, at least 1 (default: {CALIBRATION_SAMPLES}; fewer is never recorded)")
    calibrator.add_argument(
        "--items",
        action="append",
        default=None,
        metavar="ID",
        help="ask only this item id (repeatable, or comma-separated); the result is never recorded",
    )
    calibrator.add_argument("--max-total-usd", type=float, default=DEFAULT_MAX_TOTAL_USD, help=f"stop with CALIBRATION=budget once the running cost passes this, above 0 (default: {DEFAULT_MAX_TOTAL_USD})")
    calibrator.add_argument("--log", type=Path, default=None, help="append one JSON line per answered sample (answer, quote, reason, cost) to this file")
    calibrator.add_argument("--claude", type=Path, default=None, help="the claude executable (default: claude on PATH; not needed with --dry-run)")
    calibrator.add_argument("--dry-run", action="store_true", help="print each item's prompt length and the number of calls; ask nothing and write nothing")
    calibrator.add_argument("--prompts-dir", type=Path, default=None, help="with --dry-run, write each prompt to <dir>/<n>.txt, numbered in item id order")

    reporter = sub.add_parser(
        "report",
        help="print pass rates per case and subject",
        description=(
            "Print, per case and subject (model, effort, context, tools): passes/valid, "
            "rate, the 95% lower bound, pending, review and invalid counts and the most "
            "common tags. Pending-judge trials are left out of passes/valid until judged, "
            "and needs-review trials until the CD decides."
        ),
    )
    reporter.add_argument(
        "--case",
        action="append",
        type=Path,
        default=None,
        help="an eval directory (repeatable; default: every evals/*/ with a grading/trials.jsonl)",
    )

    maker = sub.add_parser(
        "make-case",
        help="build a case from its recipe and capture its evidence",
        description=(
            "Build a case's reference and broken input from <case>/grading/recipe.toml, "
            "replay each once (the reference first; the input in a neutral temp folder, "
            "with the capture venv's python) and, only if the reference passes and the "
            "input fails at the case's fails_at line, write the scripts, prompt.md, "
            "inputs/results.txt, inputs/script.pwtrace.zip and grading/capture.toml. "
            "A surprise writes nothing. Exactly two replays, one at a time; run only "
            "single replays against public sites."
        ),
    )
    maker.add_argument("--case", required=True, type=Path, help="the eval directory, e.g. evals/02-docs-journey-a")
    maker.add_argument(
        "--python",
        required=True,
        type=Path,
        help="the capture venv's python (not checked with --dry-run)",
    )
    maker.add_argument("--timeout", type=int, default=120, help="seconds before a replay is killed (default: 120)")
    maker.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff reference -> input and the planned replays; replay and write nothing",
    )

    runner = sub.add_parser(
        "run",
        help="run a case's one-shot headless trials, or check the launcher (--self-test)",
        description=(
            "Run N one-shot headless trials of a case with claude, strictly one at a time. "
            "Each trial runs in a fresh <trials-root>/<NN>-run<N>/ holding only prompt.md and "
            "inputs/; its stream log, stderr file and subject sidecar land beside that folder, "
            "where the grader looks. The parent session's variables are stripped from claude's "
            "environment and the real pwsh.exe goes first on its PATH. The batch stops at the "
            "first harness problem (a non-zero exit, a timeout, no result line). "
            "--self-test checks the launcher itself with one cheap run instead."
        ),
        epilog=(
            "Exit codes: 0 ok, 1 a harness problem or a failed self-test, 2 usage error. "
            "A trial is a real model call that costs money; only the self-test needs no case."
        ),
    )
    runner.add_argument("--case", type=Path, default=None, help="the eval directory, e.g. evals/02-docs-journey-a")
    runner.add_argument(
        "--model",
        default=None,
        help=f"model id, passed through to claude as given (required for trials; --self-test defaults to {SELF_TEST_MODEL})",
    )
    how_many = runner.add_mutually_exclusive_group()
    how_many.add_argument("--count", type=int, default=None, help="run this many new trials, numbered after the highest existing run")
    how_many.add_argument("--runs", type=_runs_arg, default=None, help="run exactly these numbers: 13 or 1,3,5-7 (none may exist yet)")
    runner.add_argument("--effort", choices=EFFORTS, default="default", help="claude's --effort; default omits the flag (default: default)")
    runner.add_argument("--context", choices=CONTEXTS, default="none", help="context files given to the subject (default: none)")
    runner.add_argument("--tools", choices=TOOLS, default="edit-only", help="the subject's tool profile (default: edit-only): the built-in tools Read, Glob, Grep, Edit, Write, Bash and PowerShell, with Edit and Write limited to the case's script; no web tools")
    runner.add_argument(
        "--trials-root",
        type=Path,
        default=DEFAULT_TRIALS_ROOT,
        help=f"folder that receives the trial folders and logs (default: {DEFAULT_TRIALS_ROOT.as_posix()})",
    )
    runner.add_argument("--claude", type=Path, default=None, help="the claude executable (default: claude on PATH)")
    runner.add_argument("--pwsh", type=Path, default=None, help="the real pwsh.exe to put first on PATH, e.g. (Get-Process -Id $PID).Path (default: pwsh on PATH, unless that is the app-execution alias)")
    runner.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=f"seconds before a trial is killed (default: {DEFAULT_TRIAL_TIMEOUT_S}; {DEFAULT_SELF_TEST_TIMEOUT_S} with --self-test)",
    )
    runner.add_argument("--dry-run", action="store_true", help="print the run numbers, folders, claude command lines and the environment names to strip; create and launch nothing")
    runner.add_argument("--self-test", action="store_true", help="run the cheap harness check instead of a case (about $0.01); takes no --case, --count, --runs or --dry-run")
    return parser


def _run_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """The ``run`` subcommand: validate the arguments, then launch trials or the self-test."""
    if args.self_test:
        for flag, given in (
            ("--case", args.case is not None),
            ("--count", args.count is not None),
            ("--runs", args.runs is not None),
            ("--dry-run", args.dry_run),
        ):
            if given:
                parser.error(f"{flag} is not used with --self-test")
        model = args.model or SELF_TEST_MODEL
        timeout_s = DEFAULT_SELF_TEST_TIMEOUT_S if args.timeout is None else args.timeout
    else:
        if args.case is None:
            parser.error("--case is required (or use --self-test)")
        if args.model is None:
            parser.error("--model is required (or use --self-test)")
        if args.count is None and args.runs is None:
            parser.error("give --count N or --runs LIST")
        if not args.case.is_dir():
            parser.error(f"--case is not a directory: {args.case}")
        model = args.model
        timeout_s = DEFAULT_TRIAL_TIMEOUT_S if args.timeout is None else args.timeout
    if timeout_s < 1:
        parser.error("--timeout must be at least 1 second")
    try:
        pwsh = resolve_pwsh(args.pwsh)
        claude = resolve_claude(args.claude)
        if args.self_test:
            return self_test(
                model=model,
                trials_root=args.trials_root,
                claude_cmd=[str(claude)],
                pwsh=pwsh,
                timeout_s=timeout_s,
            )
        return run_trials(
            args.case,
            model=model,
            effort=args.effort,
            runs=args.runs,
            count=args.count,
            trials_root=args.trials_root,
            claude_cmd=[str(claude)],
            pwsh=pwsh,
            timeout_s=timeout_s,
            dry_run=args.dry_run,
            context=args.context,
            tools=args.tools,
        )
    except ValueError as exc:  # raised before the first launch
        parser.error(str(exc))
        return 2  # parser.error exits; keeps the return type honest


def _calibrate_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """The ``calibrate`` subcommand: validate the arguments, then calibrate (or dry-run)."""
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if not args.max_total_usd > 0:
        parser.error("--max-total-usd must be above 0")
    only = None
    if args.items is not None:
        only = [part.strip() for value in args.items for part in value.split(",") if part.strip()]
        if not only:
            parser.error("--items needs at least one item id")
    try:
        ask_fn = None
        if not args.dry_run:  # a dry run needs no claude
            ask_fn = functools.partial(ask_claude, claude_cmd=[str(resolve_claude(args.claude))])
        return calibrate(
            ask_fn=ask_fn,
            repo_root=REPO_ROOT,
            judge_dir=JUDGE_DIR,
            samples=args.samples,
            only=only,
            max_total_usd=args.max_total_usd,
            log=args.log,
            dry_run=args.dry_run,
            prompts_dir=args.prompts_dir,
        )
    except ValueError as exc:  # an unknown item id, a missing claude, a broken label
        parser.error(str(exc))
        return 2  # parser.error exits; keeps the return type honest


def _judge_ask(claude: Path | None) -> AskFn:
    """The real ask function. ``claude`` is resolved on the first question, so a dry run never needs it.

    A missing ``claude`` raises ``ValueError`` then, a usage error.
    """
    claude_cmd: list[str] = []

    def ask(prompt: str) -> Answer:
        if not claude_cmd:
            claude_cmd.append(str(resolve_claude(claude)))
        return ask_claude(prompt, claude_cmd=claude_cmd)

    return ask


def _judge_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """The ``judge`` subcommand: validate the arguments, then judge (or dry-run)."""
    if not args.case.is_dir():
        parser.error(f"--case is not a directory: {args.case}")
    try:
        result = judge_trials(
            args.case,
            args.runs,
            ask_fn=_judge_ask(args.claude),
            trials_root=args.trials_root,
            projects_root=args.projects_root,
            judge_dir=JUDGE_DIR,
            dry_run=args.dry_run,
        )
    except NotCalibrated as exc:
        print(f"{PROG} judge: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:  # a bad case.toml, trials.jsonl, judge.jsonl or reviews.toml; no claude
        parser.error(str(exc))
        return 2  # parser.error exits; keeps the return type honest
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    """Run the command line; returns the process exit code."""
    # The console may not be UTF-8 and the output can contain characters like
    # the guillemets in Eval 01's page text; never crash on them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "grade":
        if not args.case.is_dir():
            parser.error(f"--case is not a directory: {args.case}")
        if args.timeout < 1:
            parser.error("--timeout must be at least 1 second")
        try:
            result = grade(
                args.case,
                args.runs,
                trials_root=args.trials_root,
                projects_root=args.projects_root,
                effort=args.effort,
                context=args.context,
                tools=args.tools,
                timeout_s=args.timeout,
            )
        except ValueError as exc:  # a bad case.toml or trials.jsonl
            parser.error(str(exc))
        return result.exit_code

    if args.command == "make-case":
        if not args.case.is_dir():
            parser.error(f"--case is not a directory: {args.case}")
        if args.timeout < 1:
            parser.error("--timeout must be at least 1 second")
        if not args.dry_run and not args.python.is_file():
            parser.error(f"--python is not a file: {args.python}")
        try:
            return make_case(
                args.case,
                repo_root=REPO_ROOT,
                python=args.python,
                timeout_s=args.timeout,
                dry_run=args.dry_run,
            )
        except ValueError as exc:  # a bad case.toml or recipe.toml
            parser.error(str(exc))

    if args.command == "run":
        return _run_command(parser, args)

    if args.command == "judge":
        return _judge_command(parser, args)

    if args.command == "calibrate":
        return _calibrate_command(parser, args)

    for case in args.case or []:
        if not case.is_dir():
            parser.error(f"--case is not a directory: {case}")
    try:
        print(report(args.case))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
