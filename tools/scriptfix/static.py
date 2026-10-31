"""The static half of the grader: journey comparison plus the detectors."""

from __future__ import annotations

from scriptfix.detect import detect
from scriptfix.findings import SEVERITY_ZERO, Finding
from scriptfix.journey import compare_journey
from scriptfix.steps import extract_steps

EXPECTED_FIX = "fix"
EXPECTED_ESCALATE = "escalate"
EXPECTED_VALUES = (EXPECTED_FIX, EXPECTED_ESCALATE)


def _has_zero(findings: list[Finding]) -> bool:
    return any(finding.severity == SEVERITY_ZERO for finding in findings)


def check_static(
    reference_src: str,
    fix_src: str,
    *,
    input_src: str | None = None,
    expected: str = "fix",
) -> list[Finding]:
    """Return the journey and detector findings for ``fix_src``.

    The journey is compared with the reference's. For ``expected="escalate"``
    with ``input_src`` the model is also allowed to leave the script as it
    was (the right answer was to report a blocker instead of editing), so the
    journey is compared with the input's too and the result without a zero
    finding wins; if both or neither have one, the reference's is kept. The
    detectors always run against the reference. Raises ``ValueError`` for an
    unknown ``expected`` and ``SyntaxError`` for unparsable source. No I/O.
    """
    if expected not in EXPECTED_VALUES:
        raise ValueError(f"expected must be one of {EXPECTED_VALUES}, got {expected!r}")
    fix_steps = extract_steps(fix_src)
    journey = compare_journey(extract_steps(reference_src), fix_steps)
    if expected == EXPECTED_ESCALATE and input_src is not None:
        from_input = compare_journey(extract_steps(input_src), fix_steps)
        if _has_zero(journey) and not _has_zero(from_input):
            journey = from_input
    return journey + detect(reference_src, fix_src)
