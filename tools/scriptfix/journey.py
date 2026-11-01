"""Compare a fix's journey with the reference's (rubric script-fix-v0, check 2).

Implements the plan's journey rules over ``steps.extract_steps`` output:

1. the ``(kind, name)`` sequence of path steps (navigations, actions,
   markers) must match, else one ``changed-journey`` and rules 2-3 are
   skipped;
2. aligned path steps with a different target or values are ``retargeted``;
3. every reference assertion needs a fix assertion in the same gap between
   path steps with the same matcher (``weakened-check`` otherwise); a
   different target or values is ``retargeted``; leftover fix assertions in
   a gap without a ``weakened-check`` are ``added-assertion``;
4. setup steps other than the timeout setters must match exactly, else one
   ``changed-setup``.
"""

from __future__ import annotations

from scriptfix.findings import SEVERITY_INFO, SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.steps import KIND_ASSERTION, KIND_SETUP, PATH_KINDS, TIMEOUT_SETTERS, Step

TAG_CHANGED_JOURNEY = "changed-journey"
TAG_RETARGETED = "retargeted"
TAG_WEAKENED_CHECK = "weakened-check"
TAG_ADDED_ASSERTION = "added-assertion"
TAG_CHANGED_SETUP = "changed-setup"


def compare_journey(reference: list[Step], fix: list[Step]) -> list[Finding]:
    """Return the journey findings for ``fix`` against ``reference``.

    Lines refer to the fix, except where the fix lacks the step (see the
    ``detail`` of ``weakened-check``, which names the reference line).
    """
    ref_path, ref_gaps = path_and_gaps(reference)
    fix_path, fix_gaps = path_and_gaps(fix)
    findings: list[Finding] = []
    divergence = _first_divergence(ref_path, fix_path)
    if divergence is not None:
        findings.append(_changed_journey(ref_path, fix_path, divergence))
    else:
        findings.extend(_compare_path_steps(ref_path, fix_path))
        for gap, (ref_asserts, fix_asserts) in enumerate(zip(ref_gaps, fix_gaps)):
            gap_line = fix_path[gap - 1].line if gap > 0 else 0
            findings.extend(_compare_gap(ref_asserts, fix_asserts, gap, gap_line))
    setup = _compare_setup(reference, fix)
    if setup is not None:
        findings.append(setup)
    return findings


def path_and_gaps(steps: list[Step]) -> tuple[list[Step], list[list[Step]]]:
    """Split steps into path steps and the assertions of each gap.

    Gap 0 is before the first path step; gap k is after path step k, so
    there is always one more gap than path steps. Waits and setup belong to
    neither.
    """
    path: list[Step] = []
    gaps: list[list[Step]] = [[]]
    for step in steps:
        if step.kind in PATH_KINDS:
            path.append(step)
            gaps.append([])
        elif step.kind == KIND_ASSERTION:
            gaps[-1].append(step)
    return path, gaps


def _first_divergence(ref_path: list[Step], fix_path: list[Step]) -> int | None:
    """Index of the first differing ``(kind, name)``, or None if the sequences match."""
    for index, (ref_step, fix_step) in enumerate(zip(ref_path, fix_path)):
        if (ref_step.kind, ref_step.name) != (fix_step.kind, fix_step.name):
            return index
    if len(ref_path) != len(fix_path):
        return min(len(ref_path), len(fix_path))
    return None


def _describe(step: Step) -> str:
    return f"{step.kind} {step.name}" + (f" on {step.target}" if step.target else "")


def _changed_journey(ref_path: list[Step], fix_path: list[Step], index: int) -> Finding:
    if index < len(fix_path):
        line = fix_path[index].line
        found = f"the fix has {_describe(fix_path[index])}"
    else:
        # The fix's path is a prefix of the reference's: point at its last step.
        line = fix_path[-1].line if fix_path else 0
        found = "the fix's path ends"
    if index < len(ref_path):
        ref_step = ref_path[index]
        expected = f"the reference has {_describe(ref_step)} (reference line {ref_step.line})"
    else:
        expected = "the reference's path ends"
    detail = f"path step {index + 1}: {expected}; {found}"
    return Finding(TAG_CHANGED_JOURNEY, SEVERITY_ZERO, line, detail)


def _compare_path_steps(ref_path: list[Step], fix_path: list[Step]) -> list[Finding]:
    # Options are ignored here: the detectors judge timeouts, force, etc.
    findings = []
    for ref_step, fix_step in zip(ref_path, fix_path):
        if (ref_step.target, ref_step.values) != (fix_step.target, fix_step.values):
            detail = (
                f"{fix_step.name}: the fix targets {fix_step.target} {list(fix_step.values)}, "
                f"the reference {ref_step.target} {list(ref_step.values)} "
                f"(reference line {ref_step.line})"
            )
            findings.append(Finding(TAG_RETARGETED, SEVERITY_JUDGE, fix_step.line, detail))
    return findings


def _compare_gap(
    ref_asserts: list[Step], fix_asserts: list[Step], gap: int, gap_line: int
) -> list[Finding]:
    """Match one gap's reference assertions, in order, against the fix's."""
    findings: list[Finding] = []
    matched: set[int] = set()
    previous = -1
    weakened = False
    for ref_step in ref_asserts:
        later = range(previous + 1, len(fix_asserts))
        exact = next(
            (
                i
                for i in later
                if (fix_asserts[i].name, fix_asserts[i].target, fix_asserts[i].values)
                == (ref_step.name, ref_step.target, ref_step.values)
            ),
            None,
        )
        if exact is not None:
            matched.add(exact)
            previous = exact
            continue
        same_matcher = next((i for i in later if fix_asserts[i].name == ref_step.name), None)
        if same_matcher is not None:
            fix_step = fix_asserts[same_matcher]
            matched.add(same_matcher)
            previous = same_matcher
            detail = (
                f"{fix_step.name}: the fix checks {fix_step.target} {list(fix_step.values)}, "
                f"the reference {ref_step.target} {list(ref_step.values)} "
                f"(reference line {ref_step.line})"
            )
            findings.append(Finding(TAG_RETARGETED, SEVERITY_JUDGE, fix_step.line, detail))
            continue
        weakened = True
        detail = (
            f"no {ref_step.name} on {ref_step.target} in gap {gap} "
            f"(reference line {ref_step.line})"
        )
        findings.append(Finding(TAG_WEAKENED_CHECK, SEVERITY_ZERO, gap_line, detail))
    if not weakened:
        # A weakened gap's leftovers are likely the replacement matcher, not
        # an addition, so they aren't credited as added assertions.
        for index, fix_step in enumerate(fix_asserts):
            if index not in matched:
                detail = f"{fix_step.name} on {fix_step.target} is not in the reference"
                findings.append(Finding(TAG_ADDED_ASSERTION, SEVERITY_INFO, fix_step.line, detail))
    return findings


def _setup_key(step: Step) -> tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    return (step.name, step.target, step.values, step.options)


def _describe_setup(step: Step) -> str:
    arguments = [*step.values, *(f"{name}={value}" for name, value in step.options)]
    return f"{step.name} on {step.target or '-'} ({', '.join(arguments)})"


def _setup_steps(steps: list[Step]) -> list[Step]:
    # Timeout setters are the longer-timeout detector's business.
    return [s for s in steps if s.kind == KIND_SETUP and s.name not in TIMEOUT_SETTERS]


def _compare_setup(reference: list[Step], fix: list[Step]) -> Finding | None:
    ref_setup = _setup_steps(reference)
    fix_setup = _setup_steps(fix)
    if [_setup_key(s) for s in ref_setup] == [_setup_key(s) for s in fix_setup]:
        return None
    index = next(
        (
            i
            for i, (r, f) in enumerate(zip(ref_setup, fix_setup))
            if _setup_key(r) != _setup_key(f)
        ),
        min(len(ref_setup), len(fix_setup)),
    )
    if index < len(fix_setup):
        line = fix_setup[index].line
        found = f"the fix has {_describe_setup(fix_setup[index])}"
    else:
        line = fix_setup[-1].line if fix_setup else 0
        found = "the fix has no more setup"
    if index < len(ref_setup):
        expected = (
            f"the reference has {_describe_setup(ref_setup[index])} "
            f"(reference line {ref_setup[index].line})"
        )
    else:
        expected = "the reference has no more setup"
    detail = f"setup step {index + 1}: {expected}; {found}"
    return Finding(TAG_CHANGED_SETUP, SEVERITY_JUDGE, line, detail)
