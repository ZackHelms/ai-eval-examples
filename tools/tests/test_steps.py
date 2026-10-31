"""Tests for scriptfix.steps: classification, source order and normalization."""

from __future__ import annotations

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


def test_steps_inside_a_classified_call_are_not_extracted() -> None:
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


def test_bare_name_step_has_an_empty_target() -> None:
    step = steps_of('click(locator)')[0]
    assert (step.kind, step.target, step.values) == (KIND_ACTION, "", ("locator",))


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


def test_module_names_are_not_substituted_inside_functions() -> None:
    source = """
        URL = "https://example.test/"
        def run(page):
            page.goto(URL)
    """
    assert steps_of(source)[0].values == ("URL",)


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
