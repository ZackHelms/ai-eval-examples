"""Calibrating the judge: ask it the labeled corpus items and see whether it agrees.

Every ``evals/*/grading/corpus/judge.toml`` labels questions the judge is
asked about corpus files (and, for an escalate case, about model responses)
with one right answer each. ``calibrate`` asks each item ``samples`` times,
one call at a time, with the same prompt a real trial would get, and passes
only when every sample equals its label (``unsure`` is a miss). A full pass
is recorded in ``rubrics/script-fix/judge/calibration.json``, keyed by the
judge version and a hash of the items, so a changed prompt or label is never
silent: ``calibration_problem`` says what no longer matches.

Calibration is uncached by design: it never reads or writes a ``judge.jsonl``.
The record holds counts and a cost only, never a quote or a reason, because
it lives outside every ``grading/`` folder.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scriptfix.case import load_case
from scriptfix.judgeprompt import (
    JUDGE_DIR,
    JUDGE_MODEL,
    Answer,
    AskFn,
    JudgeError,
    build_prompt,
    judge_version,
    questions_for,
)
from scriptfix.report import REPO_ROOT
from scriptfix.static import EXPECTED_ESCALATE, check_static

CALIBRATION_NAME = "calibration.json"
CALIBRATION_FILE = JUDGE_DIR / CALIBRATION_NAME
# A recorded calibration asks every item at least this many times.
CALIBRATION_SAMPLES = 5
DEFAULT_MAX_TOTAL_USD = 6.0
# Raw: ``\3`` would be an octal escape.
CALIBRATE_COMMAND = r".\30-grade-trials.ps1 -Calibrate"

_ITEM_KEYS = ("file", "question", "answer")


@dataclass(frozen=True)
class Item:
    """One labeled question: a corpus file (and maybe a response) and its right answer."""

    id: str  # "<slug>/<file>#<question>" or "<slug>/<response>#escalation"
    case_dir: Path
    file: str  # the corpus file, relative to grading/corpus
    question: str  # a judgeprompt.Question id
    answer: str  # the label: "ok" or "cheat"
    response: str | None  # a response file relative to grading/corpus, for the escalation question


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def calibration_items(repo_root: Path = REPO_ROOT) -> list[Item]:
    """Every item of every ``evals/*/grading/corpus/judge.toml``, sorted by id.

    Raises ``ValueError`` for a duplicate id or an item without ``file``,
    ``question`` or ``answer``.
    """
    items: dict[str, Item] = {}
    for judge_toml in sorted(Path(repo_root).glob("evals/*/grading/corpus/judge.toml")):
        case_dir = judge_toml.parents[2]
        data = tomllib.loads(judge_toml.read_text(encoding="utf-8"))
        for entry in data.get("item", []):
            for key in _ITEM_KEYS:
                if not isinstance(entry.get(key), str):
                    raise ValueError(f"{judge_toml}: an item needs a string '{key}': {entry}")
            response = entry.get("response")
            name = response if response is not None else entry["file"]
            item_id = f"{case_dir.name}/{name}#{entry['question']}"
            if item_id in items:
                raise ValueError(f"{judge_toml}: the item id '{item_id}' appears twice")
            items[item_id] = Item(
                item_id, case_dir, entry["file"], entry["question"], entry["answer"], response
            )
    return [items[item_id] for item_id in sorted(items)]


def _corpus_dir(item: Item) -> Path:
    return item.case_dir / "grading" / "corpus"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def items_hash(items: list[Item]) -> str:
    """The first 12 hex digits of a SHA-256 over one line per item, in id order.

    A line is the id, the answer, the SHA-256 of the corpus file's bytes and
    the SHA-256 of the response's bytes (empty without one), joined by ``|``.
    """
    lines = []
    for item in sorted(items, key=lambda item: item.id):
        response = _sha256(_corpus_dir(item) / item.response) if item.response else ""
        lines.append("|".join([item.id, item.answer, _sha256(_corpus_dir(item) / item.file), response]))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:12]


def item_prompt(item: Item, *, judge_dir: Path = JUDGE_DIR) -> str:
    """The prompt a real trial would get for this item, the corpus file standing in as the model's script.

    Raises ``ValueError`` when the file's static findings don't make the
    item's question (the label test keeps that from happening).
    """
    case = load_case(item.case_dir)
    reference = case.reference_script.read_text(encoding="utf-8")
    input_src = case.input_script.read_text(encoding="utf-8")
    results = (case.path / "inputs" / "results.txt").read_text(encoding="utf-8")
    fix = (_corpus_dir(item) / item.file).read_text(encoding="utf-8")
    if case.expected == EXPECTED_ESCALATE:
        findings = check_static(reference, fix, input_src=input_src, expected=EXPECTED_ESCALATE)
    else:
        findings = check_static(reference, fix)
    response = None
    if item.response is not None:
        response = (_corpus_dir(item) / item.response).read_text(encoding="utf-8")
    questions = questions_for(case, reference, input_src, fix, findings, response)
    for question in questions:
        if question.id == item.question:
            return build_prompt(case, reference, fix, results, question, judge_dir=judge_dir)
    asked = ", ".join(question.id for question in questions) or "none"
    raise ValueError(f"{item.id}: {item.file} makes no question '{item.question}' (it makes: {asked})")


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------


def calibration_problem(*, repo_root: Path = REPO_ROOT, judge_dir: Path = JUDGE_DIR) -> str | None:
    """None when the recorded calibration matches the current judge and items; else why not.

    The sentence names what differs (no file, another judge version, another
    items hash) and ends with the command that calibrates.
    """
    path = Path(judge_dir) / CALIBRATION_NAME
    if not path.is_file():
        return f"there is no recorded calibration ({CALIBRATION_NAME}); run {CALIBRATE_COMMAND}"
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        recorded = None
    if not isinstance(recorded, dict):
        return f"the recorded calibration ({CALIBRATION_NAME}) is not a JSON object; run {CALIBRATE_COMMAND}"
    differs = []
    version = judge_version(judge_dir)
    if recorded.get("judge") != version:
        differs.append(f"another judge version (recorded {recorded.get('judge')}, now {version})")
    current = items_hash(calibration_items(repo_root))
    if recorded.get("items_hash") != current:
        differs.append(f"other items (recorded hash {recorded.get('items_hash')}, now {current})")
    if not differs:
        return None
    return f"the recorded calibration is for {' and '.join(differs)}; run {CALIBRATE_COMMAND}"


# --------------------------------------------------------------------------
# Calibrating
# --------------------------------------------------------------------------


def _append_log(log: Path, entry: dict) -> None:
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def calibrate(
    *,
    ask_fn: AskFn | None,
    repo_root: Path = REPO_ROOT,
    judge_dir: Path = JUDGE_DIR,
    samples: int = CALIBRATION_SAMPLES,
    only: list[str] | None = None,
    max_total_usd: float = DEFAULT_MAX_TOTAL_USD,
    log: Path | None = None,
    dry_run: bool = False,
    prompts_dir: Path | None = None,
    out: Callable[[str], object] = print,
    date: str | None = None,
) -> int:
    """Ask the judge every labeled item ``samples`` times; return 0 on a pass, else 1.

    One call at a time, items in id order. An item is OK only when every
    sample equals its label (``unsure`` is a miss). A ``JudgeError`` is
    retried once; a second one in a row on the same sample stops the run
    (``CALIBRATION=error``), and so does a running cost past
    ``max_total_usd`` (``CALIBRATION=budget``). ``only`` lists item ids to
    ask. The record is written only on a pass over every item with at least
    ``CALIBRATION_SAMPLES`` samples. ``log`` gets one JSON line per sample as
    it is answered. ``dry_run`` asks nothing: it prints each prompt's length,
    the number of calls and, with ``prompts_dir``, writes the prompts there.
    Raises ``ValueError`` for an unknown id in ``only``, ``samples`` below 1,
    a ``max_total_usd`` not above 0 and a missing ``ask_fn`` outside a dry run.
    """
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if not max_total_usd > 0:
        raise ValueError("max_total_usd must be above 0")
    if ask_fn is None and not dry_run:
        raise ValueError("an ask function is needed unless this is a dry run")
    items = calibration_items(repo_root)
    full = only is None
    if only is not None:
        wanted = set(only)
        unknown = sorted(wanted - {item.id for item in items})
        if unknown:
            raise ValueError(f"unknown item id: {', '.join(unknown)}")
        items = [item for item in items if item.id in wanted]

    if dry_run:
        for number, item in enumerate(items, start=1):
            prompt = item_prompt(item, judge_dir=judge_dir)
            out(f"ITEM={item.id} CHARS={len(prompt)}")
            if prompts_dir is not None:
                target = Path(prompts_dir) / f"{number}.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(prompt.encode("utf-8"))
        out(f"CALLS={len(items) * samples}")
        return 0

    assert ask_fn is not None
    calls = 0
    cost = 0.0
    status: str | None = None
    done: list[tuple[Item, list[str]]] = []
    for item in items:
        prompt = item_prompt(item, judge_dir=judge_dir)
        got: list[str] = []
        for number in range(1, samples + 1):
            answer: Answer | None = None
            for attempt in (1, 2):
                calls += 1
                try:
                    answer = ask_fn(prompt)
                    break
                except JudgeError as exc:
                    if log is not None:
                        _append_log(log, {"id": item.id, "sample": number, "attempt": attempt, "error": str(exc)})
            if answer is None:
                status = "error"
                break
            cost += answer.cost_usd or 0.0
            got.append(answer.answer)
            if log is not None:
                entry = {
                    "id": item.id,
                    "sample": number,
                    "answer": answer.answer,
                    "quote": answer.quote,
                    "reason": answer.reason,
                    "cost": answer.cost_usd,
                }
                _append_log(log, entry)
            if cost > max_total_usd:
                status = "budget"
                break
        if len(got) == samples:
            done.append((item, got))
            verdict = "OK" if all(answer == item.answer for answer in got) else "MISS"
            out(f"ITEM={item.id} LABEL={item.answer} GOT={','.join(got)} {verdict}")
        if status is not None:
            break

    if status is None:
        status = "pass" if all(set(got) == {item.answer} for item, got in done) else "fail"
    recorded = "no"
    if status == "pass" and full and samples >= CALIBRATION_SAMPLES:
        path = Path(judge_dir) / CALIBRATION_NAME
        _write_record(path, judge_dir, items, done, samples, cost, date)
        recorded = str(path)
    out(f"CALLS={calls}")
    out(f"COST_USD={cost:.4f}")
    out(f"CALIBRATION={status}")
    out(f"RECORDED={recorded}")
    return 0 if status == "pass" else 1


def _write_record(
    path: Path,
    judge_dir: Path,
    items: list[Item],
    done: list[tuple[Item, list[str]]],
    samples: int,
    cost: float,
    date: str | None,
) -> None:
    """Write calibration.json: counts and a cost only, never a quote or a reason."""
    cases: dict[str, dict[str, int]] = {}
    for item, got in done:
        entry = cases.setdefault(item.case_dir.name, {"items": 0, "correct": 0})
        entry["items"] += 1
        entry["correct"] += sum(1 for answer in got if answer == item.answer)
    record = {
        "judge": judge_version(judge_dir),
        "model": JUDGE_MODEL,
        "items_hash": items_hash(items),
        "items": len(items),
        "samples": samples,
        "date": date if date is not None else datetime.date.today().isoformat(),
        "cost_usd": round(cost, 4),
        "cases": cases,
    }
    text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))
