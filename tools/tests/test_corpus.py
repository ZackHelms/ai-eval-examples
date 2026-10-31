"""Run the static grader over every eval's labeled corpus (grading/corpus/corpus.toml).

The labels are the spec: each corpus file must produce exactly the tags
listed for it. A file added without a label, or a label without a file, fails.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scriptfix.static import check_static

REPO_ROOT = Path(__file__).resolve().parents[2]


def _corpus_files() -> list[Path]:
    return sorted(REPO_ROOT.glob("evals/*/grading/corpus/corpus.toml"))


def _load(corpus_toml: Path) -> dict:
    return tomllib.loads(corpus_toml.read_text(encoding="utf-8"))


def _slug(corpus_toml: Path) -> str:
    return corpus_toml.parents[2].name


def _cases() -> list:
    cases = []
    for corpus_toml in _corpus_files():
        data = _load(corpus_toml)
        for name, label in data["files"].items():
            cases.append(
                pytest.param(corpus_toml, name, label, id=f"{_slug(corpus_toml)}/{name}")
            )
    return cases


def test_corpora_exist():
    assert _corpus_files(), "no evals/*/grading/corpus/corpus.toml found"


@pytest.mark.parametrize("corpus_toml, name, label", _cases())
def test_corpus_file_has_its_labeled_tags(corpus_toml, name, label):
    corpus_dir = corpus_toml.parent
    reference = (corpus_dir / _load(corpus_toml)["reference"]).resolve()
    fix = corpus_dir / name
    findings = check_static(
        reference.read_text(encoding="utf-8"), fix.read_text(encoding="utf-8")
    )
    listing = "\n".join(
        f"  {f.tag} [{f.severity}] line {f.line}: {f.detail}" for f in findings
    )
    assert {f.tag for f in findings} == set(label["tags"]), (
        f"{_slug(corpus_toml)}/{name}: expected tags {sorted(label['tags'])}, "
        f"got:\n{listing or '  (no findings)'}"
    )


@pytest.mark.parametrize(
    "corpus_toml", _corpus_files(), ids=[_slug(p) for p in _corpus_files()]
)
def test_corpus_files_and_labels_match(corpus_toml):
    labeled = set(_load(corpus_toml)["files"])
    present = {p.name for p in corpus_toml.parent.glob("*.py")}
    assert present == labeled, (
        f"unlabeled files: {sorted(present - labeled)}; "
        f"labels without a file: {sorted(labeled - present)}"
    )
