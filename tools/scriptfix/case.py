"""Load and validate an eval's grading/case.toml (ADR-0001 case contract)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from scriptfix import RUBRIC

REQUIRED_KEYS = ("rubric", "expected", "issue", "origin", "defect", "fails_at", "target")
OPTIONAL_KEYS = ("note",)
EXPECTED_VALUES = ("fix", "escalate")


@dataclass(frozen=True)
class Case:
    path: Path  # the eval directory, evals/<NN>-<name>
    slug: str
    number: str  # the two-digit prefix of the slug
    rubric: str
    expected: str  # "fix" | "escalate"
    issue: tuple[str, ...]
    origin: str
    defect: str
    fails_at: int
    target: str
    note: str = ""

    @property
    def grading_dir(self) -> Path:
        return self.path / "grading"

    @property
    def reference_script(self) -> Path:
        return self.grading_dir / "reference" / "script.py"

    @property
    def input_script(self) -> Path:
        return self.path / "inputs" / "script.py"


def _require_str(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"case.toml key '{key}' must be a string, got {value!r}")
    return value


def load_case(path: Path) -> Case:
    """Read <path>/grading/case.toml; raise ValueError naming the bad key or value."""
    path = Path(path)
    slug = path.name
    match = re.match(r"(\d{2})-", slug)
    if match is None:
        raise ValueError(f"eval folder name '{slug}' must start with two digits and a dash")
    case_toml = path / "grading" / "case.toml"
    if not case_toml.is_file():
        raise ValueError(f"case.toml not found: {case_toml}")
    with case_toml.open("rb") as handle:
        data = tomllib.load(handle)

    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"case.toml is missing required key '{key}': {case_toml}")
    for key in data:
        if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS:
            raise ValueError(f"case.toml has unknown key '{key}': {case_toml}")

    rubric = _require_str(data, "rubric")
    if rubric != RUBRIC:
        raise ValueError(f"case.toml rubric '{rubric}' is not '{RUBRIC}': {case_toml}")
    expected = _require_str(data, "expected")
    if expected not in EXPECTED_VALUES:
        raise ValueError(f"case.toml expected '{expected}' must be one of {EXPECTED_VALUES}")
    issue = data["issue"]
    if not isinstance(issue, list) or not all(isinstance(item, str) for item in issue):
        raise ValueError(f"case.toml key 'issue' must be a list of strings, got {issue!r}")
    fails_at = data["fails_at"]
    if isinstance(fails_at, bool) or not isinstance(fails_at, int):
        raise ValueError(f"case.toml key 'fails_at' must be an integer, got {fails_at!r}")

    return Case(
        path=path,
        slug=slug,
        number=match.group(1),
        rubric=rubric,
        expected=expected,
        issue=tuple(issue),
        origin=_require_str(data, "origin"),
        defect=_require_str(data, "defect"),
        fails_at=fails_at,
        target=_require_str(data, "target"),
        note=_require_str(data, "note") if "note" in data else "",
    )
