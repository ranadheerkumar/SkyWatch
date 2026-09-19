import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
import httpx
from pydantic import ValidationError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.schemas.test_case import AIGeneratedTestCase, AIGeneratedTestCaseSet
from app.schemas.execution import Step
from app.core.logging import log_event

# Load environment configuration
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


class AIServiceError(RuntimeError):
    pass


logger = logging.getLogger("ai-qa-engine.ai_service")


GENERATION_MODE_PROVIDER = "provider"
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", os.getenv("AI_OPENAI_MODEL", os.getenv("AI_MODEL", "gpt-4.1"))).strip() or "gpt-4.1"
DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", os.getenv("AI_OPENAI_BASE_URL", os.getenv("AI_ENDPOINT", "https://api.openai.com/v1"))).rstrip("/")
DEFAULT_GITHUB_COPILOT_BASE_URL = os.getenv("GITHUB_COPILOT_BASE_URL", os.getenv("COPILOT_BASE_URL", os.getenv("AI_ENDPOINT", "https://api.githubcopilot.com"))).rstrip("/")
DEFAULT_GITHUB_COPILOT_MODEL = os.getenv("GITHUB_COPILOT_MODEL", os.getenv("COPILOT_MODEL", os.getenv("AI_MODEL", "gpt-4o"))).strip() or "gpt-4o"


IGNORED_CONTROL_TERMS = {
    "logout",
    "log out",
    "sign out",
    "signoff",
    "cancel",
    "close",
    "back",
}


def _load_exploratory_action_limit() -> int:
    try:
        return max(4, min(100, int(os.getenv("AI_EXPLORATORY_ACTION_LIMIT", os.getenv("AI_QA_ENGINE_EXPLORATORY_ACTION_LIMIT", "16")))))
    except ValueError:
        return 16


def _load_max_discovery_screens() -> int:
    try:
        return max(1, min(30, int(os.getenv("AI_MAX_DISCOVERY_SCREENS", os.getenv("AI_QA_ENGINE_MAX_DISCOVERY_SCREENS", "6")))))
    except ValueError:
        return 6


EXPLORATORY_ACTION_LIMIT = _load_exploratory_action_limit()
MAX_DISCOVERY_SCREENS = _load_max_discovery_screens()
EXPLORATORY_BLOCKED_TERMS = {
    "approve",
    "activate",
    "create",
    "delete",
    "deactivate",
    "destroy",
    "logout",
    "purchase",
    "remove",
    "save",
    "send",
    "sign out",
    "submit",
    "update",
    "upload",
}

SOURCE_ANCHOR_STOP_WORDS = {
    "about", "after", "application", "before", "being", "case", "cases", "click", "could", "document",
    "documents", "every", "first", "from", "generated", "given", "have", "into", "must", "only",
    "quality", "requirement", "requirements", "scenario", "scenarios", "should", "system", "test", "tests",
    "that", "their", "there", "these", "they", "this", "through", "under", "using", "when", "where",
    "which", "with", "within", "workflow", "workflows", "would",
}


@dataclass(frozen=True)
class AIProviderSettings:
    provider: str
    api_key: str | None
    model: str
    base_url: str
    timeout_seconds: int


@dataclass(frozen=True)
class TargetUIContext:
    source_url: str
    title: str
    headings: list[str]
    buttons: list[str]
    links: list[str]
    input_hints: list[str]
    observed_routes: list[str]
    fetch_note: str
    exploratory_observations: list[str] = field(default_factory=list)
    exploratory_hypotheses: list[str] = field(default_factory=list)
    authenticated_snapshot: bool = False


class _TargetSnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
        self.input_hints: list[str] = []
        self._capture_tag: str | None = None
        self._capture_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): (value or "").strip() for key, value in attrs}
        lower_tag = tag.lower()

        if lower_tag in {"title", "h1", "h2", "h3", "button", "a"}:
            self._capture_tag = lower_tag
            self._capture_text_parts = []

        if lower_tag in {"input", "textarea", "select"}:
            type_val = attrs_map.get("type", "").lower()
            val = attrs_map.get("value", "").strip()
            if type_val in {"submit", "button"} or (lower_tag == "input" and val and "btn" in attrs_map.get("class", "").lower()):
                if val and len(val) >= 2:
                    self._append_unique(self.buttons, val, 30)
            tokens = [
                attrs_map.get("aria-label", ""),
                attrs_map.get("placeholder", ""),
                attrs_map.get("name", ""),
                attrs_map.get("id", ""),
                attrs_map.get("type", ""),
            ]
            hint = " ".join(part for part in tokens if part).strip()
            if hint:
                self._append_unique(self.input_hints, hint, 20)

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if self._capture_tag != lower_tag:
            return
        text = re.sub(r"\s+", " ", "".join(self._capture_text_parts)).strip()
        if text:
            if lower_tag == "title":
                self.title = text[:200]
            elif lower_tag in {"h1", "h2", "h3"}:
                self._append_unique(self.headings, text, 20)
            elif lower_tag == "button":
                self._append_unique(self.buttons, text, 20)
            elif lower_tag == "a":
                self._append_unique(self.links, text, 30)
        self._capture_tag = None
        self._capture_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._capture_text_parts.append(data)

    @staticmethod
    def _append_unique(target: list[str], value: str, max_items: int) -> None:
        normalized = value.casefold()
        if not normalized:
            return
        if any(existing.casefold() == normalized for existing in target):
            return
        if len(target) >= max_items:
            return
        target.append(value[:140])


def _strip_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _extract_dropdown_menu_paths(source_url: str, html_text: str, max_items: int = 60) -> list[str]:
    normalized_html = (html_text or "")[:450_000]
    entries: list[str] = []
    seen: set[str] = set()
    dropdown_pattern = re.compile(
        r"<li[^>]*class=[\"'][^\"']*\bdropdown\b[^\"']*[\"'][^>]*>(.*?)</li>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for dropdown_html in dropdown_pattern.findall(normalized_html):
        toggle_match = re.search(
            r"<a[^>]*class=[\"'][^\"']*\bdropdown-toggle\b[^\"']*[\"'][^>]*>(.*?)</a>",
            dropdown_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not toggle_match:
            continue
        parent_label = _strip_html_text(toggle_match.group(1))
        if not parent_label:
            continue
        menu_match = re.search(
            r"<ul[^>]*class=[\"'][^\"']*\bdropdown-menu\b[^\"']*[\"'][^>]*>(.*?)</ul>",
            dropdown_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not menu_match:
            continue
        for href, anchor_html in re.findall(
            r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            menu_match.group(1),
            flags=re.IGNORECASE | re.DOTALL,
        ):
            label = _strip_html_text(anchor_html)
            raw_href = (href or "").strip()
            if not label or not raw_href:
                continue
            if raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            path_hint = raw_href if raw_href.startswith("/") else urlparse(urljoin(source_url, raw_href)).path or raw_href
            value = f"{parent_label} > {label} ({path_hint})"
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            entries.append(value[:180])
            if len(entries) >= max_items:
                return entries
    return entries


def _parse_target_snapshot(
    source_url: str,
    html_text: str,
    fetch_note: str,
    observed_routes: list[str] | None = None,
) -> TargetUIContext:
    parser = _TargetSnapshotParser()
    parser.feed((html_text or "")[:400_000])
    dropdown_paths = _extract_dropdown_menu_paths(source_url, html_text, max_items=40)
    dropdown_labels = [item.split(">", 1)[-1].split("(", 1)[0].strip() for item in dropdown_paths if ">" in item]
    merged_links = _merge_context_values(dropdown_labels, parser.links, 32)
    merged_routes = _merge_context_values(observed_routes or [], [urljoin(source_url, path.rsplit("(", 1)[-1].rstrip(")")) for path in dropdown_paths if "(" in path], 20)
    return TargetUIContext(
        source_url=source_url,
        title=parser.title,
        headings=parser.headings[:15],
        buttons=parser.buttons[:15],
        links=_merge_context_values(dropdown_paths, merged_links, 40),
        input_hints=parser.input_hints[:15],
        observed_routes=merged_routes,
        fetch_note=fetch_note,
    )


def _context_signal_score(context: TargetUIContext) -> int:
    return (
        len(context.headings) * 3
        + len(context.buttons) * 2
        + len(context.links) * 2
        + len(context.input_hints)
        + len(context.observed_routes) * 2
    )


async def _capture_rendered_target_ui_context(target_url: str) -> TargetUIContext:
    clean_target = target_url.strip()
    if not clean_target.lower().startswith(("http://", "https://")):
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Rendered snapshot skipped: target is not an HTTP(S) URL.",
        )
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent="AI-QA-Engine/1.0 Playwright")
                page.set_default_timeout(6_000)
                await page.goto(clean_target, wait_until="domcontentloaded", timeout=10_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3_000)
                except PlaywrightTimeoutError:
                    pass
                await page.wait_for_timeout(400)
                page_html = await page.content()
                rendered_context = _parse_target_snapshot(
                    source_url=page.url,
                    html_text=page_html,
                    fetch_note="Rendered DOM snapshot captured via Playwright.",
                    observed_routes=[page.url],
                )
                button_labels, link_labels = await _collect_interactive_controls(page, max_controls=60)
                route_targets = await _collect_authenticated_navigation_targets(page, page.url, max_targets=20)
                observed_routes = [page.url, *[url for _, url in route_targets]]
                exploratory_observations, exploratory_hypotheses, _ = await _run_bounded_exploration(page)
                return TargetUIContext(
                    source_url=rendered_context.source_url,
                    title=rendered_context.title,
                    headings=rendered_context.headings,
                    buttons=_merge_context_values(button_labels, rendered_context.buttons, 40),
                    links=_merge_context_values(link_labels, rendered_context.links, 40),
                    input_hints=rendered_context.input_hints,
                    observed_routes=_merge_context_values(observed_routes, rendered_context.observed_routes, 20),
                    fetch_note=(
                        f"{rendered_context.fetch_note} "
                        "Routes, interactive controls, and a bounded safe exploratory pass were sampled from the rendered page."
                    ).strip(),
                    exploratory_observations=exploratory_observations,
                    exploratory_hypotheses=exploratory_hypotheses,
                )
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note=f"Rendered snapshot unavailable: {error}",
        )


async def _capture_target_ui_context(target_url: str) -> TargetUIContext:
    clean_target = target_url.strip()
    if not clean_target.lower().startswith(("http://", "https://")):
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Target is not an HTTP(S) URL; live UI snapshot skipped.",
        )

    base_context: TargetUIContext
    headers = {"User-Agent": "AI-QA-Engine/1.0"}
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(clean_target, headers=headers)
    except httpx.HTTPError as error:
        base_context = TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note=f"Unable to fetch target HTML: {error}",
        )
    else:
        content_type = (response.headers.get("content-type") or "").lower()
        if response.status_code >= 400:
            base_context = TargetUIContext(
                source_url=clean_target,
                title="",
                headings=[],
                buttons=[],
                links=[],
                input_hints=[],
                observed_routes=[],
                fetch_note=f"Target returned HTTP {response.status_code}; snapshot limited.",
            )
        elif "html" not in content_type:
            base_context = TargetUIContext(
                source_url=clean_target,
                title="",
                headings=[],
                buttons=[],
                links=[],
                input_hints=[],
                observed_routes=[],
                fetch_note=f"Target content type '{content_type}' is not HTML; snapshot limited.",
            )
        else:
            base_context = _parse_target_snapshot(
                source_url=str(response.url),
                html_text=response.text,
                fetch_note=f"Fetched target HTML successfully (HTTP {response.status_code}).",
            )

    rendered_context = await _capture_rendered_target_ui_context(clean_target)
    merged_context = _merge_target_context(base_context, rendered_context)
    if (
        rendered_context.exploratory_observations
        or rendered_context.exploratory_hypotheses
        or _context_signal_score(merged_context) > _context_signal_score(base_context)
    ):
        return merged_context
    return base_context


async def discover_application_context(
    target_url: str,
    *,
    include_authenticated_snapshot: bool = False,
    login_email_selector: str | None = None,
    login_password_selector: str | None = None,
    login_submit_selector: str | None = None,
    login_email: str | None = None,
    login_password: str | None = None,
) -> TargetUIContext:
    email = (login_email or "").strip()
    password = (login_password or "").strip()
    should_authenticate = include_authenticated_snapshot or bool(email and password)
    context = await _capture_target_ui_context(target_url)
    if not should_authenticate:
        return context
    authenticated_context = await _capture_authenticated_target_ui_context(
        target_url,
        login_email_selector=login_email_selector,
        login_password_selector=login_password_selector,
        login_submit_selector=login_submit_selector,
        login_email=email,
        login_password=password,
    )
    return _merge_target_context(context, authenticated_context)


def serialize_target_ui_context(context: TargetUIContext) -> dict[str, Any]:
    return {
        "source_url": context.source_url,
        "title": context.title,
        "headings": context.headings,
        "buttons": context.buttons,
        "links": context.links,
        "input_hints": context.input_hints,
        "observed_routes": context.observed_routes,
        "fetch_note": context.fetch_note,
        "exploratory_observations": context.exploratory_observations,
        "exploratory_hypotheses": context.exploratory_hypotheses,
        "authenticated_snapshot": context.authenticated_snapshot,
    }


def _merge_context_values(primary: list[str], secondary: list[str], max_items: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*primary, *secondary]:
        normalized = value.casefold().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(value[:140])
        if len(merged) >= max_items:
            break
    return merged


def _selectors_from_ui(
    login_email_selector: str | None,
    login_password_selector: str | None,
    login_submit_selector: str | None,
) -> tuple[str, str, str]:
    email_sel = (login_email_selector or "").strip() or (
        "#user_email, input[type=email], input[name=email], input[name=username], input[name=user], "
        "input[name=login], input[name=identifier], input[id*='email' i], input[id*='username' i], "
        "input[id*='user' i], #email, #username, input[placeholder*='email' i], input[placeholder*='username' i], "
        "input[autocomplete='username'], input[autocomplete='email'], [data-test*='email' i], [data-test*='username' i], "
        "[data-testid*='email' i], [data-testid*='username' i]"
    )
    pass_sel = (login_password_selector or "").strip() or (
        "#user_password, input[type=password], input[name=password], input[name=pass], input[name=pwd], "
        "input[id*='password' i], input[id*='pass' i], #password, #pass, input[placeholder*='password' i], "
        "input[placeholder*='passcode' i], input[autocomplete='current-password'], input[autocomplete='password'], "
        "[data-test*='password' i], [data-testid*='password' i]"
    )
    sub_sel = (login_submit_selector or "").strip() or (
        "button[type=submit], input[type=submit], button:has-text('Sign In'), button:has-text('Sign in'), "
        "button:has-text('Log In'), button:has-text('Log in'), button:has-text('Login'), button:has-text('Submit'), "
        "button:has-text('Continue'), button:has-text('Next'), [role='button']:has-text('Sign in'), "
        "[role='button']:has-text('Log in'), [role='button']:has-text('Login')"
    )
    return email_sel, pass_sel, sub_sel


def _is_same_origin(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url)
    candidate = urlparse(candidate_url)
    return (base.scheme, base.netloc) == (candidate.scheme, candidate.netloc)


def _normalize_control_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "")).strip()
    return cleaned[:140]


def _is_actionable_control_label(value: str) -> bool:
    label = _normalize_control_label(value)
    if len(label) < 2:
        return False
    lowered = label.casefold()
    if lowered in {"-", "—", "..."}:
        return False
    if any(term in lowered for term in IGNORED_CONTROL_TERMS):
        return False
    return True


async def _collect_interactive_controls(page: Page, max_controls: int) -> tuple[list[str], list[str]]:
    button_candidates: list[str] = []
    link_candidates: list[str] = []
    seen_buttons: set[str] = set()
    seen_links: set[str] = set()

    button_locator = page.locator("button, input[type='submit'], input[type='button'], input.btn, form .btn, [role='button']")
    total_buttons = await button_locator.count()
    for index in range(min(total_buttons, 180)):
        locator = button_locator.nth(index)
        try:
            tag = await locator.evaluate("el => el.tagName.toLowerCase()")
            if tag == "input":
                raw_text = await locator.get_attribute("value") or await locator.get_attribute("aria-label") or await locator.get_attribute("title") or ""
            else:
                raw_text = await locator.inner_text() or await locator.get_attribute("value") or await locator.get_attribute("aria-label") or ""
            text = _normalize_control_label(raw_text)
        except PlaywrightError:
            continue
        if not _is_actionable_control_label(text):
            continue
        key = text.casefold()
        if key in seen_buttons:
            continue
        seen_buttons.add(key)
        button_candidates.append(text)
        if len(button_candidates) >= max_controls:
            break

    anchor_locator = page.locator("a[href], [role='link']")
    total_links = await anchor_locator.count()
    for index in range(min(total_links, 220)):
        locator = anchor_locator.nth(index)
        try:
            text = _normalize_control_label(await locator.inner_text())
        except PlaywrightError:
            continue
        if not _is_actionable_control_label(text):
            continue
        key = text.casefold()
        if key in seen_links:
            continue
        seen_links.add(key)
        link_candidates.append(text)
        if len(link_candidates) >= max_controls:
            break
    return button_candidates, link_candidates


async def _collect_authenticated_navigation_targets(page: Page, base_url: str, max_targets: int) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    anchors = page.locator("a[href]")
    total = await anchors.count()
    for index in range(min(total, 300)):
        locator = anchors.nth(index)
        try:
            href = (await locator.get_attribute("href")) or ""
        except PlaywrightError:
            continue
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        candidate_url = urljoin(base_url, href).split("#", 1)[0]
        if not candidate_url or not _is_same_origin(base_url, candidate_url) or candidate_url in seen_urls:
            continue
        try:
            raw_text = (await locator.evaluate("el => (el.textContent || el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim()")) or ""
            label = _normalize_control_label(raw_text)
        except PlaywrightError:
            try:
                label = _normalize_control_label(await locator.inner_text())
            except PlaywrightError:
                label = ""
        if not label:
            path_part = urlparse(candidate_url).path.strip("/").replace("_", " ").replace("-", " ").title()
            label = path_part or "Home"
        if not _is_actionable_control_label(label):
            continue
        seen_urls.add(candidate_url)
        candidates.append((label[:80], candidate_url))
        if len(candidates) >= max_targets:
            break
    return candidates


def _is_exploration_blocked(*values: str) -> bool:
    combined = " ".join(value for value in values if value).casefold()
    return any(re.search(rf"\b{re.escape(term)}\b", combined) for term in EXPLORATORY_BLOCKED_TERMS)


def _is_safe_exploration_control(*, label: str, role: str, tag_name: str, control_type: str, has_popup: str, expanded: str) -> bool:
    if _is_exploration_blocked(label, role, control_type):
        return False
    if role == "tab" or expanded in {"true", "false"} or has_popup:
        return True
    if tag_name != "button" or control_type not in {"", "button"}:
        return False
    return bool(re.search(r"\b(menu|filter|sort|details|more|expand|collapse|show|hide|next|previous|back|view|open)\b", label.casefold()))


async def _collect_exploration_candidates(page: Page, max_candidates: int) -> list[tuple[str, str, str, int]]:
    candidates: list[tuple[str, str, str, int]] = []
    seen: set[str] = set()
    locator = page.locator("a[href], button, [role='button'], [role='tab'], [aria-expanded]")
    total = await locator.count()
    for index in range(min(total, 160)):
        item = locator.nth(index)
        try:
            if not await item.is_visible():
                continue
            label = _normalize_control_label(await item.inner_text())
            tag_name = (await item.evaluate("node => node.tagName.toLowerCase()")) or ""
            role = (await item.get_attribute("role") or "").strip().casefold()
            href = (await item.get_attribute("href") or "").strip()
            control_type = (await item.get_attribute("type") or "").strip().casefold()
            has_popup = (await item.get_attribute("aria-haspopup") or "").strip().casefold()
            expanded = (await item.get_attribute("aria-expanded") or "").strip().casefold()
        except PlaywrightError:
            continue
        if not label or _is_exploration_blocked(label, href):
            continue

        if tag_name == "a" and href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
            candidate_url = urljoin(page.url, href).split("#", 1)[0]
            if not _is_same_origin(page.url, candidate_url) or candidate_url == page.url:
                continue
            identity = f"navigate:{candidate_url.casefold()}"
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(("navigate", label[:100], candidate_url, index))
        elif _is_safe_exploration_control(
            label=label,
            role=role,
            tag_name=tag_name,
            control_type=control_type,
            has_popup=has_popup,
            expanded=expanded,
        ):
            identity = f"activate:{label.casefold()}:{role}:{index}"
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(("activate", label[:100], "", index))
        if len(candidates) >= max_candidates:
            break
    return candidates


def _exploration_state_signals(text: str) -> list[str]:
    patterns = (
        ("error", r"\b(error|failed|failure|exception|denied|forbidden|unauthorized)\b"),
        ("validation", r"\b(required|invalid|must be|warning|please correct)\b"),
        ("empty", r"\b(no results|no records|nothing found|empty state)\b"),
        ("loading", r"\b(loading|please wait|processing)\b"),
    )
    return [label for label, pattern in patterns if re.search(pattern, text or "", re.IGNORECASE)]


async def _describe_exploration_result(page: Page, *, action_kind: str, label: str, action_number: int) -> tuple[str, str]:
    try:
        await page.wait_for_timeout(200)
        html = await page.content()
        snapshot = _parse_target_snapshot(
            source_url=page.url,
            html_text=html,
            fetch_note="Bounded exploratory state captured after a safe interaction.",
            observed_routes=[page.url],
        )
        try:
            body_text = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
        except Exception:
            try:
                body_text = await page.locator("body").first.inner_text(timeout=1_500)
            except Exception:
                body_text = ""
    except (PlaywrightError, PlaywrightTimeoutError):
        return (
            f"Exploratory action {action_number} ({action_kind} '{label}') completed, but the resulting page state could not be fully read.",
            f"Hypothesis to verify: '{label}' should produce a stable, observable state transition without changing business data.",
        )
    state_signals = _exploration_state_signals(body_text[:30_000])
    route = urlparse(page.url).path or "/"
    state_text = ", ".join(state_signals) if state_signals else "no error, validation, empty, or loading signal observed"
    observation = (
        f"Exploratory action {action_number}: {action_kind} '{label}' -> route '{route}', "
        f"title '{snapshot.title or 'unknown'}', {len(snapshot.headings)} heading(s), "
        f"{len(snapshot.buttons) + len(snapshot.links)} visible control/link signal(s); state signals: {state_text}."
    )[:700]
    hypothesis = (
        f"Hypothesis to verify: '{label}' should preserve a safe workflow boundary and expose an observable outcome "
        f"on route '{route}'; investigate the recorded state signals before asserting business behavior."
    )[:700]
    return observation, hypothesis


async def _run_bounded_exploration(page: Page, *, max_actions: int = EXPLORATORY_ACTION_LIMIT) -> tuple[list[str], list[str], int]:
    if max_actions <= 0:
        return [], [], 0
    start_url = page.url
    candidates = await _collect_exploration_candidates(page, max_actions)
    if not candidates:
        return (
            ["Exploratory pass found no safe non-mutating navigation, tab, menu, filter, or disclosure control to exercise."],
            ["Hypothesis to verify: the available workflow may require an explicitly authorized data-entry path before more states can be explored."],
            0,
        )

    observations: list[str] = []
    hypotheses: list[str] = []
    attempted = 0
    for action_kind, label, candidate_url, locator_index in candidates:
        if attempted >= max_actions:
            break
        attempted += 1
        try:
            if action_kind == "navigate":
                await page.goto(candidate_url, wait_until="domcontentloaded", timeout=6_000)
            else:
                control_locator = page.locator("a[href], button, [role='button'], [role='tab'], [aria-expanded]").nth(locator_index)
                await control_locator.click(timeout=4_000)
            observation, hypothesis = await _describe_exploration_result(
                page,
                action_kind=action_kind,
                label=label,
                action_number=attempted,
            )
            observations.append(observation)
            hypotheses.append(hypothesis)
        except (PlaywrightError, PlaywrightTimeoutError):
            observations.append(f"Exploratory action {attempted} ({action_kind} '{label}') was unavailable within the bounded timeout.")
            hypotheses.append(f"Hypothesis to verify: '{label}' may require a different role, state, or prerequisite before it is testable.")
        finally:
            try:
                if page.url != start_url:
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=6_000)
                else:
                    await page.keyboard.press("Escape")
            except (PlaywrightError, PlaywrightTimeoutError):
                break
    return observations[:EXPLORATORY_ACTION_LIMIT], hypotheses[:EXPLORATORY_ACTION_LIMIT], attempted


def _extract_target_url_from_text(*texts: str | None) -> str | None:
    combined = "\n".join(t for t in texts if t)
    if not combined.strip():
        return None
    url_patterns = [
        r"(?:url|target|endpoint|app|site|webapp|portal)\s*(?:is|:|=)?\s*[\"']?(https?://[^\s\"'>\),]+)",
        r"[\"']?(https?://[a-zA-Z0-9_.-]+(?:\.[a-zA-Z0-9_.-]+)*(?::\d+)?(?:/[^\s\"'>\)]*)?)",
    ]
    for pattern in url_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            cand = match.group(1).strip().rstrip(".,;)>\"'")
            if cand.startswith(("http://", "https://")):
                return cand
    return None


def _extract_credentials_from_text(*texts: str | None) -> tuple[str | None, str | None]:
    combined = "\n".join(t for t in texts if t)
    if not combined.strip():
        return None, None

    extracted_email = None
    extracted_password = None

    email_patterns = [
        r"(?:login[_\s-]?email|username|user[_\s-]?name|user[_\s-]?id|userid|user|email|login|un|account|identity)\s*(?:is|:|=|\s+as)\s*[\"']?([^\s\"',;\n]+@[^\s\"',;\n]+|[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_.-]+)[\"']?",
        r"(?:sign[_\s-]?in\s+as|login\s+as|log\s+in\s+as)\s+[\"']?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_.-]+)[\"']?",
        r"[\"']?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)[\"']?\s*(?:/|and|,)\s*(?:password|pass|pwd|pw|passcode)",
    ]
    for pattern in email_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            cand = match.group(1).strip().strip("\"'")
            if cand.lower() not in {"the", "a", "an", "user", "username", "email", "password", "none", "null", "undefined"}:
                extracted_email = cand
                break

    password_patterns = [
        r"(?:login[_\s-]?password|password|passcode|pass_word|passwd|pass|pwd|pw|p/w|secret|pin|code)\s*(?:is|:|=)\s*[\"']?([^\s\"',;\n]+)[\"']?",
        r"(?:with\s+password|using\s+password|with\s+pass|using\s+pass)\s+[\"']?([^\s\"',;\n]+)[\"']?",
        r"(?:/|and|,)\s*(?:password|pass|pwd|pw|passcode)\s*[:=]?\s*[\"']?([^\s\"',;\n]+)[\"']?",
    ]
    for pattern in password_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            cand = match.group(1).strip().strip("\"'")
            if cand.lower() not in {"the", "a", "an", "user", "username", "email", "password", "none", "null", "undefined"}:
                extracted_password = cand
                break

    # Extract standalone email address and adjacent password token from plain text when labels are absent
    if not extracted_email or not extracted_password:
        lines = [line.strip() for line in combined.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            if not extracted_email:
                em_match = re.search(r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", line)
                if em_match:
                    extracted_email = em_match.group(1).strip()
                    if not extracted_password and idx + 1 < len(lines):
                        next_line = lines[idx + 1]
                        if not next_line.lower().startswith(("http://", "https://")) and "@" not in next_line:
                            p_match = re.sub(r"^(?:password|pass|pwd|pw|passcode)\s*[:=]?\s*", "", next_line, flags=re.IGNORECASE).strip().strip("\"'")
                            if p_match and len(p_match) >= 3 and not p_match.lower().startswith(("generate", "limit", "verify", "test", "coverage")):
                                extracted_password = p_match
            elif not extracted_password and idx > 0:
                if not line.lower().startswith(("http://", "https://")) and "@" not in line:
                    p_match = re.sub(r"^(?:password|pass|pwd|pw|passcode)\s*[:=]?\s*", "", line, flags=re.IGNORECASE).strip().strip("\"'")
                    if p_match and len(p_match) >= 3 and not p_match.lower().startswith(("generate", "limit", "verify", "test", "coverage")):
                        extracted_password = p_match
                        break

    return extracted_email, extracted_password


async def _fill_locator_with_fallbacks(page: Page, primary_selector: str, candidates: list[str], value: str, timeout_ms: int = 3500) -> bool:
    all_selectors: list[str] = []
    for s in [primary_selector, *candidates]:
        if not s:
            continue
        for part in s.split(","):
            cleaned = part.strip()
            if cleaned and cleaned not in all_selectors:
                all_selectors.append(cleaned)

    # 1. Try visible locators first on main page
    for sel in all_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.fill(value, timeout=timeout_ms)
                return True
        except (PlaywrightError, PlaywrightTimeoutError):
            continue

    # 2. Try with wait_for on each selector
    for sel in all_selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=min(timeout_ms, 1500))
            await loc.fill(value, timeout=timeout_ms)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            continue

    # 3. Try in frames if any
    for frame in page.frames:
        for sel in all_selectors:
            try:
                f_loc = frame.locator(sel).first
                if await f_loc.is_visible(timeout=800):
                    await f_loc.fill(value, timeout=timeout_ms)
                    return True
            except (PlaywrightError, PlaywrightTimeoutError):
                continue

    return False


async def _click_locator_with_fallbacks(page: Page, primary_selector: str, candidates: list[str], timeout_ms: int = 3500) -> bool:
    all_selectors: list[str] = []
    for s in [primary_selector, *candidates]:
        if not s:
            continue
        for part in s.split(","):
            cleaned = part.strip()
            if cleaned and cleaned not in all_selectors:
                all_selectors.append(cleaned)

    # 1. Try visible locators first on main page
    for sel in all_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                await loc.click(timeout=timeout_ms)
                return True
        except (PlaywrightError, PlaywrightTimeoutError):
            continue

    # 2. Try with wait_for on each selector
    for sel in all_selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=min(timeout_ms, 1500))
            await loc.click(timeout=timeout_ms)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            continue

    # 3. Try in frames if any
    for frame in page.frames:
        for sel in all_selectors:
            try:
                f_loc = frame.locator(sel).first
                if await f_loc.is_visible(timeout=800):
                    await f_loc.click(timeout=timeout_ms)
                    return True
            except (PlaywrightError, PlaywrightTimeoutError):
                continue

    return False


async def _capture_authenticated_target_ui_context(
    target_url: str,
    login_email_selector: str | None,
    login_password_selector: str | None,
    login_submit_selector: str | None,
    login_email: str | None = None,
    login_password: str | None = None,
) -> TargetUIContext:
    clean_target = target_url.strip()
    if not clean_target.lower().startswith(("http://", "https://")):
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Authenticated snapshot skipped: target is not an HTTP(S) URL.",
        )
    email = (login_email or "").strip()
    password = (login_password or "").strip()
    if not email or not password:
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Authenticated snapshot skipped: login credentials must be supplied through UI runtime parameters or prompt.",
        )

    selectors = _selectors_from_ui(
        login_email_selector,
        login_password_selector,
        login_submit_selector,
    )
    if not selectors:
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Authenticated snapshot skipped: login selectors must be supplied through the UI.",
        )
    email_selector, password_selector, submit_selector = selectors
    merged_context: TargetUIContext | None = None
    discovered_routes: list[str] = []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(
                    user_agent="AI-QA-Engine/1.0 Playwright",
                    viewport={"width": 1440, "height": 900},
                )
                page.set_default_timeout(10_000)
                await page.goto(clean_target, wait_until="domcontentloaded", timeout=15_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3_000)
                except PlaywrightTimeoutError:
                    pass
                await page.wait_for_timeout(800)

                email_fallback_selectors = [
                    "#user_email", "input[type='email']", "input[name='email']", "input[name='username']",
                    "input[name='user']", "input[name='login']", "input[name='identifier']",
                    "#email", "#username", "#login", "input[placeholder*='email' i]", "input[placeholder*='username' i]",
                    "input[placeholder*='user' i]", "input[placeholder*='login' i]", "input[placeholder*='identifier' i]",
                    "input[autocomplete='username']", "input[autocomplete='email']",
                    "[data-test*='email' i]", "[data-test*='username' i]", "[data-test*='user' i]",
                    "[data-testid*='email' i]", "[data-testid*='username' i]", "[data-testid*='user' i]",
                    "input[aria-label*='email' i]", "input[aria-label*='username' i]", "input[aria-label*='user' i]",
                    "form input[type='text']", "form input:not([type='hidden']):not([type='password']):not([type='checkbox']):not([type='radio'])",
                ]
                password_fallback_selectors = [
                    "#user_password", "input[type='password']", "input[name='password']", "input[name='pass']",
                    "input[name='pwd']", "input[name='user_password']", "input[name='user[password]']",
                    "#password", "#pass", "input[placeholder*='password' i]", "input[placeholder*='passcode' i]",
                    "input[autocomplete='current-password']", "input[autocomplete='password']",
                    "[data-test*='password' i]", "[data-testid*='password' i]",
                    "input[aria-label*='password' i]",
                ]
                submit_fallback_selectors = [
                    "input[type='submit']", "button[type='submit']", "button:has-text('Sign In')",
                    "button:has-text('Sign in')", "button:has-text('Log In')", "button:has-text('Log in')",
                    "button:has-text('Login')", "button:has-text('Submit')", "button:has-text('Continue')",
                    "button:has-text('Next')", "button[id*='submit' i]", "button[id*='login' i]",
                    "[role='button']:has-text('Sign in')", "[role='button']:has-text('Log in')", "[role='button']:has-text('Login')",
                ]

                # Check if email is visible or if we need to click Sign in on landing page
                email_visible = False
                for sel in [email_selector, *email_fallback_selectors]:
                    try:
                        if await page.locator(sel).first.is_visible(timeout=800):
                            email_visible = True
                            break
                    except (PlaywrightError, PlaywrightTimeoutError):
                        pass

                if not email_visible:
                    for nav_sel in [
                        "a:has-text('Sign In')", "a:has-text('Log In')", "a:has-text('Login')", "a:has-text('Sign in')", "a:has-text('Log in')",
                        "button:has-text('Sign In')", "button:has-text('Log In')", "button:has-text('Login')", "button:has-text('Sign in')", "button:has-text('Log in')",
                        "a[href*='login' i]", "a[href*='signin' i]", "a[href*='auth' i]",
                    ]:
                        try:
                            nav_loc = page.locator(nav_sel).first
                            if await nav_loc.is_visible(timeout=1000):
                                await nav_loc.click(timeout=3000)
                                await page.wait_for_timeout(600)
                                break
                        except (PlaywrightError, PlaywrightTimeoutError):
                            pass

                await _fill_locator_with_fallbacks(page, email_selector, email_fallback_selectors, email, timeout_ms=3500)

                # Check if password field is visible; if not, could be multi-step login (click Next/Continue)
                pass_visible = False
                for psel in [password_selector, *password_fallback_selectors]:
                    try:
                        if await page.locator(psel).first.is_visible(timeout=800):
                            pass_visible = True
                            break
                    except (PlaywrightError, PlaywrightTimeoutError):
                        pass

                if not pass_visible:
                    for next_sel in ["button:has-text('Next')", "button:has-text('Continue')", "button[type='submit']", "input[type='submit']"]:
                        try:
                            n_loc = page.locator(next_sel).first
                            if await n_loc.is_visible(timeout=1000):
                                await n_loc.click(timeout=2500)
                                await page.wait_for_timeout(600)
                                break
                        except (PlaywrightError, PlaywrightTimeoutError):
                            pass

                await _fill_locator_with_fallbacks(page, password_selector, password_fallback_selectors, password, timeout_ms=3500)
                await _click_locator_with_fallbacks(page, submit_selector, submit_fallback_selectors, timeout_ms=3500)
                try:
                    await page.keyboard.press("Enter")
                except (PlaywrightError, PlaywrightTimeoutError):
                    pass

                try:
                    await page.wait_for_load_state("networkidle", timeout=6_000)
                except PlaywrightTimeoutError:
                    pass
                await page.wait_for_timeout(800)
                html = await page.content()
                final_url = page.url
                merged_context = _parse_target_snapshot(
                    source_url=final_url,
                    html_text=html,
                    fetch_note="Authenticated snapshot captured after login flow.",
                    observed_routes=[final_url],
                )
                initial_buttons, initial_links = await _collect_interactive_controls(page, max_controls=60)
                merged_context = TargetUIContext(
                    source_url=merged_context.source_url,
                    title=merged_context.title,
                    headings=merged_context.headings,
                    buttons=_merge_context_values(initial_buttons, merged_context.buttons, 40),
                    links=_merge_context_values(initial_links, merged_context.links, 40),
                    input_hints=merged_context.input_hints,
                    observed_routes=merged_context.observed_routes,
                    fetch_note=merged_context.fetch_note,
                )
                exploratory_observations, exploratory_hypotheses, _ = await _run_bounded_exploration(page)
                merged_context = TargetUIContext(
                    source_url=merged_context.source_url,
                    title=merged_context.title,
                    headings=merged_context.headings,
                    buttons=merged_context.buttons,
                    links=merged_context.links,
                    input_hints=merged_context.input_hints,
                    observed_routes=merged_context.observed_routes,
                    fetch_note=merged_context.fetch_note,
                    exploratory_observations=exploratory_observations,
                    exploratory_hypotheses=exploratory_hypotheses,
                    authenticated_snapshot=True,
                )
                navigation_targets = await _collect_authenticated_navigation_targets(page, final_url, max_targets=60)
                all_screen_observations: list[str] = [*exploratory_observations]
                all_screen_hypotheses: list[str] = [*exploratory_hypotheses]
                all_discovered_route_urls: list[str] = [url for _, url in navigation_targets]
                for label, target_route in navigation_targets[:MAX_DISCOVERY_SCREENS]:
                    try:
                        await page.goto(target_route, wait_until="domcontentloaded", timeout=3_000)
                        await page.wait_for_timeout(100)
                        route_html = await page.content()
                        route_context = _parse_target_snapshot(
                            source_url=page.url,
                            html_text=route_html,
                            fetch_note=f"Captured authenticated screen for navigation '{label}'.",
                            observed_routes=[page.url],
                        )
                        route_buttons, route_links = await _collect_interactive_controls(page, max_controls=24)
                        route_context = TargetUIContext(
                            source_url=route_context.source_url,
                            title=route_context.title,
                            headings=route_context.headings,
                            buttons=_merge_context_values(route_buttons, route_context.buttons, 30),
                            links=_merge_context_values(route_links, route_context.links, 30),
                            input_hints=route_context.input_hints,
                            observed_routes=route_context.observed_routes,
                            fetch_note=route_context.fetch_note,
                            authenticated_snapshot=True,
                        )
                        merged_context = _merge_target_context(merged_context, route_context)
                        discovered_routes.append(f"{label} -> {page.url}")
                    except (PlaywrightError, PlaywrightTimeoutError) as error:
                        discovered_routes.append(f"{label} ({error.__class__.__name__})")

                for label, target_route in navigation_targets[MAX_DISCOVERY_SCREENS:]:
                    discovered_routes.append(f"{label} -> {target_route}")

                if all_discovered_route_urls:
                    merged_context = TargetUIContext(
                        source_url=merged_context.source_url,
                        title=merged_context.title,
                        headings=merged_context.headings,
                        buttons=merged_context.buttons,
                        links=merged_context.links,
                        input_hints=merged_context.input_hints,
                        observed_routes=_merge_context_values(merged_context.observed_routes, all_discovered_route_urls, 40),
                        fetch_note=merged_context.fetch_note,
                        exploratory_observations=merged_context.exploratory_observations,
                        exploratory_hypotheses=merged_context.exploratory_hypotheses,
                        authenticated_snapshot=True,
                    )
            finally:
                await browser.close()
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note=f"Authenticated snapshot failed: {error}",
        )
    if merged_context is None:
        return TargetUIContext(
            source_url=clean_target,
            title="",
            headings=[],
            buttons=[],
            links=[],
            input_hints=[],
            observed_routes=[],
            fetch_note="Authenticated snapshot failed: login completed but no page context was captured.",
        )
    if discovered_routes:
        return TargetUIContext(
            source_url=merged_context.source_url,
            title=merged_context.title,
            headings=merged_context.headings,
            buttons=merged_context.buttons,
            links=merged_context.links,
            input_hints=merged_context.input_hints,
            observed_routes=merged_context.observed_routes,
            fetch_note=f"{merged_context.fetch_note} | Authenticated route discovery: {'; '.join(discovered_routes[:20])}",
            exploratory_observations=_merge_context_values(all_screen_observations, merged_context.exploratory_observations, EXPLORATORY_ACTION_LIMIT * 4),
            exploratory_hypotheses=_merge_context_values(all_screen_hypotheses, merged_context.exploratory_hypotheses, EXPLORATORY_ACTION_LIMIT * 4),
            authenticated_snapshot=merged_context.authenticated_snapshot,
        )
    return merged_context


def _merge_target_context(base_context: TargetUIContext, authenticated_context: TargetUIContext) -> TargetUIContext:
    return TargetUIContext(
        source_url=authenticated_context.source_url or base_context.source_url,
        title=authenticated_context.title or base_context.title,
        headings=_merge_context_values(authenticated_context.headings, base_context.headings, 40),
        buttons=_merge_context_values(authenticated_context.buttons, base_context.buttons, 60),
        links=_merge_context_values(authenticated_context.links, base_context.links, 60),
        input_hints=_merge_context_values(authenticated_context.input_hints, base_context.input_hints, 30),
        observed_routes=_merge_context_values(authenticated_context.observed_routes, base_context.observed_routes, 40),
        fetch_note=f"{base_context.fetch_note} | {authenticated_context.fetch_note}",
        exploratory_observations=_merge_context_values(
            authenticated_context.exploratory_observations,
            base_context.exploratory_observations,
            EXPLORATORY_ACTION_LIMIT * 4,
        ),
        exploratory_hypotheses=_merge_context_values(
            authenticated_context.exploratory_hypotheses,
            base_context.exploratory_hypotheses,
            EXPLORATORY_ACTION_LIMIT * 4,
        ),
        authenticated_snapshot=base_context.authenticated_snapshot or authenticated_context.authenticated_snapshot,
    )


def _format_target_context_for_prompt(context: TargetUIContext, reference_cases: list[str]) -> str:
    reference_text = "\n".join(f"- {snippet}" for snippet in reference_cases[:8]) or "- None provided"
    heading_text = ", ".join(context.headings[:30]) or "None"
    button_text = ", ".join(context.buttons[:40]) or "None"
    link_text = ", ".join(context.links[:40]) or "None"
    dropdown_text = ", ".join(
        [item for item in context.links if " > " in item and "(" in item][:30]
    ) or "None"
    input_text = ", ".join(context.input_hints[:16]) or "None"
    route_text = ", ".join(context.observed_routes[:30]) or "None"
    exploratory_observation_text = "\n".join(f"- {item}" for item in context.exploratory_observations[:30]) or "- None captured"
    exploratory_hypothesis_text = "\n".join(f"- {item}" for item in context.exploratory_hypotheses[:30]) or "- None captured"
    title_text = context.title or "Unknown"
    return (
        "Observed application context:\n"
        f"- Source URL used: {context.source_url or 'Unknown'}\n"
        f"- Fetch note: {context.fetch_note}\n"
        f"- Page title: {title_text}\n"
        f"- Visible headings: {heading_text}\n"
        f"- Button labels: {button_text}\n"
        f"- Link labels: {link_text}\n"
        f"- Dropdown menu paths: {dropdown_text}\n"
        f"- Input hints: {input_text}\n"
        f"- Observed authenticated routes across application screens: {route_text}\n"
        "Bounded exploratory observations across discovered screens (observed facts):\n"
        f"{exploratory_observation_text}\n"
        "Bounded exploratory hypotheses across discovered screens (must be verified before being asserted):\n"
        f"{exploratory_hypothesis_text}\n"
        "Reference cases already available in this application:\n"
        f"{reference_text}\n"
    )


def _resolve_setting(*environment_keys: str, default: str = "") -> str:
    for key in environment_keys:
        value = os.getenv(key)
        if value is None:
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return default


def _load_timeout_seconds() -> int:
    timeout_raw = _resolve_setting(
        "AI_QA_ENGINE_AI_TIMEOUT_SECONDS",
        "AI_TIMEOUT_SECONDS",
        default="90",
    ).strip() or "90"
    try:
        timeout = int(timeout_raw)
    except ValueError as error:
        raise AIServiceError("AI timeout setting must be an integer value.") from error
    if timeout < 10:
        raise AIServiceError("AI timeout setting must be at least 10 seconds.")
    return timeout


def _build_github_copilot_settings(
    timeout_seconds: int,
    *,
    include_generic: bool,
    require_api_key: bool,
) -> AIProviderSettings:
    api_key = _resolve_setting(
        "GITHUB_TOKEN",
        "COPILOT_API_KEY",
        "GITHUB_COPILOT_API_KEY",
        "GH_TOKEN",
    )
    if require_api_key and not api_key:
        raise AIServiceError(
            "GitHub Copilot / GitHub token is missing. Please set GITHUB_TOKEN or COPILOT_API_KEY in backend/.env "
            "or configure it in the AI & Settings tab."
        )
    model = _resolve_setting(
        "AI_MODEL",
        "GITHUB_COPILOT_MODEL",
        "COPILOT_MODEL",
        "GITHUB_MODEL",
        *(("AI_QA_ENGINE_AI_MODEL",) if include_generic else ()),
        default=DEFAULT_GITHUB_COPILOT_MODEL,
    )
    base_url = _resolve_setting(
        "AI_ENDPOINT",
        "GITHUB_COPILOT_BASE_URL",
        "GITHUB_MODELS_BASE_URL",
        "COPILOT_BASE_URL",
        *(("AI_QA_ENGINE_AI_BASE_URL",) if include_generic else ()),
        default=DEFAULT_GITHUB_COPILOT_BASE_URL,
    ).rstrip("/")
    return AIProviderSettings(
        provider="github_copilot",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_openai_settings(
    timeout_seconds: int,
    *,
    include_generic: bool,
    require_api_key: bool,
) -> AIProviderSettings:
    api_key = _resolve_setting(
        "OPENAI_API_KEY",
        "AI_API_KEY",
        "AI_OPENAI_API_KEY",
        "AI_QA_ENGINE_AI_OPENAI_API_KEY",
        "AI_QA_ENGINE_AI_OPENAI_API_KEY",
        "AI_QA_ENGINE_AI_API_KEY",
    )
    if require_api_key and not api_key:
        raise AIServiceError(
            "OpenAI API key is missing. Please set OPENAI_API_KEY or AI_API_KEY in backend/.env "
            "or configure it in the AI & Settings tab."
        )
    model = _resolve_setting(
        "AI_MODEL",
        "OPENAI_MODEL",
        "AI_QA_ENGINE_AI_OPENAI_MODEL",
        "AI_QA_ENGINE_AI_OPENAI_MODEL",
        *(("AI_QA_ENGINE_AI_MODEL",) if include_generic else ()),
        default="gpt-4o",
    )
    base_url = _resolve_setting(
        "AI_ENDPOINT",
        "OPENAI_BASE_URL",
        "AI_BASE_URL",
        "AI_QA_ENGINE_AI_OPENAI_BASE_URL",
        "AI_QA_ENGINE_AI_OPENAI_BASE_URL",
        *(("AI_QA_ENGINE_AI_BASE_URL",) if include_generic else ()),
        default=DEFAULT_OPENAI_BASE_URL,
    ).rstrip("/")
    return AIProviderSettings(
        provider="openai",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_azure_openai_settings(
    timeout_seconds: int,
    *,
    include_generic: bool,
    require_api_key: bool,
) -> AIProviderSettings:
    api_key = _resolve_setting(
        "AZURE_OPENAI_API_KEY",
        "AZURE_API_KEY",
        "OPENAI_API_KEY",
        "AI_API_KEY",
    )
    if require_api_key and not api_key:
        raise AIServiceError("Azure OpenAI API key is missing. Set AZURE_OPENAI_API_KEY in backend/.env or AI & Settings.")
    model = _resolve_setting("AZURE_OPENAI_DEPLOYMENT", "AI_MODEL", "AZURE_MODEL", default="gpt-4o")
    base_url = _resolve_setting("AZURE_OPENAI_ENDPOINT", "AI_ENDPOINT", "AI_BASE_URL", default="").rstrip("/")
    if not base_url:
        raise AIServiceError("Azure OpenAI endpoint is missing. Set AZURE_OPENAI_ENDPOINT in backend/.env or AI & Settings.")
    return AIProviderSettings(
        provider="azure_openai",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_anthropic_settings(
    timeout_seconds: int,
    *,
    include_generic: bool,
    require_api_key: bool,
) -> AIProviderSettings:
    api_key = _resolve_setting("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "AI_API_KEY")
    if require_api_key and not api_key:
        raise AIServiceError("Anthropic API key is missing. Set ANTHROPIC_API_KEY in backend/.env or AI & Settings.")
    model = _resolve_setting("ANTHROPIC_MODEL", "AI_MODEL", default="claude-3-5-sonnet-20241022")
    base_url = _resolve_setting("ANTHROPIC_BASE_URL", "AI_ENDPOINT", default="https://api.anthropic.com/v1").rstrip("/")
    return AIProviderSettings(
        provider="anthropic",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_gemini_settings(
    timeout_seconds: int,
    *,
    include_generic: bool,
    require_api_key: bool,
) -> AIProviderSettings:
    api_key = _resolve_setting("GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_API_KEY")
    if require_api_key and not api_key:
        raise AIServiceError("Google Gemini API key is missing. Set GEMINI_API_KEY in backend/.env or AI & Settings.")
    model = _resolve_setting("GEMINI_MODEL", "AI_MODEL", default="gemini-1.5-pro")
    base_url = _resolve_setting(
        "GEMINI_BASE_URL",
        "AI_ENDPOINT",
        default="https://generativelanguage.googleapis.com/v1beta/openai",
    ).rstrip("/")
    return AIProviderSettings(
        provider="gemini",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _build_local_settings(timeout_seconds: int, *, include_generic: bool) -> AIProviderSettings:
    model = _resolve_setting("AI_MODEL", default="local-model")
    base_url = _resolve_setting("AI_ENDPOINT", "AI_BASE_URL", default="http://127.0.0.1:8080/v1").rstrip("/")
    api_key = _resolve_setting("AI_API_KEY", default="")
    return AIProviderSettings(
        provider="local",
        api_key=api_key or None,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


PROVIDER_FALLBACK_MODELS: dict[str, list[str]] = {
    "github_copilot": [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3.5-sonnet",
        "claude-3-5-sonnet",
        "gpt-4",
        "o3-mini",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "o3-mini",
    ],
    "azure_openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4",
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "local": [
        "local-model",
    ],
}


def _build_settings_for_single_provider(
    normalized_provider: str,
    timeout_seconds: int,
    requested_model: str | None = None,
    require_api_key: bool = True,
) -> list[AIProviderSettings]:
    canon_provider = "github_copilot"
    if normalized_provider in {"github_copilot", "copilot", "github", "github_models"}:
        base_settings = _build_github_copilot_settings(timeout_seconds, include_generic=True, require_api_key=require_api_key)
        canon_provider = "github_copilot"
    elif normalized_provider == "openai":
        base_settings = _build_openai_settings(timeout_seconds, include_generic=True, require_api_key=require_api_key)
        canon_provider = "openai"
    elif normalized_provider in {"azure_openai", "azure"}:
        base_settings = _build_azure_openai_settings(timeout_seconds, include_generic=True, require_api_key=require_api_key)
        canon_provider = "azure_openai"
    elif normalized_provider in {"anthropic", "claude"}:
        base_settings = _build_anthropic_settings(timeout_seconds, include_generic=True, require_api_key=require_api_key)
        canon_provider = "anthropic"
    elif normalized_provider in {"gemini", "google"}:
        base_settings = _build_gemini_settings(timeout_seconds, include_generic=True, require_api_key=require_api_key)
        canon_provider = "gemini"
    elif normalized_provider in {"local", "custom"}:
        base_settings = _build_local_settings(timeout_seconds, include_generic=True)
        canon_provider = "local"
    else:
        return []

    primary_model = (requested_model or base_settings.model).strip()
    primary = replace(base_settings, model=primary_model)
    settings_list = [primary]

    # Add fallback models for the same provider
    fallback_models = PROVIDER_FALLBACK_MODELS.get(canon_provider, [])
    seen_models = {primary_model.lower()}
    for fm in fallback_models:
        if fm.lower() not in seen_models:
            seen_models.add(fm.lower())
            settings_list.append(replace(base_settings, model=fm))

    return settings_list


def _load_provider_settings(
    override_provider: str | None = None,
    override_model: str | None = None,
) -> list[AIProviderSettings]:
    provider = (
        (override_provider or "").strip()
        or _resolve_setting(
            "AI_PROVIDER",
            "AI_QA_ENGINE_AI_PROVIDER",
            "AI_QA_ENGINE_AI_PROVIDER",
            default="github_copilot",
        )
    ).strip().lower()
    if provider in {"disabled", "none"}:
        raise AIServiceError("AI provider is disabled by configuration.")
    timeout_seconds = _load_timeout_seconds()

    valid_providers = {"github_copilot", "copilot", "github", "github_models", "openai", "azure_openai", "azure", "anthropic", "claude", "gemini", "google", "local", "custom"}
    if provider not in valid_providers:
        raise AIServiceError(
            f"Unsupported AI provider '{provider}'. Select one explicit provider: github_copilot, openai, azure_openai, anthropic, gemini, or local."
        )

    # 1. Primary provider settings with backup models
    settings_list = _build_settings_for_single_provider(
        provider,
        timeout_seconds,
        requested_model=override_model,
        require_api_key=True,
    )

    # 2. Check for other configured secondary providers in the environment to serve as cross-provider fallbacks
    normalized_primary = (
        "github_copilot" if provider in {"github_copilot", "copilot", "github", "github_models"}
        else "azure_openai" if provider in {"azure_openai", "azure"}
        else "anthropic" if provider in {"anthropic", "claude"}
        else "gemini" if provider in {"gemini", "google"}
        else "local" if provider in {"local", "custom"}
        else "openai"
    )

    other_candidates = ["openai", "github_copilot", "anthropic", "gemini", "azure_openai", "local"]
    for other_p in other_candidates:
        if other_p == normalized_primary:
            continue
        try:
            other_settings = _build_settings_for_single_provider(
                other_p,
                timeout_seconds,
                require_api_key=True,
            )
            if other_settings and other_settings[0].api_key:
                settings_list.extend(other_settings[:3])
        except Exception:
            continue

    if not settings_list:
        raise AIServiceError(f"No configured model settings available for provider '{provider}'.")

    return settings_list


def get_ai_provider_metadata() -> dict[str, str | bool | None]:
    try:
        settings_list = _load_provider_settings()
    except AIServiceError as error:
        return {
            "provider": "unconfigured",
            "model": "none",
            "configured": False,
            "configuration_error": str(error),
        }
    primary = settings_list[0]
    return {
        "provider": primary.provider,
        "model": primary.model,
        "configured": bool(settings_list),
        "configuration_error": None,
    }


def _provider_settings_for_connection(
    provider: str | None,
    model: str | None,
    api_key: str | None,
    endpoint: str | None,
) -> AIProviderSettings:
    normalized_provider = (
        provider
        or _resolve_setting(
            "AI_PROVIDER",
            "AI_QA_ENGINE_AI_PROVIDER",
            "AI_QA_ENGINE_AI_PROVIDER",
            default="github_copilot",
        )
    ).strip().lower()
    timeout_seconds = _load_timeout_seconds()
    if normalized_provider in {"github_copilot", "copilot", "github", "github_models"}:
        resolved = _build_github_copilot_settings(timeout_seconds, include_generic=True, require_api_key=False)
    elif normalized_provider == "openai":
        resolved = _build_openai_settings(timeout_seconds, include_generic=True, require_api_key=False)
    elif normalized_provider in {"azure_openai", "azure"}:
        resolved = _build_azure_openai_settings(timeout_seconds, include_generic=True, require_api_key=False)
    elif normalized_provider in {"anthropic", "claude"}:
        resolved = _build_anthropic_settings(timeout_seconds, include_generic=True, require_api_key=False)
    elif normalized_provider in {"gemini", "google"}:
        resolved = _build_gemini_settings(timeout_seconds, include_generic=True, require_api_key=False)
    elif normalized_provider in {"local", "custom"}:
        resolved = _build_local_settings(timeout_seconds, include_generic=True)
    else:
        raise AIServiceError(
            f"Unsupported AI provider '{provider}'. Select one explicit provider: github_copilot, openai, azure_openai, anthropic, gemini, or local."
        )

    return replace(
        resolved,
        api_key=(api_key.strip() if api_key and api_key.strip() else resolved.api_key),
        model=model.strip() if model and model.strip() else resolved.model,
        base_url=endpoint.strip().rstrip("/") if endpoint and endpoint.strip() else resolved.base_url,
    )


def _provider_connection_help(settings: AIProviderSettings) -> str:
    if settings.provider == "github_copilot":
        return (
            "Failed to connect to GitHub Copilot / GitHub Models API. "
            "Verify your GITHUB_TOKEN has access to GitHub Models (https://github.com/marketplace/models)."
        )
    return "Failed to connect to hosted AI provider."


def _extract_json_payload(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise AIServiceError("AI response was not valid JSON.")


def _build_prompt(
    application_name: str,
    platform: str,
    target: str,
    user_prompt: str,
    max_cases: int | None,
    min_steps_per_case: int,
    max_steps_per_case: int,
    include_negative_scenarios: bool,
    include_accessibility_checks: bool,
    include_api_validations: bool,
    module_focus: str,
    target_context: str,
    document_context: str = "",
    planner_context: str = "",
    generator_guidance: str = "",
    target_case_count: int | None = None,
    excluded_titles: list[str] | None = None,
    include_performance_scenarios: bool = False,
    performance_budget: str = "",
    input_format: str = "text",
) -> str:
    focus_text = module_focus.strip() or "all critical user workflows"
    case_count_instruction = f"Generate exactly {target_case_count} distinct test scenarios for this generation batch. Do not stop early when more requested scenarios remain."
    if not target_case_count:
        case_count_instruction = (
            f"Generate up to approximately {max_cases} high-value test scenarios."
            if max_cases and max_cases > 0
            else "Autonomously determine the optimal number of comprehensive test scenarios based on feature complexity, routes, and edge paths."
        )
    excluded_text = "\n".join(f"- {title}" for title in (excluded_titles or [])[:40]) or "- None"
    source_anchor_terms = _source_anchor_terms(user_prompt, document_context, module_focus)
    source_anchor_instruction = ", ".join(source_anchor_terms) or "the supplied requirement statements"
    return (
        "You are an expert Principal QA Automation Engineer and Test Architect.\n"
        "Your task is to generate high-fidelity, comprehensive end-to-end test scenarios from the authoritative uploaded "
        "requirement context and explicit user prompt by implementing the supplied AI Playwright Plan across all application "
        "modules, navigation paths, and business logic. Live UI context and existing cases are supporting evidence only.\n\n"
        "### OUTPUT FORMAT\n"
        "Return strict, valid JSON ONLY (without markdown fences, commentary, or conversational prose) in this exact schema:\n"
        "{\n"
        '  "summary": "Brief executive summary explaining the test design strategy and coverage scope",\n'
        '  "test_cases": [\n'
        "    {\n"
        '      "title": "TC01 - Descriptive scenario title",\n'
        '      "description": "Clear explanation of the scenario goal and user journey",\n'
        '      "preconditions": "Required initial system state, authentication, or test data (e.g. User is logged in; on https://...)",\n'
        '      "steps": "1. Open https://...\\n2. Enter \\"{{login_email}}\\" into Email\\n3. Enter \\"{{login_password}}\\" into Password\\n4. Click \\"Sign in\\"\\n5. Navigate to /section\\n6. Perform action...\\n7. Verify result...",\n'
        '      "expected_result": "Explicit, verifiable UI behavior, message, or system outcome",\n'
        '      "category": "positive|negative|boundary|edge|exploratory|security|accessibility|api|performance|functional",\n'
        '      "test_data": {"parameter_key": "scenario-specific value or placeholder value"},\n'
        '      "status": "draft"\n'
        "    }\n"
        "  ],\n"
        '  "exploratory_notes": "Observed exploratory facts and hypotheses used by this batch"\n'
        "}\n\n"
        "### QUALITY & COVERAGE CRITERIA\n"
        f"1. {case_count_instruction}\n"
        "2. Status must be 'draft'.\n"
        "3. PRIMARY DIRECTIVE - USER CUSTOM PROMPT: You MUST generate explicit test cases that directly implement every user story, requirement, action, and validation rule described in 'USER REQUIREMENTS & CUSTOM PROMPT' below.\n"
        "4. ALL-SCREENS EXPLORATORY COVERAGE: You MUST generate exploratory test cases (category: 'exploratory') and functional cases across ALL discovered application screens, navigation paths, menus, tabs, and routes identified by the discovery and exploration agents.\n"
        f"5. Focus on application area / modules: {focus_text}.\n"
        f"6. Include negative / error validation scenarios: {'YES' if include_negative_scenarios else 'NO'}.\n"
        f"7. Include accessibility / keyboard / focus validation scenarios: {'YES' if include_accessibility_checks else 'NO'}.\n"
        f"8. Include API / network payload validation scenarios: {'YES' if include_api_validations else 'NO'}.\n"
        f"9. Include performance and non-functional scenarios: {'YES' if include_performance_scenarios else 'NO'}.\n"
        f"10. Input format: {input_format}.\n"
        f"11. Performance budget or acceptance target: {performance_budget.strip() or 'Use a measurable threshold from the supplied sources; if none is provided, state that the threshold requires agreement.'}\n"
        "12. When API coverage is enabled, create category 'api' cases only from supplied endpoints or API requirements. Cover method, authentication, request data, expected status, response schema, negative responses, and contract validation; do not invent endpoints.\n"
        "13. When performance coverage is enabled, create category 'performance' cases with a bounded workload, concurrency or volume assumptions, measurement method, and measurable latency/throughput/error-rate acceptance criteria. Describe a safe load-test harness; do not execute unbounded traffic or destructive operations.\n"
        "14. Every test case title must start with sequential numbering: TC01 - ..., TC02 - ..., etc.\n"
        f"15. Each 'steps' field must contain {min_steps_per_case} to {max_steps_per_case} numbered, step-by-step actions.\n"
        "16. For authenticated workflows, include prerequisite login actions using '{{login_email}}' and '{{login_password}}' placeholders and explicit route navigation to the target module before executing core actions.\n"
        "17. For negative authentication or validation scenarios, use invalid test values (e.g. 'invalid.user@example.invalid', 'wrong-password') to verify error handling and access denial.\n"
        "18. Make actions explicit using observed UI elements, buttons, links, inputs, and form controls whenever present.\n"
        "19. Cover both positive happy-paths, authenticated workflows, and edge/boundary conditions.\n"
        "20. Every test case must have an explicit, non-empty 'expected_result' asserting visible UI changes, messages, or URL updates.\n"
        "21. EXPLORATORY CHARTER MANDATE: You MUST generate at least 1 to 2 high-value test cases with category 'exploratory' per batch. "
        "These exploratory test cases must implement the planned exploratory charters across different screens, probing unscripted user behaviors, complex form interaction sequences, "
        "rapid navigation transitions, session edge states, and dynamic DOM re-rendering, with explicit steps and observable UI assertions.\n"
        f"22. Every case must be directly relevant to at least one of these source anchors: {source_anchor_instruction}.\n"
        "23. Align with Playwright browser automation standards: formulate deterministic step actions (e.g. '1. Navigate to /dashboard', "
        "'2. Click button \"Filter\"', '3. Type value into search input', '4. Verify locator has text ...') and use placeholders "
        "'{{login_email}}' and '{{login_password}}' for credentials.\n"
        "24. MANDATORY STRICT TEST DATA PARAMETERIZATION: Do NOT hardcode arbitrary raw sample strings or dummy data directly inside step text without template variable placeholders. "
        "Every form field entry, search query, filter parameter, and credential MUST be parameterized using template variables: '{{variable_name}}' (e.g. '{{login_email}}', '{{login_password}}', '{{first_name}}', '{{last_name}}', '{{phone}}', '{{email}}', '{{city}}', '{{state}}', '{{zip_code}}', '{{address}}', '{{order_id}}', '{{status}}', '{{search_term}}'). "
        "For example, write: '2. Enter \"{{search_term}}\" into the search field' (NEVER write '2. Enter \"Sample Search\" into search field'). "
        "For every test case, you MUST include a complete 'test_data' dictionary binding each placeholder variable to its scenario-specific value (e.g. {\"search_term\": \"Valid Query\"} for positive tests, or {\"search_term\": \"NonExistent999\"} for negative tests).\n"
        "25. FORM SUBMISSION ACTION DISAMBIGUATION: When generating action steps for search, filter, update, save, or submit operations, "
        "always target the specific on-page form submit button label (e.g. 'Click button \"Search\"', 'Click \"Submit\"', 'Click \"Save\"', 'Click \"Apply\"') "
        "rather than top-level navigation dropdown categories or menu headers. Never generate a step that clicks a header navigation link when the goal is to submit an active form.\n"
        "26. EXPLICIT EXPLORATORY TEST SCENARIOS: You MUST generate high-value exploratory test scenarios (with 'category': 'exploratory' and titles formatted as 'TCxx - Exploratory: ...') "
        "that probe unscripted user journeys, edge input combinations, rapid navigation transitions, session resilience, and dynamic DOM state updates across all discovered application screens.\n\n"
        "### USER REQUIREMENTS & CUSTOM PROMPT (PRIMARY MANDATE)\n"
        f"{user_prompt.strip() or 'None provided'}\n\n"
        "### APPLICATION & RUNTIME CONTEXT\n"
        f"Input Format: {input_format}\n"
        f"Application Name: {application_name}\n"
        f"Platform: {platform}\n"
        f"Target URL / Endpoint: {target}\n\n"
        "### AUTHORITATIVE DOCUMENT & REQUIREMENTS CONTEXT\n"
        f"{document_context.strip() or 'No uploaded requirement documents were provided.'}\n\n"
        "### AI PLAYWRIGHT PLAN\n"
        f"{planner_context.strip() or 'No separate AI planner output was provided.'}\n\n"
        "### GENERATOR AGENT GUIDANCE\n"
        f"{generator_guidance.strip() or 'Use concrete observed controls, independent journeys, and verifiable outcomes.'}\n\n"
        "### ALREADY GENERATED TITLES TO AVOID\n"
        f"{excluded_text}\n\n"
        f"{target_context}"
    )


def _build_provider_payload(
    settings: AIProviderSettings,
    prompt: str,
    *,
    system_content: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.model,
        "temperature": 0.2,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": system_content or (
                    "You are an expert Principal QA Automation Engineer and Test Architect. "
                    "Analyze the provided application domain, page hierarchy, UI controls (headings, buttons, links, inputs, dropdowns), "
                    "and user specification to design comprehensive, realistic, and executable end-to-end test scenarios. "
                    "Ensure deep business logic understanding, edge cases, negative flows, and detailed step-by-step actions."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    if settings.provider in {"openai", "azure_openai", "github_copilot", "github_models", "local"}:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _build_provider_headers(settings: AIProviderSettings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        if settings.provider == "anthropic":
            headers["x-api-key"] = settings.api_key
            headers["anthropic-version"] = "2023-06-01"
        elif settings.provider in {"azure_openai", "azure"}:
            headers["api-key"] = settings.api_key
            headers["Authorization"] = f"Bearer {settings.api_key}"
        elif settings.provider in {"github_copilot", "copilot", "github", "github_models"}:
            headers["Authorization"] = f"Bearer {settings.api_key}"
            headers["Editor-Version"] = "vscode/1.95.0"
            headers["User-Agent"] = "GitHubCopilot/1.0"
            headers["Copilot-Integration-Id"] = "vscode-chat"
        else:
            headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


async def _post_chat_completion(
    client: httpx.AsyncClient,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    settings: AIProviderSettings,
    *,
    max_retries: int = 2,
) -> httpx.Response:
    current_payload = payload
    for attempt in range(max_retries + 1):
        try:
            response = await client.post(endpoint, headers=headers, json=current_payload)
        except httpx.HTTPError as error:
            if attempt < max_retries:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            raise AIServiceError(
                f"{_provider_connection_help(settings)} Technical detail: {error}"
            ) from error

        if response.status_code == 400 and ("response_format" in response.text or "json_object" in response.text):
            if "response_format" in current_payload:
                current_payload = dict(current_payload)
                current_payload.pop("response_format", None)
                continue

        if response.status_code == 429:
            retry_after = 1.5 * (attempt + 1)
            raw_retry_header = response.headers.get("retry-after", "")
            try:
                header_val = float(raw_retry_header) if raw_retry_header else 0.0
            except ValueError:
                header_val = 0.0
            if header_val > 5.0:
                raise AIServiceError(f"AI provider {settings.provider}:{settings.model} is rate-limited (Retry-After: {raw_retry_header}s).")
            retry_after = min(max(retry_after, header_val), 3.0)
            if attempt < max_retries:
                log_event(
                    logger,
                    "ai_rate_limit_backoff",
                    provider=settings.provider,
                    model=settings.model,
                    attempt=attempt + 1,
                    wait_seconds=retry_after,
                )
                await asyncio.sleep(retry_after)
                continue
            raise AIServiceError(_provider_http_error_message(response, settings))

        if response.status_code in {500, 502, 503, 504} and attempt < max_retries:
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code >= 400:
            raise AIServiceError(_provider_http_error_message(response, settings))

        return response
    raise AIServiceError(f"AI provider {settings.provider}:{settings.model} exceeded retry attempts.")


async def _request_provider_json(
    settings: AIProviderSettings,
    prompt: str,
    *,
    system_content: str,
    agent_key: str = "healer",
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    payload = _build_provider_payload(settings, prompt, system_content=system_content)
    headers = _build_provider_headers(settings)
    endpoint = f"{settings.base_url}/chat/completions"
    started_at = time.perf_counter()
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.timeout_seconds
    log_event(
        logger,
        f"ai_{agent_key}_request_started",
        provider=settings.provider,
        model=settings.model,
        prompt_length=len(prompt),
    )
    async with httpx.AsyncClient(timeout=effective_timeout) as client:
        response = await _post_chat_completion(client, endpoint, headers, payload, settings)
    try:
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parsed = json.loads(_extract_json_payload(content))
    except (ValueError, TypeError, IndexError, KeyError) as error:
        raise AIServiceError(f"AI {agent_key} response parsing failed: {error}") from error
    log_event(
        logger,
        f"ai_{agent_key}_response_received",
        provider=settings.provider,
        model=settings.model,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
    )
    if not isinstance(parsed, dict):
        raise AIServiceError(f"AI {agent_key} returned a non-object response")
    return parsed


def _load_dynamic_case_targets() -> tuple[int, int, int, int, int]:
    try:
        default_target = max(5, int(os.getenv("AI_DEFAULT_CASE_TARGET", os.getenv("AI_QA_ENGINE_DEFAULT_CASE_TARGET", "20"))))
    except ValueError:
        default_target = 20
    try:
        min_target = max(1, int(os.getenv("AI_MIN_CASE_TARGET", os.getenv("AI_QA_ENGINE_MIN_CASE_TARGET", "10"))))
    except ValueError:
        min_target = 10
    try:
        max_target = max(min_target, int(os.getenv("AI_MAX_CASE_TARGET", os.getenv("AI_QA_ENGINE_MAX_CASE_TARGET", "100"))))
    except ValueError:
        max_target = 100
    try:
        batch_size = max(1, int(os.getenv("AI_GENERATOR_BATCH_SIZE", os.getenv("AI_QA_ENGINE_GENERATOR_BATCH_SIZE", "15"))))
    except ValueError:
        batch_size = 15
    try:
        max_calls = max(1, int(os.getenv("AI_MAX_GENERATOR_CALLS", os.getenv("AI_QA_ENGINE_MAX_GENERATOR_CALLS", "20"))))
    except ValueError:
        max_calls = 20
    return default_target, min_target, max_target, batch_size, max_calls


DEFAULT_DYNAMIC_AI_CASE_TARGET, MIN_DYNAMIC_AI_CASE_TARGET, MAX_DYNAMIC_AI_CASE_TARGET, GENERATOR_BATCH_SIZE, MAX_GENERATOR_CALLS = _load_dynamic_case_targets()


def _bounded_string_list(value: Any, *, limit: int = 50, item_limit: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("title") or item.get("description") or ""
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text:
            values.append(text[:item_limit])
        if len(values) >= limit:
            break
    return values


def _normalize_planner_output(
    parsed: dict[str, Any],
    *,
    max_cases: int | None,
    context_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_plan = parsed.get("plan") if isinstance(parsed.get("plan"), dict) else parsed
    raw_recommended = raw_plan.get("recommended_case_count") or raw_plan.get("case_count")
    try:
        recommended_case_count = int(raw_recommended)
    except (TypeError, ValueError):
        signal_count = sum(
            int(context_snapshot.get(key) or 0)
            for key in ("requirements_found", "workflow_signals")
        ) if context_snapshot else 0
        mod_count = len(context_snapshot.get("modules", [])) if context_snapshot else 1
        recommended_case_count = max(DEFAULT_DYNAMIC_AI_CASE_TARGET, min(MAX_DYNAMIC_AI_CASE_TARGET, mod_count * 2 + signal_count))

    target_case_count = max_cases if max_cases is not None else max(
        MIN_DYNAMIC_AI_CASE_TARGET,
        min(MAX_DYNAMIC_AI_CASE_TARGET, recommended_case_count),
    )
    if max_cases is not None:
        target_case_count = max(1, min(50, max_cases))

    coverage_matrix: list[dict[str, Any]] = []
    raw_coverage = raw_plan.get("coverage_matrix") or raw_plan.get("coverage") or []
    if isinstance(raw_coverage, list):
        for item in raw_coverage[:35]:
            if isinstance(item, dict):
                area = str(item.get("area") or item.get("module") or item.get("feature") or "Core workflow").strip()[:160]
                scenarios = _bounded_string_list(item.get("scenarios") or item.get("tests"), limit=16)
            else:
                area = str(item or "Core workflow").strip()[:160]
                scenarios = []
            if area:
                coverage_matrix.append({"area": area, "scenarios": scenarios})

    exploratory_charters: list[dict[str, Any]] = []
    raw_charters = raw_plan.get("exploratory_charters") or raw_plan.get("exploratory_tests") or []
    if isinstance(raw_charters, list):
        for item in raw_charters[:EXPLORATORY_ACTION_LIMIT]:
            if not isinstance(item, dict):
                continue
            observation = str(item.get("observation") or item.get("finding") or "").strip()[:700]
            hypothesis = str(item.get("hypothesis") or item.get("risk") or "").strip()[:700]
            safe_actions = _bounded_string_list(item.get("safe_actions") or item.get("actions"), limit=6, item_limit=180)
            expected_observations = _bounded_string_list(item.get("expected_observations") or item.get("outcomes"), limit=6, item_limit=180)
            if observation or hypothesis:
                exploratory_charters.append({
                    "observation": observation,
                    "hypothesis": hypothesis,
                    "safe_actions": safe_actions,
                    "expected_observations": expected_observations,
                })
    if not exploratory_charters and context_snapshot:
        observed = list(context_snapshot.get("exploratory_observations") or [])[:EXPLORATORY_ACTION_LIMIT]
        hypotheses = list(context_snapshot.get("exploratory_hypotheses") or [])[:EXPLORATORY_ACTION_LIMIT]
        for index, observation in enumerate(observed):
            exploratory_charters.append({
                "observation": str(observation)[:700],
                "hypothesis": str(hypotheses[index] if index < len(hypotheses) else "")[:700],
                "safe_actions": [],
                "expected_observations": ["Record the resulting route, visible state, and validation, empty, loading, or error signals."],
            })
    if not exploratory_charters:
        candidate_areas = [item["area"] for item in coverage_matrix if isinstance(item, dict) and item.get("area")]
        if not candidate_areas:
            candidate_areas = ["Navigation & Session State", "Data Validation & Edge Inputs", "UI Responsiveness & Interactive States", "Error Boundaries & Recovery"]
        for area in candidate_areas[:6]:
            exploratory_charters.append({
                "observation": f"Exploratory inspection of {area} behavior under unpredictable user interaction and rapid navigation transitions.",
                "hypothesis": f"Application may exhibit unhandled exceptions, inconsistent state, or broken UI when navigating or interacting rapidly with {area}.",
                "safe_actions": [f"Navigate to {area}", "Interact with dynamic UI elements in non-standard sequence", "Verify URL parameters, state persistence, and DOM stability"],
                "expected_observations": [f"Verify {area} handles dynamic interaction gracefully without unhandled exceptions or blank screens."],
            })

    return {
        "summary": str(raw_plan.get("summary") or "AI planner created a risk-based Playwright coverage plan.").strip()[:1000],
        "recommended_case_count": target_case_count,
        "authentication_plan": str(raw_plan.get("authentication_plan") or raw_plan.get("auth_plan") or "").strip()[:1000],
        "requirements": _bounded_string_list(raw_plan.get("requirements") or raw_plan.get("requirement_signals")),
        "coverage_matrix": coverage_matrix,
        "navigation_paths": _bounded_string_list(raw_plan.get("navigation_paths") or raw_plan.get("navigation_plan")),
        "entry_points": _bounded_string_list(raw_plan.get("entry_points"), limit=16),
        "risk_areas": _bounded_string_list(raw_plan.get("risk_areas") or raw_plan.get("risks"), limit=20),
        "exploratory_charters": exploratory_charters,
    }


async def extract_intake_signals_with_ai(
    prompt: str,
    document_context: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Uses LLM Document Analysis to extract structured intake information (credentials, URL, focus, requirements) from text."""
    combined_input = f"USER PROMPT / SPECIFICATION:\n{prompt.strip() or 'None'}\n\nDOCUMENT CONTEXT:\n{document_context[:60000].strip() or 'None'}"
    if not prompt.strip() and not document_context.strip():
        return {
            "target_url": None,
            "username": None,
            "password": None,
            "login_email_selector": None,
            "login_password_selector": None,
            "login_submit_selector": None,
            "runtime_parameters": {},
            "module_focus": None,
            "modules": [],
            "features": [],
            "workflows": [],
            "requirements": [],
            "risk_signals": [],
        }

    system_content = (
        "You are the AI Document & Prompt Analysis Agent. Analyze the supplied user prompt and requirement context "
        "to extract structured application URLs, credentials, selectors, variables, all functional modules, user workflows, requirements, and risk signals. "
        "Return valid JSON only."
    )
    request_prompt = (
        "Extract structured test automation intake parameters from the following text.\n\n"
        "Return strict JSON with this exact schema:\n"
        "{\n"
        '  "target_url": "Full HTTP/HTTPS application URL if mentioned (e.g. https://...), else null",\n'
        '  "username": "Username, email, or user identifier if mentioned (e.g. from Username: ..., user ..., email ...), else null",\n'
        '  "password": "Password, passcode, or secret token if mentioned (e.g. from PW: ..., Password: ..., pass ...), else null",\n'
        '  "login_email_selector": "Email/username CSS selector or input hint if mentioned, else null",\n'
        '  "login_password_selector": "Password CSS selector if mentioned, else null",\n'
        '  "login_submit_selector": "Submit/login button selector if mentioned, else null",\n'
        '  "runtime_parameters": {"key": "value"},\n'
        '  "module_focus": "Specific module or workflow name if requested, else null",\n'
        '  "modules": ["Module / Feature Area 1", "Module / Feature Area 2", ...],\n'
        '  "features": ["Feature capability 1", ...],\n'
        '  "workflows": ["End-to-end user workflow 1", ...],\n'
        '  "requirements": ["key testable requirement statement 1", ...],\n'
        '  "risk_signals": ["critical risk or edge case signal 1", ...]\n'
        "}\n\n"
        f"{combined_input}"
    )

    try:
        provider_settings = _load_provider_settings(override_provider=provider, override_model=model)
        for settings in provider_settings:
            try:
                parsed = await _request_provider_json(
                    settings,
                    request_prompt,
                    system_content=system_content,
                    agent_key="document_analysis",
                )
                if isinstance(parsed, dict):
                    target_url = str(parsed.get("target_url") or "").strip() or None
                    if target_url and not target_url.lower().startswith(("http://", "https://")):
                        target_url = None
                    username = str(parsed.get("username") or "").strip() or None
                    password = str(parsed.get("password") or "").strip() or None
                    login_email_sel = str(parsed.get("login_email_selector") or "").strip() or None
                    login_password_sel = str(parsed.get("login_password_selector") or "").strip() or None
                    login_submit_sel = str(parsed.get("login_submit_selector") or "").strip() or None
                    raw_params = parsed.get("runtime_parameters") if isinstance(parsed.get("runtime_parameters"), dict) else {}
                    runtime_parameters = {str(k).strip(): str(v).strip() for k, v in raw_params.items() if str(k).strip()}
                    module_focus = str(parsed.get("module_focus") or "").strip() or None
                    modules = [str(m).strip() for m in parsed.get("modules", []) if str(m).strip()] if isinstance(parsed.get("modules"), list) else []
                    features = [str(f).strip() for f in parsed.get("features", []) if str(f).strip()] if isinstance(parsed.get("features"), list) else []
                    workflows = [str(w).strip() for w in parsed.get("workflows", []) if str(w).strip()] if isinstance(parsed.get("workflows"), list) else []
                    requirements = [str(r).strip() for r in parsed.get("requirements", []) if str(r).strip()] if isinstance(parsed.get("requirements"), list) else []
                    risk_signals = [str(r).strip() for r in parsed.get("risk_signals", []) if str(r).strip()] if isinstance(parsed.get("risk_signals"), list) else []

                    regex_url = _extract_target_url_from_text(prompt, document_context)
                    regex_user, regex_pass = _extract_credentials_from_text(prompt, document_context)

                    return {
                        "target_url": target_url or regex_url,
                        "username": username or regex_user,
                        "password": password or regex_pass,
                        "login_email_selector": login_email_sel,
                        "login_password_selector": login_password_sel,
                        "login_submit_selector": login_submit_sel,
                        "runtime_parameters": runtime_parameters,
                        "module_focus": module_focus,
                        "modules": modules,
                        "features": features,
                        "workflows": workflows,
                        "requirements": requirements,
                        "risk_signals": risk_signals,
                    }
            except AIServiceError:
                continue
    except Exception:
        pass

    fallback_url = _extract_target_url_from_text(prompt, document_context)
    fallback_user, fallback_pass = _extract_credentials_from_text(prompt, document_context)
    return {
        "target_url": fallback_url,
        "username": fallback_user,
        "password": fallback_pass,
        "login_email_selector": None,
        "login_password_selector": None,
        "login_submit_selector": None,
        "runtime_parameters": {},
        "module_focus": None,
        "modules": [],
        "features": [],
        "workflows": [],
        "requirements": [],
        "risk_signals": [],
    }


async def generate_ai_test_plan(
    *,
    application_name: str,
    platform: str,
    target: str,
    user_prompt: str,
    max_cases: int | None,
    module_focus: str,
    include_negative_scenarios: bool,
    include_accessibility_checks: bool,
    include_api_validations: bool,
    document_context: str,
    reference_cases: list[str],
    include_performance_scenarios: bool = False,
    performance_budget: str = "",
    input_format: str = "text",
    observed_target_context: str = "",
    include_positive_scenarios: bool = True,
    include_boundary_scenarios: bool = True,
    include_edge_cases: bool = True,
    include_security_scenarios: bool = True,
    include_validation_rules: bool = True,
    context_snapshot: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    from app.services.agent_definitions import AgentDefinitionError, build_agent_guidance_block

    try:
        planner_guidance = build_agent_guidance_block(["planner"])
    except AgentDefinitionError:
        planner_guidance = ""
    if not observed_target_context.strip():
        observed_target = await _capture_target_ui_context(target)
        observed_target_context = _format_target_context_for_prompt(observed_target, reference_cases)
    mod_count = len(context_snapshot.get("modules", [])) if context_snapshot else 1
    req_count = int(context_snapshot.get("requirements_found", 0)) if context_snapshot else 0
    calculated_min = max(12, min(50, mod_count * 2 + req_count // 2))
    requested_count = (
        str(max_cases)
        if max_cases is not None
        else f"Determine the optimal case count (typically {calculated_min} to 50 distinct test cases) to provide full, comprehensive QA coverage across every single documented module, requirement statement, and workflow."
    )
    context_text = json.dumps(context_snapshot or {}, ensure_ascii=True)[:24_000]
    reference_text = "\n".join(f"- {item[:300]}" for item in reference_cases[:12]) or "- None provided"
    prompt = (
        "You are the AI Playwright Planner Agent. Treat the supplied requirement document context and user request "
        "as the authoritative specification. Analyze the application, bounded requirements, reference cases, and "
        "observed context, then create a concrete risk-based plan for an AI test-case generator.\n\n"
        "### YOUR PLANNING MANDATE:\n"
        "1. **Authentication & Session Plan**: Explicitly plan the prerequisite login flow (using `{{login_email}}` and `{{login_password}}` placeholders), role permissions, session handling, and negative credential checks.\n"
        "2. **Route Navigation Map**: Map out multi-step navigation paths starting from base URL/login to specific inner pages, forms, modals, and tables.\n"
        "3. **Coverage Matrix**: For each application module (Auth, Navigation, CRUD, Search/Filter, Data Validation, Error Handling, Responsive UX), define concrete scenario outlines with user journeys and observable outcomes.\n"
        "4. **Assertions & Checks**: Direct the downstream generator on exact visible text, page title, and URL route verifications.\n\n"
        "Return strict JSON only with summary, recommended_case_count, authentication_plan, requirements, coverage_matrix, navigation_paths, "
        "entry_points, risk_areas, and exploratory_charters. Every planned scenario must trace to a requirement, workflow, rule, "
        "bounded exploratory observation, or explicit "
        "user prompt signal. The coverage matrix must contain distinct scenarios across positive, negative, "
        "boundary, edge, exploratory, security, accessibility, API, and performance categories when enabled. Use the bounded exploratory "
        "observations to create focused exploratory charters with an observation, clearly labeled hypothesis, safe actions, "
        "and expected observable outcomes. Never invent UI controls that are "
        "not supported by the supplied context.\n\n"
        f"Application: {application_name}\nPlatform: {platform}\nTarget: {target}\n"
        f"Requested case count: {requested_count}\nModule focus: {module_focus.strip() or 'All critical workflows'}\n"
        f"Negative scenarios enabled: {include_negative_scenarios}\n"
        f"Positive scenarios enabled: {include_positive_scenarios}\n"
        f"Boundary scenarios enabled: {include_boundary_scenarios}\n"
        f"Edge cases enabled: {include_edge_cases}\n"
        f"Security scenarios enabled: {include_security_scenarios}\n"
        f"Validation rules enabled: {include_validation_rules}\n"
        f"Accessibility checks enabled: {include_accessibility_checks}\n"
        f"API validations enabled: {include_api_validations}\n\n"
        f"Performance scenarios enabled: {include_performance_scenarios}\n"
        f"Performance budget: {performance_budget.strip() or 'Use a measurable threshold from supplied sources; otherwise mark the threshold as requiring agreement.'}\n"
        f"Input format: {input_format}\n\n"
        f"Context snapshot:\n{context_text}\n\n"
        f"Observed target UI context:\n{observed_target_context[:20_000]}\n\n"
        f"USER REQUIREMENTS & CUSTOM PROMPT:\n{user_prompt.strip() or 'None provided'}\n\n"
        f"AUTHORITATIVE REQUIREMENT DOCUMENT CONTEXT:\n{document_context[:100_000] or 'None provided'}\n\n"
        f"SUPPLEMENTAL REFERENCE CASES (use only when consistent with the authoritative requirements):\n{reference_text}\n\n"
        f"Planner guidance:\n{planner_guidance or 'Use explicit entry points, paths, risk, and observable outcomes.'}"
    )
    system_content = (
        "You are a senior QA test planner. Produce only valid JSON for the downstream test-case generator. "
        "Your plan must be specific enough to drive multiple distinct Playwright test cases."
    )
    attempted_errors: list[str] = []
    provider_settings = _load_provider_settings(
        override_provider=provider,
        override_model=model,
    )
    for settings in provider_settings:
        try:
            parsed = await _request_provider_json(
                settings,
                prompt,
                system_content=system_content,
                agent_key="planner",
            )
            return {
                "plan": _normalize_planner_output(
                    parsed,
                    max_cases=max_cases,
                    context_snapshot=context_snapshot,
                ),
                "provider": settings.provider,
                "model": settings.model,
            }
        except AIServiceError as error:
            attempted_errors.append(f"{settings.provider}:{settings.model} -> {error}")
            await asyncio.sleep(0.5)
    raise AIServiceError(
        "AI Planner failed before test generation: "
        + ("; ".join(attempted_errors) or "No AI provider is configured.")
    )


def _heuristic_dom_repair(failed_step: Step, failure_message: str, page_context: str) -> tuple[Step, str] | None:
    sel = (failed_step.selector or "").strip()
    sel_lower = sel.lower()

    if failed_step.action == "click":
        raw_text_match = re.search(r"['\"]([^'\"]+)['\"]", sel) or re.search(r"(?:text=|label=)(.+)", sel)
        target_text = raw_text_match.group(1).strip() if raw_text_match else sel.replace("text=", "").replace("label=", "").strip()
        if target_text and len(target_text) >= 2:
            safe_text = target_text.replace("'", "\\'")
            repaired_selector = (
                f"form button:has-text('{safe_text}'), "
                f"form input[type='submit'][value*='{safe_text}' i], "
                f"form input[value*='{safe_text}' i], "
                f"main button:has-text('{safe_text}'), "
                f"button:has-text('{safe_text}'), "
                f"input[type='submit'][value*='{safe_text}' i], "
                f"[role='button']:has-text('{safe_text}'), "
                f"form a:has-text('{safe_text}'), "
                f"main a:has-text('{safe_text}'), "
                f"a:has-text('{safe_text}'), "
                f"text={safe_text}"
            )
            return failed_step.model_copy(update={"selector": repaired_selector}), f"Heuristic repair: expanded clickable locator prioritizing in-form button or submit control matching '{target_text}'"

    if failed_step.action == "type":
        if "@" in sel_lower or "email" in sel_lower or "username" in sel_lower or "user" in sel_lower:
            repaired_selector = "#user_email, input[type='email'], input[name*='email' i], input[name*='username' i], input[name*='user' i], #username, #email"
            return failed_step.model_copy(update={"selector": repaired_selector}), "Heuristic repair: mapped to resilient email/username input locators"
        if "password" in sel_lower or "pass" in sel_lower or "pwd" in sel_lower:
            repaired_selector = "#user_password, input[type='password'], input[name*='password' i], #password, #pass"
            return failed_step.model_copy(update={"selector": repaired_selector}), "Heuristic repair: mapped to resilient password input locators"

        if sel.startswith("label="):
            raw_field = sel[6:].strip().strip("\"'")
            base_field = re.sub(r"\b(filter|field|input|box|the)\b", "", raw_field, flags=re.IGNORECASE).strip() or raw_field
            clean_field = base_field.lower().replace(" ", "_").replace("-", "_")
            repaired_selector = f"input#{clean_field}, input[name*='{clean_field}' i], input[id*='{clean_field}' i], label:has-text('{base_field}') + input, label:has-text('{base_field}') ~ input"
            return failed_step.model_copy(update={"selector": repaired_selector}), f"Heuristic repair: normalized field '{raw_field}' to target input control"

    if failed_step.action == "select":
        if sel.startswith("label="):
            raw_field = sel[6:].strip().strip("\"'")
            base_field = re.sub(r"\b(dropdown|select|filter|field|the)\b", "", raw_field, flags=re.IGNORECASE).strip() or raw_field
            clean_field = base_field.lower().replace(" ", "_").replace("-", "_")
            repaired_selector = f"select#{clean_field}, select[name*='{clean_field}' i], select[id*='{clean_field}' i], label:has-text('{base_field}') + select, label:has-text('{base_field}') ~ select"
            return failed_step.model_copy(update={"selector": repaired_selector}), f"Heuristic repair: normalized select field '{raw_field}' to target select control"

    if failed_step.action in {"check", "uncheck"}:
        target_name = sel.replace("label=", "").replace("text=", "").strip().strip("\"'")
        base_name = re.sub(r"\b(checkbox|box|toggle|the)\b", "", target_name, flags=re.IGNORECASE).strip() or target_name
        clean_name = base_name.lower().replace(" ", "_").replace("-", "_")
        repaired_selector = f"input[type='checkbox']#{clean_name}, input[type='checkbox'][name*='{clean_name}' i], label:has-text('{base_name}') input[type='checkbox'], label:has-text('{base_name}') + input[type='checkbox'], [role='checkbox'][aria-label*='{base_name}' i], [role='checkbox']:has-text('{base_name}')"
        return failed_step.model_copy(update={"selector": repaired_selector}), f"Heuristic repair: mapped checkbox locator for '{target_name}'"

    return None


async def generate_healing_step(
    *,
    failed_step: Step,
    failure_message: str,
    page_context: str,
    provider: str | None = None,
    model: str | None = None,
    application_id: int | None = None,
    previous_step: Step | None = None,
) -> tuple[Step, str]:
    from app.services.agent_definitions import build_agent_guidance_block

    safe_step = failed_step.model_dump(exclude_none=True)
    if failed_step.secret_name or (
        failed_step.action == "type" and "password" in (failed_step.selector or "").casefold()
    ):
        safe_step["value"] = "[redacted]"
    guidance = build_agent_guidance_block(["healer"])

    memory_section = ""
    if application_id:
        try:
            from app.services.vector_service import VectorStoreService
            vstore = VectorStoreService(application_id)
            past_repairs = await vstore.query_healing_memory(
                action=failed_step.action,
                failed_selector=failed_step.selector or "",
                failure_message=failure_message,
                top_k=2,
            )
            if past_repairs:
                mem_lines = [
                    f"- Historical repair: selector '{r.get('healed_selector')}' previously resolved similar failure ({r.get('reason', '')})"
                    for r in past_repairs
                    if r.get("healed_selector")
                ]
                if mem_lines:
                    memory_section = "\n\nHistorical Self-Healing Vector Memory (prior successful repairs on this application):\n" + "\n".join(mem_lines)
        except Exception:
            pass

    previous_step_section = ""
    if previous_step:
        previous_step_section = (
            f"Preceding Step in Workflow:\n"
            f"- Action: {previous_step.action}\n"
            f"- Selector: {previous_step.selector or 'none'}\n"
            f"- Description: {previous_step.description or 'none'}\n\n"
        )

    prompt = (
        "Repair exactly one failed Playwright test step. Return JSON only with this shape: "
        '{"action":"same action as input","selector":"resilient selector or null",'
        '"value":"only when safe","reason":"brief explanation"}. '
        "Keep the original action and secret handling. Prefer accessible roles, labels, names, "
        "stable ids, and visible text over brittle CSS paths. Never return credentials or secret values.\n\n"
        "Crucial Hierarchy & Container Rules:\n"
        "1. Differentiate in-form action controls from header/navigation links. "
        "When performing an action (such as 'click') following a form entry or input step, "
        "prioritize buttons, submit inputs, or action controls located inside the active [Form], .input-group, or [Main Content] "
        "container adjacent to the input field over global [Header/Navigation] links.\n"
        "2. When duplicate text or labels exist in the header navigation and on-page form, "
        "always provide a container-scoped selector (e.g. 'form button:has-text(\"...\")', 'form input[type=submit]', 'main button') "
        "to prevent accidental navigation away from the active form.\n\n"
        f"Agent guidance:\n{guidance}\n\n"
        f"Failed step:\n{json.dumps(safe_step, ensure_ascii=True)}\n\n"
        f"{previous_step_section}"
        f"Failure:\n{failure_message[:1200]}\n\n"
        f"Current rendered page context (annotated with container tags):\n{page_context[:14000]}"
        f"{memory_section}"
    )
    system_content = (
        "You are the Playwright Test Healer. You repair locator drift for one existing test step. "
        "Analyze container context: prioritize in-form and content buttons over header navigation links. "
        "Do not invent business actions, do not change the action type, and do not expose secrets."
    )
    last_error: AIServiceError | None = None
    try:
        for settings in _load_provider_settings(provider, model):
            try:
                parsed = await _request_provider_json(settings, prompt, system_content=system_content)
                raw_step = parsed.get("step") if isinstance(parsed.get("step"), dict) else parsed
                candidate = Step.model_validate(raw_step)
                if candidate.action != failed_step.action:
                    candidate = candidate.model_copy(update={"action": failed_step.action})
                if failed_step.action in {"type", "select", "assert_text", "assert_title", "assert_url_contains"}:
                    candidate = candidate.model_copy(
                        update={"value": failed_step.value, "secret_name": failed_step.secret_name}
                    )
                if failed_step.action not in {"navigate", "assert_title", "assert_url_contains"} and not candidate.selector:
                    raise AIServiceError("AI healer returned no selector for an element action")
                reason = str(parsed.get("reason") or "AI healer supplied a resilient locator")[:500]
                return candidate, reason
            except AIServiceError as error:
                last_error = error
    except Exception as exc:
        last_error = AIServiceError(str(exc))

    # Fast DOM heuristic fallback if AI provider is unavailable or models failed
    heuristic = _heuristic_dom_repair(failed_step, failure_message, page_context)
    if heuristic:
        return heuristic

    raise last_error or AIServiceError("No AI provider is configured for Playwright healing")


async def extract_interactive_accessibility_tree(page: Page) -> list[dict[str, Any]]:
    """Extracts a structured accessibility and container hierarchy tree of all actionable elements on the page."""
    try:
        candidates = await page.evaluate(
            """() => {
                const candidates = [];
                let nextId = 1;
                const elements = document.querySelectorAll(
                    'input, button, select, textarea, a[href], [role="button"], [role="link"], [role="tab"], [role="checkbox"], [role="radio"], [role="menuitem"], [role="combobox"], [aria-expanded], [aria-haspopup], .nav-link, .dropdown-item, .btn, label[for]'
                );
                for (const el of elements) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width <= 0 || rect.height <= 0 || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        continue;
                    }

                    const tag = el.tagName.toLowerCase();
                    const typeAttr = (el.getAttribute('type') || '').toLowerCase();
                    const idAttr = el.id || '';
                    const nameAttr = el.getAttribute('name') || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const placeholder = el.getAttribute('placeholder') || '';
                    const role = el.getAttribute('role') || '';
                    const forAttr = el.getAttribute('for') || '';
                    const titleAttr = el.getAttribute('title') || '';
                    const classNames = (el.className && typeof el.className === 'string') ? el.className.trim() : '';

                    let value = '';
                    if (tag === 'input' && (typeAttr === 'submit' || typeAttr === 'button' || typeAttr === 'reset')) {
                        value = el.value || '';
                    } else if (tag === 'input' || tag === 'textarea') {
                        value = el.value || '';
                    }
                    let text = (el.textContent || el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
                    if (tag === 'input' && value) {
                        text = value;
                    }

                    const navContainer = el.closest('header, nav, .navbar, .site-header, .top-nav, [role="navigation"]');
                    const formContainer = el.closest('form');
                    const modalContainer = el.closest('.modal, [role="dialog"], .popup, .drawer, aside');
                    const mainContainer = el.closest('main, #main, .main-content, article, .content, .container, .well, .panel');

                    let containerType = 'content';
                    let containerId = '';
                    if (modalContainer) {
                        containerType = 'modal';
                        containerId = modalContainer.id || modalContainer.getAttribute('aria-label') || '';
                    } else if (formContainer) {
                        containerType = 'form';
                        containerId = formContainer.id ? `#${formContainer.id}` : (formContainer.name ? `[name='${formContainer.name}']` : '');
                    } else if (mainContainer) {
                        containerType = 'main';
                        containerId = mainContainer.id || mainContainer.className || '';
                    } else if (navContainer) {
                        containerType = 'navigation';
                        containerId = navContainer.className || 'header-nav';
                    }

                    let suggestedSelector = '';
                    if (idAttr) {
                        suggestedSelector = `${tag}#${idAttr}`;
                    } else if (tag === 'input' && (typeAttr === 'submit' || typeAttr === 'button') && value) {
                        suggestedSelector = formContainer ? `form input[type='${typeAttr}'][value*='${value}' i]` : `input[type='${typeAttr}'][value*='${value}' i]`;
                    } else if (nameAttr && tag === 'input') {
                        suggestedSelector = `input[name='${nameAttr}']`;
                    } else if (tag === 'button' && text) {
                        suggestedSelector = formContainer ? `form button:has-text('${text}')` : `button:has-text('${text}')`;
                    } else if (tag === 'a' && text) {
                        suggestedSelector = `a:has-text('${text}')`;
                    } else if (ariaLabel) {
                        suggestedSelector = `[aria-label='${ariaLabel}']`;
                    } else if (placeholder) {
                        suggestedSelector = `[placeholder*='${placeholder}' i]`;
                    } else {
                        suggestedSelector = tag;
                    }

                    candidates.push({
                        candidate_id: nextId++,
                        container_type: containerType,
                        container_id: containerId,
                        tag: tag,
                        type: typeAttr,
                        id: idAttr,
                        name: nameAttr,
                        text: text,
                        value: value,
                        aria_label: ariaLabel,
                        placeholder: placeholder,
                        title: titleAttr,
                        classes: classNames,
                        role: role,
                        for_attr: forAttr,
                        suggested_selector: suggestedSelector,
                    });

                    if (candidates.length >= 100) break;
                }
                return candidates;
            }"""
        )
        return candidates or []
    except Exception as error:
        logger.debug("Failed to extract interactive accessibility tree: %s", error)
        return []


async def resolve_action_with_agent(
    *,
    page: Page,
    step: Step,
    previous_step: Step | None = None,
    application_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> Step | None:
    """
    Autonomous Playwright Execution Agent:
    Inspects the live accessibility and container hierarchy tree, analyzes workflow intent,
    and dynamically resolves the exact Playwright locator to execute the step across any application.
    """
    candidates = await extract_interactive_accessibility_tree(page)
    if not candidates:
        return None

    candidate_lines = []
    for c in candidates[:60]:
        c_id = c.get("candidate_id")
        c_type = str(c.get("container_type", "content")).upper()
        c_tag = c.get("tag", "")
        c_type_attr = f" type='{c.get('type')}'" if c.get("type") else ""
        c_text = f" text='{c.get('text')}'" if c.get("text") else ""
        c_val = f" value='{c.get('value')}'" if c.get("value") else ""
        c_name = f" name='{c.get('name')}'" if c.get("name") else ""
        c_classes = f" class='{c.get('classes')}'" if c.get("classes") else ""
        c_sel = c.get("suggested_selector", "")
        candidate_lines.append(
            f"[{c_type}] #{c_id}: <{c_tag}{c_type_attr}{c_name}{c_classes}{c_text}{c_val}> -> Suggested: {c_sel}"
        )
    candidates_text = "\n".join(candidate_lines)

    step_goal = step.description or f"{step.action} on {step.selector or 'target'}"
    prev_context = (
        f"Previous Step: {previous_step.action} on '{previous_step.selector}' (value: '{previous_step.value or ''}')"
        if previous_step else "None"
    )

    prompt = (
        "You are the Autonomous Playwright Execution Agent.\n"
        "Analyze the live interactive candidates below and decide the single optimal element and selector to execute the desired test step across any web application.\n\n"
        f"Target Step Action: {step.action}\n"
        f"Target Step Goal/Description: {step_goal}\n"
        f"Target Step Requested Selector: {step.selector or 'None'}\n"
        f"Target Step Value: {step.value or 'None'}\n"
        f"{prev_context}\n\n"
        "### CRITICAL DISAMBIGUATION RULES:\n"
        "1. When submitting or acting on an active form (e.g. searching, filtering, updating, saving), "
        "select the submit or button control inside the [FORM] or [MAIN] container, "
        "and NEVER select top-level links or dropdown toggles in [NAVIGATION].\n"
        "2. When navigating, selecting tabs, or clicking actions, match the element text, label, or role.\n"
        "3. Provide an exact, resilient Playwright selector for the chosen element.\n\n"
        "### LIVE INTERACTIVE CANDIDATES:\n"
        f"{candidates_text}\n\n"
        "Return strict JSON only in this format:\n"
        '{"candidate_id": int, "selector": "exact selector string", "reason": "why this candidate was selected"}'
    )

    system_content = (
        "You are the Autonomous Playwright Execution Agent. Select the exact intended element from the container tree."
    )

    # 1. Try LLM Provider settings with fast bounded timeout
    for settings in _load_provider_settings(provider, model):
        try:
            parsed = await _request_provider_json(
                settings,
                prompt,
                system_content=system_content,
                agent_key="execution_agent",
                timeout_seconds=min(settings.timeout_seconds, 10),
            )
            cand_id = parsed.get("candidate_id")
            sel = parsed.get("selector")
            if isinstance(cand_id, int):
                matching = next((c for c in candidates if c.get("candidate_id") == cand_id), None)
                if matching and matching.get("suggested_selector"):
                    return step.model_copy(update={
                        "selector": matching["suggested_selector"],
                        "description": f"Autonomous Execution Agent (LLM) selected #{cand_id}: {matching.get('text') or matching.get('value') or matching.get('suggested_selector')}",
                    })
            if sel and isinstance(sel, str) and sel.strip():
                return step.model_copy(update={"selector": sel.strip(), "description": f"Autonomous Execution Agent (LLM): {parsed.get('reason', '')}"})
        except Exception as err:
            logger.debug("Execution agent provider %s error: %s", settings.provider, err)

    # 2. Universal Semantic Agentic Resolution: Match candidate based on action intent, element text, tokens, and containers
    raw_query = f"{step.selector or ''} {step.description or ''} {step.value or ''}"
    is_auth_intent = any(w in raw_query.lower() for w in ["login", "log in", "sign in", "signin", "password", "auth", "sign_in"])
    target_tokens = [
        t.lower()
        for t in re.split(r"[\s=\-_'\":;,()]+", raw_query)
        if len(t) >= 2 and t.lower() not in {"click", "button", "text", "the", "label", "into", "field", "input", "select", "and", "for"}
    ]

    best_candidate = None
    best_score = -1

    for c in candidates:
        score = 0
        c_text_val = " ".join(filter(None, [c.get("text"), c.get("value"), c.get("name"), c.get("id"), c.get("aria_label"), c.get("placeholder"), c.get("title")])).lower()
        c_container = c.get("container_type", "content")
        c_tag = c.get("tag", "")

        # Token overlap score
        for token in target_tokens:
            if token == c_text_val.strip():
                score += 15
            elif token in c_text_val:
                score += 5
            elif is_auth_intent and token in {"log", "login", "signin", "sign"} and any(w in c_text_val for w in ["sign in", "log in", "login", "signin", "commit"]):
                score += 20

        # Container scoring
        if c_container in {"form", "main", "modal"} and any(w in (step.description or "").lower() for w in ["search", "filter", "submit", "save", "update", "apply", "create", "find", "login", "sign in"]):
            if c.get("type") == "submit" or "btn" in c.get("classes", "").lower() or c_tag == "button":
                score += 8

        if is_auth_intent and (c.get("type") == "submit" or c.get("name") == "commit" or "sign in" in c_text_val or "log in" in c_text_val):
            score += 25

        # Previous step container affinity: if previous step was an auth input (email/password), prioritize auth submit button in that form
        if previous_step and previous_step.selector:
            prev_sel_lower = previous_step.selector.lower()
            if "password" in prev_sel_lower or "email" in prev_sel_lower or "user" in prev_sel_lower:
                if c.get("type") == "submit" and ("commit" in c.get("name", "").lower() or "sign" in c_text_val or "log" in c_text_val):
                    score += 35
                elif c.get("container_type") == "navigation":
                    score -= 30

        if step.action == "type" and (c_tag in {"input", "textarea"} or c.get("role") == "textbox"):
            score += 6
        elif step.action == "click" and (c_tag in {"button", "a"} or c.get("role") in {"button", "link", "tab"} or c.get("type") in {"submit", "button"}):
            score += 6
        elif step.action == "select" and (c_tag == "select" or c.get("role") == "combobox"):
            score += 6

        if score > best_score and score > 0:
            best_score = score
            best_candidate = c

    if best_candidate and best_candidate.get("suggested_selector"):
        return step.model_copy(
            update={
                "selector": best_candidate["suggested_selector"],
                "description": f"Autonomous Execution Agent resolved '{best_candidate.get('text') or best_candidate.get('name') or best_candidate.get('id')}' ({best_candidate.get('container_type')})",
            }
        )

    return None


def _provider_http_error_message(response: httpx.Response, settings: AIProviderSettings) -> str:
    detail = response.text.strip()
    try:
        error_json = response.json()
        if isinstance(error_json, dict):
            detail = json.dumps(error_json)[:400]
    except ValueError:
        detail = detail[:400]
    return (
        f"AI provider request failed ({response.status_code}) for {settings.provider}:{settings.model}: "
        f"{detail}. {_provider_connection_help(settings)}"
    )


async def test_ai_provider_connection(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    endpoint: str | None = None,
) -> dict[str, str | int]:
    provider_settings = _provider_settings_for_connection(provider, model, api_key, endpoint)
    if provider_settings.provider != "local" and not provider_settings.api_key:
        raise AIServiceError(f"{provider_settings.provider} API key is not configured.")

    payload = _build_provider_payload(
        provider_settings,
        "Reply with a single JSON object containing the key 'status' with the value 'ok'.",
        system_content="You are a connectivity probe. Return only the requested JSON object.",
    )
    payload["max_tokens"] = 32
    headers = _build_provider_headers(provider_settings)
    endpoint_url = f"{provider_settings.base_url}/chat/completions"
    started_at = time.perf_counter()
    async with httpx.AsyncClient(timeout=provider_settings.timeout_seconds) as client:
        response = await _post_chat_completion(client, endpoint_url, headers, payload, provider_settings)

    try:
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        message = choices[0].get("message", {}) if isinstance(choices, list) and choices else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    except (ValueError, TypeError, IndexError, KeyError) as error:
        raise AIServiceError(f"AI provider response parsing failed: {error}") from error
    if not isinstance(content, str) or not content.strip():
        raise AIServiceError(f"AI provider ({provider_settings.provider}) returned empty content.")

    return {
        "provider": provider_settings.provider,
        "model": provider_settings.model,
        "response": content.strip()[:200],
        "latency_ms": round((time.perf_counter() - started_at) * 1000),
    }


async def _request_provider_generation(settings: AIProviderSettings, prompt: str) -> AIGeneratedTestCaseSet:
    payload = _build_provider_payload(
        settings,
        prompt,
        system_content=(
            "You are the AI Test Case Generator Agent. Use the supplied AI planner output, observed application context, "
            "and requirements to generate distinct, executable Playwright-oriented QA cases. Return only the requested JSON."
        ),
    )
    headers = _build_provider_headers(settings)
    endpoint = f"{settings.base_url}/chat/completions"
    started_at = time.perf_counter()
    log_event(logger, "ai_generator_request_started", provider=settings.provider, model=settings.model, prompt_length=len(prompt))
    async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
        response = await _post_chat_completion(client, endpoint, headers, payload, settings)

    data = response.json()
    usage = data.get("usage") if isinstance(data, dict) else {}
    log_event(
        logger,
        "ai_generator_response_received",
        provider=settings.provider,
        model=settings.model,
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
        completion_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
        total_tokens=usage.get("total_tokens") if isinstance(usage, dict) else None,
    )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIServiceError(f"AI provider ({settings.provider}) returned no response choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise AIServiceError(f"AI provider ({settings.provider}) returned empty content.")

    try:
        payload_text = _extract_json_payload(content)
        parsed = json.loads(payload_text)
        raw_cases = parsed.get("test_cases") or parsed.get("cases") or parsed.get("scenarios") or []
        if isinstance(parsed, list):
            raw_cases = parsed
            summary = f"Synthesized {len(raw_cases)} test scenarios based on LLM comprehension."
        else:
            summary = str(parsed.get("summary") or f"Synthesized {len(raw_cases)} test scenarios based on LLM comprehension.")

        formatted_cases: list[AIGeneratedTestCase] = []
        for idx, item in enumerate(raw_cases, start=1):
            if isinstance(item, dict):
                raw_title = str(item.get("title") or item.get("name") or f"Scenario {idx}")
                category_val = str(item.get("category") or "positive").strip().lower()
                priority_val = str(item.get("priority") or "medium").strip().lower()
                raw_td = item.get("test_data")
                parsed_td = None
                if isinstance(raw_td, dict):
                    parsed_td = {str(k): str(v) for k, v in raw_td.items() if not str(k).startswith("_")}
                elif isinstance(raw_td, str) and raw_td.strip():
                    try:
                        p_loaded = json.loads(raw_td)
                        if isinstance(p_loaded, dict):
                            parsed_td = {str(k): str(v) for k, v in p_loaded.items() if not str(k).startswith("_")}
                    except Exception:
                        pass
                raw_steps = str(item.get("steps") if isinstance(item.get("steps"), str) else "\n".join(str(s) for s in item.get("steps", [])))[:12000]
                raw_expected = str(item.get("expected_result") or item.get("expected") or "Verified successfully")[:4000]
                param_steps, param_expected, auto_td = auto_parameterize_case_steps(
                    raw_steps,
                    expected_result=raw_expected,
                    category=category_val,
                    existing_test_data=parsed_td,
                )
                formatted_cases.append(
                    AIGeneratedTestCase(
                        title=_normalize_title(idx, raw_title),
                        description=str(item.get("description") or "").strip()[:4000],
                        preconditions=str(item.get("preconditions") or item.get("precondition") or "").strip()[:4000],
                        steps=param_steps,
                        expected_result=param_expected,
                        priority=priority_val[:20],
                        category=category_val[:40],
                        tags=[str(t).strip() for t in (item.get("tags") or []) if str(t).strip()],
                        test_data=auto_td,
                        status="draft",
                    )
                )

        if not formatted_cases:
            raise AIServiceError(f"AI provider returned a response without valid test cases: {content[:300]}")

        return AIGeneratedTestCaseSet(
            summary=summary,
            test_cases=formatted_cases,
            generation_mode=GENERATION_MODE_PROVIDER,
            generation_note=f"Synthesized by LLM provider {settings.provider}:{settings.model}",
            generation_provider=f"{settings.provider}:{settings.model}",
        )
    except AIServiceError:
        raise
    except Exception as error:
        raise AIServiceError(f"AI response parsing failed: {error}. Raw content: {content[:200]}") from error


DEFAULT_PARAMETER_VALUES: dict[str, dict[str, str]] = {
    "login_email": {
        "valid": "user@example.test",
        "invalid": "invalid.user@example.invalid",
        "boundary": "",
        "edge": "test+user.qa@example.test",
    },
    "login_password": {
        "valid": "ValidPassword123!",
        "invalid": "wrong-password",
        "boundary": "P",
        "edge": "Pass'--\"<script>123",
    },
    "email": {
        "valid": "qa.user@example.test",
        "invalid": "invalid-email-format",
        "boundary": "",
        "edge": "user+test.qa@domain.co.uk",
    },
    "first_name": {
        "valid": "Jane",
        "invalid": "123456",
        "boundary": "J",
        "edge": "Mary-Jane's",
    },
    "last_name": {
        "valid": "Smith",
        "invalid": "!@#$%",
        "boundary": "S",
        "edge": "van der Rohe",
    },
    "full_name": {
        "valid": "Jane Smith",
        "invalid": "---",
        "boundary": "J",
        "edge": "Mary-Jane O'Connor",
    },
    "phone": {
        "valid": "555-0199",
        "invalid": "not-a-phone",
        "boundary": "0",
        "edge": "+1 (555) 019-9999 x101",
    },
    "city": {
        "valid": "Austin",
        "invalid": "99999",
        "boundary": "A",
        "edge": "St. Louis-East",
    },
    "state": {
        "valid": "TX",
        "invalid": "ZZ",
        "boundary": "T",
        "edge": "TX / CA",
    },
    "zip_code": {
        "valid": "73301",
        "invalid": "00000000",
        "boundary": "0",
        "edge": "90210-1234",
    },
    "address": {
        "valid": "123 Main Street",
        "invalid": "---",
        "boundary": "1",
        "edge": "Apt 4B, 100 1/2 Maple Ave #300",
    },
    "street": {
        "valid": "123 Main Street",
        "invalid": "---",
        "boundary": "1",
        "edge": "Apt 4B, 100 1/2 Maple Ave #300",
    },
    "barcode": {
        "valid": "1234567890",
        "invalid": "INVALID-BARCODE",
        "boundary": "0",
        "edge": "9999999999999",
    },
    "order_id": {
        "valid": "ORD-1001",
        "invalid": "ORD-0000-NONEXISTENT",
        "boundary": "0",
        "edge": "ORD-#9999-XYZ",
    },
    "search_term": {
        "valid": "Standard Search Query",
        "invalid": "xyz999nonexistent",
        "boundary": "%",
        "edge": "test* ' OR 1=1 --",
    },
    "status": {
        "valid": "Active",
        "invalid": "UnknownStatus",
        "boundary": "Pending",
        "edge": "Archived",
    },
    "date": {
        "valid": "2026-09-15",
        "invalid": "2026-99-99",
        "boundary": "1970-01-01",
        "edge": "2099-12-31",
    },
    "amount": {
        "valid": "49.99",
        "invalid": "-10.00",
        "boundary": "0.00",
        "edge": "999999.99",
    },
    "quantity": {
        "valid": "2",
        "invalid": "-1",
        "boundary": "0",
        "edge": "999",
    },
}


def resolve_parameter_name_for_field(field_name: str, sample_val: str, category: str = "positive") -> str:
    f_clean = (field_name or "").lower().strip()
    v_clean = (sample_val or "").lower().strip()
    is_neg = category in {"negative", "security"} or "invalid" in f_clean or "invalid" in v_clean or "wrong" in v_clean or "error" in v_clean

    if "password" in f_clean or "passwd" in f_clean or "passcode" in f_clean or "pwd" in f_clean:
        return "invalid_password" if is_neg else "login_password"
    if "login_email" in f_clean or "login_user" in f_clean or (("email" in f_clean or "@" in v_clean) and ("login" in f_clean or "user" in f_clean or "auth" in f_clean)):
        return "invalid_email" if is_neg else "login_email"
    if "email" in f_clean or "@" in v_clean:
        return "invalid_email" if is_neg else "email"
    if "first" in f_clean and "name" in f_clean:
        return "first_name"
    if "last" in f_clean and "name" in f_clean:
        return "last_name"
    if "full" in f_clean and "name" in f_clean:
        return "full_name"
    if "phone" in f_clean or "mobile" in f_clean or "tel" in f_clean:
        return "phone"
    if "zip" in f_clean or "postal" in f_clean:
        return "zip_code"
    if "city" in f_clean or "town" in f_clean:
        return "city"
    if "state" in f_clean or "province" in f_clean:
        return "state"
    if "street" in f_clean or "address" in f_clean:
        return "address"
    if "barcode" in f_clean or "sku" in f_clean or "upc" in f_clean:
        return "barcode"
    if "order" in f_clean:
        return "order_id"
    if "search" in f_clean or "query" in f_clean or "filter" in f_clean or "keyword" in f_clean:
        return "search_term"
    if "status" in f_clean:
        return "status"
    if "date" in f_clean:
        return "date"
    if "amount" in f_clean or "price" in f_clean or "cost" in f_clean:
        return "amount"
    if "quantity" in f_clean or "qty" in f_clean or "count" in f_clean:
        return "quantity"

    slug = re.sub(r"[^a-z0-9_]+", "_", f_clean).strip("_")
    if not slug or slug in {"field", "input", "the", "box", "value", "text", "filter", "area"}:
        slug = "search_term" if "search" in f_clean else "param_value"
    return slug


def synthesize_parameter_value(param_name: str, category: str = "positive") -> str:
    norm_key = re.sub(r"[^a-z0-9_]+", "_", param_name.lower()).strip("_")
    cat = (category or "positive").lower()
    scenario_type = (
        "invalid" if cat in {"negative", "security"} or "invalid" in norm_key or "wrong" in norm_key
        else "boundary" if cat == "boundary"
        else "edge" if cat in {"edge", "exploratory"}
        else "valid"
    )
    for def_key, def_map in DEFAULT_PARAMETER_VALUES.items():
        if def_key in norm_key or norm_key in def_key:
            return def_map.get(scenario_type, def_map.get("valid", "Sample Value"))

    if scenario_type == "invalid":
        return f"invalid_{norm_key}"
    elif scenario_type == "boundary":
        return ""
    elif scenario_type == "edge":
        return f"{norm_key}_edge_resilience"
    return f"sample_{norm_key}"


def auto_parameterize_case_steps(
    steps: str,
    expected_result: str = "",
    category: str = "positive",
    existing_test_data: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, str]]:
    result_data: dict[str, str] = {}
    if isinstance(existing_test_data, dict):
        result_data.update({
            str(k): str(v)
            for k, v in existing_test_data.items()
            if not str(k).startswith("_") and str(v).strip() and not str(v).strip().startswith("{{") and not str(v).strip().startswith("${")
        })

    lines = (steps or "").splitlines()
    replacements: list[tuple[str, str]] = []

    # First pass: identify all typed, entered, input, and searched sample literals
    for line in lines:
        # 1. Pattern: Enter/Type/Fill 'val' into/in/for [the] 'field' (or field)
        p1 = list(re.finditer(
            r'\b(?:enter|type|input|fill|set|populate)\s+["\']([^"\']+)["\']\s+(?:into|in|for)\s+(?:the\s+)?(?:["\']([^"\']+)["\']|([a-zA-Z0-9_\s\-]+))',
            line,
            re.IGNORECASE,
        ))
        for match in p1:
            val = match.group(1).strip()
            fld_raw = (match.group(2) or match.group(3) or "").strip()
            fld = re.sub(r"\b(field|input|filter|box|area|text|locator)\b", "", fld_raw, flags=re.IGNORECASE).strip()
            if val.startswith("{{") and val.endswith("}}"):
                tok = val[2:-2].strip()
                if tok and (tok not in result_data or str(result_data[tok]).startswith("{{")):
                    result_data[tok] = synthesize_parameter_value(tok, category)
            else:
                pname = resolve_parameter_name_for_field(fld or "field", val, category)
                result_data[pname] = val
                replacements.append((val, pname))

        # 2. Pattern: Enter/Type/Fill [the] 'field' with/as/to 'val'
        p2 = list(re.finditer(
            r'\b(?:enter|type|input|fill|set|populate)\s+(?:the\s+)?(?:["\']([^"\']+)["\']|([a-zA-Z0-9_\s\-]+?))\s+(?:with|as|to)\s+["\']([^"\']+)["\']',
            line,
            re.IGNORECASE,
        ))
        for match in p2:
            fld_raw = (match.group(1) or match.group(2) or "").strip()
            fld = re.sub(r"\b(field|input|filter|box|area|text|locator)\b", "", fld_raw, flags=re.IGNORECASE).strip()
            val = match.group(3).strip()
            if val.startswith("{{") and val.endswith("}}"):
                tok = val[2:-2].strip()
                if tok and (tok not in result_data or str(result_data[tok]).startswith("{{")):
                    result_data[tok] = synthesize_parameter_value(tok, category)
            else:
                pname = resolve_parameter_name_for_field(fld or "field", val, category)
                result_data[pname] = val
                replacements.append((val, pname))

        # 3. Pattern: Search for 'val' in [the] 'field'
        p3 = list(re.finditer(
            r'\b(?:search\s+for|lookup|query)\s+["\']([^"\']+)["\'](?:\s+(?:in|into|using|under)\s+(?:the\s+)?(?:["\']([^"\']+)["\']|([a-zA-Z0-9_\s\-]+)))?',
            line,
            re.IGNORECASE,
        ))
        for match in p3:
            val = match.group(1).strip()
            fld_raw = (match.group(2) or match.group(3) or "search_term").strip()
            fld = re.sub(r"\b(field|input|filter|box|area|text|locator)\b", "", fld_raw, flags=re.IGNORECASE).strip()
            if val.startswith("{{") and val.endswith("}}"):
                tok = val[2:-2].strip()
                if tok and (tok not in result_data or str(result_data[tok]).startswith("{{")):
                    result_data[tok] = synthesize_parameter_value(tok, category)
            elif val.lower() not in {"button", "link", "menu", "page", "tab"}:
                pname = resolve_parameter_name_for_field(fld or "search_term", val, category)
                result_data[pname] = val
                replacements.append((val, pname))

    # Second pass: apply all replacements to steps and expected result
    updated_lines: list[str] = []
    for line in lines:
        mod_line = line
        for val, pname in replacements:
            if not val or not pname:
                continue
            mod_line = mod_line.replace(f"'{val}'", f"'{{{{{pname}}}}}'").replace(f'"{val}"', f'"{{{{{pname}}}}}"')
        updated_lines.append(mod_line)

    updated_expected = expected_result or ""
    for val, pname in replacements:
        if not val or not pname:
            continue
        updated_expected = updated_expected.replace(f"'{val}'", f"'{{{{{pname}}}}}'").replace(f'"{val}"', f'"{{{{{pname}}}}}"')
        if val in updated_expected and f"{{{{{pname}}}}}" not in updated_expected:
            updated_expected = updated_expected.replace(val, f"{{{{{pname}}}}}")

    parameterized_steps = "\n".join(updated_lines)

    # Scan and populate any missing tokens in test_data
    all_tokens = re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", parameterized_steps)
    for tok in all_tokens:
        tok_clean = tok.strip()
        if tok_clean and (tok_clean not in result_data or not str(result_data[tok_clean]).strip() or str(result_data[tok_clean]).startswith("{{")):
            result_data[tok_clean] = synthesize_parameter_value(tok_clean, category)

    return parameterized_steps, updated_expected, result_data
    all_tokens = re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", parameterized_steps)
    for tok in all_tokens:
        tok_clean = tok.strip()
        if tok_clean and (tok_clean not in result_data or not str(result_data[tok_clean]).strip()):
            result_data[tok_clean] = synthesize_parameter_value(tok_clean, category)

    return parameterized_steps, updated_expected, result_data
    all_tokens = re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", parameterized_steps)
    for tok in all_tokens:
        tok_clean = tok.strip()
        if tok_clean and (tok_clean not in result_data or not str(result_data[tok_clean]).strip()):
            result_data[tok_clean] = synthesize_parameter_value(tok_clean, category)

    return parameterized_steps, updated_expected, result_data


def _normalize_steps_text(steps: str, min_steps: int, max_steps: int, target_url: str) -> str:
    parsed_lines: list[str] = []
    for raw_line in (steps or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\).:\-\s]+", "", line).strip()
        line = re.sub(r"\s{2,}", " ", line).strip(" ,")
        if line:
            parsed_lines.append(line)

    if not parsed_lines:
        parsed_lines = [f"Navigate to {target_url}", "Verify application state is displayed"]

    if max_steps and len(parsed_lines) > max_steps:
        parsed_lines = parsed_lines[:max_steps]

    return "\n".join(f"{index}. {line}" for index, line in enumerate(parsed_lines, start=1))


def _normalize_title(index: int, title: str) -> str:
    raw = (title or "").strip() or f"Generated Case {index}"
    suffix = re.sub(r"^TC\s*\d+\s*[-:]\s*", "", raw, flags=re.IGNORECASE).strip() or f"Generated Case {index}"
    return f"TC{index:02d} - {suffix}"


def _format_planner_context_for_prompt(plan: dict[str, Any]) -> str:
    parts: list[str] = []
    if plan.get("summary"):
        parts.append(f"Plan Summary: {plan['summary']}")
    if plan.get("authentication_plan"):
        parts.append(f"Authentication & Login Flow:\n{plan['authentication_plan']}")
    if plan.get("entry_points"):
        parts.append(f"Entry Points: {', '.join(plan['entry_points'])}")
    if plan.get("navigation_paths"):
        parts.append("Navigation Paths:\n" + "\n".join(f"- {p}" for p in plan["navigation_paths"]))
    if plan.get("coverage_matrix"):
        parts.append("Planned Module Scenarios:")
        for entry in plan["coverage_matrix"]:
            if isinstance(entry, dict):
                area = entry.get("area", "")
                scenarios = entry.get("scenarios", [])
                scen_text = "; ".join(scenarios) if scenarios else "All standard CRUD, validation, and workflow scenarios"
                parts.append(f"- Module '{area}': {scen_text}")
    if plan.get("risk_areas"):
        parts.append(f"Key Risk Areas: {', '.join(plan['risk_areas'])}")
    if plan.get("exploratory_charters"):
        parts.append("Exploratory Charters:")
        for charter in plan["exploratory_charters"]:
            if isinstance(charter, dict):
                obs = charter.get("observation", "")
                hyp = charter.get("hypothesis", "")
                parts.append(f"- Observation: {obs} | Hypothesis: {hyp}")
    raw_json = json.dumps(plan, ensure_ascii=True, indent=2)[:12_000]
    if parts:
        formatted_parts = "\n\n".join(parts)
        return f"{formatted_parts}\n\nStructured Plan JSON:\n{raw_json}"
    return raw_json


def _source_anchor_terms(*sources: str | None, limit: int = 300) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for raw_term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", source or ""):
            term = raw_term.casefold()
            if term in SOURCE_ANCHOR_STOP_WORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= limit:
                return terms
    return terms


def _case_matches_source(case: AIGeneratedTestCase, source_anchors: list[str]) -> bool:
    if not source_anchors:
        return True
    case_text = " ".join((case.title, case.description, case.preconditions, case.steps, case.expected_result)).casefold()
    return any(re.search(rf"\b{re.escape(anchor)}\b", case_text) for anchor in source_anchors)


def _generated_case_identity(case: AIGeneratedTestCase) -> str:
    return "|".join(
        re.sub(r"\s+", " ", value).strip().casefold()
        for value in (case.title, case.steps, case.expected_result)
    )


def _quality_gate_generated_cases(
    generated: AIGeneratedTestCaseSet,
    max_cases: int | None,
    min_steps_per_case: int,
    max_steps_per_case: int,
    target_url: str,
    source_anchors: list[str] | None = None,
) -> AIGeneratedTestCaseSet:
    cleaned_cases: list[AIGeneratedTestCase] = []
    relevant_cases = [case for case in generated.test_cases if _case_matches_source(case, source_anchors or [])]
    for index, case in enumerate(relevant_cases[:max_cases], start=1):
        expected_val = (case.expected_result or "").strip()
        if not expected_val:
            expected_val = f"Verify {case.title} completes and verifies expected application state successfully."
        cat = (case.category or "positive").strip().lower()
        if (
            cat == "exploratory"
            or any(w in case.title.lower() or w in case.steps.lower() or w in (case.description or "").lower() for w in [
                "exploratory", "charter", "hypothesis", "unscripted", "edge behavior",
                "rapid navigation", "session state", "boundary combination", "wildcard",
                "state transition", "workflow resilience", "unexpected input"
            ])
        ):
            cat = "exploratory"
        param_steps, param_expected, auto_td = auto_parameterize_case_steps(
            case.steps,
            expected_result=expected_val,
            category=cat,
            existing_test_data=case.test_data,
        )
        cleaned_cases.append(
            AIGeneratedTestCase(
                title=_normalize_title(index, case.title),
                description=(case.description or "").strip()[:4000],
                preconditions=(case.preconditions or "").strip()[:4000],
                steps=_normalize_steps_text(param_steps, min_steps_per_case, max_steps_per_case, target_url)[:12000],
                expected_result=param_expected[:4000],
                priority=(case.priority or "medium").strip()[:20],
                category=cat[:40],
                tags=[str(tag).strip()[:80] for tag in (case.tags or [])[:20] if str(tag).strip()],
                test_data=auto_td,
                status="draft",
            )
        )
    return AIGeneratedTestCaseSet(
        summary=generated.summary,
        test_cases=cleaned_cases,
        generation_mode=generated.generation_mode,
        generation_note=(generated.generation_note or "")[:2000],
        generation_provider=(generated.generation_provider or "")[:120],
        planner_used=generated.planner_used,
        planner_provider=generated.planner_provider[:120],
        planner_model=generated.planner_model[:120],
        planner_case_target=generated.planner_case_target,
        generator_call_count=generated.generator_call_count,
    )


async def generate_ai_test_cases(
    application_name: str,
    platform: str,
    target: str,
    user_prompt: str,
    max_cases: int | None,
    include_authenticated_snapshot: bool,
    login_email_selector: str | None,
    login_password_selector: str | None,
    login_submit_selector: str | None,
    min_steps_per_case: int,
    max_steps_per_case: int,
    include_negative_scenarios: bool,
    include_accessibility_checks: bool,
    include_api_validations: bool,
    module_focus: str,
    input_format: str = "text",
    include_performance_scenarios: bool = False,
    performance_budget: str = "",
    document_context: str | None = None,
    reference_cases: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    planner_plan: dict[str, Any] | None = None,
    planner_provider: str | None = None,
    planner_model: str | None = None,
    context_snapshot: dict[str, Any] | None = None,
    include_positive_scenarios: bool = True,
    include_boundary_scenarios: bool = True,
    include_edge_cases: bool = True,
    include_security_scenarios: bool = True,
    include_validation_rules: bool = True,
    observed_target_context: TargetUIContext | None = None,
    login_email: str | None = None,
    login_password: str | None = None,
) -> AIGeneratedTestCaseSet:
    from app.services.agent_definitions import AgentDefinitionError, build_agent_guidance_block

    # Auto-extract credentials from prompt and document context if not explicitly passed
    extracted_email, extracted_password = _extract_credentials_from_text(user_prompt, document_context)
    resolved_login_email = (login_email or "").strip() or extracted_email
    resolved_login_password = (login_password or "").strip() or extracted_password
    effective_authenticated = include_authenticated_snapshot or bool(resolved_login_email and resolved_login_password)

    normalized_reference_cases = [item.strip()[:300] for item in (reference_cases or []) if item and item.strip()]
    try:
        generator_guidance = build_agent_guidance_block(["generator"])
    except AgentDefinitionError:
        generator_guidance = ""
    target_context = observed_target_context or await _capture_target_ui_context(target)
    log_event(
        logger,
        "ai_context_analyzed",
        application_name=application_name,
        platform=platform,
        target=target,
        context_signal_score=_context_signal_score(target_context),
        reference_case_count=len(normalized_reference_cases),
    )
    if effective_authenticated and platform.strip().casefold() == "web" and not target_context.authenticated_snapshot:
        authenticated_context = await _capture_authenticated_target_ui_context(
            target,
            login_email_selector=login_email_selector,
            login_password_selector=login_password_selector,
            login_submit_selector=login_submit_selector,
            login_email=resolved_login_email,
            login_password=resolved_login_password,
        )
        target_context = _merge_target_context(target_context, authenticated_context)
    target_context_text = _format_target_context_for_prompt(target_context, normalized_reference_cases)
    bounded_document_context = (document_context or "").strip()[:60_000]
    exploratory_context = "\n".join(
        [
            *(target_context.exploratory_observations or []),
            *(target_context.exploratory_hypotheses or []),
            *list((context_snapshot or {}).get("exploratory_observations") or []),
            *list((context_snapshot or {}).get("exploratory_hypotheses") or []),
        ]
    )
    scope_anchor_text = " ".join(
        [
            "API endpoint request response schema" if include_api_validations else "",
            "performance latency throughput concurrency load" if include_performance_scenarios else "",
        ]
    )
    discovered_elements_text = " ".join([
        target_context.title,
        *target_context.headings,
        *target_context.buttons,
        *target_context.links,
        *target_context.observed_routes,
    ])
    source_anchors = _source_anchor_terms(
        scope_anchor_text,
        user_prompt,
        bounded_document_context,
        module_focus,
        exploratory_context,
        discovered_elements_text,
    )
    log_event(
        logger,
        "ai_prompt_generated",
        prompt_length=len(target_context_text) + len(bounded_document_context),
        authenticated_snapshot=include_authenticated_snapshot,
        document_context_chars=len(bounded_document_context),
    )

    if planner_plan is None:
        planner_result = await generate_ai_test_plan(
            application_name=application_name,
            platform=platform,
            target=target,
            user_prompt=user_prompt,
            max_cases=max_cases,
            module_focus=module_focus,
            include_negative_scenarios=include_negative_scenarios,
            include_accessibility_checks=include_accessibility_checks,
            include_api_validations=include_api_validations,
            include_performance_scenarios=include_performance_scenarios,
            performance_budget=performance_budget,
            input_format=input_format,
            include_positive_scenarios=include_positive_scenarios,
            include_boundary_scenarios=include_boundary_scenarios,
            include_edge_cases=include_edge_cases,
            include_security_scenarios=include_security_scenarios,
            include_validation_rules=include_validation_rules,
            document_context=bounded_document_context,
            reference_cases=normalized_reference_cases,
            observed_target_context=target_context_text,
            context_snapshot=context_snapshot,
            provider=provider,
            model=model,
        )
        planner_plan = planner_result["plan"]
        planner_provider = str(planner_result.get("provider") or provider or "")
        planner_model = str(planner_result.get("model") or model or "")

    try:
        planned_case_target = int(planner_plan.get("recommended_case_count") or 0)
    except (TypeError, ValueError):
        planned_case_target = 0
    target_case_count = max_cases if max_cases is not None else max(
        MIN_DYNAMIC_AI_CASE_TARGET,
        min(MAX_DYNAMIC_AI_CASE_TARGET, planned_case_target or DEFAULT_DYNAMIC_AI_CASE_TARGET),
    )
    target_case_count = max(1, min(50, target_case_count))
    planner_context_text = _format_planner_context_for_prompt(planner_plan)
    provider_settings = _load_provider_settings(
        override_provider=planner_provider or provider,
        override_model=planner_model or model,
    )
    if not provider_settings:
        raise AIServiceError(
            "No AI provider is configured. Please select one explicit provider (GitHub Copilot, OpenAI, Azure OpenAI, Anthropic, Gemini, or local) "
            "with a valid API key in the AI & Settings tab or in backend/.env."
        )

    generated_cases: list[AIGeneratedTestCase] = []
    seen_case_keys: set[str] = set()
    attempted_provider_errors: list[str] = []
    generator_call_count = 0
    stalled_batches = 0
    effective_settings: AIProviderSettings | None = None
    while len(generated_cases) < target_case_count and generator_call_count < MAX_GENERATOR_CALLS:
        batch_target = min(GENERATOR_BATCH_SIZE, target_case_count - len(generated_cases))
        batch_prompt = _build_prompt(
            application_name=application_name,
            platform=platform,
            target=target,
            user_prompt=user_prompt,
            max_cases=batch_target,
            min_steps_per_case=min_steps_per_case,
            max_steps_per_case=max_steps_per_case,
            include_negative_scenarios=include_negative_scenarios,
            include_accessibility_checks=include_accessibility_checks,
            include_api_validations=include_api_validations,
            include_performance_scenarios=include_performance_scenarios,
            performance_budget=performance_budget,
            input_format=input_format,
            module_focus=module_focus,
            target_context=target_context_text,
            document_context=bounded_document_context,
            planner_context=planner_context_text,
            generator_guidance=generator_guidance,
            target_case_count=batch_target,
            excluded_titles=[case.title for case in generated_cases],
        )
        batch_added = 0
        batch_succeeded = False
        for settings in provider_settings:
            if generator_call_count >= MAX_GENERATOR_CALLS:
                break
            generator_call_count += 1
            try:
                generated_batch = await _request_provider_generation(settings, batch_prompt)
                quality_gated_batch = _quality_gate_generated_cases(
                    generated_batch,
                    max_cases=batch_target,
                    min_steps_per_case=min_steps_per_case,
                    max_steps_per_case=max_steps_per_case,
                    target_url=target.strip() or "https://example.com/",
                    source_anchors=source_anchors,
                )
                for case in quality_gated_batch.test_cases:
                    identity = _generated_case_identity(case)
                    if identity in seen_case_keys:
                        continue
                    seen_case_keys.add(identity)
                    generated_cases.append(case)
                    batch_added += 1
                    if len(generated_cases) >= target_case_count:
                        break
                effective_settings = settings
                batch_succeeded = True
                break
            except AIServiceError as error:
                attempted_provider_errors.append(f"{settings.provider}:{settings.model} -> {error}")
                await asyncio.sleep(0.5)

        if not batch_succeeded:
            error_summary = "; ".join(attempted_provider_errors) or "All AI provider attempts failed."
            raise AIServiceError(
                f"AI Test Case Generator failed: {error_summary}. Verify provider settings and network connectivity."
            )
        if batch_added:
            stalled_batches = 0
            if len(generated_cases) < target_case_count:
                await asyncio.sleep(0.5)
        else:
            stalled_batches += 1
            if stalled_batches >= 2:
                break

    if not generated_cases or effective_settings is None:
        raise AIServiceError("AI Test Case Generator returned no distinct test cases.")

    assembled = AIGeneratedTestCaseSet(
        summary=str(planner_plan.get("summary") or "AI planner and generator completed a risk-based test design.")[:4000],
        test_cases=generated_cases,
        generation_mode=GENERATION_MODE_PROVIDER,
        generation_provider=f"{effective_settings.provider}:{effective_settings.model}",
    )
    quality_gated = _quality_gate_generated_cases(
        assembled,
        max_cases=target_case_count,
        min_steps_per_case=min_steps_per_case,
        max_steps_per_case=max_steps_per_case,
        target_url=target.strip() or "https://example.com/",
        source_anchors=source_anchors,
    )
    completion_note = (
        f"AI Planner selected a target of {target_case_count} cases; AI Generator produced "
        f"{len(quality_gated.test_cases)} distinct cases across {generator_call_count} provider call"
        f"{'s' if generator_call_count != 1 else ''}."
    )
    if len(quality_gated.test_cases) < target_case_count:
        completion_note += " The provider stopped returning new distinct cases before the target was reached."
    log_event(
        logger,
        "ai_generation_validated",
        provider=effective_settings.provider,
        model=effective_settings.model,
        generated_case_count=len(quality_gated.test_cases),
        target_case_count=target_case_count,
        generator_call_count=generator_call_count,
        validation_status="passed",
    )
    return AIGeneratedTestCaseSet(
        summary=quality_gated.summary,
        test_cases=quality_gated.test_cases,
        generation_mode=GENERATION_MODE_PROVIDER,
        generation_note=completion_note,
        generation_provider=f"{effective_settings.provider}:{effective_settings.model}",
        planner_used=True,
        planner_provider=planner_provider or effective_settings.provider,
        planner_model=planner_model or effective_settings.model,
        planner_case_target=target_case_count,
        generator_call_count=generator_call_count,
    )
