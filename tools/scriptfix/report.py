"""Pass rates per case and subject, read from each case's trials.jsonl.

``summarize`` is a pure function over trial records; ``format_rows`` turns
its rows into text. A subject is (model, effort, context, tools).

Counting rule: ``valid`` trials are the ones with verdict ``pass`` or
``fail``. ``pending-judge`` trials are excluded from ``passes/valid`` until
the judge resolves them (they could still turn into either), and ``invalid``
trials are excluded as the rubric says. Both are shown as their own counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from scriptfix.record import read_trials
from scriptfix.stats import lower_bound

# tools/scriptfix/report.py -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
TOP_TAGS = 3


@dataclass(frozen=True)
class Row:
    """One case x rubric x subject line of the report."""

    case: str
    rubric: str
    model: str
    effort: str
    context: str
    tools: str
    passes: int
    valid: int
    rate: float | None  # None when there are no valid trials
    lower: float  # one-sided 95% lower bound on the pass rate
    pending: int
    invalid: int
    top_tags: tuple[tuple[str, int], ...]  # (tag, count), most common first


def _label(value: object) -> str:
    return "?" if value is None else str(value)


def summarize(case: str, records: list[dict[str, object]]) -> list[Row]:
    """Group one case's records by rubric and subject and count them."""
    groups: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = {}
    for rec in records:
        subject = rec.get("subject")
        subject = subject if isinstance(subject, dict) else {}
        key = (
            _label(rec.get("rubric")),
            _label(subject.get("model")),
            _label(subject.get("effort")),
            _label(subject.get("context")),
            _label(subject.get("tools")),
        )
        groups.setdefault(key, []).append(rec)

    rows: list[Row] = []
    for key in sorted(groups):
        group = groups[key]
        verdicts = Counter(rec.get("verdict") for rec in group)
        passes = verdicts["pass"]
        valid = passes + verdicts["fail"]
        tag_counts: Counter[str] = Counter()
        for rec in group:
            tags = rec.get("tags")
            if isinstance(tags, list):
                tag_counts.update(str(tag) for tag in tags)
        # Count descending, then tag name, so ties are deterministic.
        top = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:TOP_TAGS]
        rows.append(
            Row(
                case=case,
                rubric=key[0],
                model=key[1],
                effort=key[2],
                context=key[3],
                tools=key[4],
                passes=passes,
                valid=valid,
                rate=passes / valid if valid else None,
                lower=lower_bound(passes, valid),
                pending=verdicts["pending-judge"],
                invalid=verdicts["invalid"],
                top_tags=tuple(top),
            )
        )
    return rows


def format_rows(rows: list[Row]) -> str:
    """Render rows as plain text, one block per case."""
    if not rows:
        return "no trials recorded"
    lines: list[str] = []
    current_case = None
    for row in rows:
        if row.case != current_case:
            current_case = row.case
            lines.append(row.case)
        rate = "n/a" if row.rate is None else f"{row.rate * 100:.1f}%"
        tags = ", ".join(f"{tag} ({count})" for tag, count in row.top_tags) or "-"
        lines.append(
            f"  {row.rubric} | model={row.model} effort={row.effort} "
            f"context={row.context} tools={row.tools}"
        )
        lines.append(
            f"    {row.passes}/{row.valid}  rate {rate}  lower95 {row.lower:.3f}  "
            f"pending {row.pending}  invalid {row.invalid}  tags: {tags}"
        )
    return "\n".join(lines)


def find_case_dirs(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Every ``evals/*/`` that has a ``grading/trials.jsonl``, sorted."""
    evals = Path(repo_root) / "evals"
    if not evals.is_dir():
        return []
    return sorted(path for path in evals.iterdir() if (path / "grading" / "trials.jsonl").is_file())


def report(case_dirs: list[Path] | None = None, repo_root: Path = REPO_ROOT) -> str:
    """Build the report text for ``case_dirs`` (default: every recorded case)."""
    dirs = find_case_dirs(repo_root) if case_dirs is None else [Path(path) for path in case_dirs]
    rows: list[Row] = []
    for case_dir in dirs:
        records = read_trials(case_dir / "grading" / "trials.jsonl")
        rows.extend(summarize(case_dir.name, records))
    return format_rows(rows)
