"""Tests for scriptfix.record: hashes, saved fixes and trials.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scriptfix.record import (
    RECORD_FIELDS,
    fix_hash,
    make_record,
    merge_trials,
    read_trials,
    save_fix,
    update_trials,
    write_trials,
)


def record(run: int, rubric: str = "script-fix-v0", verdict: str = "pass", **extra) -> dict:
    fields = dict(
        run=run,
        date="2026-10-31",
        rubric=rubric,
        grader="0.1.0",
        subject={"model": "m", "effort": "default", "context": "none", "tools": "edit-only", "cli": "1"},
        verdict=verdict,
        tags=[],
        fix=None,
        session=None,
        cost_usd=None,
        replay=None,
    )
    fields.update(extra)
    return make_record(**fields)


# -- fix_hash ----------------------------------------------------------------


def test_hash_ignores_formatting_and_comments() -> None:
    a = b"x = 'a'  # one\n"
    b = b'x = "a"\n\n\n# two\n'
    assert fix_hash(a) == fix_hash(b)
    assert len(fix_hash(a)) == 12


def test_hash_differs_for_different_programs() -> None:
    assert fix_hash(b"x = 1\n") != fix_hash(b"x = 2\n")


def test_hash_of_unparsable_script_is_over_raw_bytes() -> None:
    first, second = b"def (:\n", b"def (:  \n"
    assert fix_hash(first) != fix_hash(second)
    assert fix_hash(first) == fix_hash(first)


def test_hash_of_non_utf8_script_does_not_raise() -> None:
    assert len(fix_hash(b"x = '\xff'\n")) == 12


# -- save_fix ----------------------------------------------------------------


def test_save_fix_copies_bytes_exactly_and_keeps_the_first_copy(tmp_path: Path) -> None:
    data = 'x = "»"\r\n'.encode("utf-8")  # CRLF and non-ASCII must survive
    digest, written = save_fix(tmp_path / "grading", data)
    target = tmp_path / "grading" / "fixes" / f"{digest}.py"
    assert written is True
    assert target.read_bytes() == data

    other = b"x = '\xc2\xbb'\n"  # same program, different bytes
    again, written_again = save_fix(tmp_path / "grading", other)
    assert again == fix_hash(other) and written_again is (again != digest)
    assert target.read_bytes() == data  # the earlier copy is not overwritten


# -- make_record / trials.jsonl ----------------------------------------------


def test_make_record_orders_fields_and_sorts_tags() -> None:
    rec = record(3, tags=["sleep", "first-nth", "sleep"])
    assert tuple(rec) == RECORD_FIELDS
    assert rec["tags"] == ["first-nth", "sleep"]
    assert rec["judge"] == []
    assert list(rec["subject"]) == ["model", "effort", "context", "tools", "cli"]


def test_merge_replaces_same_run_and_rubric_and_sorts() -> None:
    existing = [record(2), record(1, verdict="fail"), record(1, rubric="script-fix-v1")]
    merged = merge_trials(existing, [record(1, verdict="pass"), record(3)])
    assert [(r["run"], r["rubric"], r["verdict"]) for r in merged] == [
        (1, "script-fix-v0", "pass"),
        (1, "script-fix-v1", "pass"),
        (2, "script-fix-v0", "pass"),
        (3, "script-fix-v0", "pass"),
    ]


def test_runs_sort_numerically_not_as_text() -> None:
    merged = merge_trials([record(10), record(2)], [record(1)])
    assert [r["run"] for r in merged] == [1, 2, 10]


def test_write_is_utf8_lf_and_keeps_non_ascii(tmp_path: Path) -> None:
    path = tmp_path / "grading" / "trials.jsonl"
    write_trials(path, [record(1, tags=["a"]), record(2)])
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert len(raw.splitlines()) == 2
    write_trials(path, [record(1, session="s»")])
    assert "s»".encode("utf-8") in path.read_bytes()  # not escaped to »
    assert read_trials(path)[0]["session"] == "s»"


def test_update_trials_roundtrip_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    assert read_trials(path) == []
    update_trials(path, [record(2)])
    update_trials(path, [record(1), record(2, verdict="fail")])
    assert [(r["run"], r["verdict"]) for r in read_trials(path)] == [(1, "pass"), (2, "fail")]


def test_read_trials_names_the_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    path.write_text(json.dumps(record(1)) + "\nnot json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        read_trials(path)
    path.write_text('{"run": 1}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_trials(path)
