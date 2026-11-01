"""Tracked text files use LF line endings.

The repo is LF, but Python's text mode and many Windows tools write CRLF,
and a whole-file CRLF rewrite hides the real diff. Captured evidence is
exempt: `inputs/` and `grading/fixes/` hold byte-exact copies of real runs
and model-written scripts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BINARY_SNIFF_BYTES = 8000


def _tracked_files() -> list[str]:
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ls-files is unavailable")
    return [path for path in done.stdout.decode("utf-8").split("\0") if path]


def _is_byte_exact_copy(path: str) -> bool:
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "evals":
        return False
    return parts[2] == "inputs" or parts[2:4] == ["grading", "fixes"]


def test_tracked_text_files_have_no_carriage_returns() -> None:
    offenders = []
    for path in _tracked_files():
        file = REPO_ROOT / path
        if _is_byte_exact_copy(path) or not file.is_file():
            continue
        data = file.read_bytes()
        if b"\0" in data[:BINARY_SNIFF_BYTES]:
            continue
        if b"\r" in data:
            offenders.append(path)
    assert offenders == [], f"CR line endings in {offenders}; write files with newline='\\n'"


@pytest.mark.parametrize(
    ("path", "exempt"),
    [
        ("evals/01-x/inputs/results.txt", True),
        ("evals/01-x/grading/fixes/abc.py", True),
        ("evals/01-x/grading/reference/script.py", False),
        ("tools/scriptfix/grade.py", False),
    ],
)
def test_only_captured_evidence_is_exempt(path: str, exempt: bool) -> None:
    assert _is_byte_exact_copy(path) is exempt
