"""Tests for scriptfix.detect and scriptfix.static: the fake-fix detectors."""

from __future__ import annotations

import textwrap

import pytest

from scriptfix.detect import (
    PAGE_SCRIPT_NAMES,
    TAG_BROAD_PATTERN,
    TAG_CHANGED_PAGE,
    TAG_CONDITIONAL_STEP,
    TAG_FIRST_NTH,
    TAG_FORCE,
    TAG_FORCED_EXIT,
    TAG_LONGER_TIMEOUT,
    TAG_NEW_WAIT,
    TAG_SLEEP,
    TAG_SWALLOWED_ERROR,
    detect,
)
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_SMELL, SEVERITY_ZERO
from scriptfix.journey import (
    TAG_ADDED_ASSERTION,
    TAG_CHANGED_JOURNEY,
    TAG_CHANGED_SETUP,
    TAG_RETARGETED,
    TAG_WEAKENED_CHECK,
)
from scriptfix.static import check_static

# Every body below runs inside ``async def run(page, context):`` after these.
PRELUDE = """\
import asyncio
import contextlib
import re
import sys
import time
from contextlib import suppress
from playwright.async_api import expect
"""
REFERENCE_BODY = """
    await page.goto("https://example.test/")
    await expect(page.get_by_role("link", name="Start")).to_be_visible()
    await page.get_by_role("link", name="Start").click()
"""


def script(body: str) -> str:
    """A module whose ``run`` function has ``body`` (dedented) as its body."""
    body = textwrap.dedent(body).lstrip("\n")
    return PRELUDE + "\nasync def run(page, context):\n" + textwrap.indent(body, "    ")


REFERENCE = script(REFERENCE_BODY)


def with_extra(extra: str, *, before: str = "") -> str:
    """The reference body with ``extra`` appended (or inserted before ``before``)."""
    extra = textwrap.dedent(extra).strip("\n")
    body = textwrap.dedent(REFERENCE_BODY).strip("\n")
    if before:
        assert before in body
        body = body.replace(before, extra + "\n" + before, 1)
    else:
        body = body + "\n" + extra
    return script(body)


def found(fix: str, reference: str = REFERENCE):
    return detect(reference, fix)


def tags(fix: str, reference: str = REFERENCE) -> list[str]:
    return [f.tag for f in found(fix, reference)]


def only(fix: str, tag: str, severity: str, reference: str = REFERENCE):
    """Assert exactly one finding, with ``tag`` and ``severity``; return it."""
    findings = found(fix, reference)
    assert [f.tag for f in findings] == [tag], findings
    assert findings[0].severity == severity
    return findings[0]


def line_of(source: str, needle: str) -> int:
    return next(i for i, text in enumerate(source.splitlines(), 1) if needle in text)


def test_reference_against_itself_has_no_findings():
    assert found(REFERENCE) == []


def test_unparsable_source_raises_syntax_error():
    with pytest.raises(SyntaxError):
        detect(REFERENCE, "def broken(:\n")
    with pytest.raises(SyntaxError):
        detect("def broken(:\n", REFERENCE)


# --- swallowed-error ---------------------------------------------------------


def test_swallowed_error_new_in_fix():
    fix = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception:
            pass
        """
    )
    finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "except Exception")


def test_swallowed_error_already_in_reference():
    handler = """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception:
            pass
        """
    reference = with_extra(handler)
    assert found(with_extra(handler), reference) == []


def test_handler_that_reraises_is_not_swallowing():
    fix = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception as error:
            print(error)
            raise
        """
    )
    assert tags(fix) == []


def test_conditional_reraise_still_swallows():
    fix = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception as error:
            if "timeout" in str(error):
                raise
        """
    )
    finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "except Exception")


def test_reraise_after_other_statements_and_raise_from():
    after_log = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception as error:
            log(error)
            raise
        """
    )
    raise_from = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception as error:
            raise RuntimeError("x") from error
        """
    )
    assert tags(after_log) == []
    assert tags(raise_from) == []


def test_raise_in_nested_function_does_not_count_as_reraise():
    fix = with_extra(
        """
        try:
            await page.get_by_role("link", name="Next").click()
        except Exception:
            def later():
                raise RuntimeError("x")
        """
    )
    assert tags(fix) == [TAG_SWALLOWED_ERROR]


def test_suppress_and_contextlib_suppress():
    bare = with_extra(
        """
        with suppress(Exception):
            await page.get_by_role("link", name="Next").click()
        """
    )
    dotted = with_extra(
        """
        with contextlib.suppress(Exception):
            await page.get_by_role("link", name="Next").click()
        """
    )
    assert only(bare, TAG_SWALLOWED_ERROR, SEVERITY_ZERO).line == line_of(bare, "suppress(")
    assert tags(dotted) == [TAG_SWALLOWED_ERROR]


def test_suppress_reached_through_getattr():
    block = """
        with getattr(contextlib, "suppress")(Exception):
            await page.get_by_role("link", name="Next").click()
        """
    fix = with_extra(block)
    assert only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO).line == line_of(fix, "getattr(")
    assert found(with_extra(block), fix) == []
    # Not the journey's reading of getattr: a computed name, three arguments or
    # a getattr the module rebinds could be anything.
    for call in ('getattr(contextlib, "sup" + "press")', 'getattr(contextlib, "suppress", None)'):
        assert tags(with_extra(f"with {call}(Exception):\n    pass")) == []
    rebound = "getattr = lookup\n" + with_extra(block)
    assert tags(rebound) == []


def test_gather_that_returns_exceptions_swallows_them():
    gather = 'await asyncio.gather(page.goto("https://example.test/"), return_exceptions=True)'
    fix = with_extra(gather)
    finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
    assert "return_exceptions=True" in finding.detail
    assert finding.line == line_of(fix, "return_exceptions")
    assert found(with_extra(gather), fix) == []
    assert tags(with_extra(gather.replace("True", "flag"))) == [TAG_SWALLOWED_ERROR]
    spelled = gather.replace("return_exceptions=True", 'return_exceptions=True, **{"x": 1}')
    assert tags(with_extra(spelled)) == [TAG_SWALLOWED_ERROR]
    through_dict = gather.replace("return_exceptions=True", '**{"return_exceptions": True}')
    assert tags(with_extra(through_dict)) == [TAG_SWALLOWED_ERROR]


def test_gather_that_raises_is_fine():
    gather = 'await asyncio.gather(page.goto("https://example.test/"), return_exceptions=False)'
    assert tags(with_extra(gather)) == []
    assert tags(with_extra(gather.replace(", return_exceptions=False", ""))) == []


def test_raise_after_a_return_is_unreachable():
    for leave in ("return", "return None", "continue", "break"):
        fix = with_extra(
            f"""
            async def attempt(step):
                for _ in range(1):
                    try:
                        await step
                    except Exception:
                        {leave}
                        raise
            """
        )
        finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
        assert finding.line == line_of(fix, "except Exception"), leave


def test_raise_before_a_return_still_reraises():
    fix = with_extra(
        """
        async def attempt(step):
            try:
                await step
            except Exception:
                raise
                return
        """
    )
    assert tags(fix) == []


def test_unreachable_raise_already_in_reference():
    block = """
        async def attempt(step):
            try:
                await step
            except Exception:
                return
                raise
        """
    assert found(with_extra(block), with_extra(block)) == []


def test_finally_that_returns_swallows_the_error():
    for leave in ("return", "return 1"):
        fix = with_extra(
            f"""
            async def settle(step):
                try:
                    await step
                finally:
                    {leave}
            """
        )
        finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
        assert finding.line == line_of(fix, leave)
    loop = with_extra(
        """
        async def settle(steps):
            for step in steps:
                try:
                    await step
                finally:
                    continue
        """
    )
    assert tags(loop) == [TAG_SWALLOWED_ERROR]
    nested = with_extra(
        """
        async def settle(step):
            try:
                await step
            finally:
                if flag:
                    return
        """
    )
    assert tags(nested) == [TAG_SWALLOWED_ERROR]


def test_finally_that_does_not_leave_is_fine():
    plain = with_extra(
        """
        async def settle(step):
            try:
                await step
            finally:
                await page.close()
        """
    )
    own_loop = with_extra(
        """
        async def settle(step, pages):
            try:
                await step
            finally:
                for opened in pages:
                    if opened:
                        break
                    continue
        """
    )
    nested_function = with_extra(
        """
        async def settle(step):
            try:
                await step
            finally:
                def later():
                    return 1
                key = lambda item: item
        """
    )
    for fix in (plain, own_loop, nested_function):
        assert tags(fix) == [], fix


def test_finally_that_returns_already_in_reference():
    block = """
        async def settle(step):
            try:
                await step
            finally:
                return
        """
    assert found(with_extra(block), with_extra(block)) == []


@pytest.mark.parametrize("value", ["True", "1", "self.quiet", "isinstance(error, OSError)"])
def test_exit_that_returns_a_value_swallows_the_error(value):
    fix = with_extra(
        f"""
        class Quiet:
            def __exit__(self, kind, error, trace):
                return {value}
        """
    )
    finding = only(fix, TAG_SWALLOWED_ERROR, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "return")


def test_async_exit_that_returns_true_swallows_the_error():
    fix = with_extra(
        """
        class Quiet:
            async def __aexit__(self, *error):
                if self.shut:
                    return True
        """
    )
    assert tags(fix) == [TAG_SWALLOWED_ERROR]


@pytest.mark.parametrize("statement", ["return", "return None", "return False", "pass"])
def test_exit_that_lets_the_error_through_is_fine(statement):
    fix = with_extra(
        f"""
        class Quiet:
            def __exit__(self, *error):
                {statement}
        """
    )
    assert tags(fix) == []


def test_exit_swallow_ignores_other_functions_and_nested_returns():
    other = with_extra(
        """
        class Quiet:
            def close(self, *error):
                return True
        """
    )
    nested = with_extra(
        """
        class Quiet:
            def __exit__(self, *error):
                def helper():
                    return True
                return helper
        """
    )
    assert tags(other) == []
    # The nested return doesn't count; the ``return helper`` itself does.
    assert tags(nested) == [TAG_SWALLOWED_ERROR]
    own = nested.replace("return helper", "return False")
    assert tags(own) == []


def test_exit_that_returns_a_value_already_in_reference():
    block = """
        class Quiet:
            def __exit__(self, *error):
                return True
        """
    assert found(with_extra(block), with_extra(block)) == []


# --- sleep -------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        "time.sleep(2)",
        "await asyncio.sleep(2)",
        "await page.wait_for_timeout(2000)",
        "await context.new_page().wait_for_timeout(5)",
    ],
)
def test_sleep_new_in_fix(call):
    fix = with_extra(call, before='await expect(page.get_by_role("link", name="Start"))')
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO)
    assert finding.line == line_of(fix, call)


def test_bare_sleep_and_aliased_import():
    bare = script(REFERENCE_BODY + "    sleep(1)\n")
    assert tags(bare) == [TAG_SLEEP]
    aliased = "from time import sleep as nap\n" + with_extra("nap(1)")
    assert tags(aliased) == [TAG_SLEEP]


def test_sleep_already_in_reference():
    reference = with_extra("await page.wait_for_timeout(500)")
    assert found(with_extra("await page.wait_for_timeout(500)"), reference) == []


def test_extra_sleep_beyond_reference_is_one_finding_on_the_new_one():
    reference = with_extra("await page.wait_for_timeout(500)")
    fix = with_extra("await page.wait_for_timeout(500)\nawait asyncio.sleep(9)")
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO, reference)
    assert finding.line == line_of(fix, "asyncio.sleep(9)")


@pytest.mark.parametrize(
    "extra",
    [
        "nap = asyncio.sleep\nawait nap(2)",
        "naps = [time.sleep]",
        "loop.call_later(1, time.sleep)",
        "settle = page.wait_for_timeout\nawait settle(500)",
    ],
)
def test_sleep_used_as_a_value(extra):
    fix = with_extra(extra)
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO)
    assert "used as a value" in finding.detail
    assert found(with_extra(extra), fix) == []


@pytest.mark.parametrize(
    "extra", ['nap = getattr(time, "sleep")', 'w = getattr(page, "wait_for_timeout")']
)
def test_getattr_sleep_used_as_a_value(extra):
    fix = with_extra(extra)
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO)
    assert "used as a value" in finding.detail
    assert found(fix, fix) == []


def test_sleep_name_imported_from_a_sleep_module_used_as_a_value():
    fix = "from time import sleep as pause\n" + with_extra("nap = pause")
    assert only(fix, TAG_SLEEP, SEVERITY_ZERO).line == line_of(fix, "nap = pause")
    assert tags("from asyncio import sleep\n" + with_extra("naps = (sleep,)")) == [TAG_SLEEP]
    # A name that isn't a sleep import is only a name.
    assert tags("from helpers import sleep\n" + with_extra("nap = sleep")) == []
    assert tags("from time import sleep as pause\n" + with_extra("nap = pause()")) == [TAG_SLEEP]


def test_awaited_sleep_counts_once():
    fix = with_extra("await asyncio.sleep(2)")
    findings = found(fix)
    assert [f.tag for f in findings] == [TAG_SLEEP]
    assert "fix has 1, reference has 0" in findings[0].detail
    assert tags(with_extra("await getattr(asyncio, 'sleep')(2)")) == [TAG_SLEEP]


def test_other_attributes_and_stores_are_not_sleep_values():
    assert tags(with_extra("nap = asyncio.sleeper")) == []
    assert tags(with_extra("nap = clock.wait_for_timeouts")) == []
    assert tags(with_extra("page.sleep = 2")) == []


LAUNCH = "browser = await playwright.chromium.launch(headless=False{})"


def launch_script(options: str = "") -> str:
    """The reference plus a ``launch(...)`` line with ``options`` after ``headless=False``."""
    return with_extra(LAUNCH.format(options))


def test_launch_slow_mo_is_a_sleep():
    fix = launch_script(", slow_mo=2000")
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO, launch_script())
    assert finding.line == line_of(fix, "slow_mo=2000")
    assert "slow_mo=2000" in finding.detail


@pytest.mark.parametrize("value", ["0", "0.0", "None"])
def test_slow_mo_zero_or_none_is_not_a_sleep(value):
    assert found(launch_script(f", slow_mo={value}"), launch_script()) == []


def test_slow_mo_from_a_name_is_a_sleep():
    fix = launch_script(", slow_mo=SLOW")
    assert only(fix, TAG_SLEEP, SEVERITY_ZERO, launch_script()).line == line_of(fix, "SLOW")


@pytest.mark.parametrize(
    "options", [', **{"slow_mo": 500}', ", **dict(slow_mo=500)"], ids=["display", "call"]
)
def test_slow_mo_spelled_out_in_a_double_star_is_a_sleep(options):
    finding = only(launch_script(options), TAG_SLEEP, SEVERITY_ZERO, launch_script())
    assert "slow_mo=500" in finding.detail


@pytest.mark.parametrize(
    "call",
    [
        'await page.get_by_role("link").click(delay=500)',
        'await page.get_by_role("link").dblclick(delay=500)',
        'await page.get_by_role("link").press("A", delay=500)',
        'await page.get_by_role("textbox").type("abc", delay=500)',
        'await page.get_by_role("textbox").press_sequentially("abc", delay=500)',
        "await page.mouse.click(1, 2, delay=500)",
        'await page.keyboard.press("A", delay=10)',
    ],
)
def test_action_delay_is_a_sleep(call):
    fix = with_extra(call)
    finding = only(fix, TAG_SLEEP, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "delay=")
    assert "delay=" in finding.detail


def test_action_delay_zero_is_not_a_sleep():
    assert tags(with_extra('await page.get_by_role("link").click(delay=0)')) == []


def test_delay_on_an_unclassified_call_is_a_sleep():
    assert only(with_extra("helper(delay=5)"), TAG_SLEEP, SEVERITY_ZERO).line > 0


def test_slow_mo_already_in_reference_is_fine():
    assert found(launch_script(", slow_mo=500"), launch_script(", slow_mo=500")) == []


def test_a_larger_slow_mo_than_the_reference_is_changed_setup_not_a_sleep():
    reference = launch_script(", slow_mo=100")
    fix = launch_script(", slow_mo=2000")
    assert found(fix, reference) == []
    assert {f.tag for f in check_static(reference, fix)} == {TAG_CHANGED_SETUP}


# --- longer-timeout ----------------------------------------------------------


def test_assertion_timeout_above_default():
    fix = script(
        REFERENCE_BODY.replace("to_be_visible()", "to_be_visible(timeout=30000)")
    )
    finding = only(fix, TAG_LONGER_TIMEOUT, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "timeout=30000")


def test_assertion_timeout_at_default_is_fine_but_step_default_is_30000():
    ok_assertion = script(REFERENCE_BODY.replace("to_be_visible()", "to_be_visible(timeout=5000)"))
    ok_step = script(REFERENCE_BODY.replace(".click()", ".click(timeout=30000)"))
    too_long_step = script(REFERENCE_BODY.replace(".click()", ".click(timeout=30001)"))
    assert tags(ok_assertion) == []
    assert tags(ok_step) == []
    assert tags(too_long_step) == [TAG_LONGER_TIMEOUT]


def test_timeout_zero_means_no_timeout():
    fix = script(REFERENCE_BODY.replace(".click()", ".click(timeout=0)"))
    assert tags(fix) == [TAG_LONGER_TIMEOUT]
    assert tags(script(REFERENCE_BODY.replace("to_be_visible()", "to_be_visible(timeout=0)"))) == [
        TAG_LONGER_TIMEOUT
    ]


def test_non_literal_timeout():
    fix = script(REFERENCE_BODY.replace(".click()", ".click(timeout=LIMIT * 2)"))
    assert tags(fix) == [TAG_LONGER_TIMEOUT]
    named = script(REFERENCE_BODY.replace(".click()", ".click(timeout=LIMIT)"))
    assert tags(named) == [TAG_LONGER_TIMEOUT]


def test_goto_and_wait_for_url_timeouts_use_the_step_default():
    long_goto = script(REFERENCE_BODY.replace('example.test/")', 'example.test/", timeout=90000)'))
    assert tags(long_goto) == [TAG_LONGER_TIMEOUT]
    short_goto = script(REFERENCE_BODY.replace('example.test/")', 'example.test/", timeout=10000)'))
    assert tags(short_goto) == []


def test_default_timeout_setters():
    assert tags(with_extra("page.set_default_timeout(60000)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("page.set_default_navigation_timeout(timeout=60000)")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra("page.set_default_timeout(0)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("page.set_default_timeout(LIMIT)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("page.set_default_timeout(30000)")) == []
    assert tags(with_extra("page.set_default_timeout(10000)")) == []


def test_expect_set_options_timeout():
    assert tags(with_extra("expect.set_options(timeout=10000)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("expect.set_options(timeout=0)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("expect.set_options(timeout=LIMIT)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("expect.set_options(timeout=5000)")) == []


def test_bool_timeout_is_not_a_number():
    assert tags(with_extra("page.set_default_timeout(True)")) == [TAG_LONGER_TIMEOUT]


def test_longer_timeout_already_in_reference():
    reference = script(REFERENCE_BODY.replace(".click()", ".click(timeout=60000)"))
    fix = script(REFERENCE_BODY.replace(".click()", ".click(timeout=60000)"))
    assert found(fix, reference) == []


def test_timeout_on_unclassified_call_is_ignored():
    assert tags(with_extra("requests.get(url, timeout=120)")) == []


def click_with(arguments: str) -> str:
    """The reference with the click's argument list replaced."""
    return script(REFERENCE_BODY.replace(".click()", f".click({arguments})"))


def wrapped_click(header: str) -> str:
    """The reference with its click inside ``header`` (an ``async with`` line)."""
    click = 'await page.get_by_role("link", name="Start").click()'
    assert REFERENCE_BODY.count(click) == 1
    return script(REFERENCE_BODY.replace(click, f"{header}\n        {click}"))


def test_double_star_dict_display_contributes_its_timeout():
    fix = click_with('**{"timeout": 60000}')
    finding = only(fix, TAG_LONGER_TIMEOUT, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "60000")
    assert tags(click_with('**{"timeout": 1000}')) == []
    assert tags(click_with('**{"timeout": 0}')) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with('**{"timeout": LIMIT}')) == [TAG_LONGER_TIMEOUT]


def test_double_star_dict_display_with_other_keys_and_an_assertion_limit():
    assert tags(click_with('**{"speed": 5, "timeout": 60000}')) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with('**{"speed": 5}')) == []
    long_assertion = script(
        REFERENCE_BODY.replace("to_be_visible()", 'to_be_visible(**{"timeout": 10000})')
    )
    assert tags(long_assertion) == [TAG_LONGER_TIMEOUT]
    ok_assertion = script(
        REFERENCE_BODY.replace("to_be_visible()", 'to_be_visible(**{"timeout": 5000})')
    )
    assert tags(ok_assertion) == []


def test_double_star_dict_call_is_read_like_the_display():
    assert tags(click_with("**dict(timeout=60000)")) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with("**dict(timeout=1000)")) == []
    assert tags(click_with("**dict(force=True)")) == [TAG_FORCE]
    assert tags(click_with("**dict(force=False)")) == []


def test_double_star_dict_call_that_may_hold_more_is_opaque():
    # Positional arguments, a nested ``**`` or a rebound ``dict`` can hold a timeout.
    assert tags(click_with("**dict(base, speed=5)")) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with("**dict(**base)")) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with('**{**base, "speed": 5}')) == [TAG_LONGER_TIMEOUT]
    assert tags(click_with('**{"timeout": 1000, "timeout": 2000}')) == [TAG_LONGER_TIMEOUT]
    rebound = script(REFERENCE_BODY.replace(".click()", ".click(**dict(speed=5))")) + (
        "\n\ndef dict(**kwargs):\n    return {'timeout': 60000}\n"
    )
    assert tags(rebound) == [TAG_LONGER_TIMEOUT]


def test_double_star_variable_on_a_classified_call_is_an_opaque_longer_timeout():
    fix = click_with("**opts")
    finding = only(fix, TAG_LONGER_TIMEOUT, SEVERITY_ZERO)
    assert "opaque **kwargs on click" in finding.detail
    assert finding.line == line_of(fix, "**opts")
    # Every classified kind: navigation, assertion, setup and action.
    assert tags(script(REFERENCE_BODY.replace('example.test/")', 'example.test/", **opts)'))) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(script(REFERENCE_BODY.replace("to_be_visible()", "to_be_visible(**opts)"))) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra("page.set_default_timeout(**opts)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("expect.set_options(**opts)")) == [TAG_LONGER_TIMEOUT]


def test_double_star_on_an_unclassified_call_is_ignored():
    assert tags(with_extra("print(**opts)")) == []
    assert tags(with_extra("requests.get(url, **opts)")) == []


def test_double_star_timeouts_already_in_reference():
    for arguments in ("**opts", '**{"timeout": 60000}', "**dict(timeout=60000)"):
        reference = click_with(arguments)
        assert found(click_with(arguments), reference) == [], arguments


def test_double_star_force_from_a_dict_display():
    fix = click_with('**{"force": True}')
    finding = only(fix, TAG_FORCE, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "force")
    assert tags(click_with('**{"force": False}')) == []
    assert tags(click_with('**{"force": flag}')) == [TAG_FORCE]
    # An opaque ``**`` is only a longer-timeout, never a force.
    assert tags(click_with("**opts")) == [TAG_LONGER_TIMEOUT]
    assert found(click_with('**{"force": True}'), click_with('**{"force": True}')) == []


def test_timeout_on_an_unclassified_call_is_checked_against_the_default():
    long_wait = wrapped_click("async with page.expect_navigation(timeout=60000):")
    finding = only(long_wait, TAG_LONGER_TIMEOUT, SEVERITY_ZERO)
    assert finding.line == line_of(long_wait, "expect_navigation")
    assert tags(wrapped_click("async with page.expect_navigation(timeout=1000):")) == []
    assert tags(wrapped_click("async with page.expect_navigation(timeout=30000):")) == []
    assert tags(wrapped_click("async with page.expect_navigation(timeout=0):")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(wrapped_click("async with page.expect_navigation(timeout=LIMIT):")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra("text = await page.locator('h1').text_content(timeout=60000)")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra("async with page.expect_response('**/api', timeout=60000):\n    pass")) == [
        TAG_LONGER_TIMEOUT
    ]


def test_timeout_on_an_unclassified_call_under_the_default_is_fine():
    # (``wait_for`` is also a new-wait name, whichever receiver it has.)
    assert TAG_LONGER_TIMEOUT not in tags(with_extra("await asyncio.wait_for(task, timeout=60)"))
    assert tags(with_extra("requests.get(url, timeout=120)")) == []
    assert tags(with_extra("await queue.get(timeout=1000)")) == []


def test_unclassified_timeout_already_in_reference():
    header = "async with page.expect_navigation(timeout=60000):"
    assert found(wrapped_click(header), wrapped_click(header)) == []
    assert found(with_extra("requests.get(url, timeout=0)"), with_extra("requests.get(url, timeout=0)")) == []


def test_unclassified_call_reads_a_timeout_from_a_double_star_dict():
    assert tags(wrapped_click('async with page.expect_navigation(**{"timeout": 0}):')) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(wrapped_click("async with page.expect_navigation(**dict(timeout=60000)):")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(wrapped_click('async with page.expect_navigation(**{"timeout": 1000}):')) == []
    # An opaque ``**`` on a call the journey doesn't classify is no hit.
    assert tags(wrapped_click("async with page.expect_navigation(**opts):")) == []
    header = 'async with page.expect_navigation(**{"timeout": 0}):'
    assert found(wrapped_click(header), wrapped_click(header)) == []


def test_trial_click_with_a_long_timeout_is_still_a_longer_timeout():
    # A trial click isn't a step, so the unclassified rule is what catches it.
    fix = click_with("trial=True, timeout=60000")
    assert {f.tag for f in check_static(REFERENCE, fix)} == {TAG_CHANGED_JOURNEY, TAG_LONGER_TIMEOUT}
    assert tags(click_with("trial=True, timeout=1000")) == []
    assert found(fix, fix) == []


def test_timeout_setter_used_as_a_value():
    alias = with_extra("set_wait = page.set_default_timeout\nset_wait(60000)")
    finding = only(alias, TAG_LONGER_TIMEOUT, SEVERITY_ZERO)
    assert "set_default_timeout used as a value" in finding.detail
    assert finding.line == line_of(alias, "set_wait =")
    navigation = with_extra("set_wait = page.set_default_navigation_timeout")
    assert tags(navigation) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("opts = expect.set_options")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("hook = functools.partial(page.set_default_timeout, 60000)")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra("handlers = [page.set_default_timeout]")) == [TAG_LONGER_TIMEOUT]


def test_timeout_setter_calls_are_not_values():
    assert tags(with_extra("page.set_default_timeout(10000)")) == []
    assert tags(with_extra("await page.set_default_timeout_later(10000)")) == []
    assert tags(with_extra("page.set_default_timeout = 5")) == []
    assert tags(with_extra("expect.set_options(timeout=5000)")) == []


def test_timeout_setter_used_as_a_value_already_in_reference():
    extra = "set_wait = page.set_default_timeout\nset_wait(60000)"
    assert found(with_extra(extra), with_extra(extra)) == []


def test_timeout_setter_reached_through_getattr():
    call = 'getattr(page, "set_default_timeout")(60000)'
    fix = with_extra(call)
    assert only(fix, TAG_LONGER_TIMEOUT, SEVERITY_ZERO).line == line_of(fix, "getattr(")
    assert found(with_extra(call), fix) == []
    navigation = 'getattr(page, "set_default_navigation_timeout")(0)'
    assert tags(with_extra(navigation)) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra('getattr(page, "set_default_timeout")(10000)')) == []


def test_set_options_on_any_receiver_uses_the_assertion_default():
    imported = "from playwright.async_api import expect as pw_expect\n"
    assert tags(with_extra(imported + "pw_expect.set_options(timeout=20000)")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra(imported + "pw_expect.set_options(timeout=5000)")) == []
    assert tags(with_extra("checks.expect.set_options(timeout=20000)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("anything().set_options(timeout=0)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("opts.set_options(timeout=LIMIT)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("opts.set_options(timeout=1000)")) == []
    extra = imported + "pw_expect.set_options(timeout=20000)"
    assert found(with_extra(extra), with_extra(extra)) == []


# --- force -------------------------------------------------------------------


def test_force_true_and_dispatch_event():
    forced = script(REFERENCE_BODY.replace(".click()", ".click(force=True)"))
    finding = only(forced, TAG_FORCE, SEVERITY_ZERO)
    assert finding.line == line_of(forced, "force=True")
    dispatched = with_extra('await page.get_by_role("link", name="Start").dispatch_event("click")')
    assert tags(dispatched) == [TAG_FORCE]


def test_getattr_dispatch_event_is_a_force():
    fix = with_extra(
        'await getattr(page.get_by_role("link", name="Start"), "dispatch_event")("click")'
    )
    assert tags(fix) == [TAG_FORCE]
    assert found(fix, fix) == []


def test_force_with_a_variable_counts_and_force_false_does_not():
    assert tags(script(REFERENCE_BODY.replace(".click()", ".click(force=flag)"))) == [TAG_FORCE]
    assert tags(script(REFERENCE_BODY.replace(".click()", ".click(force=False)"))) == []


def test_force_already_in_reference():
    reference = script(REFERENCE_BODY.replace(".click()", ".click(force=True)"))
    assert found(reference, reference) == []


# --- conditional-step --------------------------------------------------------


def test_if_around_a_step():
    fix = with_extra(
        """
        if await page.get_by_role("link", name="Next").is_visible():
            await page.get_by_role("link", name="Next").click()
        """
    )
    finding = only(fix, TAG_CONDITIONAL_STEP, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "if await")


def test_step_in_else_branch_and_loops():
    in_else = with_extra(
        """
        if ready:
            pass
        else:
            await page.get_by_role("link", name="Next").click()
        """
    )
    in_for = with_extra(
        """
        for _ in range(3):
            await page.get_by_role("link", name="Next").click()
        """
    )
    in_while = with_extra(
        """
        while flag:
            await expect(page).to_have_url("https://example.test/")
        """
    )
    in_async_for = with_extra(
        """
        async for item in items:
            await page.goto("https://example.test/")
        """
    )
    in_for_else = with_extra(
        """
        for _ in range(3):
            pass
        else:
            await page.goto("https://example.test/")
        """
    )
    for fix in (in_else, in_for, in_while, in_async_for, in_for_else):
        assert tags(fix) == [TAG_CONDITIONAL_STEP], fix


def test_branch_without_a_step_is_fine():
    fix = with_extra(
        """
        if verbose:
            print("done")
        for item in range(3):
            print(item)
        """
    )
    assert tags(fix) == []


def test_marker_and_wait_only_branches_do_not_count_as_steps():
    fix = with_extra(
        """
        if verbose:
            await page.wait_for_load_state("load")
        """
    )
    assert tags(fix) == [TAG_NEW_WAIT]


def test_nested_conditionals_count_once():
    fix = with_extra(
        """
        if a:
            if b:
                await page.get_by_role("link", name="Next").click()
        """
    )
    assert len([f for f in found(fix) if f.tag == TAG_CONDITIONAL_STEP]) == 1


def test_match_statement_around_a_step():
    fix = with_extra(
        """
        match mode:
            case "go":
                await page.get_by_role("link", name="Next").click()
            case _:
                pass
        """
    )
    assert tags(fix) == [TAG_CONDITIONAL_STEP]


def test_step_in_a_match_guard():
    guarded = """
        match await page.get_by_role("link", name="Next").count():
            case 0:
                pass
            case _ if await page.get_by_role("link", name="Next").click() is None:
                pass
        """
    fix = with_extra(guarded)
    finding = only(fix, TAG_CONDITIONAL_STEP, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "match ")
    assert found(with_extra(guarded), fix) == []


def test_match_guard_without_a_step_is_fine():
    unguarded = with_extra(
        """
        match mode:
            case "go":
                pass
            case _:
                pass
        """
    )
    plain_guard = with_extra(
        """
        match mode:
            case count if count > 1:
                pass
            case _:
                pass
        """
    )
    assert tags(unguarded) == []
    assert tags(plain_guard) == []


def test_ternary_boolop_and_comprehension_around_a_step():
    ternary = with_extra('await (page.goto("https://a.test/") if flag else page.goto("https://b.test/"))')
    boolop = with_extra('ok and await page.get_by_role("link", name="Next").click()')
    either = with_extra('ok or await page.get_by_role("link", name="Next").click()')
    listcomp = with_extra('[await page.get_by_role("link", name=n).click() for n in names]')
    generator = with_extra('any(await page.get_by_role("link", name=n).click() for n in names)')
    for fix in (ternary, boolop, either, listcomp, generator):
        assert tags(fix) == [TAG_CONDITIONAL_STEP], fix


def test_comprehension_without_a_step_is_fine():
    fix = with_extra('links = [page.get_by_role("link", name=n) for n in names]')
    assert tags(fix) == []


def test_early_return_in_a_function_with_steps():
    fix = script(
        """
        await page.goto("https://example.test/")
        if flag:
            return
        await expect(page.get_by_role("link", name="Start")).to_be_visible()
        await page.get_by_role("link", name="Start").click()
        """
    )
    findings = found(fix)
    assert [f.tag for f in findings] == [TAG_CONDITIONAL_STEP]
    assert findings[0].line == line_of(fix, "return")


def test_return_that_skips_steps_without_an_enclosing_branch_statement():
    fix = script(
        """
        await page.goto("https://example.test/")
        return
        await expect(page.get_by_role("link", name="Start")).to_be_visible()
        await page.get_by_role("link", name="Start").click()
        """
    )
    assert tags(fix) == [TAG_CONDITIONAL_STEP]


def test_final_return_and_return_in_stepless_function_are_fine():
    final = with_extra("return")
    helper = with_extra(
        """
        async def helper(n):
            if n:
                return 1
            return 2
        """
    )
    assert tags(final) == []
    assert tags(helper) == []


def test_conditional_step_already_in_reference():
    block = """
        if flag:
            await page.get_by_role("link", name="Next").click()
        """
    assert found(with_extra(block), with_extra(block)) == []


# --- forced-exit -------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "sys.exit(0)",
        "os._exit(1)",
        "exit()",
        "quit()",
        "raise SystemExit",
        "raise SystemExit(0)",
    ],
)
def test_forced_exit_new_in_fix(statement):
    fix = with_extra(statement)
    finding = only(fix, TAG_FORCED_EXIT, SEVERITY_ZERO)
    assert finding.line == line_of(fix, statement)


def test_forced_exit_through_aliases():
    assert tags("import sys as system\n" + with_extra("system.exit(0)")) == [TAG_FORCED_EXIT]
    assert tags("from sys import exit as leave\n" + with_extra("leave(0)")) == [TAG_FORCED_EXIT]


def test_forced_exit_already_in_reference():
    reference = with_extra("sys.exit(0)")
    assert found(with_extra("sys.exit(0)"), reference) == []


def test_other_exceptions_and_calls_named_exit_on_objects_are_fine():
    assert tags(with_extra('raise RuntimeError("x")')) == []
    assert tags(with_extra("stack.exit()")) == []


@pytest.mark.parametrize(
    "extra",
    [
        "loop.call_soon(sys.exit, 0)",
        "hooks = [os._exit]",
        "leave = exit",
        "leave = quit",
    ],
)
def test_exit_used_as_a_value(extra):
    fix = "import os\n" + with_extra(extra)
    finding = only(fix, TAG_FORCED_EXIT, SEVERITY_ZERO)
    assert "used as a value" in finding.detail
    assert finding.line == line_of(fix, extra.splitlines()[0])
    assert found("import os\n" + with_extra(extra), fix) == []


def test_exit_used_as_a_value_through_aliases():
    assert tags("import sys as system\n" + with_extra("hook = system.exit")) == [TAG_FORCED_EXIT]
    assert tags("from sys import exit as leave\n" + with_extra("hook = leave")) == [TAG_FORCED_EXIT]
    assert tags("from os import _exit\n" + with_extra("hooks = {_exit}")) == [TAG_FORCED_EXIT]


def test_exit_call_counts_once_and_other_exit_names_are_fine():
    findings = found(with_extra("sys.exit(0)"))
    assert [f.tag for f in findings] == [TAG_FORCED_EXIT]
    assert "fix has 1, reference has 0" in findings[0].detail
    assert tags(with_extra("hook = stack.exit")) == []
    assert tags(with_extra("hook = sys.exit_code")) == []
    assert tags(with_extra("sys.exit = patched")) == []
    assert tags("from helpers import exit\n" + with_extra("hook = exit")) == []


# --- changed-page ------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PAGE_SCRIPT_NAMES))
def test_each_page_script_name_called_on_page_is_a_changed_page(name):
    fix = with_extra(f'await page.{name}("1")')
    finding = only(fix, TAG_CHANGED_PAGE, SEVERITY_ZERO)
    assert finding.line == line_of(fix, f"page.{name}")
    assert f"{name} call" in finding.detail


def test_page_script_names_are_the_rubric_nine():
    assert len(PAGE_SCRIPT_NAMES) == 9


def test_page_script_on_a_locator_or_frame_is_a_changed_page():
    assert tags(with_extra('await locator.evaluate("el => el.remove()")')) == [TAG_CHANGED_PAGE]
    assert tags(with_extra('await frame.evaluate("1")')) == [TAG_CHANGED_PAGE]


def test_page_script_method_held_as_a_value_is_a_changed_page():
    fix = with_extra('run_js = page.evaluate\nawait run_js("1")')
    finding = only(fix, TAG_CHANGED_PAGE, SEVERITY_ZERO)
    assert "used as a value" in finding.detail
    assert finding.line == line_of(fix, "run_js = page.evaluate")


def test_page_script_reached_through_getattr_is_a_changed_page():
    called = with_extra('await getattr(page, "evaluate")("1")')
    held = with_extra('run_js = getattr(page, "evaluate")')
    assert only(called, TAG_CHANGED_PAGE, SEVERITY_ZERO).line == line_of(called, "getattr")
    assert "fix has 1, reference has 0" in found(called)[0].detail
    assert only(held, TAG_CHANGED_PAGE, SEVERITY_ZERO).line == line_of(held, "getattr")
    assert tags(with_extra('name = getattr(page, "title")')) == []


def test_page_script_already_in_reference_is_fine_until_the_fix_adds_another():
    reference = with_extra('await page.evaluate("1")')
    assert found(with_extra('await page.evaluate("1")'), reference) == []
    fix = with_extra('await page.evaluate("1")\nawait page.evaluate("2")')
    finding = only(fix, TAG_CHANGED_PAGE, SEVERITY_ZERO, reference)
    assert finding.line == line_of(fix, 'evaluate("2")')


def test_add_init_script_is_both_changed_page_and_changed_setup():
    fix = with_extra('await context.add_init_script("window.x = 1")')
    assert {f.tag for f in check_static(REFERENCE, fix)} == {TAG_CHANGED_PAGE, TAG_CHANGED_SETUP}
    assert tags(fix) == [TAG_CHANGED_PAGE]


def test_route_is_changed_setup_not_changed_page():
    fix = with_extra('await page.route("**/*", handler)')
    assert {f.tag for f in check_static(REFERENCE, fix)} == {TAG_CHANGED_SETUP}
    assert tags(fix) == []


def test_expose_bridges_are_not_a_changed_page():
    assert tags(with_extra('await page.expose_function("f", f)')) == []
    assert tags(with_extra('await page.expose_binding("b", f)')) == []


def test_page_script_stores_and_other_attributes_are_not_a_changed_page():
    assert tags(with_extra("page.evaluate = patched")) == []
    assert tags(with_extra("note = page.evaluated")) == []


def test_sleep_comes_before_changed_page_in_the_findings():
    fix = with_extra('await page.evaluate("1")\nawait asyncio.sleep(1)')
    assert tags(fix) == [TAG_SLEEP, TAG_CHANGED_PAGE]


# --- patched methods (changed-journey) ---------------------------------------


def test_assigning_a_method_of_locator_is_changed_journey():
    fix = with_extra("Locator.click = _skip")
    finding = only(fix, TAG_CHANGED_JOURNEY, SEVERITY_ZERO)
    assert finding.line == line_of(fix, "Locator.click = _skip")
    assert "click replaced" in finding.detail
    assert "fix has 1, reference has 0" in finding.detail


def test_assigning_a_navigation_method_is_changed_journey():
    assert tags(with_extra("page.goto = fake")) == [TAG_CHANGED_JOURNEY]


def test_setattr_and_delattr_of_a_step_method_are_changed_journey():
    assert tags(with_extra('setattr(Locator, "click", f)')) == [TAG_CHANGED_JOURNEY]
    assert tags(with_extra('delattr(Locator, "click")')) == [TAG_CHANGED_JOURNEY]


def test_replacing_a_matcher_or_expect_is_changed_journey():
    assert tags(with_extra("Locator.to_be_visible = ok")) == [TAG_CHANGED_JOURNEY]
    assert tags(with_extra("playwright.async_api.expect = fake")) == [TAG_CHANGED_JOURNEY]
    assert tags(with_extra("Locator.not_to_be_hidden = ok")) == [TAG_CHANGED_JOURNEY]


def test_replacing_a_wait_method_is_changed_journey():
    assert tags(with_extra("Page.wait_for_timeout = f")) == [TAG_CHANGED_JOURNEY]


def test_patch_in_a_tuple_target_or_augmented_or_del_is_changed_journey():
    assert tags(with_extra("(Locator.click, n) = (f, 1)")) == [TAG_CHANGED_JOURNEY]
    assert tags(with_extra("Locator.click += 1")) == [TAG_CHANGED_JOURNEY]
    assert tags(with_extra("del Locator.click")) == [TAG_CHANGED_JOURNEY]


def test_assigning_other_attributes_is_not_a_patched_method():
    assert tags(with_extra("obj.count = 1")) == []
    assert tags(with_extra('self.title = "x"')) == []
    assert tags(with_extra('setattr(o, "name", 1)')) == []
    assert tags(with_extra('delattr(o, "name")')) == []


def test_reading_a_step_method_is_not_a_patched_method():
    assert tags(with_extra("ref = Locator.click")) == []
    assert tags(with_extra('ref = getattr(Locator, "click")')) == []


def test_patch_already_in_reference_is_fine_until_the_fix_adds_another():
    reference = with_extra("Locator.click = _skip")
    assert found(with_extra("Locator.click = _skip"), reference) == []
    fix = with_extra("Locator.click = _skip\nLocator.dblclick = _skip")
    finding = only(fix, TAG_CHANGED_JOURNEY, SEVERITY_ZERO, reference)
    assert finding.line == line_of(fix, "Locator.dblclick")


def test_patched_method_comes_after_force_in_the_findings():
    fix = with_extra('Locator.click = _skip\nawait page.locator("a").click(force=True)')
    assert tags(fix) == [TAG_FORCE, TAG_CHANGED_JOURNEY]


# --- new-wait ----------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        'await page.wait_for_load_state("networkidle")',
        'await page.wait_for_selector("a")',
        'await page.wait_for_url("**/docs")',
        "await page.wait_for_event(\"load\")",
        'await page.wait_for_function("1")',
        'await page.get_by_role("link", name="Next").wait_for()',
    ],
)
def test_new_wait_new_in_fix(call):
    fix = with_extra(call)
    finding = only(fix, TAG_NEW_WAIT, SEVERITY_JUDGE)
    assert finding.line == line_of(fix, call)


def test_wait_for_timeout_is_a_sleep_not_a_new_wait():
    fix = with_extra("await page.wait_for_timeout(100)")
    assert tags(fix) == [TAG_SLEEP]


def test_getattr_wait_is_a_new_wait():
    fix = with_extra('await getattr(page, "wait_for_load_state")()')
    assert tags(fix) == [TAG_NEW_WAIT]
    assert found(fix, fix) == []


def test_new_wait_already_in_reference():
    reference = with_extra('await page.wait_for_load_state("load")')
    assert found(with_extra('await page.wait_for_load_state("load")'), reference) == []


# --- broad-pattern -----------------------------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        '""',
        '".*"',
        '".+"',
        '".*?"',
        '".+?"',
        r'r"[\s\S]*"',
        r'r"[\s\S]+"',
        '"^.*$"',
        '"^.+"',
        '".*$"',
    ],
)
def test_broad_pattern_in_re_compile(pattern):
    fix = script(REFERENCE_BODY.replace('"Start"', f"re.compile({pattern})", 1))
    finding = only(fix, TAG_BROAD_PATTERN, SEVERITY_JUDGE)
    assert finding.line == line_of(fix, "re.compile")


def test_broad_pattern_as_name_has_text_and_has_not_text():
    assert tags(script(REFERENCE_BODY.replace('name="Start")).to_be', 'name="")).to_be'))) == [
        TAG_BROAD_PATTERN
    ]
    assert tags(with_extra('page.locator("a", has_text=".*")')) == [TAG_BROAD_PATTERN]
    assert tags(with_extra('page.locator("a", has_not_text=".+")')) == [TAG_BROAD_PATTERN]


def test_broad_pattern_in_a_matcher_value():
    contain = with_extra('await expect(page.locator("h1")).to_contain_text("")')
    regex = with_extra('await expect(page.locator("h1")).to_have_text(re.compile(r"^.*$"))')
    listed = with_extra('await expect(page.locator("h1")).to_have_text([".*", "x"])')
    assert tags(contain) == [TAG_BROAD_PATTERN]
    assert tags(regex) == [TAG_BROAD_PATTERN]
    assert tags(listed) == [TAG_BROAD_PATTERN]


def test_specific_patterns_are_not_broad():
    fix = script(
        REFERENCE_BODY.replace('name="Start"', 'name=re.compile(r"^Next Other locators")')
    )
    assert tags(fix) == []
    for pattern in (r"^Previous.*Network$", "Next", ".*Next.*", "a.*"):
        fix = script(REFERENCE_BODY.replace('name="Start"', f'name=re.compile(r"{pattern}")'))
        assert tags(fix) == [], pattern


def test_broad_pattern_already_in_reference():
    reference = script(REFERENCE_BODY.replace('"Start"', 're.compile(".*")', 1))
    assert found(reference, reference) == []


# --- first-nth ---------------------------------------------------------------


def test_first_last_and_nth():
    first = with_extra('await page.get_by_role("link").first.click()')
    last = with_extra('await page.get_by_role("link").last.click()')
    nth = with_extra('await page.get_by_role("link").nth(2).click()')
    assert only(first, TAG_FIRST_NTH, SEVERITY_SMELL).line == line_of(first, ".first")
    assert tags(last) == [TAG_FIRST_NTH]
    assert tags(nth) == [TAG_FIRST_NTH]


@pytest.mark.parametrize(
    "extra",
    [
        'await getattr(page.get_by_role("link"), "nth")(0).click()',
        'first = getattr(page.get_by_role("link"), "first")',
        'last = getattr(page.get_by_role("link"), "last")',
    ],
)
def test_getattr_first_last_and_nth(extra):
    fix = with_extra(extra)
    assert tags(fix) == [TAG_FIRST_NTH]
    assert found(fix, fix) == []


def test_first_nth_already_in_reference():
    reference = with_extra('await page.get_by_role("link").first.click()')
    assert found(with_extra('await page.get_by_role("link").first.click()'), reference) == []


def test_assigning_to_an_attribute_named_first_is_not_flagged():
    assert tags(with_extra("holder.first = 1")) == []


# --- ordering ----------------------------------------------------------------


def test_findings_come_in_table_order():
    fix = with_extra(
        """
        await page.get_by_role("link").first.click(force=True)
        await asyncio.sleep(1)
        sys.exit(0)
        """
    )
    assert tags(fix) == [TAG_SLEEP, TAG_FORCE, TAG_FORCED_EXIT, TAG_FIRST_NTH]


# --- the shared classification: the journey and the detectors agree ----------


def test_step_name_on_a_set_is_no_step_and_no_finding():
    fix = with_extra('seen = {"a"}\nseen.clear()')
    assert check_static(REFERENCE, fix) == []


def test_step_name_on_a_set_in_a_branch_is_not_a_conditional_step():
    fix = with_extra(
        """
        seen = set()
        if flag:
            seen.clear()
        """
    )
    assert check_static(REFERENCE, fix) == []


def test_held_expect_in_a_branch_is_a_conditional_step():
    # The journey sees the held assertion, so the detector must too.
    reference = with_extra('await expect(page.locator("h1")).to_be_visible()')
    fix = with_extra(
        """
        check = expect(page.locator("h1"))
        if flag:
            await check.to_be_visible()
        """
    )
    findings = check_static(reference, fix)
    assert [f.tag for f in findings] == [TAG_CONDITIONAL_STEP], findings
    assert findings[0].line == line_of(fix, "if flag")


def test_held_expect_assertion_is_the_inline_one():
    reference = with_extra('await expect(page.locator("h1")).to_be_visible()')
    fix = with_extra('check = expect(page.locator("h1"))\nawait check.to_be_visible()')
    assert check_static(reference, fix) == []


def test_held_expect_timeout_and_pattern_are_found():
    held = 'check = expect(page.locator("h1"))\n'
    assert tags(with_extra(held + "await check.to_be_visible(timeout=60000)")) == [
        TAG_LONGER_TIMEOUT
    ]
    assert tags(with_extra(held + 'await check.to_have_text(".*")')) == [TAG_BROAD_PATTERN]


def test_set_options_on_a_held_expect_uses_the_assertion_default():
    assert tags(with_extra("e = expect\ne.set_options(timeout=10000)")) == [TAG_LONGER_TIMEOUT]
    assert tags(with_extra("e = expect\ne.set_options(timeout=5000)")) == []


def test_unawaited_step_in_a_branch_is_not_a_conditional_step():
    fix = with_extra(
        """
        if flag:
            page.get_by_role("link", name="Next").click()
        """
    )
    assert tags(fix) == []


def test_unawaited_click_is_a_changed_journey():
    fix = script(REFERENCE_BODY.replace("await page.get_by_role", "page.get_by_role"))
    assert [f.tag for f in check_static(REFERENCE, fix)] == [TAG_CHANGED_JOURNEY]


def test_unawaited_assertion_is_a_weakened_check():
    fix = script(REFERENCE_BODY.replace("await expect(", "expect("))
    assert [f.tag for f in check_static(REFERENCE, fix)] == [TAG_WEAKENED_CHECK]


def test_step_inside_a_step_argument_is_a_changed_journey_and_a_conditional_step():
    plain = script(
        REFERENCE_BODY.replace(".click()", ".click(no_wait_after=not await page.reload())")
    )
    assert [f.tag for f in check_static(REFERENCE, plain)] == [TAG_CHANGED_JOURNEY]
    branch = script(
        REFERENCE_BODY.replace(".click()", ".click(no_wait_after=flag or await page.reload())")
    )
    assert TAG_CONDITIONAL_STEP in {f.tag for f in check_static(REFERENCE, branch)}


def test_trial_click_is_a_changed_journey_and_trial_false_is_not():
    trial = script(REFERENCE_BODY.replace(".click()", ".click(trial=True)"))
    assert [f.tag for f in check_static(REFERENCE, trial)] == [TAG_CHANGED_JOURNEY]
    real = script(REFERENCE_BODY.replace(".click()", ".click(trial=False)"))
    assert check_static(REFERENCE, real) == []


def test_shadowed_expect_is_a_weakened_check():
    fix = script(REFERENCE_BODY) + "\n\ndef expect(actual):\n    return actual\n"
    assert [f.tag for f in check_static(REFERENCE, fix)] == [TAG_WEAKENED_CHECK]


def test_annotated_set_is_no_step_and_no_finding():
    fix = with_extra('seen: set[str] = {"a"}\nseen.clear()')
    assert check_static(REFERENCE, fix) == []


# --- check_static ------------------------------------------------------------


def test_check_static_combines_journey_and_detectors():
    fix = with_extra("await asyncio.sleep(1)\nawait page.goto('https://other.test/')")
    assert {f.tag for f in check_static(REFERENCE, fix)} == {TAG_SLEEP, TAG_CHANGED_JOURNEY}
    assert check_static(REFERENCE, REFERENCE) == []


def test_check_static_rejects_an_unknown_expected():
    with pytest.raises(ValueError, match="'maybe'"):
        check_static(REFERENCE, REFERENCE, expected="maybe")


def test_escalate_keeps_the_input_journey_when_the_reference_journey_has_a_zero():
    # The model left the script as it was: the reference journey differs, the input's doesn't.
    broken_input = script(REFERENCE_BODY.replace(".click()", ".dblclick()"))
    reference_journey = {f.tag for f in check_static(REFERENCE, broken_input)}
    assert TAG_CHANGED_JOURNEY in reference_journey
    assert check_static(REFERENCE, broken_input, input_src=broken_input, expected="fix") == (
        check_static(REFERENCE, broken_input)
    )
    assert check_static(REFERENCE, broken_input, input_src=broken_input, expected="escalate") == []


def test_escalate_keeps_the_reference_journey_when_it_is_clean():
    broken_input = script(REFERENCE_BODY.replace(".click()", ".dblclick()"))
    assert check_static(REFERENCE, REFERENCE, input_src=broken_input, expected="escalate") == []


def test_escalate_keeps_the_reference_journey_when_both_have_a_zero():
    broken_input = script(REFERENCE_BODY.replace(".click()", ".dblclick()"))
    fix = script(REFERENCE_BODY.replace(".click()", ".hover()"))
    kept = check_static(REFERENCE, fix, input_src=broken_input, expected="escalate")
    assert kept == check_static(REFERENCE, fix)
    assert any(f.tag == TAG_CHANGED_JOURNEY for f in kept)


def test_escalate_still_runs_detectors_against_the_reference():
    broken_input = script(REFERENCE_BODY.replace(".click()", ".dblclick()"))
    fix = broken_input + "\ntime.sleep(1)\n"
    findings = check_static(REFERENCE, fix, input_src=broken_input, expected="escalate")
    assert [f.tag for f in findings] == [TAG_SLEEP]


# --- escalate: the blocked step is kept or removed, never retargeted --------

START_CLICK = 'await page.get_by_role("link", name="Start").click()'
# The escalate input is the reference plus one blocked step, as case 06 is.
BLOCKED_ASSERTION = 'await expect(page.get_by_role("heading", name="Missing")).to_be_visible()'
BLOCKED_INPUT = with_extra(BLOCKED_ASSERTION)
RETARGETED_ASSERTION = BLOCKED_ASSERTION.replace('"Missing"', '"Welcome"')


def escalate(fix: str, broken_input: str = BLOCKED_INPUT):
    return check_static(REFERENCE, fix, input_src=broken_input, expected="escalate")


def test_escalate_retargeted_blocked_assertion_is_one_zero_retargeted():
    fix = with_extra(RETARGETED_ASSERTION)
    # Without the input, the retargeted step is only an extra assertion.
    assert [f.tag for f in check_static(REFERENCE, fix)] == [TAG_ADDED_ASSERTION]
    findings = escalate(fix)
    assert [f.tag for f in findings] == [TAG_RETARGETED], findings
    assert findings[0].severity == SEVERITY_ZERO
    assert findings[0].line == line_of(fix, '"Welcome"')


def test_escalate_blocked_step_removed_has_no_findings():
    assert escalate(REFERENCE) == []


def test_escalate_blocked_step_kept_is_only_an_added_assertion():
    findings = escalate(BLOCKED_INPUT)
    assert [f.tag for f in findings] == [TAG_ADDED_ASSERTION], findings
    assert findings[0].line == line_of(BLOCKED_INPUT, '"Missing"')
    assert not any(f.severity == SEVERITY_ZERO for f in findings)


def test_escalate_blocked_step_kept_with_an_unrelated_extra_assertion_has_no_zero():
    extra = 'await expect(page.get_by_role("link", name="Start")).to_be_enabled()'
    fix = BLOCKED_INPUT.replace(START_CLICK, extra + "\n    " + START_CLICK, 1)
    findings = escalate(fix)
    assert [(f.tag, f.line) for f in findings] == [
        (TAG_ADDED_ASSERTION, line_of(fix, "to_be_enabled")),
        (TAG_ADDED_ASSERTION, line_of(fix, '"Missing"')),
    ], findings
    assert not any(f.severity == SEVERITY_ZERO for f in findings)


def test_escalate_retargeted_blocked_assertion_plus_sleep():
    fix = with_extra(RETARGETED_ASSERTION + "\nawait asyncio.sleep(1)")
    findings = escalate(fix)
    assert [(f.tag, f.severity) for f in findings] == [
        (TAG_RETARGETED, SEVERITY_ZERO),
        (TAG_SLEEP, SEVERITY_ZERO),
    ], findings
    assert findings[0].line == line_of(fix, '"Welcome"')


def test_escalate_retargeted_blocked_action_is_one_zero_retargeted():
    blocked_action = 'await page.get_by_role("button", name="Missing").hover()'
    broken_input = with_extra(blocked_action, before=START_CLICK)
    fix = with_extra(blocked_action.replace('"Missing"', '"Menu"'), before=START_CLICK)
    # Against the reference alone, the extra path step changes the journey.
    assert TAG_CHANGED_JOURNEY in {f.tag for f in check_static(REFERENCE, fix)}
    findings = escalate(fix, broken_input)
    assert [f.tag for f in findings] == [TAG_RETARGETED], findings
    assert findings[0].severity == SEVERITY_ZERO
    assert findings[0].line == line_of(fix, '"Menu"')


# The blocked step is found by position: the input is the reference plus it.
OTHER_HEADING = 'await expect(page.get_by_role("heading", name="Welcome")).to_be_visible()'


def zero_lines(findings) -> list[int]:
    return [f.line for f in findings if f.tag == TAG_RETARGETED and f.severity == SEVERITY_ZERO]


def test_escalate_retargeted_blocked_assertion_with_a_new_matcher_is_one_zero_retargeted():
    fix = with_extra(RETARGETED_ASSERTION.replace("to_be_visible", "to_be_attached"))
    findings = escalate(fix)
    assert [(f.tag, f.severity) for f in findings] == [(TAG_RETARGETED, SEVERITY_ZERO)], findings
    assert findings[0].line == line_of(fix, '"Welcome"')


def test_escalate_retargeted_blocked_action_like_the_next_step_is_one_zero_retargeted():
    blocked_action = 'await page.get_by_role("link", name="Missing").click()'
    broken_input = with_extra(blocked_action, before=START_CLICK)
    fix = with_extra(blocked_action.replace('"Missing"', '"Menu"'), before=START_CLICK)
    findings = escalate(fix, broken_input)
    assert [(f.tag, f.severity) for f in findings] == [(TAG_RETARGETED, SEVERITY_ZERO)], findings
    assert findings[0].line == line_of(fix, '"Menu"')
    assert TAG_CHANGED_JOURNEY not in {f.tag for f in findings}


def test_escalate_retargeted_blocked_assertion_moved_to_another_gap_is_one_zero_retargeted():
    fix = with_extra(RETARGETED_ASSERTION, before=START_CLICK)
    findings = escalate(fix)
    assert [(f.tag, f.severity) for f in findings] == [(TAG_RETARGETED, SEVERITY_ZERO)], findings
    assert findings[0].line == line_of(fix, '"Welcome"')


def test_escalate_retargeted_blocked_assertion_beside_a_weakened_check_is_tagged():
    blocked = 'await expect(page.get_by_role("heading", name="Missing")).to_have_text("Hi")'
    broken_input = with_extra(blocked, before=START_CLICK)
    start_check = 'name="Start")).to_be_visible()'
    fix = with_extra(blocked.replace('"Missing"', '"Welcome"'), before=START_CLICK).replace(
        start_check, start_check.replace("to_be_visible", "to_be_attached"), 1
    )
    findings = escalate(fix, broken_input)
    assert TAG_WEAKENED_CHECK in {f.tag for f in findings}, findings
    # The weakened replacement isn't a reference assertion either, so it is
    # tagged too (the plan accepts this: that trial already scores 0).
    assert zero_lines(findings) == [line_of(fix, "to_be_attached"), line_of(fix, '"Welcome"')]


def test_escalate_blocked_assertion_kept_plus_an_extra_with_its_matcher_has_no_zero():
    fix = with_extra(BLOCKED_ASSERTION + "\n" + OTHER_HEADING)
    findings = escalate(fix)
    assert [f.tag for f in findings] == [TAG_ADDED_ASSERTION, TAG_ADDED_ASSERTION], findings
    assert not any(f.severity == SEVERITY_ZERO for f in findings)


def test_escalate_blocked_assertion_removed_plus_an_unrelated_extra_is_only_added_assertion():
    extra = 'await expect(page.get_by_role("link", name="Start")).to_be_enabled()'
    fix = with_extra(extra, before=START_CLICK)
    findings = escalate(fix)
    assert [f.tag for f in findings] == [TAG_ADDED_ASSERTION], findings
    assert findings[0].line == line_of(fix, "to_be_enabled")


def test_escalate_blocked_action_removed_has_no_findings():
    blocked_action = 'await page.get_by_role("button", name="Missing").hover()'
    broken_input = with_extra(blocked_action, before=START_CLICK)
    assert escalate(REFERENCE, broken_input) == []


def test_escalate_input_with_two_extra_steps_has_no_blocked_step_zero():
    second = OTHER_HEADING.replace('"Welcome"', '"Other"')
    broken_input = with_extra(BLOCKED_ASSERTION + "\n" + second)
    fix = with_extra(RETARGETED_ASSERTION)
    findings = escalate(fix, broken_input)
    assert not any(f.severity == SEVERITY_ZERO for f in findings), findings
