"""The finding record every grader check produces."""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ZERO = "zero"
SEVERITY_JUDGE = "judge"
SEVERITY_SMELL = "smell"
SEVERITY_INFO = "info"
SEVERITY_INVALID = "invalid"

SEVERITIES = (
    SEVERITY_ZERO,
    SEVERITY_JUDGE,
    SEVERITY_SMELL,
    SEVERITY_INFO,
    SEVERITY_INVALID,
)


@dataclass(frozen=True)
class Finding:
    """One rubric observation about a script or transcript."""

    tag: str  # a tag from rubric-v0.md
    severity: str  # one of SEVERITIES
    line: int  # 1-based line in the script it concerns; 0 for transcript findings
    detail: str  # short human-readable reason
