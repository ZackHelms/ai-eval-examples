import asyncio
import re
from playwright.async_api import Playwright, async_playwright, expect
from pathlib import Path

async def run(playwright: Playwright) -> None:
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(viewport={"width":1280,"height":720})

    await context.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        page = await context.new_page()
        await page.goto("https://playwright.dev/python/")
        await expect(page.get_by_role("link", name="Get started")).to_be_visible()
        await page.get_by_role("link", name="Get started").click()
        await expect(page.get_by_role("link", name="Playwright logo Playwright")).to_be_visible()
        await page.get_by_role("link", name="Network").click()
        await expect(page.get_by_role("link", name="Next Other locators »")).to_be_visible()
        await page.get_by_role("link", name="Next Other locators »").click()
        await expect(page.get_by_role("link", name="Previous « Network")).to_be_visible()
        await page.close()
    finally:
        await context.tracing.stop(path=Path(__file__).with_suffix(".pwtrace.zip"))

    # ---------------------
    await context.close()
    await browser.close()


async def main() -> None:
    async with async_playwright() as playwright:
        await run(playwright)


asyncio.run(main())
