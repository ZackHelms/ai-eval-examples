"""The judge's right answers (grading/corpus/judge.toml) match the grader's questions.

A corpus file reaches the judge when its static findings have no zero and
at least one judge finding. Each judge finding is one question,
"<tag>:<line>", and judge.toml gives it exactly one right answer. An
escalate corpus also labels model responses under grading/corpus/responses/:
each such item pairs one response with a corpus file that reaches the
judge, for the "escalation" question. Answers are "ok" or "cheat";
calibration asks each item five times (grader-01e).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scriptfix.case import load_case
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.static import EXPECTED_ESCALATE, check_static

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSWERS = ("ok", "cheat")
REQUIRED_KEYS = {"file", "question", "answer", "why"}
ESCALATION = "escalation"


def _corpora() -> list[Path]:
    return sorted(REPO_ROOT.glob("evals/*/grading/corpus/corpus.toml"))


def _ids(paths: list[Path]) -> list[str]:
    return [path.parents[2].name for path in paths]


def _labels(corpus_toml: Path) -> dict:
    return tomllib.loads(corpus_toml.read_text(encoding="utf-8"))


def _items(corpus_toml: Path) -> list[dict]:
    path = corpus_toml.parent / "judge.toml"
    if not path.is_file():
        return []
    return tomllib.loads(path.read_text(encoding="utf-8")).get("item", [])


def _findings(corpus_toml: Path, name: str) -> list[Finding]:
    corpus_dir = corpus_toml.parent
    case = load_case(corpus_toml.parents[2])
    reference = (corpus_dir / _labels(corpus_toml)["reference"]).read_text(encoding="utf-8")
    fix = (corpus_dir / name).read_text(encoding="utf-8")
    if case.expected == EXPECTED_ESCALATE:
        broken = case.input_script.read_text(encoding="utf-8")
        return check_static(reference, fix, input_src=broken, expected=EXPECTED_ESCALATE)
    return check_static(reference, fix)


def _reaches_judge(findings: list[Finding]) -> bool:
    return not any(f.severity == SEVERITY_ZERO for f in findings)


def _questions(corpus_toml: Path) -> set[tuple[str, str]]:
    """(file, question) for every judge finding of a file that reaches the judge."""
    questions = set()
    for name in _labels(corpus_toml)["files"]:
        findings = _findings(corpus_toml, name)
        if _reaches_judge(findings):
            questions |= {(name, f"{f.tag}:{f.line}") for f in findings if f.severity == SEVERITY_JUDGE}
    return questions


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_items_are_well_formed(corpus_toml: Path) -> None:
    files = _labels(corpus_toml)["files"]
    for item in _items(corpus_toml):
        keys = set(item)
        assert REQUIRED_KEYS <= keys <= REQUIRED_KEYS | {"response"}, f"bad keys {sorted(keys)}: {item}"
        assert item["answer"] in ANSWERS, f"the answer must be ok or cheat: {item}"
        assert isinstance(item["why"], str) and item["why"].strip(), f"empty why: {item}"
        assert item["file"] in files, f"not a labeled corpus file: {item}"


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_every_judge_question_has_one_label(corpus_toml: Path) -> None:
    labeled = [(item["file"], item["question"]) for item in _items(corpus_toml) if "response" not in item]
    assert len(labeled) == len(set(labeled)), f"a question is labeled twice: {sorted(labeled)}"
    expected = _questions(corpus_toml)
    assert set(labeled) == expected, (
        f"unlabeled questions: {sorted(expected - set(labeled))}; "
        f"labels without a question: {sorted(set(labeled) - expected)}"
    )


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_responses_are_labeled_once_each(corpus_toml: Path) -> None:
    escalate = load_case(corpus_toml.parents[2]).expected == EXPECTED_ESCALATE
    items = [item for item in _items(corpus_toml) if "response" in item]
    responses = corpus_toml.parent / "responses"
    present = sorted(path.name for path in responses.glob("*.md")) if responses.is_dir() else []
    if not escalate:
        assert items == [] and present == [], "only an escalate corpus labels responses"
        return
    assert present, "an escalate corpus needs labeled responses for the escalation question"
    used = sorted(item["response"] for item in items)
    assert used == sorted(f"responses/{name}" for name in present), f"responses {present}, labeled {used}"
    for item in items:
        assert item["question"] == ESCALATION, f"a response item asks the escalation question: {item}"
        assert _reaches_judge(_findings(corpus_toml, item["file"])), f"{item['file']} has a zero finding"
