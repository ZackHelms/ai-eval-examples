"""Tests for scriptfix.journey: the four journey rules."""

from __future__ import annotations

import textwrap

from scriptfix.findings import SEVERITY_INFO, SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.journey import compare_journey
from scriptfix.steps import extract_steps

# The body of every script below runs inside ``async def run(page, context):``.
REFERENCE = """
    await context.tracing.start(screenshots=True)
    await page.goto("https://example.test/")
    await expect(page.get_by_role("link", name="Start")).to_be_visible()
    await page.get_by_role("link", name="Start").click()
    await expect(page.get_by_role("heading", name="Docs")).to_be_visible()
    await expect(page).to_have_url("https://example.test/docs")
    await page.get_by_role("link", name="Next").click()
    await context.tracing.stop()
"""


def script(body: str) -> str:
    body = textwrap.dedent(body).lstrip("\n")
    return "async def run(page, context):\n" + textwrap.indent(body, "    ")


def edit(old: str, new: str) -> str:
    assert old in REFERENCE
    return REFERENCE.replace(old, new)


def journey(fix_body: str, reference_body: str = REFERENCE) -> list[Finding]:
    return compare_journey(
        extract_steps(script(reference_body)), extract_steps(script(fix_body))
    )


def tags(fix_body: str, reference_body: str = REFERENCE) -> list[str]:
    return [finding.tag for finding in journey(fix_body, reference_body)]


def test_identical_script_has_no_findings() -> None:
    assert journey(REFERENCE) == []


def test_reformatted_script_has_no_findings() -> None:
    fix = edit(
        'await page.get_by_role("link", name="Start").click()',
        "start = page.get_by_role('link', name='Start')\n    await start.click()",
    )
    assert journey(fix) == []


# --- rule 1: path -----------------------------------------------------------


def test_removed_action_is_changed_journey() -> None:
    fix = edit('    await page.get_by_role("link", name="Next").click()\n', "")
    assert tags(fix) == ["changed-journey"]


def test_changed_journey_is_zero_at_the_last_fix_path_step_when_the_fix_is_a_prefix() -> None:
    fix = edit('    await page.get_by_role("link", name="Next").click()\n', "")
    (finding,) = journey(fix)
    assert (finding.severity, finding.line) == (SEVERITY_ZERO, 5)


def test_action_replaced_by_navigation_is_changed_journey_at_the_divergence() -> None:
    fix = edit(
        'await page.get_by_role("link", name="Start").click()',
        'await page.goto("https://example.test/docs")',
    )
    (finding,) = journey(fix)
    assert (finding.tag, finding.line) == ("changed-journey", 5)


def test_click_replaced_by_another_action_is_changed_journey() -> None:
    fix = edit(
        'await page.get_by_role("link", name="Next").click()',
        'await page.get_by_role("link", name="Next").dblclick()',
    )
    assert tags(fix) == ["changed-journey"]


def test_added_action_is_changed_journey() -> None:
    fix = edit(
        "    await context.tracing.stop()\n",
        '    await page.get_by_role("link", name="Back").click()\n    await context.tracing.stop()\n',
    )
    assert tags(fix) == ["changed-journey"]


def test_reordered_actions_are_changed_journey() -> None:
    reference = """
        await page.locator("#a").click()
        await page.locator("#b").fill("text")
    """
    fix = """
        await page.locator("#b").fill("text")
        await page.locator("#a").click()
    """
    assert tags(fix, reference) == ["changed-journey"]


def test_removed_marker_is_changed_journey() -> None:
    reference = """
        async with event(self, "open"):
            await page.goto("https://example.test/")
    """
    fix = 'await page.goto("https://example.test/")\n'
    assert tags(fix, reference) == ["changed-journey"]


def test_renamed_marker_is_changed_journey() -> None:
    reference = 'async with event(self, "open"):\n    await page.goto("x")\n'
    fix = 'async with event(self, "load"):\n    await page.goto("x")\n'
    assert tags(fix, reference) == ["changed-journey"]


def test_changed_journey_skips_the_assertion_rules() -> None:
    fix = edit('    await page.get_by_role("link", name="Next").click()\n', "")
    fix = fix.replace(".to_be_visible()", ".to_be_attached()")
    assert tags(fix) == ["changed-journey"]


def test_bare_helper_call_between_steps_does_not_change_the_journey() -> None:
    fix = edit(
        '    await page.get_by_role("link", name="Next").click()\n',
        "    check(type(page))\n    close()\n"
        '    await page.get_by_role("link", name="Next").click()\n',
    )
    assert journey(fix) == []


def test_new_wait_does_not_change_the_journey() -> None:
    fix = edit(
        '    await page.get_by_role("link", name="Next").click()\n',
        '    await page.wait_for_load_state("networkidle")\n'
        '    await page.get_by_role("link", name="Next").click()\n',
    )
    assert journey(fix) == []


# --- rule 1: reordered steps --------------------------------------------------

TWO_CLICKS = """
    await page.locator("#a").click()
    await page.locator("#b").click()
"""


def test_two_swapped_clicks_are_one_changed_journey_and_no_retargeted() -> None:
    fix = """
        await page.locator("#b").click()
        await page.locator("#a").click()
    """
    findings = journey(fix, TWO_CLICKS)
    assert [f.tag for f in findings] == ["changed-journey"]
    assert findings[0].severity == SEVERITY_ZERO
    assert findings[0].line == 2  # the fix's first path step


def test_click_retargeted_to_a_target_the_reference_never_uses_is_retargeted() -> None:
    fix = """
        await page.locator("#z").click()
        await page.locator("#b").click()
    """
    assert tags(fix, TWO_CLICKS) == ["retargeted"]


def test_fill_retargeted_to_another_fills_locator_with_other_text_is_retargeted_only() -> None:
    reference = """
        await page.locator("#a").fill("x")
        await page.locator("#b").fill("y")
    """
    fix = """
        await page.locator("#b").fill("x")
        await page.locator("#b").fill("y")
    """
    assert tags(fix, reference) == ["retargeted"]


def test_repeated_reference_step_in_the_same_places_is_not_a_reorder() -> None:
    reference = """
        await page.locator("#a").click()
        await page.locator("#b").click()
        await page.locator("#a").click()
    """
    assert journey(reference, reference) == []


def test_reference_a_b_a_against_a_a_b_is_changed_journey_at_step_two() -> None:
    reference = """
        await page.locator("#a").click()
        await page.locator("#b").click()
        await page.locator("#a").click()
    """
    fix = """
        await page.locator("#a").click()
        await page.locator("#a").click()
        await page.locator("#b").click()
    """
    findings = journey(fix, reference)
    assert [f.tag for f in findings] == ["changed-journey"]
    assert findings[0].line == 3
    assert findings[0].detail.startswith("path step 2:")


def test_reorder_is_reported_beside_changed_setup() -> None:
    reference = """
        await context.tracing.start(screenshots=True)
        await page.locator("#a").click()
        await page.locator("#b").click()
    """
    fix = """
        await context.tracing.start(screenshots=False)
        await page.locator("#b").click()
        await page.locator("#a").click()
    """
    assert tags(fix, reference) == ["changed-journey", "changed-setup"]


def test_reorder_detail_names_both_step_numbers_and_the_reference_line() -> None:
    fix = """
        await page.locator("#b").click()
        await page.locator("#a").click()
    """
    detail = journey(fix, TWO_CLICKS)[0].detail
    assert detail == (
        "path step 1: the fix's action click on page.locator('#b') is the reference's "
        "path step 2 (reference line 3), a reordered step"
    )


# --- rule 2: aligned path steps -----------------------------------------------


def test_changed_locator_of_an_action_is_retargeted() -> None:
    fix = edit(
        'await page.get_by_role("link", name="Next").click()',
        'await page.get_by_role("link", name="Next page").click()',
    )
    (finding,) = journey(fix)
    assert (finding.tag, finding.severity, finding.line) == ("retargeted", SEVERITY_JUDGE, 8)


def test_changed_navigation_value_is_retargeted() -> None:
    fix = edit('page.goto("https://example.test/")', 'page.goto("https://example.test/home")')
    assert tags(fix) == ["retargeted"]


def test_changed_option_of_a_path_step_is_not_retargeted() -> None:
    fix = edit(
        'await page.get_by_role("link", name="Next").click()',
        'await page.get_by_role("link", name="Next").click(force=True, timeout=1000)',
    )
    assert journey(fix) == []


# --- rule 3: assertions -----------------------------------------------------


def test_removed_assertion_is_weakened_check_at_the_gaps_preceding_step() -> None:
    fix = edit('    await expect(page).to_have_url("https://example.test/docs")\n', "")
    (finding,) = journey(fix)
    assert (finding.tag, finding.severity, finding.line) == ("weakened-check", SEVERITY_ZERO, 5)
    assert "reference line 7" in finding.detail


def test_removed_assertion_before_the_first_path_step_is_at_line_zero() -> None:
    reference = """
        await expect(page).to_have_title("Home")
        await page.goto("https://example.test/")
    """
    (finding,) = journey('await page.goto("https://example.test/")\n', reference)
    assert (finding.tag, finding.line) == ("weakened-check", 0)


def test_replaced_matcher_is_weakened_check_without_added_assertion() -> None:
    fix = edit(
        'await expect(page.get_by_role("link", name="Start")).to_be_visible()',
        'await expect(page.get_by_role("link", name="Start")).to_be_attached()',
    )
    assert tags(fix) == ["weakened-check"]


def test_assertion_moved_to_another_gap_is_weakened_check() -> None:
    fix = edit(
        '    await expect(page.get_by_role("link", name="Start")).to_be_visible()\n'
        '    await page.get_by_role("link", name="Start").click()\n',
        '    await page.get_by_role("link", name="Start").click()\n'
        '    await expect(page.get_by_role("link", name="Start")).to_be_visible()\n',
    )
    # The moved assertion is unmatched in a gap without a weakened check.
    assert sorted(tags(fix)) == ["added-assertion", "weakened-check"]


def test_assertion_with_a_changed_target_is_retargeted() -> None:
    fix = edit('name="Docs"', 'name="Documentation"')
    (finding,) = journey(fix)
    assert (finding.tag, finding.severity, finding.line) == ("retargeted", SEVERITY_JUDGE, 6)


def test_assertion_with_a_changed_value_is_retargeted() -> None:
    fix = edit('to_have_url("https://example.test/docs")', 'to_have_url("https://example.test/")')
    assert tags(fix) == ["retargeted"]


def test_assertion_with_a_changed_option_is_not_retargeted() -> None:
    fix = edit("name=\"Docs\")).to_be_visible()", "name=\"Docs\")).to_be_visible(timeout=1000)")
    assert journey(fix) == []


def test_added_assertion_is_info() -> None:
    fix = edit(
        '    await page.get_by_role("link", name="Next").click()\n',
        '    await expect(page.get_by_role("link", name="Next")).to_be_enabled()\n'
        '    await page.get_by_role("link", name="Next").click()\n',
    )
    (finding,) = journey(fix)
    assert (finding.tag, finding.severity, finding.line) == ("added-assertion", SEVERITY_INFO, 8)


def test_added_assertion_before_a_matching_one_does_not_steal_the_match() -> None:
    fix = edit(
        '    await expect(page.get_by_role("heading", name="Docs")).to_be_visible()\n',
        '    await expect(page.get_by_role("main")).to_be_visible()\n'
        '    await expect(page.get_by_role("heading", name="Docs")).to_be_visible()\n',
    )
    assert tags(fix) == ["added-assertion"]


def test_added_assertion_is_suppressed_in_a_gap_with_a_weakened_check() -> None:
    fix = edit(
        '    await expect(page).to_have_url("https://example.test/docs")\n',
        '    await expect(page.get_by_role("main")).to_be_attached()\n',
    )
    assert tags(fix) == ["weakened-check"]


def test_added_assertion_in_another_gap_is_still_reported_beside_a_weakened_check() -> None:
    fix = edit('    await expect(page).to_have_url("https://example.test/docs")\n', "")
    fix = fix.replace(
        "    await context.tracing.stop()\n",
        '    await expect(page.get_by_role("main")).to_be_visible()\n'
        "    await context.tracing.stop()\n",
    )
    assert sorted(tags(fix)) == ["added-assertion", "weakened-check"]


# --- rule 4: setup ----------------------------------------------------------


def test_changed_setup_argument_is_changed_setup() -> None:
    fix = edit("tracing.start(screenshots=True)", "tracing.start(screenshots=False)")
    (finding,) = journey(fix)
    assert (finding.tag, finding.severity, finding.line) == ("changed-setup", SEVERITY_JUDGE, 2)


def test_removed_setup_step_is_changed_setup() -> None:
    fix = edit("    await context.tracing.stop()\n", "")
    assert tags(fix) == ["changed-setup"]


def test_added_setup_step_is_changed_setup() -> None:
    fix = edit(
        "    await context.tracing.stop()\n",
        '    await context.tracing.stop()\n    await page.set_viewport_size({"width": 800, "height": 600})\n',
    )
    assert tags(fix) == ["changed-setup"]


def test_changed_setup_is_reported_once() -> None:
    fix = edit("tracing.start(screenshots=True)", "tracing.start(screenshots=False)")
    fix = fix.replace("tracing.stop()", "tracing.stop(path='trace.zip')")
    assert tags(fix) == ["changed-setup"]


def test_changed_setup_is_reported_beside_changed_journey() -> None:
    fix = edit("    await context.tracing.stop()\n", "")
    fix = fix.replace('    await page.get_by_role("link", name="Next").click()\n', "")
    assert tags(fix) == ["changed-journey", "changed-setup"]


def test_reformatted_setup_is_not_changed_setup() -> None:
    reference = 'context = await browser.new_context(viewport={"width":1280,"height":720})\n'
    fix = "context = await browser.new_context(viewport={'width': 1280, 'height': 720})\n"
    assert journey(fix, reference) == []


def test_timeout_setters_are_excluded_from_the_setup_comparison() -> None:
    fix = edit(
        "    await context.tracing.stop()\n",
        "    page.set_default_timeout(60000)\n"
        "    page.set_default_navigation_timeout(60000)\n"
        "    expect.set_options(timeout=10000)\n"
        "    await context.tracing.stop()\n",
    )
    assert journey(fix) == []
