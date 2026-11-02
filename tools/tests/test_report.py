"""Tests for scriptfix.report: aggregation and formatting."""

from __future__ import annotations

import json
from pathlib import Path

from scriptfix.record import make_record, write_trials
from scriptfix.report import find_case_dirs, format_rows, report, summarize
from scriptfix.stats import lower_bound


def rec(run: int, verdict: str, tags: list[str] | None = None, model: str = "m1", effort: str = "default") -> dict:
    return make_record(
        run=run,
        date="2026-10-31",
        rubric="script-fix-v0",
        grader="0.1.0",
        subject={"model": model, "effort": effort, "context": "none", "tools": "edit-only", "cli": "1"},
        verdict=verdict,
        tags=tags or [],
        fix=None,
        session=None,
        cost_usd=None,
        replay=None,
    )


def test_counts_lower_bound_and_pending_policy() -> None:
    records = [
        rec(1, "pass"),
        rec(2, "pass"),
        rec(3, "pass"),
        rec(4, "fail", ["new-failure"]),
        rec(5, "invalid", ["harness-error"]),
        rec(6, "pending-judge", ["retargeted"]),
    ]
    (row,) = summarize("01-x", records)
    # Pending trials are left out of passes/valid until the judge resolves them.
    assert (row.passes, row.valid) == (3, 4)
    assert row.rate == 0.75
    assert row.lower == lower_bound(3, 4)
    assert (row.pending, row.invalid) == (1, 1)


def test_needs_review_has_its_own_count_and_is_left_out_of_passes() -> None:
    records = [
        rec(1, "pass"),
        rec(2, "fail", ["not-fixed"]),
        rec(3, "needs-review", ["retargeted"]),
        rec(4, "needs-review", ["new-wait"]),
        rec(5, "pending-judge", ["retargeted"]),
        rec(6, "invalid", ["harness-error"]),
    ]
    (row,) = summarize("01-x", records)
    assert (row.passes, row.valid) == (1, 2)
    assert (row.pending, row.review, row.invalid) == (1, 2, 1)
    assert "  pending 1  review 2  invalid 1  " in format_rows([row])


def test_groups_by_subject() -> None:
    records = [rec(1, "pass", model="a"), rec(2, "fail", ["x"], model="a"), rec(1, "pass", model="b", effort="high")]
    rows = summarize("01-x", records)
    assert [(r.model, r.effort, r.passes, r.valid) for r in rows] == [("a", "default", 1, 2), ("b", "high", 1, 1)]


def test_top_three_tags_ties_broken_alphabetically() -> None:
    records = [
        rec(1, "fail", ["zeta", "alpha"]),
        rec(2, "fail", ["zeta", "beta"]),
        rec(3, "fail", ["zeta", "gamma"]),
        rec(4, "fail", ["beta"]),
    ]
    (row,) = summarize("01-x", records)
    assert row.top_tags == (("zeta", 3), ("beta", 2), ("alpha", 1))


def test_no_valid_trials_has_no_rate() -> None:
    (row,) = summarize("01-x", [rec(1, "invalid", ["harness-error"])])
    assert row.rate is None and row.lower == 0.0
    assert "rate n/a" in format_rows([row])


def test_format_rows_shows_the_numbers() -> None:
    (row,) = summarize("01-x", [rec(1, "pass"), rec(2, "fail", ["not-fixed"])])
    text = format_rows([row])
    assert text.splitlines()[0] == "01-x"
    assert "1/2" in text and "50.0%" in text and f"{lower_bound(1, 2):.3f}" in text
    assert "not-fixed (1)" in text
    assert format_rows([]) == "no trials recorded"


def test_report_reads_trials_files_and_finds_cases(tmp_path: Path) -> None:
    for slug in ("01-a", "02-b", "03-none"):
        (tmp_path / "evals" / slug / "grading").mkdir(parents=True)
    write_trials(tmp_path / "evals" / "01-a" / "grading" / "trials.jsonl", [rec(1, "pass")])
    write_trials(tmp_path / "evals" / "02-b" / "grading" / "trials.jsonl", [rec(1, "fail", ["sleep"])])
    assert [p.name for p in find_case_dirs(tmp_path)] == ["01-a", "02-b"]

    both = report(repo_root=tmp_path)
    assert "01-a" in both and "02-b" in both and "03-none" not in both
    one = report([tmp_path / "evals" / "02-b"])
    assert "02-b" in one and "01-a" not in one
    assert report(repo_root=tmp_path / "nowhere") == "no trials recorded"
    # a report line is plain JSON-derived text, never a crash on odd subjects
    path = tmp_path / "evals" / "01-a" / "grading" / "trials.jsonl"
    path.write_text(json.dumps({"run": 1, "rubric": "r", "verdict": "pass"}) + "\n", encoding="utf-8")
    assert "?" in report([tmp_path / "evals" / "01-a"])
