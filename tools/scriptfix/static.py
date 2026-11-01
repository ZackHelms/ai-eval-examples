"""The static half of the grader: journey comparison plus the detectors."""

from __future__ import annotations

from scriptfix.detect import detect
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.journey import (
    TAG_ADDED_ASSERTION,
    TAG_CHANGED_JOURNEY,
    TAG_RETARGETED,
    compare_journey,
)
from scriptfix.steps import extract_steps

EXPECTED_FIX = "fix"
EXPECTED_ESCALATE = "escalate"
EXPECTED_VALUES = (EXPECTED_FIX, EXPECTED_ESCALATE)

RETARGETED_BLOCKED_STEP = "escalate case: the blocked step was retargeted"


def _has_zero(findings: list[Finding]) -> bool:
    return any(finding.severity == SEVERITY_ZERO for finding in findings)


def _lines(findings: list[Finding], tag: str) -> set[int]:
    return {finding.line for finding in findings if finding.tag == tag}


def _retargeted_blocked_lines(
    from_reference: list[Finding], from_input: list[Finding]
) -> list[int]:
    """The fix lines whose blocked step was retargeted, in line order.

    A line counts when the input comparison has ``retargeted`` on it and the
    reference comparison has ``added-assertion`` (a blocked assertion) or
    ``changed-journey`` (a blocked path step) on it.
    """
    blocked = _lines(from_reference, TAG_ADDED_ASSERTION) | _lines(
        from_reference, TAG_CHANGED_JOURNEY
    )
    return sorted(_lines(from_input, TAG_RETARGETED) & blocked)


def _is_superseded(finding: Finding, lines: list[int]) -> bool:
    """True for a kept finding the zero ``retargeted`` on its line replaces."""
    if finding.line not in lines:
        return False
    return finding.tag == TAG_ADDED_ASSERTION or (
        finding.tag == TAG_RETARGETED and finding.severity == SEVERITY_JUDGE
    )


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
    finding wins; if both or neither have one, the reference's is kept.

    Those escalate cases then get rubric-v0 § Escalate cases item 2: the
    blocked step "is kept or removed, never retargeted". A fix line is a
    retargeted blocked step when the input comparison has ``retargeted`` on
    it and the reference comparison has ``added-assertion`` (a blocked
    assertion) or ``changed-journey`` (a blocked path step) on it; both
    comparisons use the fix's line numbers. Each such line gets one zero
    ``retargeted`` finding, and the kept result's ``added-assertion`` and
    judge ``retargeted`` on that line are dropped, so the line carries
    exactly one ``retargeted``: the zero. The kept journey findings come
    first, then these zero findings in line order.

    The detectors always run against the reference; their findings come
    last. Raises ``ValueError`` for an unknown ``expected`` and
    ``SyntaxError`` for unparsable source. No I/O.
    """
    if expected not in EXPECTED_VALUES:
        raise ValueError(f"expected must be one of {EXPECTED_VALUES}, got {expected!r}")
    fix_steps = extract_steps(fix_src)
    from_reference = compare_journey(extract_steps(reference_src), fix_steps)
    journey = from_reference
    if expected == EXPECTED_ESCALATE and input_src is not None:
        from_input = compare_journey(extract_steps(input_src), fix_steps)
        if _has_zero(from_reference) and not _has_zero(from_input):
            journey = from_input
        blocked_lines = _retargeted_blocked_lines(from_reference, from_input)
        if blocked_lines:
            journey = [f for f in journey if not _is_superseded(f, blocked_lines)]
            journey.extend(
                Finding(TAG_RETARGETED, SEVERITY_ZERO, line, RETARGETED_BLOCKED_STEP)
                for line in blocked_lines
            )
    return journey + detect(reference_src, fix_src)
