"""Tests for scriptfix.case.load_case."""

from __future__ import annotations

from pathlib import Path

import pytest

from scriptfix.case import load_case

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_01 = REPO_ROOT / "evals" / "01-playwright-python-basic"

VALID: dict[str, str] = {
    "rubric": '"script-fix-v0"',
    "expected": '"fix"',
    "issue": '["locator-text"]',
    "origin": '"handmade"',
    "defect": '"a defect"',
    "fails_at": "3",
    "target": '"http://localhost"',
}


def make_eval(tmp_path: Path, **overrides: str | None) -> Path:
    """Build tmp_path/07-demo/grading/case.toml; a None override drops the key."""
    values = {**VALID, **overrides}
    lines = [f"{key} = {value}" for key, value in values.items() if value is not None]
    grading = tmp_path / "07-demo" / "grading"
    grading.mkdir(parents=True)
    (grading / "case.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path / "07-demo"


def test_eval_01_case_loads_number() -> None:
    assert load_case(EVAL_01).number == "01"


def test_eval_01_case_loads_expected_and_fails_at() -> None:
    case = load_case(EVAL_01)
    assert case.expected == "fix"
    assert case.fails_at == 18


def test_eval_01_case_loads_issue_as_tuple() -> None:
    assert load_case(EVAL_01).issue == ("locator-text",)


def test_eval_01_case_paths() -> None:
    case = load_case(EVAL_01)
    assert case.input_script == EVAL_01 / "inputs" / "script.py"
    assert case.reference_script == EVAL_01 / "grading" / "reference" / "script.py"


def test_note_defaults_to_empty(tmp_path: Path) -> None:
    assert load_case(make_eval(tmp_path)).note == ""


def test_missing_key_is_named(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="origin"):
        load_case(make_eval(tmp_path, origin=None))


def test_unknown_key_is_named(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="surprise"):
        load_case(make_eval(tmp_path, surprise='"x"'))


def test_bad_expected_value_is_named(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="maybe"):
        load_case(make_eval(tmp_path, expected='"maybe"'))


def test_wrong_rubric_value_is_named(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="script-fix-v9"):
        load_case(make_eval(tmp_path, rubric='"script-fix-v9"'))


def test_bool_fails_at_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fails_at"):
        load_case(make_eval(tmp_path, fails_at="true"))


def test_missing_case_toml_names_path(tmp_path: Path) -> None:
    (tmp_path / "07-demo").mkdir()
    with pytest.raises(ValueError, match="case.toml"):
        load_case(tmp_path / "07-demo")


def test_folder_without_number_prefix_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="demo"):
        load_case(tmp_path / "demo")
