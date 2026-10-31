"""Command line: ``python -m scriptfix grade ...`` and ``python -m scriptfix report``.

Wiring only: argument parsing here, the work in ``grade.py`` and
``report.py``. Exit codes: 0 success, 1 a control replay was surprising
(the batch is void), 2 usage errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scriptfix import RUBRIC, __version__
from scriptfix.grade import grade, parse_runs
from scriptfix.report import report

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
            "grade saved trials of a script-fix case and report pass rates. "
            "Everything except the LLM judge."
        ),
        epilog="Exit codes: 0 ok, 1 a control replay was surprising, 2 usage error.",
    )
    sub = parser.add_subparsers(dest="command", metavar="{grade,report}", required=True)

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
    grader.add_argument("--effort", default="default", help="subject effort to record (default: default)")
    grader.add_argument("--context", default="none", help="subject context files to record (default: none)")
    grader.add_argument("--tools", default="edit-only", help="subject tool profile to record (default: edit-only)")
    grader.add_argument("--timeout", type=int, default=120, help="seconds before a replay is killed (default: 120)")

    reporter = sub.add_parser(
        "report",
        help="print pass rates per case and subject",
        description=(
            "Print, per case and subject (model, effort, context, tools): passes/valid, "
            "rate, the 95% lower bound, pending and invalid counts and the most common "
            "tags. Pending-judge trials are left out of passes/valid until judged."
        ),
    )
    reporter.add_argument(
        "--case",
        action="append",
        type=Path,
        default=None,
        help="an eval directory (repeatable; default: every evals/*/ with a grading/trials.jsonl)",
    )
    return parser


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
