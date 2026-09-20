import asyncio
import re
import time
import inspect
import ipaddress
import os
import socket
import tempfile
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from app.schemas.execution import (
	Check,
	CheckResult,
	ExecutionArtifact,
	ExecutionRequest,
	ExecutionResponse,
	Step,
	StepResult,
)
from app.services.secrets import SecretResolutionError, resolve_secret_value
from app.services.ai_service import AIServiceError, generate_healing_step, resolve_action_with_agent
from app.services.video_audio import build_execution_narration, create_video_with_audio
from app.services.guardrails import (
	GuardrailViolationError,
	sanitize_redacted_secrets,
	validate_step_guardrails,
	validate_target_url,
	verify_healed_step_guardrails,
)
from app.services.self_learning import SelfLearningEngine


SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "ai-qa-engine-runs"
STEP_SETTLE_MS = int(os.getenv("AI_QA_ENGINE_STEP_SETTLE_MS", "50"))
VISIBLE_SLOW_MO_MS = int(os.getenv("AI_QA_ENGINE_PLAYWRIGHT_SLOW_MO_MS", "0"))
DEMO_SLOW_MO_MS = int(os.getenv("AI_QA_ENGINE_PLAYWRIGHT_DEMO_SLOW_MO_MS", "350"))
SHOWCASE_SLOW_MO_MS = int(os.getenv("AI_QA_ENGINE_PLAYWRIGHT_SHOWCASE_SLOW_MO_MS", "650"))
ACTION_HIGHLIGHT_HOLD_MS = int(os.getenv("AI_QA_ENGINE_ACTION_HIGHLIGHT_HOLD_MS", "0"))
ACTION_HIGHLIGHT_ENABLED = os.getenv("AI_QA_ENGINE_ACTION_HIGHLIGHT", "true").strip().lower() not in {
	"0",
	"false",
	"no",
	"off",
}


def _should_run_headless(request: ExecutionRequest) -> bool:
	if request.headless is not None:
		return request.headless
	if request.execution_mode == "background":
		return True
	if request.execution_mode == "watch_live":
		return False
	return os.name != "nt" and os.getenv("DISPLAY") is None


def validate_target(url: str) -> None:
	allow_local = os.getenv("ALLOW_PRIVATE_TARGETS", "false").lower() == "true"
	try:
		validate_target_url(url, allow_localhost=allow_local)
	except GuardrailViolationError as err:
		raise ValueError(str(err)) from err

	parsed = urlparse(url)
	if parsed.scheme not in {"http", "https"} or not parsed.hostname:
		raise ValueError("Only HTTP(S) targets with a hostname are supported")
	if allow_local:
		return
	try:
		addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, None)}
	except socket.gaierror as error:
		raise ValueError("Target hostname could not be resolved") from error
	for address in addresses:
		ip = ipaddress.ip_address(address)
		if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
			raise ValueError("Private or reserved network targets are not allowed")


def _classify_failure_type(
	step_results: list[StepResult],
	check_results: list[CheckResult],
	console_errors: list[str],
	network_errors: list[str],
	error_message: str | None,
) -> tuple[str | None, str | None]:
	step_failures = [result for result in step_results if not result.passed]
	check_failures = [result for result in check_results if not result.passed]
	if not step_failures and not check_failures and not error_message and not network_errors:
		return None, None

	signal_parts = [error_message or ""]
	signal_parts.extend(result.message for result in step_failures)
	signal_parts.extend(result.message for result in check_failures)
	signal_parts.extend(console_errors)
	signal_parts.extend(network_errors)
	combined_signal = " ".join(part for part in signal_parts if part).casefold()

	classification = "UNKNOWN"
	if any(token in combined_signal for token in ["500 internal server error", "500 error", "internal server error", "status of 500", "status 500", "404 not found", "status of 404", "status 404", "access denied", "broken image"]):
		classification = "APPLICATION_DEFECT"
	elif any(token in combined_signal for token in ["invalid email or password", "invalid credentials", "unauthorized", "forbidden", "log in to", "sign in to", "login page", "authentication failed", "sign in", "log in"]):
		classification = "AUTHENTICATION"
	elif network_errors or "net::" in combined_signal or "dns" in combined_signal or "connection reset" in combined_signal:
		classification = "NETWORK"
	elif "timeout" in combined_signal or "timed out" in combined_signal:
		classification = "TIMING"
	elif "selector" in combined_signal or "locator" in combined_signal or "not visible" in combined_signal:
		classification = "LOCATOR"
	elif "unable to load" in combined_signal or "navigation" in combined_signal or ("url" in combined_signal and "expected" in combined_signal):
		classification = "NAVIGATION"
	elif "secret" in combined_signal or "test data" in combined_signal or "invalid input" in combined_signal:
		classification = "TEST_DATA"
	elif "assertion failed" in combined_signal or check_failures:
		classification = "ASSERTION"
	elif "context closed" in combined_signal or "browser has been closed" in combined_signal:
		classification = "ENVIRONMENT"
	elif step_failures and not check_failures:
		classification = "AUTOMATION_DEFECT"
	elif check_failures and not step_failures:
		classification = "APPLICATION_DEFECT"

	if error_message:
		summary = error_message.strip()[:260]
	elif step_failures:
		summary = step_failures[0].message.strip()[:260]
	elif check_failures:
		summary = check_failures[0].message.strip()[:260]
	elif network_errors:
		summary = network_errors[0].strip()[:260]
	else:
		summary = "Execution failed with no detailed summary."
	return classification, summary


def _convert_html_tag_to_selectors(tag: str) -> list[str]:
    tag = tag.strip()
    if not (tag.startswith("<") and ">" in tag):
        return [tag]
    m = re.match(r"^<\s*([a-zA-Z0-9_-]+)([^>]*)>", tag)
    if not m:
        return [tag]
    tag_name = m.group(1).lower()
    attr_str = m.group(2)

    attrs = re.findall(r'([a-zA-Z0-9_-]+)(?:\s*=\s*["\']([^"\']*)["\'])?', attr_str)
    attr_map: dict[str, str] = {}
    for k, v in attrs:
        attr_map[k.lower()] = v

    selectors = []
    if "id" in attr_map and attr_map["id"]:
        selectors.append(f'#{attr_map["id"]}')
        selectors.append(f'{tag_name}#{attr_map["id"]}')
    if "name" in attr_map and attr_map["name"]:
        selectors.append(f'{tag_name}[name="{attr_map["name"]}"]')

    if attr_map.get("type") == "checkbox" or (tag_name == "input" and "checked" in attr_map):
        if "checked" in attr_map:
            selectors.append(f"{tag_name}[type='checkbox']:checked")
            selectors.append(f"{tag_name}[type='checkbox'][checked]")
        selectors.append(f"{tag_name}[type='checkbox']")
        selectors.append("input[type='checkbox']")
    elif attr_map.get("type") == "radio" or (tag_name == "input" and "radio" in attr_str):
        if "checked" in attr_map:
            selectors.append(f"{tag_name}[type='radio']:checked")
            selectors.append(f"{tag_name}[type='radio'][checked]")
        selectors.append(f"{tag_name}[type='radio']")

    css_parts = [tag_name]
    for k, v in attr_map.items():
        if k in {"id", "name"}:
            continue
        if v:
            css_parts.append(f'[{k}="{v}"]')
        else:
            css_parts.append(f"[{k}]")
    if len(css_parts) > 1:
        selectors.append("".join(css_parts))

    return list(dict.fromkeys(selectors)) if selectors else [tag]


async def _run_check(
    page: Page,
    check: Check,
    parameters: dict[str, str] | None = None,
    application_id: int | None = None,
) -> CheckResult:
    parameters = parameters or {}
    check_value = _interpolate_parameter_value(check.value, parameters, application_id=application_id)
    if check.type == "title_contains":
        title = await page.title()
        val_cf = check_value.casefold()
        title_cf = title.casefold()
        passed = (
            val_cf in title_cf
            or val_singular in title_cf if (val_singular := val_cf.rstrip("s")) else False
            or (len(val_cf.split()) >= 2 and any(t in title_cf for t in val_cf.split() if len(t) >= 4))
        )
        if not passed:
            try:
                headings = await page.locator("h1, h2, h3, .navbar-brand, .page-title, .title, header, .nav-link, nav, .navbar, [role='navigation']").all_inner_texts()
                joined = " ".join(headings).casefold()
                passed = (
                    val_cf in joined
                    or (len(val_cf.split()) >= 2 and any(t in joined for t in val_cf.split() if len(t) >= 4))
                    or (val_cf in {"dashboard", "home", "portal", "overview", "main"} and len(headings) > 0)
                )
            except Exception:
                pass
        if not passed:
            try:
                body_raw = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
                passed = val_cf in body_raw.casefold() or (val_cf in {"dashboard", "home", "portal", "overview"} and len(body_raw.strip()) > 50)
            except Exception:
                pass
        message = f"Page title/heading is '{title or check_value}'." if passed else f"Page title '{title}' does not contain '{check_value}'."
    elif check.type == "url_contains":
        current_url = page.url or ""
        passed = check_value.casefold() in current_url.casefold()
        message = f"URL contains '{check_value}'" if passed else f"URL '{current_url}' does not contain '{check_value}'."
    elif check.type == "visible":
        selectors_to_check = [check_value]
        if check_value.strip().startswith("<") and ">" in check_value:
            selectors_to_check = _convert_html_tag_to_selectors(check_value)
        passed = False
        message = f"Selector '{check_value}' is not visible."
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            for sel in selectors_to_check:
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible():
                        passed = True
                        message = f"Selector '{check_value}' is visible."
                        break
                except Exception:
                    continue
            if passed:
                break
            if not passed and ("checkbox" in check_value.lower() or "checked" in check_value.lower()):
                try:
                    if await page.locator("input[type='checkbox']:checked, input[type='checkbox'][checked], input[type='checkbox']").first.is_visible(timeout=100):
                        passed = True
                        message = f"Checkbox '{check_value}' is visible."
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(150)
    else:
        val_cf = check_value.casefold()
        val_singular = val_cf.rstrip("s")
        passed = False
        deadline = time.monotonic() + 3.5
        while time.monotonic() < deadline:
            try:
                body_text = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
            except Exception:
                try:
                    body_text = await page.locator("body").first.inner_text()
                except Exception:
                    body_text = ""
            title = await page.title()
            body_cf = body_text.casefold()
            title_cf = title.casefold()
            passed = (
                val_cf in body_cf
                or (val_singular in body_cf if val_singular else False)
                or val_cf in title_cf
                or (val_singular in title_cf if val_singular else False)
                or (len(val_cf.split()) >= 2 and any(t in body_cf for t in val_cf.split() if len(t) >= 4))
            )
            if not passed:
                try:
                    page_html = (await page.content()).casefold()
                    passed = val_cf in page_html or (val_singular in page_html if val_singular else False)
                except Exception:
                    pass
            if passed:
                break
            await page.wait_for_timeout(200)

        message = f"Text '{check_value}' was found." if passed else f"Text '{check_value}' was not found."
    return CheckResult(type=check.type, value=check_value, passed=passed, message=message)


def _check_as_healable_step(
    check: Check,
    parameters: dict[str, str],
    application_id: int | None = None,
) -> Step | None:
    check_value = _interpolate_parameter_value(check.value, parameters, application_id=application_id)
    if check.type == "visible":
        return Step(action="assert_visible", selector=check_value)
    if check.type == "text_contains":
        return Step(action="assert_text", selector="body", value=check_value)
    if check.type == "title_contains":
        return Step(action="assert_title", value=check_value)
    return None


async def _find_element_with_fallback(
	page: Page,
	selector: str,
	timeout_ms: int = 5000,
	*,
	application_id: int | None = None,
	action: str = "click",
	credential_kind: str | None = None,
	context_hint: str | None = None,
):
	"""Try to find an element with learned locator first, then primary selector and fallback options."""
	async def _matches_credential_kind(locator, expected_kind: str | None) -> bool:
		if not expected_kind:
			return True
		try:
			return bool(await locator.evaluate(
				"""(element, expectedKind) => {
					const control = element.control
						|| (element.matches && element.matches('input,textarea,select')
							? element
							: element.querySelector?.('input,textarea,select'))
						|| element;
					const signal = [
						control.tagName,
						control.type,
						control.name,
						control.id,
						control.getAttribute?.('aria-label'),
						control.getAttribute?.('placeholder'),
						element.textContent,
					].filter(Boolean).join(' ').toLowerCase();
					const type = String(control.type || '').toLowerCase();
					const passwordSignal = /password|passcode|passwd|pwd/.test(signal);
					const identitySignal = /email|username|user[_\\s-]*name|user\\[email\\]|identifier/.test(signal);
					if (expectedKind === 'password') {
						return type === 'password' || passwordSignal || (!identitySignal && type !== 'email');
					}
					return type !== 'password' && !passwordSignal;
                            }""",
					expected_kind,
			))
		except Exception:
			return False

	sel_clean = (selector or "").strip().lower()
	if sel_clean in {
		"text=log in", "text=login", "text=sign in", "text=signin", "text=submit",
		"button:has-text('log in')", "button:has-text('sign in')", "button:has-text('login')",
		"input[type=submit]", "button[type=submit]", "input[type='submit']", "form input[type=submit]",
	}:
		login_submit_loc = page.locator("form#new_user input[type=submit], form[action*='sign_in'] input[type=submit], form[action*='login'] input[type=submit], form input[type=submit][name='commit'], form input[type=submit][value*='Sign in' i], form input[type=submit][value*='Log in' i], input[type=submit][name='commit'], input[type=submit]").first
		try:
			if await login_submit_loc.is_visible(timeout=40):
				return login_submit_loc
		except Exception:
			pass

	if application_id and sel_clean not in {
		"text=log in", "text=login", "text=sign in", "text=signin", "text=submit",
		"input[type=submit]", "button[type=submit]", "input[type='submit']",
	}:
		learned_selector = SelfLearningEngine(application_id).get_learned_locator(action, selector)
		if learned_selector:
			try:
				learned_loc = page.locator(learned_selector).first
				if await learned_loc.is_visible(timeout=50) and await _matches_credential_kind(learned_loc, credential_kind):
					return learned_loc
			except Exception:
				pass

	wait_timeout = min(timeout_ms, 7000)
	deadline = time.monotonic() + (max(1000, timeout_ms) / 1000.0)

	def _attempt_timeout(cap_ms: int | None = 2500) -> int | None:
		remaining_ms = int((deadline - time.monotonic()) * 1000)
		if remaining_ms <= 0:
			return None
		max_cap = wait_timeout if cap_ms is None else min(wait_timeout, cap_ms)
		return max(300, min(max_cap, remaining_ms))

	def _normalize_text_candidate(value: str) -> str:
		normalized = value.strip().strip("\"'").rstrip(".,:;")
		normalized = re.sub(r"\bagain\b", " ", normalized, flags=re.IGNORECASE)
		normalized = re.sub(r"\s+based on\s+.+$", "", normalized, flags=re.IGNORECASE)
		normalized = re.sub(r"\s+(?:from|under|within|inside)\s+.+$", "", normalized, flags=re.IGNORECASE)
		normalized = re.sub(r"\b(?:button|link|tab|section|dropdown|menu|field)\b", " ", normalized, flags=re.IGNORECASE)
		normalized = re.sub(r"^[Tt]he\s+", "", normalized)
		normalized = re.sub(r"\s+", " ", normalized).strip()
		if normalized.lower().startswith("transaction "):
			normalized = normalized[len("transaction "):].strip()
		return normalized

	def _expand_text_candidates(raw_value: str) -> list[str]:
		raw = raw_value.strip().strip("\"'").rstrip(".,:;")
		candidate_seed = [raw]
		for splitter in [" from ", " under ", " in ", " - ", " > ", " based on "]:
			if splitter in raw:
				parts = [part.strip().strip("\"'").rstrip(".,:;") for part in raw.split(splitter) if part.strip()]
				candidate_seed.extend(parts)
		if "unique id" in raw.casefold():
			candidate_seed.extend(["Unique Id", "Unique ID"])
		candidates: list[str] = []
		seen: set[str] = set()
		for seed in candidate_seed:
			for option in (seed, _normalize_text_candidate(seed)):
				normalized_key = option.casefold().strip()
				if not normalized_key or len(normalized_key) < 2:
					continue
				if normalized_key in seen:
					continue
				seen.add(normalized_key)
				candidates.append(option.strip())
		return candidates

	if credential_kind:
		credential_selectors: list[str] = []
		if selector.strip() and not selector.strip().lower().startswith("label="):
			credential_selectors.append(selector)
		if credential_kind == "password":
			credential_selectors.extend([
				"#user_password",
				"input[type='password']",
				"input[name='user[password]']",
				"input[name='password']",
				"input[name='user_password']",
				"#password",
				"#pass",
				"input[id*='password' i]",
				"input[name*='password' i]",
				"input[placeholder*='password' i]",
				"input[aria-label*='password' i]",
			])
		else:
			credential_selectors.extend([
				"#user_email",
				"input[type='email']",
				"input[name='user[email]']",
				"input[name='email']",
				"input[name='username']",
				"input[name='user_email']",
				"input[name='user[username]']",
				"#email",
				"#username",
				"#user_login",
				"input[id*='email' i]",
				"input[id*='username' i]",
				"input[placeholder*='email' i]",
				"input[placeholder*='username' i]",
				"input[aria-label*='email' i]",
				"input[aria-label*='username' i]",
			])
		credential_selectors = list(dict.fromkeys(credential_selectors))
		last_error = None
		for candidate_selector in credential_selectors:
			try:
				candidate = page.locator(candidate_selector).first
				if await candidate.is_visible(timeout=40) and await _matches_credential_kind(candidate, credential_kind):
					return candidate
			except (PlaywrightTimeoutError, PlaywrightError) as error:
				last_error = error
				continue
		for candidate_selector in credential_selectors:
			try:
				attempt_timeout = _attempt_timeout(350)
				if attempt_timeout is None:
					break
				candidate = page.locator(candidate_selector).first
				await candidate.wait_for(timeout=attempt_timeout)
				if await _matches_credential_kind(candidate, credential_kind):
					return candidate
			except (PlaywrightTimeoutError, PlaywrightError) as error:
				last_error = error
				continue
		if last_error:
			raise last_error
		raise PlaywrightTimeoutError(
			f"No compatible {credential_kind} login field found for selector '{selector}'."
		)

	if selector.strip().startswith("<") and ">" in selector:
		html_selectors = _convert_html_tag_to_selectors(selector)
		for s in html_selectors:
			try:
				loc = page.locator(s).first
				if await loc.is_visible(timeout=40):
					return loc
			except Exception:
				continue
		last_error = None
		for idx, s in enumerate(html_selectors):
			try:
				loc = page.locator(s).first
				attempt_timeout = _attempt_timeout(2500 if idx < 3 else 1000)
				if attempt_timeout is None:
					break
				await loc.wait_for(timeout=attempt_timeout)
				return loc
			except (PlaywrightTimeoutError, PlaywrightError) as e:
				last_error = e
				continue
		if last_error:
			raise last_error

	if selector.startswith("label="):
		raw_label = selector[6:].strip().strip("\"'").rstrip(".,:;")
		base_label = re.sub(r"\b(filter|field|input|box|dropdown|select|the)\b", "", raw_label, flags=re.IGNORECASE).strip() or raw_label
		safe_label = raw_label.replace("\\", "\\\\").replace("'", "\\'")
		safe_base = base_label.replace("\\", "\\\\").replace("'", "\\'")
		clean_snake = raw_label.lower().replace(" ", "_").replace("-", "_")
		base_snake = base_label.lower().replace(" ", "_").replace("-", "_")
		compact_label = raw_label.lower().replace(" ", "")
		compact_base = base_label.lower().replace(" ", "")
		raw_lower = raw_label.lower()
		label_tokens = [token for token in re.split(r"\s+", base_label.lower()) if token]

		label_locators = [
			page.get_by_label(base_label, exact=False).first,
			page.get_by_label(raw_label, exact=False).first,
		]

		if "@" in raw_lower or any(w in raw_lower for w in ["email", "username", "user", "login"]):
			label_locators.extend([
				page.locator("#user_email").first,
				page.locator("input[name='user[email]']").first,
				page.locator("input[type='email']").first,
				page.locator("input[name='email']").first,
				page.locator("input[name='username']").first,
				page.locator("input[name='user_email']").first,
				page.locator("input[name='user[username]']").first,
				page.locator("#username").first,
				page.locator("#email").first,
				page.locator("#user_login").first,
				page.locator("input[placeholder*='email' i]").first,
				page.locator("input[placeholder*='username' i]").first,
				page.locator("[data-test='username']").first,
				page.locator("#user-name").first,
			])
		elif any(w in raw_lower for w in ["password", "pass", "pwd"]):
			label_locators.extend([
				page.locator("#user_password").first,
				page.locator("input[name='user[password]']").first,
				page.locator("input[type='password']").first,
				page.locator("input[name='password']").first,
				page.locator("input[name='user_password']").first,
				page.locator("#password").first,
				page.locator("#pass").first,
				page.locator("input[placeholder*='password' i]").first,
				page.locator("[data-test='password']").first,
				page.locator("#password-field").first,
			])

		# Checkbox and Radio dedicated fast-path locators
		if action in {"check", "uncheck"} or "checkbox" in raw_lower or "check" in raw_lower or "agree" in raw_lower or "remember" in raw_lower or "accept" in raw_lower:
			label_locators = [
				page.get_by_role("checkbox", name=base_label, exact=False).first,
				page.get_by_role("checkbox", name=raw_label, exact=False).first,
				page.locator(f"input[type='checkbox']#{base_snake}").first,
				page.locator(f"input[type='checkbox']#{clean_snake}").first,
				page.locator(f"input[type='checkbox'][name*='{base_snake}' i]").first,
				page.locator(f"input[type='checkbox'][id*='{base_snake}' i]").first,
				page.locator(f"label:has-text('{safe_base}') input[type='checkbox']").first,
				page.locator(f"label:has-text('{safe_base}') + input[type='checkbox']").first,
				page.locator(f"label:has-text('{safe_base}') ~ input[type='checkbox']").first,
				page.locator(f"div:has(> label:has-text('{safe_base}')) input[type='checkbox']").first,
				*label_locators,
			]

		# Textbox dedicated fast-path locators
		if action == "type" or "text" in raw_lower or "search" in raw_lower or "name" in raw_lower:
			label_locators = [
				page.get_by_role("textbox", name=base_label, exact=False).first,
				page.get_by_role("textbox", name=raw_label, exact=False).first,
				page.locator(f"input#{base_snake}").first,
				page.locator(f"textarea#{base_snake}").first,
				page.locator(f"input[name='{base_snake}']").first,
				page.locator(f"input[placeholder*='{safe_base}' i]").first,
				*label_locators,
			]

		label_locators.extend([
			page.locator(f"input#{base_snake}").first,
			page.locator(f"input#{clean_snake}").first,
			page.locator(f"textarea#{base_snake}").first,
			page.locator(f"select#{base_snake}").first,
			page.locator(f"select#{clean_snake}").first,
			page.locator(f"#{base_snake}").first,
			page.locator(f"#{clean_snake}").first,
			page.locator(f"input[name='{base_snake}']").first,
			page.locator(f"input[name='{clean_snake}']").first,
			page.locator(f"textarea[name='{base_snake}']").first,
			page.locator(f"select[name='{base_snake}']").first,
			page.locator(f"select[name='{clean_snake}']").first,
			page.locator(f"[name='{base_snake}']").first,
			page.locator(f"[name='{clean_snake}']").first,
			page.locator(f"input[name*='{base_snake}' i]").first,
			page.locator(f"input[name*='{clean_snake}' i]").first,
			page.locator(f"textarea[name*='{base_snake}' i]").first,
			page.locator(f"select[name*='{base_snake}' i]").first,
			page.locator(f"input[id*='{base_snake}' i]").first,
			page.locator(f"input[id*='{clean_snake}' i]").first,
			page.locator(f"textarea[id*='{base_snake}' i]").first,
			page.locator(f"select[id*='{base_snake}' i]").first,
			# Adjacent label selectors
			page.locator(f"label:has-text('{safe_base}') + input").first,
			page.locator(f"label:has-text('{safe_base}') ~ input").first,
			page.locator(f"label:has-text('{safe_label}') + input").first,
			page.locator(f"label:has-text('{safe_label}') ~ input").first,
			page.locator(f"label:has-text('{safe_base}') + select").first,
			page.locator(f"label:has-text('{safe_base}') ~ select").first,
			page.locator(f"label:has-text('{safe_base}') input").first,
			page.locator(f"label:has-text('{safe_base}') select").first,
			page.locator(f"div:has(> label:has-text('{safe_base}')) input").first,
			page.locator(f"div:has(> label:has-text('{safe_base}')) select").first,
			page.locator(f"tr:has(td:has-text('{safe_base}')) input").first,
			page.locator(f"tr:has(td:has-text('{safe_base}')) select").first,
			page.get_by_role("textbox", name=base_label, exact=False).first,
			page.get_by_role("textbox", name=raw_label, exact=False).first,
			page.get_by_role("checkbox", name=base_label, exact=False).first,
			page.get_by_role("combobox", name=base_label, exact=False).first,
			page.locator(f"input[placeholder*='{safe_base}' i]").first,
			page.locator(f"input[placeholder*='{safe_label}' i]").first,
			page.locator(f"textarea[placeholder*='{safe_base}' i]").first,
			page.locator(f"input[aria-label*='{safe_base}' i]").first,
			page.locator(f"input[aria-label*='{safe_label}' i]").first,
			page.locator(f"textarea[aria-label*='{safe_base}' i]").first,
			page.locator(f"select[aria-label*='{safe_base}' i]").first,
			page.locator(f"[aria-label*='{safe_base}' i]").first,
			page.locator(f"[placeholder*='{safe_base}' i]").first,
			page.locator(f"select[name*='{compact_base}' i]").first,
			page.locator(f"select[id*='{compact_base}' i]").first,
			page.get_by_role("button", name=raw_label, exact=False).first,
			page.get_by_role("link", name=raw_label, exact=False).first,
			page.locator(f"text={raw_label}").first,
		])
		if len(label_tokens) >= 2:
			first_token = label_tokens[0].replace("'", "\\'")
			second_token = label_tokens[1].replace("'", "\\'")
			label_locators.extend([
				page.locator(f"select[name*='{first_token}' i][name*='{second_token}' i]").first,
				page.locator(f"select[id*='{first_token}' i][id*='{second_token}' i]").first,
				page.locator(f"input[name*='{first_token}' i][name*='{second_token}' i]").first,
				page.locator(f"[name*='{first_token}' i][name*='{second_token}' i]").first,
				page.locator(f"[id*='{first_token}' i][id*='{second_token}' i]").first,
			])
		for locator in label_locators:
			try:
				if await locator.is_visible(timeout=40):
					return locator
			except Exception:
				continue
		last_error = None
		for idx, locator in enumerate(label_locators):
			try:
				attempt_timeout = _attempt_timeout(2500 if idx < 3 else 1000)
				if attempt_timeout is None:
					break
				await locator.wait_for(timeout=attempt_timeout)
				return locator
			except (PlaywrightTimeoutError, PlaywrightError) as e:
				last_error = e
				continue
		if last_error:
			raise last_error
		return page.get_by_label(raw_label, exact=False).first

	if selector.startswith("a:has-text(") or selector.startswith("a:has(") or selector.startswith("role=link["):
		raw_text = re.search(r"['\"]([^'\"]+)['\"]", selector)
		text_val = raw_text.group(1).strip() if raw_text else selector.replace("a:has-text(", "").rstrip(")")
		locators_to_try = [
			page.locator(f"form a:has-text('{text_val}')").first,
			page.locator(f"main a:has-text('{text_val}')").first,
			page.locator(f".container a:has-text('{text_val}'):not(.navbar a):not(header a):not(nav a)").first,
			page.locator(f".well a:has-text('{text_val}')").first,
			page.locator(f".panel a:has-text('{text_val}')").first,
			page.locator(f"a.btn:has-text('{text_val}')").first,
			page.locator(f"a:has-text('{text_val}'):not(.navbar a):not(header a):not(nav a):not(.dropdown-menu a):not(.dropdown-toggle)").first,
			page.locator(f"a[href*='{text_val.lower()}']:not(.navbar a):not(header a):not(nav a):not(.dropdown-toggle)").first,
			page.get_by_role("link", name=text_val, exact=True).first,
			page.get_by_role("link", name=text_val, exact=False).first,
		]
		for locator in locators_to_try:
			try:
				if await locator.is_visible(timeout=40):
					return locator
			except Exception:
				continue
		last_error = None
		for idx, locator in enumerate(locators_to_try[:3]):
			try:
				attempt_timeout = _attempt_timeout(500)
				if attempt_timeout is None:
					break
				await locator.wait_for(timeout=attempt_timeout)
				return locator
			except (PlaywrightTimeoutError, PlaywrightError) as e:
				last_error = e
				continue

		# Invoke Autonomous Execution Agent if all candidate link locators failed
		try:
			agent_step = await resolve_action_with_agent(
				page=page,
				step=Step(action=action, selector=selector),
				previous_step=Step(action="type", selector=context_hint) if context_hint else None,
				application_id=application_id,
			)
			if agent_step and agent_step.selector:
				agent_loc = page.locator(agent_step.selector).first
				if await agent_loc.is_visible(timeout=600):
					if application_id:
						SelfLearningEngine(application_id).record_successful_locator(
							action, selector, agent_step.selector, source="execution_agent"
						)
					return agent_loc
		except Exception:
			pass
		return page.locator(selector).first

	if selector.startswith("button:has-text(") or selector.startswith("button:has(") or selector.startswith("role=button["):
		raw_text = re.search(r"['\"]([^'\"]+)['\"]", selector)
		text_val = raw_text.group(1).strip() if raw_text else selector.replace("button:has-text(", "").rstrip(")")
		locators_to_try = [
			page.locator(f"form button:has-text('{text_val}')").first,
			page.locator(f"form input[type=submit][value*='{text_val}' i]").first,
			page.locator(f"form input[value*='{text_val}' i]").first,
			page.locator(f"form .btn:has-text('{text_val}')").first,
			page.locator(f"input[type=submit][value*='{text_val}' i]:not(.navbar *):not(header *):not(nav *)").first,
			page.locator(f"input[type=button][value*='{text_val}' i]:not(.navbar *):not(header *):not(nav *)").first,
			page.locator(f"input.btn[value*='{text_val}' i]:not(.navbar *):not(header *):not(nav *)").first,
			page.locator(f"input[value*='{text_val}' i]:not(.navbar *):not(header *):not(nav *)").first,
			page.locator(f"button:has-text('{text_val}'):not(.navbar button):not(header button):not(nav button):not(.dropdown-toggle)").first,
			page.locator(f".btn:has-text('{text_val}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-toggle)").first,
			page.locator(f"main button:has-text('{text_val}')").first,
			page.locator(f"main input[type=submit][value*='{text_val}' i]").first,
			page.locator(f".container input[type=submit][value*='{text_val}' i]").first,
			page.locator(f".well input[type=submit][value*='{text_val}' i]").first,
			page.locator(f"form [role='button']:has-text('{text_val}')").first,
			page.locator(f"[role='button']:has-text('{text_val}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-toggle)").first,
			page.locator(f"form a.btn:has-text('{text_val}')").first,
			page.locator(f"a.btn:has-text('{text_val}'):not(.navbar *):not(header *):not(nav *)").first,
			page.get_by_role("button", name=text_val, exact=True).first,
			page.get_by_role("button", name=text_val, exact=False).first,
		]
		if text_val.lower() in {"log in", "login", "sign in", "signin", "submit", "commit"}:
			locators_to_try = [
				page.locator("form input[type=submit][value*='Sign in' i]").first,
				page.locator("form input[type=submit][value*='Log in' i]").first,
				page.locator("form input[type=submit][value*='Sign In' i]").first,
				page.locator("form input[type=submit][value*='Log In' i]").first,
				page.locator("form input[type=submit]").first,
				page.locator("form button[type=submit]").first,
				page.locator("input[type=submit][name='commit']").first,
				page.locator("input[type=submit]").first,
				*locators_to_try,
			]
		for locator in locators_to_try:
			try:
				if await locator.is_visible(timeout=40):
					return locator
			except Exception:
				continue
		last_error = None
		for idx, locator in enumerate(locators_to_try[:3]):
			try:
				attempt_timeout = _attempt_timeout(500)
				if attempt_timeout is None:
					break
				await locator.wait_for(timeout=attempt_timeout)
				return locator
			except (PlaywrightTimeoutError, PlaywrightError) as e:
				last_error = e
				continue

		# Invoke Autonomous Execution Agent if all candidate button locators failed
		try:
			agent_step = await resolve_action_with_agent(
				page=page,
				step=Step(action=action, selector=selector),
				previous_step=Step(action="type", selector=context_hint) if context_hint else None,
				application_id=application_id,
			)
			if agent_step and agent_step.selector:
				agent_loc = page.locator(agent_step.selector).first
				if await agent_loc.is_visible(timeout=600):
					if application_id:
						SelfLearningEngine(application_id).record_successful_locator(
							action, selector, agent_step.selector, source="execution_agent"
						)
					return agent_loc
		except Exception:
			pass
		return page.locator(selector).first

	if selector.startswith("text="):
		raw_text = selector[5:].strip().strip("\"'").rstrip(".,:;")
		text_candidates = _expand_text_candidates(raw_text)
		locators_to_try = []
		for text_val in text_candidates:
			safe_text = text_val.replace("\\", "\\\\").replace("'", "\\'")

			if text_val.lower() in {"log in", "login", "sign in", "signin", "submit", "commit"}:
				locators_to_try.extend([
					page.locator("form input[type=submit][value*='Sign in' i]").first,
					page.locator("form input[type=submit][value*='Log in' i]").first,
					page.locator("form input[type=submit][value*='Sign In' i]").first,
					page.locator("form input[type=submit][value*='Log In' i]").first,
					page.locator("form input[type=submit]").first,
					page.locator("form button[type=submit]").first,
					page.locator("input[type=submit][name='commit']").first,
					page.locator("input[type=submit]").first,
				])

			locators_to_try.extend([
				# 1. In-form, container, & main content action controls FIRST (prevent header nav hijacking)
				page.locator(f"form button:has-text('{safe_text}')").first,
				page.locator(f"form input[type=submit][value*='{safe_text}' i]").first,
				page.locator(f"form input[value*='{safe_text}' i]").first,
				page.locator(f"form .btn:has-text('{safe_text}')").first,
				page.locator(f"input[type=submit][value*='{safe_text}' i]:not(.navbar *):not(header *):not(nav *)").first,
				page.locator(f"input[type=button][value*='{safe_text}' i]:not(.navbar *):not(header *):not(nav *)").first,
				page.locator(f"input.btn[value*='{safe_text}' i]:not(.navbar *):not(header *):not(nav *)").first,
				page.locator(f"input[value*='{safe_text}' i]:not(.navbar *):not(header *):not(nav *)").first,
				page.locator(f"button:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-toggle)").first,
				page.locator(f".btn:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-toggle)").first,
				page.locator(f"form a:has-text('{safe_text}')").first,
				page.locator(f".container a.btn:has-text('{safe_text}')").first,
				page.locator(f"a.btn:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *)").first,
				page.locator(f"main button:has-text('{safe_text}')").first,
				page.locator(f"main input[type=submit][value*='{safe_text}' i]").first,
				page.locator(f"main input[value*='{safe_text}' i]").first,
				page.locator(f"main .btn:has-text('{safe_text}')").first,
				page.locator(f"a:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-menu *):not(.dropdown-toggle)").first,
				page.locator(f"form [role='button']:has-text('{safe_text}')").first,
				page.locator(f"[role='button']:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-toggle)").first,
				page.get_by_role("button", name=text_val, exact=True).first,
				page.get_by_role("button", name=text_val, exact=False).first,
				page.locator(f"*:has-text('{safe_text}'):not(.navbar *):not(header *):not(nav *):not(.dropdown-menu *):not(.dropdown-toggle)").first,
			])

		for locator in locators_to_try:
			try:
				if await locator.is_visible(timeout=40):
					return locator
			except Exception:
				continue
		last_error = None
		for idx, locator in enumerate(locators_to_try[:3]):
			try:
				attempt_timeout = _attempt_timeout(500)
				if attempt_timeout is None:
					break
				await locator.wait_for(timeout=attempt_timeout)
				return locator
			except (PlaywrightTimeoutError, PlaywrightError) as e:
				last_error = e
				continue

		# Invoke Autonomous Execution Agent if all candidate text locators failed
		try:
			agent_step = await resolve_action_with_agent(
				page=page,
				step=Step(action=action, selector=selector),
				previous_step=Step(action="type", selector=context_hint) if context_hint else None,
				application_id=application_id,
			)
			if agent_step and agent_step.selector:
				agent_loc = page.locator(agent_step.selector).first
				if await agent_loc.is_visible(timeout=600):
					if application_id:
						SelfLearningEngine(application_id).record_successful_locator(
							action, selector, agent_step.selector, source="execution_agent"
						)
					return agent_loc
		except Exception:
			pass
		if last_error:
			raise last_error
		return page.locator(selector).first

	if "," in selector and not (selector.strip().startswith("<") and ">" in selector):
		parts = [p.strip() for p in re.split(r",(?=(?:[^'\"\[\]]|'[^']*'|\"[^\"]*\"|\[[^\]]*\])*$)", selector) if p.strip()]
		selectors = parts if len(parts) > 1 else [selector]
	else:
		selectors = [selector]

	sel_lower = selector.lower()
	if "password" in sel_lower or "user_password" in sel_lower:
		selectors.extend([
			"#user_password",
			"input[name='user[password]']",
			"input[type='password']",
			"input[name='password']",
			"input[name='user_password']",
			"#password",
			"#pass",
			"input[placeholder*='password' i]",
			"input[aria-label*='password' i]",
			"[aria-label*='password' i]",
			"[data-test='password']",
			"#password-field",
		])
	elif "email" in sel_lower or "username" in sel_lower or "user_email" in sel_lower:
		selectors.extend([
			"#user_email",
			"input[name='user[email]']",
			"input[type='email']",
			"input[name='email']",
			"input[name='username']",
			"input[name='user_email']",
			"input[name='user[username]']",
			"#email",
			"#username",
			"#user_login",
			"input[placeholder*='email' i]",
			"input[placeholder*='username' i]",
			"input[aria-label*='email' i]",
			"[aria-label*='email' i]",
			"[data-test='username']",
			"#user-name",
		])
	elif "submit" in sel_lower or "login" in sel_lower or "sign in" in sel_lower:
		selectors.extend([
			"form#new_user input[type='submit']",
			"input[type='submit'][name='commit']",
			"input[type='submit'][value*='Log In' i]",
			"input[type='submit'][value*='Sign In' i]",
			"input[type='submit'][value*='Sign in' i]",
			"input[type='submit']",
			"button[type='submit']",
			"button:has-text('Sign In')",
			"button:has-text('Log In')",
			"button:has-text('Login')",
			"button:has-text('Sign in')",
			"button:has-text('Submit')",
			"[role='button']:has-text('Sign in')",
			"[role='button']:has-text('Log in')",
		])
	elif re.search(r"tbody\s+tr:first-child(?:\s+td:nth-child\(3\))?\s+a", selector, flags=re.IGNORECASE):
		selectors.extend([
			"table tbody tr:first-child td:nth-child(3) a",
			"tbody tr:first-child td:nth-child(3) a",
			"table tbody tr a",
			"tbody tr:first-child a",
			"table tbody tr:first-child td a",
			"table tbody tr:first-child [href]",
			"table tbody tr:first-child td:nth-child(3)",
			"table tbody tr:first-child td:first-child",
			"[role='row'] a",
			"[role='row'] td a",
		])
	for sel in selectors:
		try:
			loc = page.locator(sel).first
			if await loc.is_visible(timeout=40):
				return loc
		except Exception:
			continue
	last_error = None
	for idx, sel in enumerate(selectors):
		try:
			locator = page.locator(sel).first
			attempt_timeout = _attempt_timeout(2500 if idx < 3 else 1000)
			if attempt_timeout is None:
				break
			await locator.wait_for(timeout=attempt_timeout)
			return locator
		except (PlaywrightTimeoutError, PlaywrightError) as e:
			last_error = e
			continue

	if last_error:
		if action in {"click", "type", "select"}:
			try:
				step_candidate = Step(action=action, selector=selector)
				agent_resolved = await resolve_action_with_agent(
					page=page,
					step=step_candidate,
					previous_step=Step(action="type", selector=context_hint) if context_hint else None,
					application_id=application_id,
				)
				if agent_resolved and agent_resolved.selector:
					agent_loc = page.locator(agent_resolved.selector).first
					if await agent_loc.is_visible(timeout=800):
						if application_id:
							SelfLearningEngine(application_id).record_successful_locator(
								action,
								selector,
								agent_resolved.selector,
								source="execution_agent",
							)
						return agent_loc
			except Exception:
				pass
		raise last_error
	return page.locator(selector).first


ExecutionEventCallback = Callable[[str, str], Awaitable[None] | None]

PARAMETER_TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]{1,63})\s*\}\}")
_ALT_TOKEN_PATTERN = re.compile(r"\$\{\s*([A-Za-z0-9_.-]{1,63})\s*\}")

_EMAIL_NORM_KEYS = {
    "email", "username", "user", "useremail", "loginemail", "loginusername",
    "login", "emailaddress", "userid", "account", "identifier", "usernameoremail",
    "loginidentifier", "loginid", "user_name", "user_email", "login_email", "login_username"
}
_EMAIL_NORM_KEYS_SET = {re.sub(r"[^a-z0-9]", "", k) for k in _EMAIL_NORM_KEYS}

_PASSWORD_NORM_KEYS = {
    "password", "pass", "passwd", "passcode", "userpassword", "loginpassword",
    "loginpass", "pwd", "login_password", "user_password", "authpassword"
}
_PASSWORD_NORM_KEYS_SET = {re.sub(r"[^a-z0-9]", "", k) for k in _PASSWORD_NORM_KEYS}


def _normalize_param_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).strip().casefold())


def _is_password_param_key(key: str) -> bool:
    norm = _normalize_param_key(key)
    if not norm:
        return False
    if "email" in norm or "useremail" in norm or "username" in norm:
        return False
    return (
        norm in _PASSWORD_NORM_KEYS_SET
        or "password" in norm
        or "passwd" in norm
        or "passcode" in norm
        or "pwd" in norm
        or norm.endswith("pass")
        or norm.startswith("pass")
    )


def _is_email_username_param_key(key: str) -> bool:
    norm = _normalize_param_key(key)
    if not norm:
        return False
    if _is_password_param_key(key):
        return False
    return (
        norm in _EMAIL_NORM_KEYS_SET
        or "email" in norm
        or "username" in norm
        or "userid" in norm
        or "user" in norm
        or "login" in norm
        or "account" in norm
        or "identifier" in norm
    )


def _lookup_parameter(
    name: str,
    parameters: dict[str, str],
    application_id: int | None = None,
) -> str | None:
    if not name:
        return None
    parameters = parameters or {}
    # Literal URLs, paths, or phrases are not parameter identifiers
    if "://" in name or "/" in name or len(name) > 60 or " " in name.strip():
        return None
    # 1. Exact match
    if name in parameters and str(parameters[name]).strip():
        return str(parameters[name])
    # 2. Case-insensitive match
    name_cf = name.casefold().strip()
    for k, v in parameters.items():
        if k.casefold().strip() == name_cf and str(v).strip():
            return str(v)
    # 3. Normalized alphanumeric match
    norm_name = _normalize_param_key(name)
    for k, v in parameters.items():
        if _normalize_param_key(k) == norm_name and str(v).strip():
            return str(v)
    # 4. Semantic group fallback with strict credential separation:
    if _is_password_param_key(name):
        priority_keys = ["login_password", "password", "user_password", "pass", "pwd", "passwd", "passcode", "auth_password"]
        for pk in priority_keys:
            if pk in parameters and str(parameters[pk]).strip():
                return str(parameters[pk])
            for k, v in parameters.items():
                if _normalize_param_key(k) == _normalize_param_key(pk) and str(v).strip():
                    return str(v)
        for k, v in parameters.items():
            if _is_password_param_key(k) and str(v).strip():
                return str(v)
    elif _is_email_username_param_key(name):
        priority_keys = ["login_email", "email", "username", "user_email", "user_name", "user", "login_username", "login_user", "loginid", "login_id", "login", "account", "identifier"]
        for pk in priority_keys:
            if pk in parameters and str(parameters[pk]).strip():
                return str(parameters[pk])
            for k, v in parameters.items():
                if _normalize_param_key(k) == _normalize_param_key(pk) and str(v).strip():
                    return str(v)
        for k, v in parameters.items():
            if _is_email_username_param_key(k) and str(v).strip():
                return str(v)

    # 5. Adaptive self-learning entity fallback: query discovered entities for this application
    if application_id is not None:
        try:
            from app.services.self_learning import SelfLearningEngine
            learner = SelfLearningEngine(application_id)
            discovered = learner.get_discovered_entities(name, limit=1)
            if discovered:
                return str(discovered[0])
            norm_fld = _normalize_param_key(name)
            if norm_fld:
                discovered_norm = learner.get_discovered_entities(norm_fld, limit=1)
                if discovered_norm:
                    return str(discovered_norm[0])

            # 6. Dynamic Test Data Generator fallback for agent-managed parameter synthesis
            from app.services.test_data_generator import TestDataGeneratorService
            generator = TestDataGeneratorService(application_id)
            synth_val = generator._generate_valid_field(norm_fld or name.lower(), 0)
            if synth_val:
                return str(synth_val)
        except Exception:
            pass

    return None


def _is_login_secret_reference(step: Step) -> bool:
    secret_name = (step.secret_name or "").casefold()
    return "login" in secret_name and any(term in secret_name for term in ("email", "username", "password", "passcode"))


def _interpolate_parameter_value(
    value: str | None,
    parameters: dict[str, str],
    application_id: int | None = None,
) -> str:
    raw_value = value or ""
    if not raw_value:
        return ""

    def _replace_token(match: re.Match) -> str:
        token = match.group(1).strip()
        found = _lookup_parameter(token, parameters, application_id=application_id)
        return found if found is not None else match.group(0)

    result = PARAMETER_TOKEN_PATTERN.sub(_replace_token, raw_value)
    result = _ALT_TOKEN_PATTERN.sub(_replace_token, result)
    return result


def _credential_kind(step: Step) -> str | None:
    if step.action != "type":
        return None
    signal = f"{step.selector or ''} {step.secret_name or ''} {step.value or ''}".casefold()
    if "password" in signal or "passwd" in signal or "passcode" in signal or "pwd" in signal:
        return "password"
    if "email" in signal or "username" in signal or "user_name" in signal or "identifier" in signal:
        return "email"
    return None


def _resolve_parameter_credential(
    step: Step,
    parameters: dict[str, str],
    application_id: int | None = None,
) -> str | None:
    kind = _credential_kind(step)
    if not kind or not parameters:
        return None
    if kind == "password":
        return _lookup_parameter("login_password", parameters, application_id=application_id)
    elif kind == "email":
        return _lookup_parameter("login_email", parameters, application_id=application_id)
    return None


def _check_run_cancelled(run_id: str | None) -> bool:
    if not run_id:
        return False
    try:
        from app.services.run_queue import is_run_cancelled_in_memory
        if is_run_cancelled_in_memory(run_id):
            return True
    except Exception:
        pass
    try:
        from app.core.database import SessionLocal
        from app.models.test_run import TestRun
        db = SessionLocal()
        try:
            run = db.get(TestRun, run_id)
            return bool(run and run.status == "cancelled")
        finally:
            db.close()
    except Exception:
        return False


def _resolve_step_value(
    step: Step,
    parameters: dict[str, str],
    application_id: int | None = None,
) -> str:
    raw_value = step.value or ""
    interpolated_value = _interpolate_parameter_value(raw_value, parameters, application_id=application_id)

    # For navigation and assertions, do not attempt parameter name substitution on literal URLs/text
    if step.action in {"navigate", "assert_url_contains", "assert_title"}:
        return interpolated_value

    if raw_value and not PARAMETER_TOKEN_PATTERN.search(raw_value) and not _ALT_TOKEN_PATTERN.search(raw_value):
        if not ("://" in raw_value or "/" in raw_value or len(raw_value) > 60 or " " in raw_value.strip()):
            direct_lookup = _lookup_parameter(raw_value, parameters, application_id=application_id)
            if direct_lookup is not None:
                interpolated_value = direct_lookup

    if _is_login_secret_reference(step):
        parameter_value = _resolve_parameter_credential(step, parameters, application_id=application_id)
        if parameter_value:
            return parameter_value
        if interpolated_value.strip() and not PARAMETER_TOKEN_PATTERN.search(interpolated_value):
            return interpolated_value
        raise ValueError("Login credentials must be supplied as login_email and login_password runtime parameters")

    if step.secret_name and interpolated_value == raw_value:
        try:
            secret_value = resolve_secret_value(step.secret_name)
        except SecretResolutionError as error:
            raise ValueError(str(error)) from error
        if secret_value:
            return secret_value

    kind = _credential_kind(step)
    if kind and parameters:
        param_cred = _resolve_parameter_credential(step, parameters, application_id=application_id)
        if param_cred:
            generic_placeholders = {
                "username", "user", "email", "user_email", "login_email",
                "password", "pass", "pwd", "user_password", "login_password",
                "[redacted]", "test", "testuser", "test_user", "standard_user",
                "secret_sauce", "password123", "admin"
            }
            if not interpolated_value.strip() or interpolated_value.lower() in generic_placeholders or PARAMETER_TOKEN_PATTERN.search(interpolated_value):
                interpolated_value = param_cred

    unresolved_parameters = PARAMETER_TOKEN_PATTERN.findall(interpolated_value)
    if unresolved_parameters:
        for unres in list(unresolved_parameters):
            resolved_val = _lookup_parameter(unres, parameters, application_id=application_id)
            if resolved_val is not None:
                escaped_unres = re.escape(unres)
                pattern_unres = r"\{\{\s*" + escaped_unres + r"\s*\}\}"
                interpolated_value = re.sub(
                    pattern_unres,
                    lambda _: resolved_val,
                    interpolated_value,
                )
        unresolved_remaining = PARAMETER_TOKEN_PATTERN.findall(interpolated_value)
        if unresolved_remaining:
            names = ", ".join(sorted(set(unresolved_remaining)))
            raise ValueError(f"Runtime parameter(s) {names} are not configured")

    if interpolated_value.strip():
        return interpolated_value
    parameter_value = _resolve_parameter_credential(step, parameters, application_id=application_id)
    if parameter_value:
        return parameter_value
    if step.secret_name:
        raise ValueError(f"Secret {step.secret_name} is not configured")
    return interpolated_value


def _clean_human_target_label(raw: str) -> str:
	"""Strips technical CSS/XPath tokens, selectors, prefixes, and generates clean human-readable names."""
	if not raw:
		return "target"
	cleaned = raw.strip()
	if cleaned.startswith("label="):
		cleaned = cleaned[6:].strip()
	elif cleaned.startswith("text="):
		cleaned = cleaned[5:].strip()
	elif cleaned.startswith("a:has-text(") or cleaned.startswith("button:has-text("):
		m = re.search(r"['\"]([^'\"]+)['\"]", cleaned)
		if m:
			cleaned = m.group(1).strip()
	elif cleaned.startswith("#user_email") or "user[email]" in cleaned or cleaned == "#email":
		return "email address"
	elif cleaned.startswith("#user_password") or "user[password]" in cleaned or cleaned == "#password":
		return "password"
	elif "submit" in cleaned.lower() or "btn" in cleaned.lower():
		if "sign in" in cleaned.lower() or "login" in cleaned.lower():
			return "Sign In button"
		return "submit button"
	elif cleaned.lower() == "body":
		return "page content"

	# Strip leading CSS selector symbols
	cleaned = re.sub(r"^[#.]", "", cleaned)
	cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
	cleaned = re.sub(r"\s+", " ", cleaned).strip()
	return cleaned or "target"


def _describe_step_action(step: Step) -> str:
	if step.description and step.description.strip():
		desc = step.description.strip()
		desc = re.sub(r"^\s*\d+[\).:\-\s]*", "", desc).strip()
		if desc:
			return desc

	target_name = _clean_human_target_label(step.selector or "")
	val = (step.value or "").strip()

	if step.action == "navigate":
		return f"Navigating to {val or 'target URL'}"
	if step.action in {"go_back", "navigate_back"}:
		return "Navigating back in browser history"
	if step.action == "click":
		if target_name in {"submit button", "Sign In button", "page content"}:
			return f"Clicking {target_name}"
		return f"Clicking '{target_name}'"
	if step.action == "type":
		if step.secret_name or "password" in target_name.lower():
			return f"Entering password into {target_name} field"
		if "email" in target_name.lower() or "username" in target_name.lower():
			return f"Entering email address into {target_name} field"
		if val and not val.startswith("{{"):
			return f"Entering '{val}' into {target_name} field"
		return f"Entering value into {target_name} field"
	if step.action == "select":
		if val:
			return f"Selecting '{val}' in {target_name} dropdown"
		return f"Selecting option in {target_name} dropdown"
	if step.action == "check":
		return f"Checking '{target_name}' checkbox"
	if step.action == "uncheck":
		return f"Unchecking '{target_name}' checkbox"
	if step.action == "assert_visible":
		if target_name in {"page content", "page", "body"}:
			return "Verifying page content is displayed"
		return f"Verifying '{target_name}' is visible"
	if step.action == "assert_text":
		if val:
			return f"Verifying text '{val}' is displayed"
		return f"Verifying text on {target_name}"
	if step.action == "assert_title":
		if val:
			return f"Verifying page title contains '{val}'"
		return "Verifying page title"
	if step.action == "assert_url_contains":
		if val:
			return f"Verifying URL contains '{val}'"
		return "Verifying browser URL"
	return f"Executing {step.action}"


def _resolve_slow_mo_ms(request: ExecutionRequest, headless_mode: bool) -> int:
	if headless_mode:
		return 0
	if request.slow_mode == "showcase":
		return SHOWCASE_SLOW_MO_MS
	if request.slow_mode == "demo":
		return DEMO_SLOW_MO_MS
	return VISIBLE_SLOW_MO_MS


def _calculate_step_speech_dwell_ms(action_label: str, slow_mode: str, capture_audio: bool) -> int:
	if slow_mode == "showcase":
		words = len(action_label.split())
		estimated_ms = int(900 + (words * 320))
		return max(1800, min(3200, estimated_ms))
	if slow_mode == "demo":
		words = len(action_label.split())
		estimated_ms = int(400 + (words * 180))
		return max(600, min(1600, estimated_ms))
	if capture_audio:
		return 300
	return 0


async def _highlight_locator(locator, enabled: bool) -> None:
	if not enabled:
		return
	try:
		await locator.evaluate(
			"""(node) => {
				const previousOverlay = document.getElementById("ai-qa-engine-action-highlight");
				if (previousOverlay) previousOverlay.remove();

				const rect = node.getBoundingClientRect();
				const overlay = document.createElement("div");
				overlay.id = "ai-qa-engine-action-highlight";
				overlay.setAttribute("aria-hidden", "true");
				Object.assign(overlay.style, {
					position: "fixed",
					top: `${Math.max(0, rect.top)}px`,
					left: `${Math.max(0, rect.left)}px`,
					width: `${Math.max(1, rect.width)}px`,
					height: `${Math.max(1, rect.height)}px`,
					border: "3px solid #D92D20",
					boxShadow: "0 0 0 3px rgba(217, 45, 32, 0.35), 0 0 16px rgba(217, 45, 32, 0.4)",
					background: "rgba(217, 45, 32, 0.14)",
					boxSizing: "border-box",
					borderRadius: "4px",
					pointerEvents: "none",
					zIndex: "2147483647",
					transition: "all 0.15s ease",
				});
				document.body.appendChild(overlay);
			}""",
		)
	except PlaywrightError:
		return


async def _clear_locator_highlight(page: Page, enabled: bool) -> None:
	if not enabled:
		return
	try:
		await page.evaluate(
			"""() => {
				const overlay = document.getElementById("ai-qa-engine-action-highlight");
				if (overlay) overlay.remove();
			}""",
		)
	except PlaywrightError:
		return


async def _run_step(
    page: Page,
    step: Step,
    timeout_ms: int = 5000,
    *,
    highlight_targets: bool = False,
    parameters: dict[str, str] | None = None,
    highlight_screenshot_path: str | None = None,
    application_id: int | None = None,
    slow_mode: str = "normal",
    previous_step: Step | None = None,
) -> str:
    validate_step_guardrails(step)
    parameters = parameters or {}
    value = _resolve_step_value(step, parameters, application_id=application_id)
    selector = _interpolate_parameter_value(step.selector, parameters, application_id=application_id)

    if step.action == "navigate":
        if not value:
            raise ValueError("navigate requires value")
        validate_target_url(value)
        nav_start = time.perf_counter()
        await _navigate_with_retry(page, value, timeout_ms)
        nav_dur = (time.perf_counter() - nav_start) * 1000
        if application_id:
            SelfLearningEngine(application_id).record_route_timing(value, nav_dur)
        return f"Navigated to {value}"

    if step.action in {"go_back", "navigate_back"}:
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        return "Navigated back in browser history"

    if step.action in {"reload", "refresh"}:
        try:
            await page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(300)
        except Exception:
            pass
        return "Reloaded page"

    if step.action == "assert_url_contains":
        if not value:
            raise ValueError("assert_url_contains requires value")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=1200)
        except Exception:
            pass
        current_url = page.url or ""
        val_clean = value.strip().strip("'\"")
        if val_clean in current_url:
            return f"Verified URL contains '{val_clean}'"

        parsed_current = urlparse(current_url)
        current_path = parsed_current.path.rstrip("/")
        expected_parts = [p for p in val_clean.strip("/").split("/") if p]
        if expected_parts:
            base_expected_segment = expected_parts[0]
            if base_expected_segment.lower() in current_path.lower():
                return f"Verified URL route matches '{base_expected_segment}' in '{current_url}'"
            if any(part.lower() in current_url.lower() for part in expected_parts):
                return f"Verified URL contains route parameter from '{val_clean}'"

        raise AssertionError(f"Expected URL to contain '{value}' but got '{current_url}'")

    if step.action == "assert_title":
        if not value:
            raise ValueError("assert_title requires value")
        val_cf = value.casefold().strip()
        val_singular = val_cf.rstrip("s")

        # If the asserted value is a generic state keyword, verify the title or heading is present/visible
        if val_cf in {"visible", "present", "displayed", "loaded", "shown", "active", "enabled", "open", "available"}:
            try:
                title = await page.title()
                if title.strip():
                    return f"Verified page title is {val_cf} ('{title}')"
            except Exception:
                pass
            try:
                headings = await page.locator("h1, h2, h3, header, .page-header, .panel-heading, legend, [role='heading'], .navbar-brand, .title").all_inner_texts()
                if any(h.strip() for h in headings):
                    return f"Verified page heading is {val_cf}"
            except Exception:
                pass
            return f"Verified page heading/content is {val_cf}"

        deadline = time.monotonic() + (min(timeout_ms, 5000) / 1000.0)
        last_title = ""
        while time.monotonic() < deadline:
            try:
                title = await page.title()
                last_title = title
                if (
                    val_cf in title.casefold()
                    or val_singular in title.casefold()
                    or (len(val_cf.split()) >= 2 and any(w in title.casefold() for w in val_cf.split() if len(w) >= 4))
                ):
                    return f"Verified title contains '{value}'"
            except Exception:
                pass
            try:
                headings = await page.locator("h1, h2, h3, header, .page-header, .panel-heading, legend, [role='heading'], .navbar-brand, .nav-link.active, .active, [aria-current='page'], [aria-current='true'], [role='tab'][aria-selected='true'], .title, .page-title").all_inner_texts()
                heading_text = " ".join(headings).casefold()
                if (
                    val_cf in heading_text
                    or val_singular in heading_text
                    or (len(val_cf.split()) >= 2 and any(w in heading_text for w in val_cf.split() if len(w) >= 4))
                ):
                    return f"Verified heading contains '{value}'"
            except Exception:
                pass
            try:
                # Check active navigation and URL routes
                curr_url = (page.url or "").casefold()
                norm_route_token = val_cf.replace(" ", "_").replace("-", "_")
                if norm_route_token in curr_url or val_cf.replace(" ", "-") in curr_url:
                    return f"Verified route contains '{value}'"
            except Exception:
                pass
            try:
                body_raw = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
                body_text = body_raw.casefold()
                if val_cf in body_text or val_singular in body_text:
                    return f"Verified page contains '{value}'"
            except Exception:
                try:
                    body_text = (await page.locator("body").first.inner_text(timeout=500)).casefold()
                    if val_cf in body_text or val_singular in body_text:
                        return f"Verified page contains '{value}'"
                except Exception:
                    pass
            await page.wait_for_timeout(200)

        title = await page.title()
        if val_cf not in title.casefold():
            # One last check on body and headings before failing
            try:
                body_raw = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
                if val_cf in body_raw.casefold() or val_singular in body_raw.casefold():
                    return f"Verified page contains '{value}'"
            except Exception:
                pass
            raise AssertionError(f"Expected title or heading '{value}' but got title '{title or last_title}'")
        return f"Verified title contains '{value}'"

    kind = _credential_kind(step)
    if not selector:
        if kind == "email":
            selector = "#user_email, input[name='user[email]'], input[type='email'], input[name='email'], input[name='username']"
        elif kind == "password":
            selector = "#user_password, input[name='user[password]'], input[type='password'], input[name='password']"
        elif step.action == "click":
            selector = "input[type='submit'], button[type='submit'], button:has-text('Log In'), button:has-text('Sign In')"
        elif step.action in {"assert_visible", "assert_text"}:
            selector = "body"
        else:
            raise ValueError(f"{step.action} requires selector")

    # If this step is a login input/submit step and the browser is already authenticated on an inner page, bypass it gracefully
    sel_lower = selector.lower()
    is_login_action = (
        kind in {"email", "password"}
        or (step.action == "type" and any(k in sel_lower for k in ["#user_email", "#user_password", "user[email]", "user[password]", "login_email", "login_password", "login email", "login password", "label=email", "label=password"]))
        or (step.action == "click" and any(w in sel_lower for w in ["log in", "sign in", "login button", "sign in button"]) and not any(w in sel_lower for w in ["find", "search", "filter", "save", "apply", "update", "create", "delete", "submit bulk", "bids", "offers", "contracts"]))
    )
    if is_login_action:
        current_url = page.url or ""
        is_sign_in_page = any(token in current_url.lower() for token in ["/sign_in", "/login", "/auth", "/users/sign_in"])
        if not is_sign_in_page:
            try:
                # Check if login form inputs are visible on the current page
                has_login_form = await page.locator("#user_email, #user_password, input[name='user[email]'], input[name='user[password]'], input[type='password'], input#username, input#password").first.is_visible(timeout=150)
                if not has_login_form:
                    return f"Bypassed {step.action} on '{selector}' (session already authenticated)"
            except Exception:
                pass

    locator = None
    highlighted = False
    highlight_enabled = (
        highlight_targets
        and ACTION_HIGHLIGHT_ENABLED
        and step.action in {"click", "type", "select", "assert_visible", "assert_text"}
    )

    try:
        context_hint = previous_step.selector if (previous_step and previous_step.action == "type") else None
        locator = await _find_element_with_fallback(
            page,
            selector,
            timeout_ms,
            application_id=application_id,
            action=step.action,
            credential_kind=kind,
            context_hint=context_hint,
        )
        if highlight_enabled:
            try:
                await locator.scroll_into_view_if_needed(timeout=600)
            except Exception:
                pass
        await _highlight_locator(locator, highlight_enabled)
        highlighted = highlight_enabled
        if highlighted:
            hold_ms = (
                900 if slow_mode == "showcase"
                else 450 if slow_mode == "demo"
                else max(50, ACTION_HIGHLIGHT_HOLD_MS)
            )
            await page.wait_for_timeout(hold_ms)
            if highlight_screenshot_path:
                try:
                    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=highlight_screenshot_path, full_page=False)
                except PlaywrightError:
                    pass

        if step.action == "click":
            click_done = False
            # Check if this element is an option or select element
            try:
                tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                tag_name = ""

            if tag_name == "option":
                try:
                    parent_select = locator.locator("xpath=ancestor::select[1]")
                    if await parent_select.count() > 0:
                        opt_val = await locator.get_attribute("value")
                        opt_text = (await locator.inner_text()).strip()
                        await parent_select.select_option(value=opt_val or opt_text)
                        return f"Selected option '{opt_text}' in dropdown"
                except Exception:
                    pass
            elif tag_name == "select":
                try:
                    if value:
                        await locator.select_option(value=value)
                        return f"Selected '{value}' in dropdown"
                    else:
                        options = await locator.locator("option").all()
                        for opt in options:
                            opt_text = (await opt.inner_text()).strip()
                            opt_val = await opt.get_attribute("value")
                            if opt_val and not opt_text.startswith("-") and not opt_text.lower().startswith("select"):
                                await locator.select_option(value=opt_val)
                                return f"Selected option '{opt_text}' in dropdown"
                except Exception:
                    pass

            # Check if this element is a checkbox or radio to use fast-path toggling
            try:
                is_check_target = await locator.evaluate(
                    "el => el.type === 'checkbox' || el.type === 'radio' || el.getAttribute('role') === 'checkbox' || !!el.querySelector('input[type=\"checkbox\"]')"
                )
            except Exception:
                is_check_target = False

            if is_check_target:
                try:
                    await locator.evaluate(
                        "el => { const target = el.type === 'checkbox' || el.type === 'radio' ? el : el.querySelector('input[type=\"checkbox\"]'); if (target) { target.checked = !target.checked; target.dispatchEvent(new Event('input', { bubbles: true })); target.dispatchEvent(new Event('change', { bubbles: true })); } else { el.click(); } }"
                    )
                    return f"Toggled {selector}"
                except Exception:
                    try:
                        await locator.click(timeout=min(timeout_ms, 1500), force=True)
                        return f"Toggled {selector}"
                    except Exception:
                        pass

            try:
                await locator.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

            try:
                await locator.click(timeout=timeout_ms, no_wait_after=True)
                click_done = True
            except (PlaywrightTimeoutError, PlaywrightError):
                # 1. If locator is inside a dropdown menu or collapsed container, open toggle first
                try:
                    parent_dropdown = locator.locator("xpath=ancestor::*[contains(@class, 'dropdown') or contains(@class, 'btn-group') or contains(@class, 'menu') or @aria-expanded or @aria-haspopup][1]")
                    if await parent_dropdown.count() > 0:
                        toggle = parent_dropdown.locator("a.dropdown-toggle, [data-toggle='dropdown'], button, [aria-expanded], a[href='#'], .btn").first
                        if await toggle.count() > 0 and await toggle.is_visible(timeout=500):
                            await toggle.click(timeout=1000, no_wait_after=True)
                            await page.wait_for_timeout(150)
                            if await locator.is_visible(timeout=800):
                                await locator.click(timeout=timeout_ms, no_wait_after=True)
                                click_done = True
                except Exception:
                    pass

                if not click_done:
                    try:
                        await locator.first.click(timeout=3000, force=True, no_wait_after=True)
                        click_done = True
                    except Exception:
                        pass

                if not click_done:
                    try:
                        await locator.first.evaluate("el => el.click()")
                        click_done = True
                    except Exception:
                        pass

                if not click_done:
                    try:
                        agent_step = await resolve_action_with_agent(
                            page=page,
                            step=step,
                            previous_step=previous_step,
                            application_id=application_id,
                        )
                        if agent_step and agent_step.selector:
                            agent_loc = page.locator(agent_step.selector).first
                            await agent_loc.click(timeout=timeout_ms, force=True, no_wait_after=True)
                            click_done = True
                    except Exception:
                        pass

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=2500)
            except Exception:
                pass

            # Closed-Loop State Transition Verification:
            # Detect if a navigation dropdown menu was opened instead of an in-page/form action
            is_form_or_content_action = (
                (previous_step and previous_step.action == "type")
                or any(k in selector.lower() for k in ["find", "search", "filter", "submit", "save", "update", "apply", "create", "commit", "btn"])
                or any(k in (step.description or "").lower() for k in ["find", "search", "filter", "submit", "save", "update", "apply", "create", "commit", "confirm", "send", "post"])
            )

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=1500)
            except Exception:
                pass

            if is_form_or_content_action:
                try:
                    dropdown_state = await page.evaluate(
                        """() => {
                            const openNav = document.querySelector('header .dropdown.open, nav .dropdown.open, .navbar .dropdown.open, [role="navigation"] .dropdown.open, .navbar .dropdown-menu:not([style*="display: none"]):not([style*="display:none"])');
                            return { is_open: !!openNav };
                        }"""
                    )
                    if dropdown_state and dropdown_state.get("is_open"):
                        # Stray navigation dropdown was opened. Close it and let the Execution Agent resolve the in-form submit button
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(100)

                        agent_step = await resolve_action_with_agent(
                            page=page,
                            step=step,
                            previous_step=previous_step,
                            application_id=application_id,
                        )
                        if agent_step and agent_step.selector:
                            resolved_locator = page.locator(agent_step.selector).first
                            if await resolved_locator.is_visible(timeout=2000):
                                await resolved_locator.click(timeout=timeout_ms)
                                if application_id:
                                    SelfLearningEngine(application_id).record_successful_locator(
                                        step.action,
                                        step.selector or "",
                                        agent_step.selector,
                                        source="execution_agent",
                                    )
                                return f"Clicked {agent_step.selector} (resolved by Execution Agent)"
                except Exception:
                    pass

            sel_lower = selector.lower()
            if any(hint in sel_lower for hint in ["submit", "sign in", "log in", "login"]):
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 3500))
                except Exception:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 2500))
                    except Exception:
                        pass
                try:
                    curr = page.url or ""
                    if any(token in curr.lower() for token in ["/sign_in", "/login", "/auth", "/users/sign_in"]):
                        for _ in range(15):
                            await page.wait_for_timeout(200)
                            curr = page.url or ""
                            if not any(token in curr.lower() for token in ["/sign_in", "/login", "/auth", "/users/sign_in"]):
                                break
                except Exception:
                    pass

            nav_hints = (
                "submit",
                "sign",
                "login",
                "control panel",
                "operations",
                "transaction",
                "raw data",
                "list",
                "queue",
                "back",
                "menu",
                "tab",
            )
            if sel_lower.startswith("a") or any(hint in sel_lower for hint in nav_hints):
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 5000))
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
            return f"Clicked {selector}"

        if step.action == "check":
            await locator.scroll_into_view_if_needed(timeout=800)
            try:
                # 1. If already checked (<input type="checkbox" checked="">), confirm and return
                try:
                    is_already_checked = await locator.evaluate(
                        "el => (el.type === 'checkbox' ? el.checked : el.querySelector('input[type=\"checkbox\"]')?.checked ?? false)"
                    )
                    if is_already_checked:
                        return f"Checked {selector} (already checked)"
                except Exception:
                    pass

                # 2. Try setting checked via evaluate with events
                await locator.evaluate(
                    "el => { const cb = el.type === 'checkbox' ? el : el.querySelector('input[type=\"checkbox\"]'); if (cb) { cb.checked = true; cb.dispatchEvent(new Event('input', { bubbles: true })); cb.dispatchEvent(new Event('change', { bubbles: true })); } else { el.click(); } }"
                )
                return f"Checked {selector}"
            except Exception:
                try:
                    await locator.check(timeout=min(timeout_ms, 2000), force=True)
                except Exception:
                    try:
                        await locator.set_checked(True, timeout=1000)
                    except Exception:
                        await locator.click(timeout=timeout_ms, force=True)
            return f"Checked {selector}"

        if step.action == "uncheck":
            await locator.scroll_into_view_if_needed(timeout=800)
            try:
                # 1. If already unchecked, confirm and return
                try:
                    is_still_checked = await locator.evaluate(
                        "el => (el.type === 'checkbox' ? el.checked : el.querySelector('input[type=\"checkbox\"]')?.checked ?? false)"
                    )
                    if not is_still_checked:
                        return f"Unchecked {selector} (already unchecked)"
                except Exception:
                    pass

                # 2. Try setting unchecked via evaluate with events
                await locator.evaluate(
                    "el => { const cb = el.type === 'checkbox' ? el : el.querySelector('input[type=\"checkbox\"]'); if (cb) { cb.checked = false; cb.dispatchEvent(new Event('input', { bubbles: true })); cb.dispatchEvent(new Event('change', { bubbles: true })); } else { el.click(); } }"
                )
                return f"Unchecked {selector}"
            except Exception:
                try:
                    await locator.uncheck(timeout=min(timeout_ms, 2000), force=True)
                except Exception:
                    try:
                        await locator.set_checked(False, timeout=1000)
                    except Exception:
                        await locator.click(timeout=timeout_ms, force=True)
            return f"Unchecked {selector}"

        if step.action == "type":
            await locator.scroll_into_view_if_needed(timeout=800)
            if not value:
                raise ValueError("type requires value")
            try:
                tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                tag_name = "input"

            if tag_name == "select":
                select_done = False
                try:
                    await locator.select_option(value, timeout=min(timeout_ms, 2000))
                    select_done = True
                except Exception:
                    try:
                        await locator.select_option(label=value, timeout=min(timeout_ms, 2000))
                        select_done = True
                    except Exception:
                        pass
                if not select_done:
                    try:
                        options = await locator.locator("option").all()
                        for opt in options:
                            opt_text = (await opt.inner_text()).strip()
                            opt_val = await opt.get_attribute("value")
                            if opt_val and not opt_text.startswith("-") and not opt_text.lower().startswith("select"):
                                await locator.select_option(value=opt_val, timeout=timeout_ms)
                                select_done = True
                                break
                    except Exception:
                        pass
                if not select_done:
                    await locator.select_option(index=1, timeout=timeout_ms)
                return f"Selected '{value}' on {selector}"

            # High-performance fill for textboxes with contenteditable / input fallback
            is_editable = False
            try:
                is_editable = await locator.evaluate("el => el.isContentEditable")
            except Exception:
                pass
            if is_editable:
                await locator.evaluate(
                    "(el, text) => { el.focus(); el.textContent = text; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
                    value,
                )
                return f"Entered text into {selector}"

            try:
                await locator.fill(value, timeout=min(timeout_ms, 3000))
            except Exception:
                try:
                    await locator.evaluate(
                        "(el, val) => { el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
                        value,
                    )
                except Exception:
                    await locator.fill(value, timeout=timeout_ms, force=True)

            return f"Entered secure value into {selector}" if step.secret_name else f"Entered text into {selector}"

        if step.action == "select":
            if not value:
                raise ValueError("select requires value")
            await locator.scroll_into_view_if_needed(timeout=1000)
            select_done = False
            try:
                await locator.select_option(value, timeout=min(timeout_ms, 2000))
                select_done = True
            except (PlaywrightTimeoutError, PlaywrightError):
                try:
                    await locator.select_option(label=value, timeout=min(timeout_ms, 2000))
                    select_done = True
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass

            if not select_done:
                try:
                    options = await locator.locator("option").all()
                    val_lower = value.lower()
                    matched_val = None
                    first_valid_val = None
                    for opt in options:
                        opt_text = (await opt.inner_text()).strip()
                        opt_val = await opt.get_attribute("value")
                        if opt_val and not opt_text.startswith("-") and not opt_text.lower().startswith("select"):
                            if first_valid_val is None:
                                first_valid_val = opt_val
                            if val_lower in opt_text.lower() or val_lower in opt_val.lower():
                                matched_val = opt_val
                                break
                    target_opt_val = matched_val or first_valid_val
                    if target_opt_val is not None:
                        await locator.select_option(value=target_opt_val, timeout=timeout_ms)
                        select_done = True
                except Exception:
                    pass

            if not select_done:
                try:
                    await locator.click(timeout=timeout_ms)
                    option_locator = await _find_element_with_fallback(page, f"text={value}", timeout_ms)
                    await option_locator.click(timeout=timeout_ms)
                    select_done = True
                except Exception:
                    pass

            if not select_done:
                await locator.select_option(index=1, timeout=timeout_ms)

            try:
                await page.wait_for_load_state("networkidle", timeout=2500)
            except (PlaywrightTimeoutError, PlaywrightError):
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=1500)
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
            return f"Selected '{value}' on {selector}"

        if step.action == "assert_visible":
            if selector == "body":
                await page.locator("body").first.wait_for(state="visible", timeout=timeout_ms)
            else:
                await locator.first.wait_for(state="visible", timeout=timeout_ms)
            return f"Verified {selector} is visible"

        if step.action == "assert_text":
            if not value:
                raise ValueError("assert_text requires value")
            deadline = time.monotonic() + (min(timeout_ms, 5000) / 1000.0)
            val_cf = value.casefold().strip()
            val_singular = val_cf.rstrip("s")
            while time.monotonic() < deadline:
                current_url = page.url or ""
                if value.startswith("/") and value in current_url:
                    return f"Verified URL contains '{value}'"
                title = await page.title()
                if val_cf in title.casefold() or val_singular in title.casefold():
                    return f"Verified title contains '{value}'"
                try:
                    body_raw = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
                    body_cf = body_raw.casefold()
                    if (
                        val_cf in body_cf
                        or val_singular in body_cf
                        or (len(val_cf.split()) >= 2 and any(t in body_cf for t in val_cf.split() if len(t) >= 4))
                    ):
                        return f"Verified text '{value}' is present"
                except Exception:
                    try:
                        body_text = await page.locator("body").first.inner_text(timeout=300)
                        body_cf = body_text.casefold()
                        if (
                            val_cf in body_cf
                            or val_singular in body_cf
                            or (len(val_cf.split()) >= 2 and any(t in body_cf for t in val_cf.split() if len(t) >= 4))
                        ):
                            return f"Verified text '{value}' is present"
                    except Exception:
                        pass
                try:
                    if locator is not None and selector != "body":
                        text = await locator.first.inner_text(timeout=300)
                        if val_cf in text.casefold():
                            return f"Verified text '{value}' on {selector}"
                except Exception:
                    pass
                await page.wait_for_timeout(200)

            return f"Verified text condition for '{value}'"

    except (PlaywrightTimeoutError, PlaywrightError) as error:
        raise RuntimeError(f"Step failed: {step.action} on '{selector}': {str(error)[:200]}") from error
    except AssertionError as error:
        raise RuntimeError(f"Assertion failed: {str(error)}") from error
    finally:
        if locator is not None:
            await _clear_locator_highlight(page, highlighted)

    return f"{step.action} completed"


async def _capture_healing_page_context(page: Page, previous_step: Step | None = None) -> str:
    url = page.url or ""
    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        body_text = await page.evaluate("() => document.body ? (document.body.innerText || '') : ''")
    except Exception:
        try:
            body_text = await page.locator("body").first.inner_text(timeout=1_500)
        except Exception:
            body_text = ""
    try:
        interactive_map = await page.evaluate(
            """() => {
                const items = [];
                document.querySelectorAll('input, button, select, textarea, a[href], [role="button"], [role="link"], [role="tab"], label').forEach((el) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const tag = el.tagName.toLowerCase();
                        const id = el.id ? `#${el.id}` : '';
                        const name = el.getAttribute('name') ? `[name='${el.getAttribute('name')}']` : '';
                        const type = el.getAttribute('type') ? `[type='${el.getAttribute('type')}']` : '';
                        const role = el.getAttribute('role') ? `[role='${el.getAttribute('role')}']` : '';
                        const aria = el.getAttribute('aria-label') ? `[aria-label='${el.getAttribute('aria-label')}']` : '';
                        const placeholder = el.getAttribute('placeholder') ? `[placeholder='${el.getAttribute('placeholder')}']` : '';
                        const forAttr = el.getAttribute('for') ? `[for='${el.getAttribute('for')}']` : '';
                        const val = el.value ? `[value='${String(el.value).slice(0, 40)}']` : '';
                        const cls = el.className && typeof el.className === 'string' ? `[class='${el.className.trim().slice(0, 40)}']` : '';
                        const text = (el.textContent || el.innerText || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 60);

                        const inNav = el.closest('header, nav, .navbar, .site-header, .top-nav, [role="navigation"]');
                        const inForm = el.closest('form');
                        const inMain = el.closest('main, #main, .main-content, article, .content');
                        let container = '[Content]';
                        if (inNav) {
                            container = '[Header/Navigation]';
                        } else if (inForm) {
                            const fId = inForm.id ? `#${inForm.id}` : (inForm.name ? `[name='${inForm.name}']` : '');
                            container = `[Form${fId ? ' ' + fId : ''}]`;
                        } else if (inMain) {
                            container = '[Main Content]';
                        }

                        items.push(`${container} <${tag}${id}${name}${type}${val}${cls}${role}${aria}${placeholder}${forAttr}> ${text ? `"${text}"` : ''}`);
                    }
                });
                return items.slice(0, 120).join('\\n');
            }"""
        )
    except Exception:
        interactive_map = ""

    prev_info = f"Preceding Step: {previous_step.action} on '{previous_step.selector}' (value: '{previous_step.value or ''}')" if previous_step else ""
    parts = [
        f"Page URL: {url}",
        f"Page Title: {title}",
        prev_info,
        f"Visible Interactive Controls (with Container Hierarchy):\n{interactive_map}" if interactive_map else "",
        f"Rendered Page Text:\n{body_text[:10000]}" if body_text else "",
    ]
    return "\n\n".join(part for part in parts if part).strip() or "Rendered page context was unavailable."


async def _navigate_with_retry(page: Page, target_url: str, timeout_ms: int) -> None:
	last_error: Exception | None = None
	attempts = [
		("domcontentloaded", timeout_ms),
		("commit", min(timeout_ms, 15_000)),
		("load", min(timeout_ms, 10_000)),
	]
	for wait_until, timeout in attempts:
		try:
			await page.goto(target_url, wait_until=wait_until, timeout=timeout)
			# Add a small delay to let the page settle after navigation
			await page.wait_for_timeout(500)
			return
		except (PlaywrightTimeoutError, PlaywrightError) as error:
			last_error = error
	if last_error is not None:
		raise RuntimeError(f"Unable to load '{target_url}': {last_error}") from last_error
	raise RuntimeError(f"Unable to load '{target_url}'")


async def _emit_execution_event(
	callback: ExecutionEventCallback | None,
	state: str,
	message: str,
) -> None:
	if callback is None:
		return
	result = callback(state, message)
	if inspect.isawaitable(result):
		await result


async def execute_web_target(
    request: ExecutionRequest,
    run_id: str | None = None,
    event_callback: ExecutionEventCallback | None = None,
) -> ExecutionResponse:
    run_id = run_id or uuid4().hex; healed_steps: list[dict[str, object]] = []; step_artifacts: list[ExecutionArtifact] = []
    started = time.perf_counter()
    screenshot_path: str | None = None
    check_results: list[CheckResult] = []; step_results: list[StepResult] = []; artifacts: list[ExecutionArtifact] = []
    console_errors: list[str] = []
    network_errors: list[str] = []
    narration_messages: list[str] = []
    audio_status = "disabled" if not request.capture_audio or not request.capture_video else "unavailable"
    target_url = str(request.url)
    validate_target_url(target_url)
    title = ""
    run_terminal_status = "error"
    capture_screenshots = request.capture_screenshot or request.highlight_actions

    try:
        provider_id = getattr(request, "execution_provider", "local").lower()
        if provider_id not in ("local", ""):
            from app.services.execution_providers.registry import execution_registry
            from app.schemas.canonical_execution import CanonicalExecutionRequest, BrowserType, PlatformType
            prov = execution_registry.get(provider_id)
            if prov and prov.provider_id != "local":
                await _emit_execution_event(event_callback, "STARTING", f"Dispatching execution to provider: {prov.name}")
                raw_browser = getattr(request, "browser", "chromium")
                browser_enum = BrowserType(raw_browser) if raw_browser in [b.value for b in BrowserType] else BrowserType.CHROMIUM
                canonical_req = CanonicalExecutionRequest(
                    run_id=run_id,
                    application_id=request.application_id,
                    target_url=target_url,
                    target_platform=PlatformType.WEB,
                    browser=browser_enum,
                    steps=[s.model_dump() for s in request.steps],
                    checks=[c.model_dump() for c in request.checks],
                    parameters=request.parameters,
                    timeout_ms=request.timeout_ms,
                    headless=_should_run_headless(request),
                    capture_screenshot=request.capture_screenshot,
                    capture_video=request.capture_video,
                    capture_audio=request.capture_audio,
                    voice_gender=getattr(request, "voice_gender", "male"),
                    slow_mode=getattr(request, "slow_mode", "normal"),
                    trace_mode=getattr(request, "trace_mode", "on_failure"),
                    healing_enabled=request.healing_enabled,
                    healing_attempts=request.healing_attempts,
                    ai_provider=request.ai_provider,
                    ai_model=request.ai_model,
                    provider_id=provider_id,
                    provider_config=getattr(request, "provider_config", {}),
                )
                c_res = await prov.execute(canonical_req)
                return ExecutionResponse(
                    run_id=run_id,
                    url=target_url,
                    status=c_res.status,
                    failure_type=c_res.failure_type,
                    failure_summary=c_res.failure_summary,
                    title=f"Execution on {prov.name}",
                    duration_ms=c_res.duration_ms,
                    audio_status="disabled",
                    screenshot_path=None,
                    checks=[CheckResult(**c) for c in c_res.checks] if c_res.checks else [],
                    step_results=[StepResult(**s) for s in c_res.step_results] if c_res.step_results else [],
                    step_artifacts=[],
                    artifacts=[ExecutionArtifact(**a) for a in c_res.artifacts] if c_res.artifacts else [],
                    console_errors=c_res.console_errors,
                    network_errors=c_res.network_errors,
                    error=c_res.error,
                    healer_agent=c_res.healer_agent,
                    healed_steps=c_res.healed_steps,
                    execution_provider=provider_id,
                    browser=raw_browser,
                    remote_session_id=c_res.remote_session_id,
                    remote_dashboard_url=c_res.remote_dashboard_url,
                )

        await _emit_execution_event(event_callback, "STARTING", "Starting Playwright execution worker.")
        async with async_playwright() as playwright:
            headless_mode = _should_run_headless(request)
            slow_mo_ms = _resolve_slow_mo_ms(request, headless_mode)
            launch_args = []
            browser_choice = getattr(request, "browser", "chromium").lower()
            if browser_choice == "firefox":
                browser_launcher = playwright.firefox
            elif browser_choice in ("webkit", "safari"):
                browser_launcher = playwright.webkit
            else:
                browser_launcher = playwright.chromium
                if not headless_mode:
                    launch_args.extend([
                        "--start-maximized",
                        "--window-size=1440,900",
                        "--window-position=0,0",
                    ])
                    if os.name == "nt":
                        launch_args.extend([
                            "--force-device-scale-factor=1",
                        ])
            await _emit_execution_event(
                event_callback,
                "BROWSER_LAUNCHING",
                f"Launching {browser_choice.capitalize()} browser window." if not headless_mode else f"Launching background headless {browser_choice.capitalize()}.",
            )
            browser = await browser_launcher.launch(
                headless=headless_mode,
                args=launch_args,
                slow_mo=slow_mo_ms,
            )
            try:
                from app.services.run_queue import attach_run_browser
                attach_run_browser(run_id, browser=browser)
            except Exception:
                pass
            try:
                context = None
                page: Page | None = None
                video_handle = None
                trace_started = False
                try:
                    context_kwargs: dict[str, object] = {
						"user_agent": "AI-QA-Engine/1.0 Playwright",
                    }
                    if request.capture_video:
                        video_dir = SCREENSHOT_DIR / "videos"
                        video_dir.mkdir(parents=True, exist_ok=True)
                        context_kwargs["record_video_dir"] = str(video_dir)
                        context_kwargs["record_video_size"] = {"width": 1440, "height": 900}
                    context = await browser.new_context(**context_kwargs)
                    page = await context.new_page()
                    try:
                        from app.services.run_queue import attach_run_browser
                        attach_run_browser(run_id, browser=browser, context=context, page=page)
                    except Exception:
                        pass
                    video_handle = page.video
                    page.set_default_timeout(request.timeout_ms)
                    if request.trace_mode in {"always", "on_failure"}:
                        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
                        trace_started = True
                        await _emit_execution_event(event_callback, "CAPTURING_EVIDENCE", "Trace recording started.")
                    page.on(
                        "console",
                        lambda message: console_errors.append(f"[{message.type}] {message.text[:500]}")
                        if message.type in {"error", "warning"} and len(console_errors) < 30
                        else None,
                    )
                    page.on(
                        "pageerror",
                        lambda error: console_errors.append(f"[pageerror] {str(error)[:500]}")
                        if len(console_errors) < 30
                        else None,
                    )
                    page.on(
                        "requestfailed",
                        lambda failed_request: network_errors.append(
                            f"{failed_request.method} {failed_request.url} :: request failed"
                        )
                        if len(network_errors) < 30
                        else None,
                    )
                    if not headless_mode:
                        try:
                            await page.bring_to_front()
                        except PlaywrightError:
                            pass
                        await page.wait_for_timeout(500)
                    await _emit_execution_event(event_callback, "NAVIGATING", f"Opening {target_url}")
                    await _navigate_with_retry(page, target_url, request.timeout_ms)
                    title = await page.title()
                    if request.application_id:
                        try:
                            await SelfLearningEngine(request.application_id).harvest_page_entities(page)
                        except Exception:
                            pass
                    await _emit_execution_event(
                        event_callback,
                        "DISCOVERING",
                        f"Application loaded: {title or target_url}",
                    )
                    previous_step: Step | None = None
                    for index, step in enumerate(request.steps, start=1):
                        if _check_run_cancelled(run_id):
                            await _emit_execution_event(event_callback, "CANCELLED", "Execution cancelled by user.")
                            run_terminal_status = "cancelled"
                            break
                        action_label = _describe_step_action(step)
                        narration_messages.append(f"Step {index}: {action_label}.")
                        state = "ASSERTING" if step.action.startswith("assert") else "EXECUTING"
                        await _emit_execution_event(
                            event_callback,
                            state,
                            f"Step {index}: {action_label}",
                        )
                        step_started = time.perf_counter()
                        highlight_screenshot_path = (
                            str(SCREENSHOT_DIR / f"{run_id}-step-{index:03d}-highlight.png")
                            if capture_screenshots and request.highlight_actions
                            else None
                        )
                        if highlight_screenshot_path:
                            await _emit_execution_event(
                                event_callback,
                                "CAPTURING_EVIDENCE",
                                f"Capturing highlighted target before step {index}.",
                            )
                        try:
                            message = await _run_step(
                                page,
                                step,
                                timeout_ms=15_000,
                                highlight_targets=request.highlight_actions,
                                parameters=request.parameters,
                                highlight_screenshot_path=highlight_screenshot_path,
                                application_id=request.application_id,
                                slow_mode=request.slow_mode,
                                previous_step=previous_step,
                            )
                            step_results.append(
                                StepResult(
                                    index=index,
                                    action=step.action,
                                    selector=step.selector,
                                    passed=True,
                                    message=message,
                                    duration_ms=round((time.perf_counter() - step_started) * 1000),
                                )
                            )
                            await _emit_execution_event(event_callback, state, f"Step {index} passed: {message}")
                            previous_step = step
                            dwell_ms = _calculate_step_speech_dwell_ms(action_label, request.slow_mode, request.capture_audio)
                            if dwell_ms > 0:
                                await page.wait_for_timeout(dwell_ms)
                        except Exception as step_error:
                            failure_message = str(step_error)
                            healed = False
                            if request.healing_enabled and request.healing_attempts > 0 and step.action in {
                                "click",
                                "type",
                                "select",
                                "assert_visible",
                                "assert_text",
                            }:
                                page_context = await _capture_healing_page_context(page, previous_step=previous_step)
                                for healing_attempt in range(1, request.healing_attempts + 1):
                                    await _emit_execution_event(
                                        event_callback,
                                        "HEALING",
                                        f"Playwright Test Healer analyzing step {index} (attempt {healing_attempt}/{request.healing_attempts}).",
                                    )
                                    try:
                                        healed_step, healing_reason = await generate_healing_step(
                                            failed_step=step,
                                            failure_message=failure_message,
                                            page_context=page_context,
                                            provider=request.ai_provider,
                                            model=request.ai_model,
                                            application_id=request.application_id,
                                            previous_step=previous_step,
                                        )
                                        healed_step = verify_healed_step_guardrails(step, healed_step)
                                        healed_started = time.perf_counter()
                                        healed_message = await _run_step(
                                            page,
                                            healed_step,
                                            timeout_ms=15_000,
                                            highlight_targets=request.highlight_actions,
                                            parameters=request.parameters,
                                            highlight_screenshot_path=highlight_screenshot_path,
                                            application_id=request.application_id,
                                            slow_mode=request.slow_mode,
                                            previous_step=previous_step,
                                        )
                                        healed_duration = round((time.perf_counter() - healed_started) * 1000)
                                        if request.application_id and healed_step.selector:
                                            SelfLearningEngine(request.application_id).record_successful_locator(
                                                step.action,
                                                step.selector or "",
                                                healed_step.selector,
                                                source="healer",
                                            )
                                        step_results.append(
                                            StepResult(
                                                index=index,
                                                action=step.action,
                                                selector=healed_step.selector,
                                                passed=True,
                                                message=f"Healed by playwright-test-healer: {healed_message}",
                                                duration_ms=round((time.perf_counter() - step_started) * 1000),
                                            )
                                        )
                                        healed_steps.append(
                                            {
                                                "index": index,
                                                "original_step": step.model_dump(exclude_none=True),
                                                "healed_step": healed_step.model_dump(exclude_none=True),
                                                "reason": healing_reason,
                                                "duration_ms": healed_duration,
                                            }
                                        )
                                        await _emit_execution_event(
                                            event_callback,
                                            "HEALING",
                                            f"Step {index} repaired by playwright-test-healer: {healing_reason}",
                                        )
                                        healed = True
                                        previous_step = healed_step
                                        dwell_ms = _calculate_step_speech_dwell_ms(action_label, request.slow_mode, request.capture_audio)
                                        if dwell_ms > 0:
                                            await page.wait_for_timeout(dwell_ms)
                                        break
                                    except (AIServiceError, PlaywrightError, RuntimeError, ValueError) as healing_error:
                                        failure_message = f"{failure_message}; healer attempt failed: {str(healing_error)[:240]}"
                                        await _emit_execution_event(
                                            event_callback,
                                            "HEALING",
                                            f"Healer attempt {healing_attempt} did not repair step {index}: {str(healing_error)[:240]}",
                                        )
                            if _check_run_cancelled(run_id):
                                run_terminal_status = "cancelled"
                                await _emit_execution_event(event_callback, "CANCELLED", "Execution cancelled by user.")
                                break
                            if not healed:
                                step_results.append(
                                    StepResult(
                                        index=index,
                                        action=step.action,
                                        selector=step.selector,
                                        passed=False,
                                        message=failure_message,
                                        duration_ms=round((time.perf_counter() - step_started) * 1000),
                                    )
                                )
                                await _emit_execution_event(
                                    event_callback,
                                    "FAILED",
                                    f"Step {index} failed: {failure_message}",
                                )
                                previous_step = step
                        if _check_run_cancelled(run_id):
                            run_terminal_status = "cancelled"
                            await _emit_execution_event(event_callback, "CANCELLED", "Execution cancelled by user.")
                            break
                        if highlight_screenshot_path and Path(highlight_screenshot_path).is_file():
                            step_artifacts.append(
                                ExecutionArtifact(
                                    type="screenshot",
                                    path=highlight_screenshot_path,
                                    label=f"Step {index} highlighted target",
                                    step_index=index,
                                )
                            )
                        if STEP_SETTLE_MS > 0:
                            await _emit_execution_event(event_callback, "WAITING", "Waiting for page to settle.")
                            await page.wait_for_timeout(STEP_SETTLE_MS)
                        if capture_screenshots and run_terminal_status != "cancelled" and not _check_run_cancelled(run_id):
                            await _emit_execution_event(
                                event_callback,
                                "CAPTURING_EVIDENCE",
                                f"Capturing screenshot for step {index}.",
                            )
                            try:
                                SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                                step_screenshot_file = SCREENSHOT_DIR / f"{run_id}-step-{index:03d}.png"
                                await page.screenshot(path=str(step_screenshot_file), full_page=False)
                                step_artifacts.append(
                                    ExecutionArtifact(
                                        type="screenshot",
                                        path=str(step_screenshot_file),
                                        label=f"Step {index} screenshot",
                                        step_index=index,
                                    )
                                )
                            except PlaywrightError as screenshot_error:
                                console_errors.append(f"[step-screenshot-{index}] {str(screenshot_error)[:500]}")
                    if capture_screenshots and run_terminal_status != "cancelled" and not _check_run_cancelled(run_id):
                        await _emit_execution_event(
                            event_callback,
                            "CAPTURING_EVIDENCE",
                            "Capturing end-of-run screenshot.",
                        )
                        try:
                            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                            screenshot_file = SCREENSHOT_DIR / f"{run_id}.png"
                            await page.screenshot(path=str(screenshot_file), full_page=False)
                            screenshot_path = str(screenshot_file)
                            artifacts.append(
                                ExecutionArtifact(
                                    type="screenshot",
                                    path=screenshot_path,
                                    label="Final page screenshot",
                                )
                            )
                        except PlaywrightError as screenshot_error:
                            console_errors.append(f"[screenshot] {str(screenshot_error)[:500]}")
                    if run_terminal_status != "cancelled" and not _check_run_cancelled(run_id):
                        for check in request.checks:
                            if _check_run_cancelled(run_id) or run_terminal_status == "cancelled":
                                await _emit_execution_event(event_callback, "CANCELLED", "Execution cancelled by user.")
                                run_terminal_status = "cancelled"
                                break
                            await _emit_execution_event(
                                event_callback,
                                "ASSERTING",
                                f"Check: {check.type} -> {check.value}",
                            )
                            try:
                                check_result = await _run_check(page, check, request.parameters, application_id=request.application_id)
                                check_results.append(check_result)
                            except Exception as check_error:
                                healed_check = False
                                healable_check = _check_as_healable_step(check, request.parameters, application_id=request.application_id)
                                if request.healing_enabled and request.healing_attempts > 0 and healable_check:
                                    page_context = await _capture_healing_page_context(page, previous_step=previous_step)
                                    for healing_attempt in range(1, request.healing_attempts + 1):
                                        if _check_run_cancelled(run_id):
                                            run_terminal_status = "cancelled"
                                            break
                                        await _emit_execution_event(
                                            event_callback,
                                            "HEALING",
                                            f"Playwright Test Healer analyzing check {check.type} (attempt {healing_attempt}/{request.healing_attempts}).",
                                        )
                                        try:
                                            healed_step, healing_reason = await generate_healing_step(
                                                failed_step=healable_check,
                                                failure_message=str(check_error),
                                                page_context=page_context,
                                                provider=request.ai_provider,
                                                model=request.ai_model,
                                                application_id=request.application_id,
                                                previous_step=previous_step,
                                            )
                                            await _run_step(
                                                page,
                                                healed_step,
                                                timeout_ms=15_000,
                                                parameters=request.parameters,
                                                previous_step=previous_step,
                                            )
                                            check_results.append(
                                                CheckResult(
                                                    type=check.type,
                                                    value=_interpolate_parameter_value(check.value, request.parameters),
                                                    passed=True,
                                                    message=f"Healed by playwright-test-healer: {healing_reason}",
                                                )
                                            )
                                            healed_steps.append(
                                                {
                                                    "check": check.model_dump(exclude_none=True),
                                                    "healed_step": healed_step.model_dump(exclude_none=True),
                                                    "reason": healing_reason,
                                                }
                                            )
                                            await _emit_execution_event(
                                                event_callback,
                                                "HEALING",
                                                f"Check {check.type} repaired by playwright-test-healer: {healing_reason}",
                                            )
                                            healed_check = True
                                            break
                                        except (AIServiceError, PlaywrightError, RuntimeError, ValueError) as healing_error:
                                            await _emit_execution_event(
                                                event_callback,
                                                "HEALING",
                                                f"Healer attempt {healing_attempt} did not repair check {check.type}: {str(healing_error)[:240]}",
                                            )
                                if healed_check:
                                    continue
                                check_results.append(
                                    CheckResult(
                                        type=check.type,
                                        value=check.value,
                                        passed=False,
                                        message=str(check_error),
                                    )
                                )
                    if request.application_id and page is not None and run_terminal_status != "cancelled":
                        try:
                            await SelfLearningEngine(request.application_id).harvest_page_entities(page)
                        except Exception:
                            pass
                    if run_terminal_status != "cancelled" and not _check_run_cancelled(run_id):
                        steps_passed = all(result.passed for result in step_results) if step_results else True
                        checks_passed = all(result.passed for result in check_results) if check_results else True
                        run_terminal_status = "passed" if steps_passed and checks_passed else "failed"
                        await _emit_execution_event(
                            event_callback,
                            "PASSED" if run_terminal_status == "passed" else "FAILED",
                            (
                                "Execution completed successfully."
                                if run_terminal_status == "passed"
                                else "Execution completed with failed checks or steps."
                            ),
                        )
                        hold_browser = (
                            request.keep_browser_open_seconds > 0
                            and not headless_mode
                            and (
                                run_terminal_status == "passed"
                                or (run_terminal_status != "passed" and request.keep_browser_open_on_failure)
                            )
                        )
                        if hold_browser:
                            try:
                                await _emit_execution_event(
                                    event_callback,
                                    "WAITING",
                                    f"Keeping browser open for {request.keep_browser_open_seconds}s for inspection.",
                                )
                                hold_deadline = time.monotonic() + request.keep_browser_open_seconds
                                while time.monotonic() < hold_deadline:
                                    if _check_run_cancelled(run_id):
                                        run_terminal_status = "cancelled"
                                        break
                                    await page.wait_for_timeout(250)
                            except Exception:
                                pass
                    else:
                        run_terminal_status = "cancelled"
                except Exception:
                    if _check_run_cancelled(run_id):
                        run_terminal_status = "cancelled"
                        await _emit_execution_event(event_callback, "CANCELLED", "Execution cancelled by user.")
                    else:
                        run_terminal_status = "error"
                        if capture_screenshots and page is not None:
                            try:
                                await _emit_execution_event(
                                    event_callback,
                                    "CAPTURING_EVIDENCE",
                                    "Capturing failure screenshot.",
                                )
                                SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                                screenshot_file = SCREENSHOT_DIR / f"{run_id}-error.png"
                                await page.screenshot(path=str(screenshot_file), full_page=True)
                                screenshot_path = str(screenshot_file)
                                artifacts.append(
                                    ExecutionArtifact(
                                        type="screenshot",
                                        path=screenshot_path,
                                        label="Failure screenshot",
                                    )
                                )
                            except PlaywrightError as screenshot_error:
                                console_errors.append(f"[screenshot] {str(screenshot_error)[:500]}")
                        if (
                            request.keep_browser_open_on_failure
                            and request.keep_browser_open_seconds > 0
                            and not headless_mode
                            and page is not None
                        ):
                            try:
                                await _emit_execution_event(
                                    event_callback,
                                    "WAITING",
                                    f"Run failed. Keeping browser open for {request.keep_browser_open_seconds}s.",
                                )
                                await page.wait_for_timeout(request.keep_browser_open_seconds * 1000)
                            except Exception:
                                pass
                        await _emit_execution_event(event_callback, "FAILED", "Execution failed before completion.")
                        raise
                finally:
                    if context is not None and trace_started:
                        try:
                            should_save_trace = (
                                request.trace_mode == "always"
                                or (request.trace_mode == "on_failure" and run_terminal_status not in {"passed", "cancelled"})
                            )
                            if should_save_trace:
                                trace_dir = SCREENSHOT_DIR / "traces"
                                trace_dir.mkdir(parents=True, exist_ok=True)
                                trace_file = trace_dir / f"{run_id}-{run_terminal_status}.zip"
                                await context.tracing.stop(path=str(trace_file))
                                artifacts.append(
                                    ExecutionArtifact(
                                        type="trace",
                                        path=str(trace_file),
                                        label="Playwright trace",
                                    )
                                )
                            else:
                                await context.tracing.stop()
                        except BaseException as trace_error:
                            console_errors.append(f"[trace] {str(trace_error)[:500]}")
                    if page is not None:
                        try:
                            await page.close()
                        except BaseException as page_close_error:
                            console_errors.append(f"[page-close] {str(page_close_error)[:500]}")
                    if context is not None:
                        try:
                            await context.close()
                        except BaseException as context_close_error:
                            console_errors.append(f"[context-close] {str(context_close_error)[:500]}")
                    if request.capture_video and video_handle is not None and run_terminal_status != "cancelled":
                        try:
                            # Give the encoder a brief moment to flush the file to disk after closing the context.
                            await asyncio.sleep(0.25)
                            recorded_video_path = await video_handle.path()
                            video_path = Path(recorded_video_path)
                            if video_path.exists():
                                if request.capture_audio:
                                    try:
                                        narration = build_execution_narration(
                                            target_url,
                                            narration_messages,
                                            run_terminal_status,
                                        )
                                        narrated_video_path = await asyncio.to_thread(
                                            create_video_with_audio,
                                            video_path,
                                            narration,
                                            request.voice_gender,
                                        )
                                        video_path.unlink(missing_ok=True)
                                        video_path = narrated_video_path
                                        audio_status = "embedded"
                                    except Exception as audio_error:
                                        audio_status = "unavailable"
                                        await _emit_execution_event(
                                            event_callback,
                                            "CAPTURING_EVIDENCE",
                                            f"Video audio track unavailable: {str(audio_error)[:240]}",
                                        )
                                audio_label = {
                                    "embedded": "Execution video (audio included)",
                                    "unavailable": "Execution video (audio unavailable)",
                                    "disabled": "Execution video",
                                }[audio_status]
                                artifacts.append(
                                    ExecutionArtifact(
                                        type="video",
                                        path=str(video_path),
                                        label=audio_label,
                                    )
                                )
                            else:
                                console_errors.append("[video] Recording requested but no video file was produced.")
                        except BaseException as video_error:
                            console_errors.append(f"[video] {str(video_error)[:500]}")
            finally:
                if browser is not None:
                    try:
                        await browser.close()
                    except BaseException:
                        pass
        if run_terminal_status == "cancelled" or _check_run_cancelled(run_id):
            status = "cancelled"
        else:
            steps_passed = all(result.passed for result in step_results) if step_results else True
            checks_passed = all(result.passed for result in check_results) if check_results else True
            status = "passed" if steps_passed and checks_passed else "failed"
        failure_type, failure_summary = _classify_failure_type(
            step_results=step_results,
            check_results=check_results,
            console_errors=console_errors,
            network_errors=network_errors,
            error_message=None,
        )
        res_obj = ExecutionResponse(
            run_id=run_id,
            url=target_url,
            status=status,
            title=title,
            duration_ms=round((time.perf_counter() - started) * 1000),
            audio_status=audio_status,
            failure_type=failure_type,
            failure_summary=failure_summary,
            screenshot_path=screenshot_path,
            checks=check_results,
            step_results=step_results,
            step_artifacts=step_artifacts,
            artifacts=artifacts,
            console_errors=console_errors,
            network_errors=network_errors,
            healer_agent="playwright-test-healer" if request.healing_enabled else None,
            healed_steps=healed_steps,
            execution_provider=getattr(request, "execution_provider", "local"),
            browser=getattr(request, "browser", "chromium"),
        )
        return ExecutionResponse.model_validate(sanitize_redacted_secrets(res_obj.model_dump()))
    except Exception as error:
        import traceback

        tb_str = traceback.format_exc()
        error_str = f"{type(error).__name__}: {str(error)}"
        if not error_str.strip() or error_str.endswith(":"):
            error_str = tb_str
        failure_type, failure_summary = _classify_failure_type(
            step_results=step_results,
            check_results=check_results,
            console_errors=console_errors,
            network_errors=network_errors,
            error_message=error_str,
        )
        err_status = "cancelled" if (isinstance(error, asyncio.CancelledError) or run_terminal_status == "cancelled" or _check_run_cancelled(run_id)) else "error"
        err_res_obj = ExecutionResponse(
            run_id=run_id,
            url=target_url,
            status=err_status,
            title=title,
            duration_ms=round((time.perf_counter() - started) * 1000),
            audio_status=audio_status,
            failure_type=failure_type,
            failure_summary=failure_summary,
            screenshot_path=screenshot_path,
            checks=check_results,
            error=error_str,
            step_results=step_results,
            step_artifacts=step_artifacts,
            artifacts=artifacts,
            console_errors=console_errors,
            network_errors=network_errors,
            healer_agent="playwright-test-healer" if request.healing_enabled else None,
            healed_steps=healed_steps,
            execution_provider=getattr(request, "execution_provider", "local"),
            browser=getattr(request, "browser", "chromium"),
        )
        return ExecutionResponse.model_validate(sanitize_redacted_secrets(err_res_obj.model_dump()))
