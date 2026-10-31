"""The grading record: fix hashes, saved fixes and a case's trials.jsonl.

A case keeps, under ``grading/``, every model script it has graded
(``fixes/<hash>.py``, byte for byte) and one JSON line per (run, rubric) in
``trials.jsonl``. Re-grading a run replaces its line; lines of other
rubrics are left alone. Files are UTF-8 with LF line endings whatever the
host's text-mode default is.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

HASH_LENGTH = 12

# The order of the keys in every trials.jsonl line (plan, "Record").
RECORD_FIELDS = (
    "run",
    "date",
    "rubric",
    "grader",
    "subject",
    "verdict",
    "tags",
    "fix",
    "judge",
    "session",
    "cost_usd",
    "replay",
)
SUBJECT_FIELDS = ("model", "effort", "context", "tools", "cli")


def fix_hash(data: bytes) -> str:
    """Return the first 12 hex digits of the script's normalized SHA-256.

    The digest is over ``ast.dump(ast.parse(source))`` so formatting, quotes
    and comments don't make two equal scripts differ; a script that doesn't
    parse (or isn't UTF-8) is hashed over its raw bytes instead.
    """
    try:
        digest_input = ast.dump(ast.parse(data.decode("utf-8"))).encode("utf-8")
    except (SyntaxError, ValueError):  # UnicodeDecodeError and null bytes are ValueErrors
        digest_input = data
    return hashlib.sha256(digest_input).hexdigest()[:HASH_LENGTH]


def save_fix(grading_dir: Path, data: bytes) -> tuple[str, bool]:
    """Copy ``data`` to ``<grading_dir>/fixes/<hash>.py`` unless it is there.

    Returns ``(hash, written)``. An existing file is kept as is: the hash
    names the normalized script, and the first byte-exact copy stays the
    record.
    """
    digest = fix_hash(data)
    target = Path(grading_dir) / "fixes" / f"{digest}.py"
    if target.exists():
        return digest, False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return digest, True


def make_record(
    *,
    run: int,
    date: str,
    rubric: str,
    grader: str,
    subject: dict[str, object],
    verdict: str,
    tags: list[str] | tuple[str, ...],
    fix: str | None,
    session: str | None,
    cost_usd: float | None,
    replay: dict[str, object] | None,
) -> dict[str, object]:
    """Build one trials.jsonl record with its fields in the documented order."""
    return {
        "run": run,
        "date": date,
        "rubric": rubric,
        "grader": grader,
        "subject": {name: subject.get(name) for name in SUBJECT_FIELDS},
        "verdict": verdict,
        "tags": sorted(set(tags)),
        "fix": fix,
        "judge": [],  # filled in by the judge stage, not this one
        "session": session,
        "cost_usd": cost_usd,
        "replay": replay,
    }


def read_trials(path: Path) -> list[dict[str, object]]:
    """Read trials.jsonl; a missing file is an empty list.

    Raises ValueError naming the line number for a line that isn't a JSON
    object with ``run`` and ``rubric``.
    """
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    text = path.read_text(encoding="utf-8")
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"{path} line {number}: not valid JSON ({exc})") from exc
        if not isinstance(obj, dict) or "run" not in obj or "rubric" not in obj:
            raise ValueError(f"{path} line {number}: expected an object with 'run' and 'rubric'")
        records.append(obj)
    return records


def merge_trials(
    existing: list[dict[str, object]], new: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Return ``existing`` with ``new`` replacing lines of the same (run, rubric).

    The result is sorted by run, then rubric, so the file is stable under
    re-grading in any order.
    """
    merged = {(rec["run"], rec["rubric"]): rec for rec in existing}
    for rec in new:
        merged[(rec["run"], rec["rubric"])] = rec
    return [merged[key] for key in sorted(merged, key=lambda key: (int(key[0]), str(key[1])))]


def write_trials(path: Path, records: list[dict[str, object]]) -> None:
    """Write ``records`` as JSON Lines: UTF-8, LF, non-ASCII kept as is."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")


def update_trials(path: Path, new: list[dict[str, object]]) -> list[dict[str, object]]:
    """Merge ``new`` into the file at ``path`` and rewrite it; return the result."""
    merged = merge_trials(read_trials(path), new)
    write_trials(path, merged)
    return merged
