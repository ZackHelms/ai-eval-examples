"""Tracked text files use LF line endings and no stray control characters.

The repo is LF, but Python's text mode and many Windows tools write CRLF,
and a whole-file CRLF rewrite hides the real diff. A control character other
than tab and LF is almost always an escape gone wrong (an octal escape in a
non-raw string writes a byte such as 0x10), and nothing else in the gate sees
one. Captured evidence is exempt: `inputs/` and `grading/fixes/` hold
byte-exact copies of real runs and model-written scripts.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BINARY_SNIFF_BYTES = 8000
# Control characters other than tab, LF and CR; CR has its own test.
CONTROL_BYTES = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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


def control_bytes(data: bytes) -> list[tuple[int, int]]:
    """The ``(line, byte)`` of every control character in ``data``."""
    return [
        (data.count(b"\n", 0, match.start()) + 1, match.group()[0])
        for match in CONTROL_BYTES.finditer(data)
    ]


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


def test_tracked_text_files_have_no_control_characters() -> None:
    offenders = []
    for path in _tracked_files():
        file = REPO_ROOT / path
        if _is_byte_exact_copy(path) or not file.is_file():
            continue
        data = file.read_bytes()
        if b"\0" in data[:BINARY_SNIFF_BYTES]:
            continue
        offenders += [f"{path}:{line} (0x{byte:02x})" for line, byte in control_bytes(data)]
    assert offenders == [], f"control characters at {offenders}; look for an octal escape in a non-raw string"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"a\tb\nc\n", []),
        (b"crlf\r\n", []),
        (b"x\n.\x10-run\n", [(2, 0x10)]),
        (b"\x1b[0m", [(1, 0x1B)]),
        (b"del\x7f", [(1, 0x7F)]),
        (b"\x0c", [(1, 0x0C)]),
    ],
)
def test_control_bytes_finds_only_control_characters(
    data: bytes, expected: list[tuple[int, int]]
) -> None:
    assert control_bytes(data) == expected


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
