"""Tests for scriptfix.steps: classification, source order and normalization."""

from __future__ import annotations

import ast
import textwrap

import pytest

from scriptfix.steps import (
    KIND_ACTION,
    KIND_ASSERTION,
    KIND_MARKER,
    KIND_NAVIGATION,
    KIND_SETUP,
    KIND_WAIT,
    Step,
    call_key,
    call_name,
    classify_module,
    extract_steps,
)


def steps_of(source: str) -> list[Step]:
    return extract_steps(textwrap.dedent(source))


def kinds_and_names(source: str) -> list[tuple[str, str]]:
    return [(step.kind, step.name) for step in steps_of(source)]


def only(source: str, kind: str) -> list[Step]:
    return [step for step in steps_of(source) if step.kind == kind]


ASYNC_SCRIPT = """
    import asyncio
    from playwright.async_api import async_playwright, expect

    async def run(playwright):
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://example.test/")
        await expect(page.get_by_role("link", name="Start")).to_be_visible()
        await page.get_by_role("link", name="Start").click()
        await context.close()

    async def main():
        async with async_playwright() as playwright:
            await run(playwright)

    asyncio.run(main())
"""

SYNC_SCRIPT = """
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://example.test/")
        expect(page.get_by_role("link", name="Start")).to_be_visible()
        page.get_by_role("link", name="Start").click()
        context.close()
"""

EXPECTED_STEPS = [
    (KIND_SETUP, "launch", "playwright.chromium"),
    (KIND_SETUP, "new_context", "browser"),
    (KIND_SETUP, "new_page", "context"),
    (KIND_NAVIGATION, "goto", "page"),
    (KIND_ASSERTION, "to_be_visible", "page.get_by_role('link', name='Start')"),
    (KIND_ACTION, "click", "page.get_by_role('link', name='Start')"),
    (KIND_SETUP, "close", "context"),
]


# --- async and sync API -----------------------------------------------------


def test_async_api_script_yields_its_steps_in_order() -> None:
    assert [(s.kind, s.name, s.target) for s in steps_of(ASYNC_SCRIPT)] == EXPECTED_STEPS


def test_sync_api_script_yields_the_same_steps_as_the_async_one() -> None:
    assert [(s.kind, s.name, s.target) for s in steps_of(SYNC_SCRIPT)] == EXPECTED_STEPS


def test_sync_api_page_from_new_page_is_not_substituted() -> None:
    goto = only(SYNC_SCRIPT, KIND_NAVIGATION)[0]
    assert goto.target == "page"


def test_step_line_is_the_line_of_the_call() -> None:
    goto = only(ASYNC_SCRIPT, KIND_NAVIGATION)[0]
    assert goto.line == 9


def test_syntax_error_propagates() -> None:
    with pytest.raises(SyntaxError):
        extract_steps("page.goto(")


# --- classification ---------------------------------------------------------


def test_classified_assertion_is_one_step_without_its_inner_calls() -> None:
    source = 'await expect(page.get_by_role("link", name="X")).to_be_visible()'
    assert steps_of(source) == [
        Step(KIND_ASSERTION, "to_be_visible", "page.get_by_role('link', name='X')", (), (), 1)
    ]


def test_a_non_step_call_inside_a_classified_call_adds_no_step() -> None:
    source = 'await page.goto(await page.get_attribute("a", "href"))'
    assert kinds_and_names(source) == [(KIND_NAVIGATION, "goto")]


def test_steps_inside_an_unclassified_call_are_extracted() -> None:
    source = 'helper(page.click("#a"), page.fill("#b", "text"))'
    assert kinds_and_names(source) == [(KIND_ACTION, "click"), (KIND_ACTION, "fill")]


def test_steps_in_an_unclassified_receiver_are_extracted() -> None:
    source = 'page.goto("x").then()'
    assert kinds_and_names(source) == [(KIND_NAVIGATION, "goto")]


def test_bare_expect_call_is_not_a_step() -> None:
    assert steps_of("expect(page)") == []


def test_negated_matcher_is_an_assertion() -> None:
    assert kinds_and_names("expect(page.locator('a')).not_to_be_visible()") == [
        (KIND_ASSERTION, "not_to_be_visible")
    ]


def test_matcher_on_a_non_expect_receiver_is_not_an_assertion() -> None:
    assert steps_of("checker.to_be_visible()") == []


def test_assertion_values_are_the_matcher_arguments() -> None:
    step = steps_of('expect(page).to_have_url("https://example.test/")')[0]
    assert (step.target, step.values) == ("page", ("'https://example.test/'",))


def test_wait_for_and_wait_for_timeout_are_distinct_waits() -> None:
    source = """
        page.locator("a").wait_for()
        page.wait_for_timeout(1000)
    """
    assert kinds_and_names(source) == [(KIND_WAIT, "wait_for"), (KIND_WAIT, "wait_for_timeout")]


def test_tracing_start_and_stop_are_setup_on_a_tracing_receiver() -> None:
    source = """
        context.tracing.start(screenshots=True)
        context.tracing.stop()
    """
    assert kinds_and_names(source) == [(KIND_SETUP, "start"), (KIND_SETUP, "stop")]


def test_start_and_stop_on_other_receivers_are_not_steps() -> None:
    source = """
        timer.start()
        server.stop()
        tracing_helper.start()
    """
    assert steps_of(source) == []


def test_tracing_receiver_held_in_a_local_variable_is_still_tracing() -> None:
    source = """
        tracer = context.tracing
        tracer.start()
    """
    assert kinds_and_names(source) == [(KIND_SETUP, "start")]


def test_expect_set_options_is_setup() -> None:
    assert kinds_and_names("expect.set_options(timeout=10000)") == [(KIND_SETUP, "set_options")]


def test_set_options_on_another_receiver_is_not_a_step() -> None:
    assert steps_of("client.set_options(timeout=10000)") == []


def test_unknown_playwright_methods_are_not_steps() -> None:
    assert steps_of('page.get_by_role("link").count()') == []


# --- the shared classification ------------------------------------------------


def test_classify_module_keys_every_step_by_start_and_end() -> None:
    source = textwrap.dedent(ASYNC_SCRIPT)
    tree = ast.parse(source)
    kinds = classify_module(tree)
    assert sorted(kinds.values()) == sorted(s.kind for s in steps_of(ASYNC_SCRIPT))
    matcher = next(
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) == "to_be_visible"
    )
    inner = matcher.func.value  # the expect(...) call, starting where the matcher does
    assert call_key(matcher)[:2] == call_key(inner)[:2]
    assert kinds[call_key(matcher)] == KIND_ASSERTION
    assert call_key(inner) not in kinds


def test_step_name_on_a_set_literal_is_not_a_step() -> None:
    source = """
        seen = {"a"}
        seen.clear()
    """
    assert steps_of(source) == []


@pytest.mark.parametrize(
    "receiver",
    ['"s"', "[1]", "(1, 2)", "{1}", '{"k": 1}', 'f"{x}"', "[n for n in ns]", "set()", "dict(a=1)"],
)
def test_literal_and_builtin_receivers_are_not_steps(receiver: str) -> None:
    assert steps_of(f"{receiver}.clear()") == []


def test_builtin_rebound_in_the_module_is_an_unknown_receiver() -> None:
    source = """
        set = lambda: page
        set().click()
    """
    assert kinds_and_names(source) == [(KIND_ACTION, "click")]


@pytest.mark.parametrize("rebinding", ["def f(set): pass", "from helpers import *"])
def test_builtin_that_may_be_rebound_elsewhere_is_an_unknown_receiver(rebinding: str) -> None:
    assert kinds_and_names(f"{rebinding}\nset().click()") == [(KIND_ACTION, "click")]


def test_subscript_receiver_is_still_a_step() -> None:
    assert kinds_and_names("[page][0].click()") == [(KIND_ACTION, "click")]


def test_parameter_receiver_is_still_a_step() -> None:
    assert kinds_and_names("def go(p):\n    p.click()") == [(KIND_ACTION, "click")]


def test_non_step_method_on_a_string_is_nothing() -> None:
    source = """
        x = "s"
        x.strip()
    """
    assert steps_of(source) == []


def test_expect_held_in_a_name_is_the_inline_assertion() -> None:
    inline = """
        async def run(page):
            loc = page.get_by_role("link", name="Next")
            await expect(loc).to_be_visible(timeout=1000)
    """
    held = """
        async def run(page):
            loc = page.get_by_role("link", name="Next")
            check = expect(loc)
            await check.to_be_visible(timeout=1000)
    """
    first, second = steps_of(inline), steps_of(held)
    assert [(s.kind, s.name, s.target, s.values, s.options) for s in first] == [
        (s.kind, s.name, s.target, s.values, s.options) for s in second
    ]
    assert first[0].target == "page.get_by_role('link', name='Next')"


def test_expect_assigned_twice_is_not_an_assertion() -> None:
    source = """
        async def run(page):
            check = expect(page.locator("a"))
            check = expect(page.locator("b"))
            await check.to_be_visible()
    """
    assert steps_of(source) == []


def test_one_held_expect_used_twice_is_two_assertions() -> None:
    source = """
        async def run(page):
            e = expect(page.locator("a"))
            await e.to_be_visible()
            await e.to_have_text("A")
    """
    assert [(s.kind, s.name, s.target) for s in steps_of(source)] == [
        (KIND_ASSERTION, "to_be_visible", "page.locator('a')"),
        (KIND_ASSERTION, "to_have_text", "page.locator('a')"),
    ]


def test_unawaited_step_statements_in_an_async_def_are_not_steps() -> None:
    source = """
        async def run(page):
            page.goto("a")
            page.locator("b").click()
            expect(page.locator("c")).to_be_visible()
            await page.locator("d").click()
    """
    assert [(s.kind, s.name, s.target) for s in steps_of(source)] == [
        (KIND_ACTION, "click", "page.locator('d')")
    ]


def test_unawaited_setup_and_waits_keep_their_kind() -> None:
    source = """
        async def run(page):
            page.set_default_timeout(1000)
            page.wait_for_timeout(10)
            expect.set_options(timeout=1000)
    """
    assert kinds_and_names(source) == [
        (KIND_SETUP, "set_default_timeout"),
        (KIND_WAIT, "wait_for_timeout"),
        (KIND_SETUP, "set_options"),
    ]


def test_step_statements_outside_an_async_def_are_steps() -> None:
    source = """
        page.click("a")

        def run(page):
            page.click("b")

        async def outer(page):
            def inner():
                page.click("c")
    """
    assert [s.values for s in steps_of(source)] == [("'a'",), ("'b'",), ("'c'",)]


def test_unawaited_step_nested_in_another_expression_is_still_a_step() -> None:
    source = """
        async def run(page):
            await asyncio.gather(page.click("a"))
            asyncio.ensure_future(page.click("b"))
    """
    assert [s.values for s in steps_of(source)] == [("'a'",), ("'b'",)]


def test_steps_in_a_classified_call_come_before_it() -> None:
    source = """
        async def run(page):
            await page.locator(await page.goto("a")).click(no_wait_after=not await page.reload())
    """
    assert kinds_and_names(source) == [
        (KIND_NAVIGATION, "goto"),
        (KIND_NAVIGATION, "reload"),
        (KIND_ACTION, "click"),
    ]


def test_arguments_of_an_unawaited_step_are_still_searched() -> None:
    source = """
        async def run(page):
            page.click("a", no_wait_after=await page.reload())
    """
    assert kinds_and_names(source) == [(KIND_NAVIGATION, "reload")]


@pytest.mark.parametrize(
    ("trial", "is_step"),
    [("trial=False", True), ("trial=True", False), ("trial=flag", False), ("trial=1", False)],
)
def test_trial_action_is_not_a_step(trial: str, is_step: bool) -> None:
    steps = steps_of(f'page.locator("a").click({trial})')
    assert [s.name for s in steps] == (["click"] if is_step else [])


def test_trial_keyword_on_a_non_action_keeps_its_kind() -> None:
    assert kinds_and_names('page.goto("a", trial=True)') == [(KIND_NAVIGATION, "goto")]


@pytest.mark.parametrize(
    "binding",
    [
        "from playwright.async_api import expect",
        "from playwright.sync_api import expect",
        "from playwright.async_api import *",
        "import asyncio",  # no binding of expect at all
    ],
)
def test_playwright_expect_makes_assertions(binding: str) -> None:
    source = f"{binding}\nexpect(page).to_have_url('a')\nexpect.set_options(timeout=1000)"
    assert kinds_and_names(source) == [
        (KIND_ASSERTION, "to_have_url"),
        (KIND_SETUP, "set_options"),
    ]


@pytest.mark.parametrize(
    "binding",
    [
        "def expect(actual):\n    return actual",
        "class expect: pass",
        "expect = make_checker()",
        "from playwright.async_api import expect as expect",
        "from helpers import expect",
        "from helpers import *",
        "import expect",
        "def run(expect): pass",
        "for expect in checkers: pass",
        "from playwright.async_api import expect\nexpect = other",
    ],
)
def test_shadowed_expect_makes_no_assertions(binding: str) -> None:
    source = f"{binding}\nexpect(page).to_have_url('a')\nexpect.set_options(timeout=1000)"
    assert steps_of(source) == []


def test_attribute_expect_is_unchanged_when_the_name_is_shadowed() -> None:
    source = "def expect(actual):\n    return actual\npw.expect(page).to_have_url('a')"
    assert kinds_and_names(source) == [(KIND_ASSERTION, "to_have_url")]


def test_annotated_assignment_is_a_plain_binding() -> None:
    source = """
        def run(page):
            seen: set[str] = {"a"}
            seen.clear()
            link: object = page.locator("b")
            link.click()
    """
    assert [(s.name, s.target) for s in steps_of(source)] == [("click", "page.locator('b')")]


def test_annotation_without_a_value_is_another_binding() -> None:
    source = """
        def run(page):
            seen: set[str]
            seen = {"a"}
            seen.clear()
    """
    assert [(s.name, s.target) for s in steps_of(source)] == [("clear", "seen")]


# --- arguments --------------------------------------------------------------


def test_option_kwargs_go_to_options_not_values() -> None:
    step = steps_of('page.locator("a").click(button="right", force=True, timeout=5000)')[0]
    assert step.values == ()
    assert step.options == (("button", "'right'"), ("force", "True"), ("timeout", "5000"))


def test_value_kwargs_follow_positionals_sorted_by_name() -> None:
    step = steps_of('page.goto(url, b=2, a=1, wait_until="load")')[0]
    assert step.values == ("url", "a=1", "b=2")
    assert step.options == (("wait_until", "'load'"),)


def test_double_star_kwargs_are_kept_as_values() -> None:
    step = steps_of("page.goto(url, **extra)")[0]
    assert step.values == ("url", "**extra")


@pytest.mark.parametrize("call", ["type(x)", "check()", "close()", "click(locator)"])
def test_bare_name_call_is_not_a_step(call: str) -> None:
    assert steps_of(call) == []


def test_bare_call_wrapping_a_bare_call_has_no_steps() -> None:
    assert steps_of("print(type(x))") == []


def test_arguments_of_a_bare_call_are_still_searched() -> None:
    assert kinds_and_names("foo(page.click('a'))") == [(KIND_ACTION, "click")]


def test_bare_helper_call_between_steps_keeps_the_same_steps() -> None:
    plain = """
        page.goto("a")
        page.click("b")
    """
    with_helper = """
        page.goto("a")
        check(close(type(page)))
        page.click("b")
    """
    assert [(s.kind, s.name, s.target, s.values) for s in steps_of(with_helper)] == [
        (s.kind, s.name, s.target, s.values) for s in steps_of(plain)
    ]


# --- source order -----------------------------------------------------------


def test_source_order_is_kept_through_try_and_if() -> None:
    source = """
        async def run(page):
            await page.goto("a")
            try:
                await page.click("b")
            except Exception:
                await page.reload()
            else:
                await page.fill("c", "d")
            finally:
                await page.hover("e")
            if ready:
                await page.press("f", "Enter")
            else:
                await page.go_back()
            await page.check("g")
    """
    assert [name for _, name in kinds_and_names(source)] == [
        "goto", "click", "reload", "fill", "hover", "press", "go_back", "check",
    ]


def test_source_order_is_kept_through_loops_and_with_bodies() -> None:
    source = """
        for item in items:
            page.click(item)
        else:
            page.reload()
        while busy:
            page.hover("a")
        with lock:
            page.fill("b", "c")
    """
    assert [name for _, name in kinds_and_names(source)] == ["click", "reload", "hover", "fill"]


def test_steps_in_nested_arguments_come_out_by_position() -> None:
    source = 'helper(page.click("a"), {"k": page.hover("b")}, page.fill("c", "d"))'
    assert [name for _, name in kinds_and_names(source)] == ["click", "hover", "fill"]


def test_steps_in_a_conditional_expression_come_out_by_position() -> None:
    source = 'helper(page.click("a") if page.hover("b") else page.fill("c", "d"))'
    assert [name for _, name in kinds_and_names(source)] == ["click", "hover", "fill"]


def test_function_and_class_bodies_are_walked_in_order() -> None:
    source = """
        page.goto("a")

        class User:
            def task(self):
                self.page.click("b")

        def other(page):
            page.hover("c")
    """
    assert [name for _, name in kinds_and_names(source)] == ["goto", "click", "hover"]


# --- markers ----------------------------------------------------------------


def test_marker_produces_start_and_end_steps_around_its_body() -> None:
    source = """
        async def task(self):
            async with event(self, "login"):
                await self.page.goto("a")
                await self.page.click("b")
            await self.page.hover("c")
    """
    assert kinds_and_names(source) == [
        (KIND_MARKER, "start:login"),
        (KIND_NAVIGATION, "goto"),
        (KIND_ACTION, "click"),
        (KIND_MARKER, "end"),
        (KIND_ACTION, "hover"),
    ]


def test_marker_steps_have_empty_target_values_and_options() -> None:
    marker = steps_of('with event(self, "login"):\n    pass')
    assert marker == [
        Step(KIND_MARKER, "start:login", "", (), (), 1),
        Step(KIND_MARKER, "end", "", (), (), 1),
    ]


def test_marker_on_an_attribute_call_is_recognized() -> None:
    source = 'with markers.event(self, "checkout"):\n    pass'
    assert [s.name for s in steps_of(source)] == ["start:checkout", "end"]


def test_marker_label_falls_back_to_the_unparsed_first_argument() -> None:
    source = "with event(label_for(step)):\n    pass"
    assert steps_of(source)[0].name == "start:label_for(step)"


def test_nested_markers_close_in_order() -> None:
    source = """
        with event(self, "outer"), event(self, "inner"):
            page.click("a")
    """
    assert [s.name for s in steps_of(source)] == ["start:outer", "start:inner", "click", "end", "end"]


def test_steps_in_a_markers_arguments_come_before_its_start() -> None:
    source = """
        with event("t", note=await page.click("#a")):
            await page.hover("#b")
    """
    assert kinds_and_names(source) == [
        (KIND_ACTION, "click"),
        (KIND_MARKER, "start:t"),
        (KIND_ACTION, "hover"),
        (KIND_MARKER, "end"),
    ]


def test_steps_in_a_markers_arguments_come_in_source_order() -> None:
    source = """
        with event(await page.fill("#a", "x"), await page.press("#a", "A"), note=page.hover("#b")):
            pass
    """
    assert kinds_and_names(source) == [
        (KIND_ACTION, "fill"),
        (KIND_ACTION, "press"),
        (KIND_ACTION, "hover"),
        (KIND_MARKER, "start:await page.fill('#a', 'x')"),
        (KIND_MARKER, "end"),
    ]


def test_non_marker_with_item_is_searched_for_steps() -> None:
    source = """
        with page.expect_navigation(timeout=page.click("a")):
            page.hover("b")
    """
    assert [name for _, name in kinds_and_names(source)] == ["click", "hover"]


# --- normalization ----------------------------------------------------------


def test_quotes_and_spacing_are_normalized() -> None:
    first = steps_of("page.goto( 'a' , referer = \"b\" )")[0]
    second = steps_of('page.goto("a", referer="b")')[0]
    assert (first.target, first.values, first.options) == (
        second.target,
        second.values,
        second.options,
    )


def test_locator_in_a_local_variable_normalizes_to_the_same_target() -> None:
    inline = """
        async def run(page):
            await expect(page.get_by_role("link", name="Next")).to_be_visible()
            await page.get_by_role("link", name="Next").click()
    """
    local = """
        async def run(page):
            next_link = page.get_by_role("link", name="Next")
            await expect(next_link).to_be_visible()
            await next_link.click()
    """
    assert [(s.kind, s.name, s.target) for s in steps_of(inline)] == [
        (s.kind, s.name, s.target) for s in steps_of(local)
    ]


def test_substitution_applies_to_values_and_options() -> None:
    source = """
        url = "https://example.test/"
        wait = 5000
        page.goto(url, timeout=wait)
    """
    step = steps_of(source)[0]
    assert (step.values, step.options) == (("'https://example.test/'",), (("timeout", "5000"),))


def test_substitution_is_recursive() -> None:
    source = """
        menu = page.locator("#menu")
        item = menu.get_by_text("Save")
        item.click()
    """
    assert steps_of(source)[0].target == "page.locator('#menu').get_by_text('Save')"


def test_substitution_cycle_stops_at_the_depth_limit() -> None:
    source = """
        a = b
        b = a
        a.click()
    """
    assert steps_of(source)[0].target in {"a", "b"}


def test_name_assigned_from_await_is_not_substituted() -> None:
    source = """
        async def run(context):
            page = await context.new_page()
            handle = await page.query_selector("a")
            await handle.click()
    """
    assert steps_of(source)[-1].target == "handle"


def test_name_assigned_twice_is_not_substituted() -> None:
    source = """
        def run(page):
            link = page.get_by_role("link", name="A")
            link = page.get_by_role("link", name="B")
            link.click()
    """
    assert steps_of(source)[0].target == "link"


def test_parameter_name_is_not_substituted() -> None:
    source = """
        def run(link):
            link = page.locator("a")
            link.click()
    """
    assert steps_of(source)[0].target == "link"


@pytest.mark.parametrize(
    "rebinding",
    [
        "link += other",
        "link: object = None",
        "link, other = pair",
        "for link in links: pass",
        "with opener() as link: pass",
        "try:\n    pass\nexcept Exception as link:\n    pass",
        "(link := other)",
        "import link",
        "def link(): pass",
        "class link: pass",
        "del link",
    ],
)
def test_any_other_binding_of_the_name_prevents_substitution(rebinding: str) -> None:
    source = 'def run(page):\n    link = page.locator("a")\n'
    source += textwrap.indent(rebinding, "    ") + "\n    link.click()\n"
    assert steps_of(source)[0].target == "link"


def test_name_declared_global_in_its_function_is_not_substituted() -> None:
    source = """
        def run(page):
            global link
            link = page.locator("a")
            link.click()
    """
    assert steps_of(source)[0].target == "link"


def test_nonlocal_rebinding_in_a_nested_function_prevents_substitution() -> None:
    source = """
        def run(page):
            link = page.locator("a")
            def swap():
                nonlocal link
                link = page.locator("b")
            link.click()
    """
    assert [s.target for s in steps_of(source)] == ["link"]


def test_module_name_declared_global_in_a_function_is_not_substituted() -> None:
    source = """
        link = page.locator("a")
        def swap():
            global link
            link = page.locator("b")
        link.click()
    """
    assert [s.target for s in steps_of(source)] == ["link"]


def test_name_assigned_from_an_expect_call_is_not_substituted() -> None:
    source = """
        check = expect(page.locator("a"))
        page.goto(check)
    """
    assert steps_of(source)[0].values == ("check",)


def test_name_assigned_a_lambda_is_not_substituted() -> None:
    source = """
        pick = lambda: page.locator("a")
        pick().click()
    """
    assert steps_of(source)[0].target == "pick()"


def test_a_nested_function_does_not_see_the_enclosing_scope() -> None:
    source = """
        def run(page):
            link = page.locator("a")
            def inner():
                link.click()
    """
    assert steps_of(source)[0].target == "link"


def test_lambda_parameter_shadows_a_substitutable_name() -> None:
    source = """
        loc = page.locator("a")
        page.on("dialog", lambda loc: loc.click())
    """
    assert steps_of(source)[0].target == "loc"


def test_comprehension_variable_shadows_a_substitutable_name() -> None:
    source = """
        loc = page.locator("a")
        [loc.click() for loc in items]
    """
    assert steps_of(source)[0].target == "loc"


# --- module constants ---------------------------------------------------------


def goto_values(source: str) -> list[tuple[str, ...]]:
    return [step.values for step in steps_of(source) if step.name == "goto"]


def without_lines(source: str) -> list[tuple[str, str, str, tuple[str, ...], tuple]]:
    """The steps of ``source`` less their line numbers, to compare differently laid-out sources."""
    return [(s.kind, s.name, s.target, s.values, s.options) for s in steps_of(source)]


def test_module_constant_substitutes_into_a_function() -> None:
    constant = """
        URL = "https://x/"

        async def run(page):
            await page.goto(URL)
    """
    literal = """
        async def run(page):
            await page.goto("https://x/")
    """
    assert without_lines(constant) == without_lines(literal)
    assert goto_values(constant) == [("'https://x/'",)]


@pytest.mark.parametrize("literal", ["7", "1.5", '"text"'])
def test_module_constant_may_be_a_str_int_or_float(literal: str) -> None:
    source = f"""
        VALUE = {literal}

        def run(page):
            page.fill("#a", VALUE)
    """
    assert steps_of(source)[0].values == ("'#a'", literal.replace('"', "'"))


@pytest.mark.parametrize("value", ["True", "None", 'b"x"', "make_url()", '"a" + "b"', '["a"]'])
def test_module_name_that_is_not_a_scalar_constant_does_not_substitute(value: str) -> None:
    source = f"""
        URL = {value}

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("URL",)]


def test_module_constant_assigned_twice_does_not_substitute() -> None:
    source = """
        URL = "https://x/"
        URL = "https://y/"

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("URL",)]


def test_module_constant_declared_global_anywhere_does_not_substitute() -> None:
    source = """
        URL = "https://x/"

        def retarget():
            global URL
            URL = "https://y/"

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("URL",)]


def test_function_binding_of_a_module_constant_name_wins() -> None:
    source = """
        URL = "https://x/"

        def run(page):
            URL = "https://y/"
            page.goto(URL)

        def other(page, URL):
            page.goto(URL)
    """
    assert goto_values(source) == [("'https://y/'",), ("URL",)]


def test_module_constant_is_shadowed_by_an_enclosing_function() -> None:
    source = """
        URL = "https://x/"

        def outer(page):
            URL = make_url()

            def inner():
                page.goto(URL)
    """
    assert goto_values(source) == [("URL",)]


def test_module_constant_reaches_nested_functions_and_methods() -> None:
    source = """
        URL = "https://x/"

        def outer(page):
            def inner():
                page.goto(URL)

        class Runner:
            def run(self, page):
                page.goto(URL)
    """
    assert goto_values(source) == [("'https://x/'",), ("'https://x/'",)]


@pytest.mark.parametrize(
    "call", ["globals()", "vars()", "setattr(m, 'n', 1)", "exec(code)", "eval(code)"]
)
def test_module_that_can_rebind_names_invisibly_has_no_module_constants(call: str) -> None:
    source = f"""
        URL = "https://x/"
        {call}

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("URL",)]


def test_module_without_dynamic_name_calls_keeps_its_module_constants() -> None:
    source = """
        URL = "https://x/"
        print(globals_report)

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("'https://x/'",)]


def test_dynamic_name_must_be_a_bare_call_to_block_module_constants() -> None:
    source = """
        URL = "https://x/"
        report.globals()

        def run(page):
            page.goto(URL)
    """
    assert goto_values(source) == [("'https://x/'",)]


# --- ``**`` arguments that spell out their keywords ----------------------------


def test_double_star_dict_display_splits_like_explicit_keywords() -> None:
    spelled = steps_of('page.get_by_role("link").click(**{"timeout": 5000})')
    explicit = steps_of('page.get_by_role("link").click(timeout=5000)')
    assert spelled == explicit
    assert spelled[0].options == (("timeout", "5000"),)


def test_double_star_dict_splits_options_and_named_values() -> None:
    spelled = steps_of('page.fill("#a", "x", **{"timeout": 5000, "no_wait_after": True})')
    explicit = steps_of('page.fill("#a", "x", timeout=5000, no_wait_after=True)')
    assert spelled == explicit
    named = steps_of('page.select_option("#a", **{"label": "A"})')
    assert named == steps_of('page.select_option("#a", label="A")')


def test_double_star_dict_held_in_a_name_assigned_once_splits() -> None:
    source = """
        opts = {"timeout": 5000}
        page.get_by_role("link").click(**opts)
    """
    assert without_lines(source) == without_lines('page.get_by_role("link").click(timeout=5000)')


def test_double_star_dict_held_in_a_name_assigned_twice_stays_opaque() -> None:
    source = """
        opts = {"timeout": 5000}
        opts = {"timeout": 1}
        page.get_by_role("link").click(**opts)
    """
    step = steps_of(source)[0]
    assert step.values == ("**opts",)
    assert step.options == ()


@pytest.mark.parametrize(
    "unpacked, expected",
    [
        ("{**a}", "**{**a}"),
        ("{k: 1}", "**{k: 1}"),
        ('{"timeout": 1, **a}', "**{'timeout': 1, **a}"),
        ('{"timeout": 1, "timeout": 2}', "**{'timeout': 1, 'timeout': 2}"),
        ("opts", "**opts"),
        ("make_options()", "**make_options()"),
    ],
)
def test_double_star_that_may_hold_other_keys_stays_an_opaque_value(
    unpacked: str, expected: str
) -> None:
    step = steps_of(f"page.get_by_role('link').click(**{unpacked})")[0]
    assert step.values == (expected,)
    assert step.options == ()


def test_double_star_dict_call_splits_like_the_dict_display() -> None:
    spelled = steps_of('page.get_by_role("link").click(**dict(timeout=5000))')
    assert spelled == steps_of('page.get_by_role("link").click(timeout=5000)')
    assert spelled == steps_of('page.get_by_role("link").click(**{"timeout": 5000})')


@pytest.mark.parametrize(
    "setup, call",
    [
        ("dict = make_dict", "dict(timeout=5000)"),
        ("def f(dict): pass", "dict(timeout=5000)"),
        ("from helpers import *", "dict(timeout=5000)"),
        ("", "dict({'timeout': 5000})"),
        ("", "dict(other, timeout=5000)"),
        ("", "dict(**other)"),
        ("", "dict(timeout=5000, **other)"),
    ],
)
def test_double_star_dict_call_that_may_hold_other_keys_stays_opaque(setup: str, call: str) -> None:
    step = steps_of(f"{setup}\npage.get_by_role('link').click(**{call})")[0]
    assert step.options == ()
    assert step.values[0].startswith("**")


# --- ``getattr(<expr>, "<name>")`` ---------------------------------------------


def test_getattr_with_a_literal_name_is_the_attribute() -> None:
    spelled = steps_of('getattr(page, "goto")("https://x/")')
    assert spelled == steps_of('page.goto("https://x/")')
    assert kinds_and_names('getattr(page.locator("a"), "click")()') == [(KIND_ACTION, "click")]


def test_getattr_attribute_keeps_the_call_key_of_the_raw_call() -> None:
    tree = ast.parse('async def run(page):\n    await getattr(page, "goto")("https://x/")\n')
    call = next(
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Call)
    )
    assert classify_module(tree)[call_key(call)] == KIND_NAVIGATION


def test_getattr_of_a_matcher_is_the_assertion() -> None:
    source = 'getattr(expect(page.locator("a")), "to_be_visible")()'
    assert steps_of(source) == steps_of('expect(page.locator("a")).to_be_visible()')


@pytest.mark.parametrize(
    "setup, call",
    [
        ("", 'getattr(page, "goto", None)("https://x/")'),
        ("", 'getattr(page, "goto", default=None)("https://x/")'),
        ("", 'getattr(page, "go-to")("https://x/")'),
        ("", 'getattr(page, name)("https://x/")'),
        ("", 'getattr(page, b"goto")("https://x/")'),
        ("", 'getattr(page)("https://x/")'),
        ("getattr = make_getattr", 'getattr(page, "goto")("https://x/")'),
        ("def f(getattr): pass", 'getattr(page, "goto")("https://x/")'),
        ("from helpers import *", 'getattr(page, "goto")("https://x/")'),
    ],
)
def test_getattr_that_is_not_the_plain_two_argument_form_is_not_a_step(
    setup: str, call: str
) -> None:
    assert steps_of(f"{setup}\n{call}") == []


def test_a_getattr_navigation_result_is_not_substituted_like_the_plain_call() -> None:
    plain = """
        resp = page.goto(url)
        expect(resp).to_be_ok()
    """
    spelled = """
        resp = getattr(page, "goto")(url)
        expect(resp).to_be_ok()
    """

    def shape(source: str) -> list[tuple[str, str, str, tuple[str, ...]]]:
        return [(s.kind, s.name, s.target, s.values) for s in steps_of(source)]

    assert shape(spelled) == shape(plain)
    assert shape(plain)[-1][2] == "resp"


@pytest.mark.parametrize(
    "name", ["set_options", "start", "stop", "click", "goto", "wait_for_url"]
)
def test_a_getattr_call_of_a_step_setup_or_tracing_name_is_not_substitutable(name: str) -> None:
    source = f"""
        def run(page, thing):
            value = getattr(thing, "{name}")(1)
            value.click()
    """
    assert steps_of(source)[-1].target == "value"


# --- boolean state keywords on matchers ---------------------------------------


@pytest.mark.parametrize("state", ["visible", "checked", "enabled", "editable", "attached"])
def test_matcher_state_false_is_the_negated_matcher(state: str) -> None:
    spelled = steps_of(f'expect(page.locator("a")).to_be_{state}({state}=False)')
    assert spelled == steps_of(f'expect(page.locator("a")).not_to_be_{state}()')
    flipped = steps_of(f'expect(page.locator("a")).not_to_be_{state}({state}=False)')
    assert flipped == steps_of(f'expect(page.locator("a")).to_be_{state}()')


@pytest.mark.parametrize("state", ["visible", "checked", "enabled", "editable", "attached"])
def test_matcher_state_true_is_the_default(state: str) -> None:
    for prefix in ("to_be", "not_to_be"):
        spelled = steps_of(f'expect(page.locator("a")).{prefix}_{state}({state}=True)')
        assert spelled == steps_of(f'expect(page.locator("a")).{prefix}_{state}()')


def test_matcher_state_keeps_other_keywords() -> None:
    spelled = steps_of('expect(page.locator("a")).to_be_visible(visible=False, timeout=1000)')
    plain = steps_of('expect(page.locator("a")).not_to_be_visible(timeout=1000)')
    assert spelled == plain
    assert spelled[0].options == (("timeout", "1000"),)


def test_matcher_state_that_is_not_a_literal_boolean_stays() -> None:
    for value in ("flag", "0", "None", "not True"):
        step = steps_of(f'expect(page.locator("a")).to_be_visible(visible={value})')[0]
        assert step.name == "to_be_visible"
        assert step.values == (f"visible={value}",)


def test_matcher_state_on_a_matcher_without_one_is_untouched() -> None:
    step = steps_of('expect(page.locator("a")).to_have_text("x", visible=False)')[0]
    assert step.name == "to_have_text"
    assert step.values == ("'x'", "visible=False")


def test_matcher_state_keeps_the_call_key_of_the_raw_call() -> None:
    tree = ast.parse('expect(page.locator("a")).to_be_visible(visible=False)')
    matcher = next(
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) == "to_be_visible"
    )
    assert classify_module(tree)[call_key(matcher)] == KIND_ASSERTION
