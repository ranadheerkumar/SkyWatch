"""Browser interaction tools wrapping the existing Playwright infrastructure.

Provides tools for navigating, clicking, typing, screenshotting, and inspecting
web pages. Wraps the existing Playwright-based execution logic from
test_execution.py and ai_service.py without duplicating it.
"""

from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any

from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.types import ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tools.browser")


class BrowserNavigateTool(AgentTool):
    """Navigate a browser to a URL and capture a page snapshot."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_navigate",
            description=(
                "Navigate a Playwright browser to a URL. Returns the page title, "
                "visible headings, buttons, links, input fields, and current URL. "
                "Use this to explore a web application and understand its structure."
            ),
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", description="The URL to navigate to.", type="string"),
                ToolParameter(
                    name="wait_for_selector",
                    description="Optional CSS selector to wait for before capturing snapshot.",
                    type="string",
                    required=False,
                ),
            ],
        )

    async def _execute(self, url: str, wait_for_selector: str | None = None, **_: Any) -> dict[str, Any]:
        from app.services.ai_service import _capture_target_ui_context, serialize_target_ui_context

        context = await _capture_target_ui_context(url)
        return serialize_target_ui_context(context)


class BrowserScreenshotTool(AgentTool):
    """Take a screenshot of the current page state."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_screenshot",
            description=(
                "Capture a screenshot of a web page at the given URL. Returns the "
                "screenshot as a base64-encoded PNG and the file path where it was saved."
            ),
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", description="The URL to screenshot.", type="string"),
                ToolParameter(
                    name="full_page",
                    description="Whether to capture the full scrollable page.",
                    type="boolean",
                    required=False,
                    default=False,
                ),
            ],
        )

    async def _execute(self, url: str, full_page: bool = False, **_: Any) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        screenshot_dir = Path(tempfile.gettempdir()) / "ai-qa-engine-runs"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent="AI-QA-Engine/1.0 Agent")
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass

                screenshot_path = screenshot_dir / f"agent_screenshot_{page.url.split('/')[-1][:30]}.png"
                screenshot_bytes = await page.screenshot(full_page=full_page)
                screenshot_path.write_bytes(screenshot_bytes)

                return {
                    "url": page.url,
                    "title": await page.title(),
                    "screenshot_path": str(screenshot_path),
                    "screenshot_base64": base64.b64encode(screenshot_bytes).hexdigest()[:40] + "...",
                    "size_bytes": len(screenshot_bytes),
                }
            finally:
                await browser.close()


class BrowserInspectDOMTool(AgentTool):
    """Inspect the DOM structure of a web page for specific elements."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser_inspect_dom",
            description=(
                "Inspect the DOM of a web page at a URL. Returns interactive elements "
                "(buttons, links, inputs, forms) with their selectors, text content, "
                "and visibility state. Useful for understanding page structure before "
                "generating test cases."
            ),
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", description="The URL to inspect.", type="string"),
                ToolParameter(
                    name="selector",
                    description="Optional CSS selector to scope the inspection to a subtree.",
                    type="string",
                    required=False,
                ),
            ],
        )

    async def _execute(self, url: str, selector: str | None = None, **_: Any) -> dict[str, Any]:
        from playwright.async_api import async_playwright, Error as PlaywrightError

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent="AI-QA-Engine/1.0 Agent")
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass

                root = page if not selector else page.locator(selector)
                elements: list[dict[str, Any]] = []

                # Collect interactive elements
                for query, kind in [
                    ("button, input[type='submit'], input[type='button'], [role='button']", "button"),
                    ("a[href]", "link"),
                    ("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select", "input"),
                    ("form", "form"),
                ]:
                    try:
                        locator = root.locator(query) if selector else page.locator(query)
                        count = await locator.count()
                        for i in range(min(count, 50)):
                            item = locator.nth(i)
                            try:
                                is_visible = await item.is_visible(timeout=500)
                                text = ""
                                try:
                                    text = (await item.inner_text(timeout=500)).strip()[:100]
                                except PlaywrightError:
                                    pass
                                tag_name = await item.evaluate("el => el.tagName.toLowerCase()")
                                attrs = await item.evaluate(
                                    "el => Object.fromEntries("
                                    "['id','name','type','href','placeholder','aria-label','role','value','class']"
                                    ".filter(a => el.getAttribute(a)).map(a => [a, el.getAttribute(a)]))"
                                )
                                elements.append({
                                    "kind": kind,
                                    "tag": tag_name,
                                    "text": text,
                                    "visible": is_visible,
                                    "attributes": attrs,
                                })
                            except PlaywrightError:
                                continue
                    except PlaywrightError:
                        continue

                return {
                    "url": page.url,
                    "title": await page.title(),
                    "element_count": len(elements),
                    "elements": elements[:100],
                }
            finally:
                await browser.close()


def create_browser_tools() -> list[AgentTool]:
    """Factory to create all browser tool instances."""
    return [
        BrowserNavigateTool(),
        BrowserScreenshotTool(),
        BrowserInspectDOMTool(),
    ]
