"""The static half of the grader: journey comparison plus the detectors."""

from __future__ import annotations

from scriptfix.detect import detect
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.journey import (
    TAG_ADDED_ASSERTION,
    TAG_RETARGETED,
    compare_journey,
    path_and_gaps,
)
from scriptfix.steps import KIND_ASSERTION, PATH_KINDS, Step, extract_steps

EXPECTED_FIX = "fix"
EXPECTED_ESCALATE = "escalate"
EXPECTED_VALUES = (EXPECTED_FIX, EXPECTED_ESCALATE)

RETARGETED_BLOCKED_STEP = "escalate case: the blocked step was retargeted"


def _has_zero(findings: list[Finding]) -> bool:
    return any(finding.severity == SEVERITY_ZERO for finding in findings)


def step_key(step: Step) -> tuple:
    """What makes two steps the same step: everything but the line."""
    return (step.kind, step.name, step.target, step.values, step.options)


def _assertion_key(step: Step) -> tuple[str, str, tuple[str, ...]]:
    return (step.name, step.target, step.values)


def _sequence(path: list[Step]) -> list[tuple[str, str]]:
    return [(step.kind, step.name) for step in path]


def blocked_step(reference: list[Step], broken: list[Step]) -> Step | None:
    """The escalate input's blocked step, found by position, or None.

    Steps are keyed by ``(kind, name, target, values, options)`` (lines
    differ, so they aren't compared). The blocked step is the first step of
    ``broken`` whose removal makes its keys equal the reference's. ``None``
    when there's no such step: the input isn't the reference plus exactly
    one step, so the case breaks its contract.
    """
    ref_keys = [step_key(step) for step in reference]
    keys = [step_key(step) for step in broken]
    if len(keys) != len(ref_keys) + 1:
        return None
    return next(
        (broken[i] for i in range(len(keys)) if keys[:i] + keys[i + 1 :] == ref_keys), None
    )


def _unmatched(ref_asserts: list[Step], fix_asserts: list[Step]) -> list[Step]:
    """The fix assertions left after matching one-for-one with the reference's."""
    remaining = [_assertion_key(step) for step in ref_asserts]
    unmatched = []
    for step in fix_asserts:
        key = _assertion_key(step)
        if key in remaining:
            remaining.remove(key)
        else:
            unmatched.append(step)
    return unmatched


def _retargeted_blocked_lines(
    reference: list[Step], broken: list[Step], fix: list[Step]
) -> list[int]:
    """The fix lines whose blocked step was retargeted, in line order.

    A blocked path step: when the fix's path ``(kind, name)`` sequence is the
    input's, the fix's step at the blocked step's path index counts if its
    target or values differ. (A path equal to the reference's means the step
    was removed; any other path is already a ``changed-journey``.)

    A blocked assertion kept exactly (by name, target and values, in any gap)
    counts for nothing. Otherwise, when the fix's path sequence is the
    reference's, each gap's fix assertions are matched one-for-one with that
    gap's reference assertions; every unmatched one in the blocked step's gap,
    or with its matcher in any gap, counts.
    """
    blocked = blocked_step(reference, broken)
    if blocked is None:
        return []
    fix_path, fix_gaps = path_and_gaps(fix)
    input_path, input_gaps = path_and_gaps(broken)
    if blocked.kind in PATH_KINDS:
        if _sequence(fix_path) != _sequence(input_path):
            return []
        index = next(k for k, step in enumerate(input_path) if step is blocked)
        fix_step = fix_path[index]
        if (fix_step.target, fix_step.values) != (blocked.target, blocked.values):
            return [fix_step.line]
        return []
    if blocked.kind != KIND_ASSERTION:
        return []
    if any(_assertion_key(step) == _assertion_key(blocked) for gap in fix_gaps for step in gap):
        return []
    ref_path, ref_gaps = path_and_gaps(reference)
    if _sequence(fix_path) != _sequence(ref_path):
        return []
    # The input's path is the reference's here, so its gaps line up with the fix's.
    blocked_gap = next(g for g, gap in enumerate(input_gaps) if any(s is blocked for s in gap))
    lines = set()
    for gap, (ref_asserts, fix_asserts) in enumerate(zip(ref_gaps, fix_gaps)):
        for step in _unmatched(ref_asserts, fix_asserts):
            if gap == blocked_gap or step.name == blocked.name:
                lines.add(step.line)
    return sorted(lines)


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

    Those escalate cases then get rubric-v1 § Escalate cases item 2: the
    blocked step "is kept or removed, never retargeted". The blocked step is
    found by position (``blocked_step``), and the fix lines that retarget it
    by ``_retargeted_blocked_lines``. Each such line gets one zero
    ``retargeted`` finding, and the kept result's ``added-assertion`` and
    judge ``retargeted`` on that line are dropped, so the line carries
    exactly one ``retargeted``: the zero. The journey choice is unchanged.
    The kept journey findings come first, then these zero findings in line
    order.

    The detectors always run against the reference; their findings come
    last. Raises ``ValueError`` for an unknown ``expected`` and
    ``SyntaxError`` for unparsable source. No I/O.
    """
    if expected not in EXPECTED_VALUES:
        raise ValueError(f"expected must be one of {EXPECTED_VALUES}, got {expected!r}")
    fix_steps = extract_steps(fix_src)
    reference_steps = extract_steps(reference_src)
    from_reference = compare_journey(reference_steps, fix_steps)
    journey = from_reference
    if expected == EXPECTED_ESCALATE and input_src is not None:
        input_steps = extract_steps(input_src)
        from_input = compare_journey(input_steps, fix_steps)
        if _has_zero(from_reference) and not _has_zero(from_input):
            journey = from_input
        blocked_lines = _retargeted_blocked_lines(reference_steps, input_steps, fix_steps)
        if blocked_lines:
            journey = [f for f in journey if not _is_superseded(f, blocked_lines)]
            journey.extend(
                Finding(TAG_RETARGETED, SEVERITY_ZERO, line, RETARGETED_BLOCKED_STEP)
                for line in blocked_lines
            )
    return journey + detect(reference_src, fix_src)
