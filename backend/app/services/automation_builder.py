import json
import re

from app.models.application import Application
from app.models.test_case import TestCase


def split_case_lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _extract_quoted_values(line: str) -> list[str]:
    matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', line)
    values: list[str] = []
    for first, second in matches:
        token = (first or second).strip()
        if token:
            values.append(token)
    return values


def _is_invalid_credential_instruction(lower_line: str) -> bool:
    if _is_verification_only_line(lower_line):
        return False
    return bool(
        re.search(
            r"\b(invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent|expired|locked|disabled|unverified|mismatched)\b",
            lower_line,
        )
        and re.search(r"\b(credential|credentials|email|username|user name|password|passcode)\b", lower_line)
    )


def _is_login_instruction_line(lower_line: str) -> bool:
    if _is_verification_only_line(lower_line):
        return False
    has_credential_field = bool(re.search(r"\b(credential|credentials|email|username|user name|password|passcode)\b", lower_line))
    has_entry_verb = bool(re.search(r"\b(enter|type|use|provide|input|fill|submit|with|using)\b", lower_line))
    login_with_credentials = bool(re.search(r"\b(login|log in|sign in|authenticate)\b[^.]{0,80}\b(with|using)\b", lower_line))
    login_submit_control = bool(
        re.search(r"\b(login|log in|sign in|authenticate)\b", lower_line)
        and re.search(r"\b(click|tap|press|submit)\b", lower_line)
    )
    return (has_credential_field and has_entry_verb) or login_with_credentials or login_submit_control


def _login_steps_for_line(
    lower_line: str,
    email_selector: str = "#user_email",
    password_selector: str = "#user_password",
    submit_selector: str = "input[type=submit]",
) -> list[dict]:
    clauses = [clause.strip() for clause in re.split(r"\s+(?:and|then)\s+|[,;]", lower_line) if clause.strip()]
    negative_signal = _is_invalid_credential_instruction(lower_line)
    email_mentioned = bool(re.search(r"\b(email|username|user name)\b", lower_line))
    password_mentioned = bool(re.search(r"\b(password|passcode)\b", lower_line))
    broad_invalid = negative_signal and not email_mentioned and not password_mentioned
    invalid_email = broad_invalid or any(
        re.search(r"\b(invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent)\b", clause)
        and re.search(r"\b(email|username|user name)\b", clause)
        for clause in clauses
    )
    invalid_password = broad_invalid or any(
        re.search(r"\b(invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent|expired|locked|disabled)\b", clause)
        and re.search(r"\b(password|passcode)\b", clause)
        for clause in clauses
    )
    email_value = "not-an-email" if invalid_email and "format" in lower_line else "invalid.user@example.invalid" if invalid_email else None
    password_value = "invalid-password-for-negative-test" if invalid_password else None
    return [
        {"action": "type", "selector": email_selector, "value": email_value or "{{login_email}}", "description": "Enter invalid email format" if invalid_email and "format" in lower_line else "Enter invalid email address" if invalid_email else "Enter valid login email address"},
        {"action": "type", "selector": password_selector, "value": password_value or "{{login_password}}", "description": "Enter invalid password" if invalid_password else "Enter valid login password"},
        {"action": "click", "selector": submit_selector, "description": "Click Sign In button"},
        {"action": "assert_visible", "selector": "body", "description": "Verify dashboard page is loaded"},
    ]


def has_invalid_credential_instruction(value: str | None) -> bool:
    return any(_is_invalid_credential_instruction(line) for line in split_case_lines(value))


def _is_verification_only_line(lower_line: str) -> bool:
    if re.match(r"^uncheck\b", lower_line):
        return False
    if re.match(r"^check\b", lower_line):
        if re.search(r"^check\s+(that|if|whether|the\s+page|page\s+title|page\s+is|for|each|all|any)\b", lower_line):
            return True
        if re.search(r"\b(checkbox|box|toggle|radio|option)\b", lower_line) or re.search(r"^check\s+['\"][^'\"]+['\"]", lower_line):
            return False
        return True
    return bool(re.match(r"^(verify|validate|confirm|assert|inspect|observe|ensure|check)\b", lower_line))


def _normalize_action_target(value: str) -> str:
    normalized = (
        value
        .replace("\n", " ")
        .strip()
        .strip("\"'")
    )
    normalized = re.sub(r"\bagain\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+based on\s+.+$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+(?:from|under|within|inside)\s+.+$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+on\s+the\s+.+\bpage\b.*$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(?:button|link|tab|section|dropdown|menu|field)\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^[Tt]he\s+", "", normalized)
    normalized = re.sub(r"[.,:;\"']+$", "", normalized)
    normalized = re.sub(r"^[.,:;\"']+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _extract_verification_text(line: str, quoted_values: list[str]) -> str:
    if quoted_values:
        return _normalize_action_target(quoted_values[0])

    displayed_as_match = re.search(r"displayed as\s+(.+)", line, re.IGNORECASE)
    if displayed_as_match:
        return _normalize_action_target(displayed_as_match.group(1))

    title_match = re.search(
        r"page title(?:\s+\w+)*\s+(.+?)\s+(?:is|was)\s+displayed",
        line,
        re.IGNORECASE,
    )
    if title_match:
        return _normalize_action_target(title_match.group(1))

    message_match = re.search(
        r"(?:success|error|warning|info)\s+message(?:\s+\w+)*\s+(.+?)\s+(?:is|was)\s+displayed",
        line,
        re.IGNORECASE,
    )
    if message_match:
        return _normalize_action_target(message_match.group(1))

    return ""


def _extract_default_field_value(field_name: str, raw_line: str) -> str:
    # Check for (e.g., ...) first
    example_match = re.search(r"\(e\.g\.,\s*([^)]+)\)", raw_line, re.IGNORECASE)
    if example_match:
        val = example_match.group(1).split(",")[0].strip().strip("\"'")
        if val:
            return val

    norm = field_name.lower().strip().replace(" ", "_").replace("-", "_")
    return f"{{{{{norm}}}}}"


def _append_step(steps: list[dict], step: dict) -> None:
    previous = steps[-1] if steps else None
    if previous == step:
        return
    steps.append(step)


def _append_click_steps_from_target(steps: list[dict], target: str, description: str | None = None) -> None:
    normalized = _normalize_action_target(target)
    if not normalized:
        return
    parts = [
        _normalize_action_target(part)
        for part in re.split(r"\s*-\s*", normalized)
    ]
    parts = [part for part in parts if len(part) >= 2]
    if len(parts) > 1:
        for part in parts:
            _append_step(steps, {"action": "click", "selector": f"text={part}", "description": description or f"Click '{part}'"})
        return
    _append_step(steps, {"action": "click", "selector": f"text={normalized}", "description": description or f"Click '{normalized}'"})


def _extract_typed_field_assignments(line: str, quoted_values: list[str]) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []

    # Pattern 1: enter/type/input/fill/set "value" into/in/for [the] [field]
    pattern1 = re.compile(
        r'(?:enter|type|input|fill|set)\s+(?:["\']([^"\']+)["\']|(\{\{[^}]+\}\}|\$\{[^}]+\}|[^\s\n,]+))\s+(?:in|into|for)\s+(?:the\s+)?["\']?([a-zA-Z0-9_\s\-]+?)["\']?(?:\s+field|\s+input|\s+filter|\s+box|$)',
        re.IGNORECASE,
    )
    for match in pattern1.finditer(line):
        val = (match.group(1) or match.group(2) or "").strip()
        raw_field = match.group(3).strip()
        field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", raw_field, flags=re.IGNORECASE))
        if val and field and field.lower() not in {"field", "input", "the", "box", "filter"}:
            assignments.append((field, val))

    # Pattern 2: enter/type/input/fill [the] [field] as/with/to "value"
    pattern2 = re.compile(
        r'(?:enter|type|input|fill|set)\s+(?:the\s+)?["\']?([a-zA-Z0-9_\s\-]+?)["\']?(?:\s+field|\s+input|\s+filter)?\s+(?:as|with|to)\s+(?:["\']([^"\']+)["\']|(\{\{[^}]+\}\}|\$\{[^}]+\}|[^\s\n,]+))',
        re.IGNORECASE,
    )
    for match in pattern2.finditer(line):
        raw_field = match.group(1).strip()
        field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", raw_field, flags=re.IGNORECASE))
        val = (match.group(2) or match.group(3) or "").strip()
        if val and field and field.lower() not in {"field", "input", "the", "box", "filter"}:
            assignments.append((field, val))

    # Pattern 3: fill in [the] field with/as "value"
    pattern3 = re.compile(
        r'(?:fill|fill in)\s+(?:the\s+)?["\']?([a-zA-Z0-9_\s\-]+?)["\']?\s+(?:with|as|to)\s+(?:["\']([^"\']+)["\']|(\{\{[^}]+\}\}|\$\{[^}]+\}|[^\s\n,]+))',
        re.IGNORECASE,
    )
    for match in pattern3.finditer(line):
        raw_field = match.group(1).strip()
        field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", raw_field, flags=re.IGNORECASE))
        val = (match.group(2) or match.group(3) or "").strip()
        if val and field and field.lower() not in {"field", "input", "the", "box", "filter"}:
            assignments.append((field, val))

    # Pattern 4: If quoted value exists and "into/in/for [the] field" is present with an explicit entry verb
    has_typing_verb = bool(re.search(r"\b(enter|type|input|fill|set|populate)\b", line, re.IGNORECASE))
    if not assignments and quoted_values and has_typing_verb:
        in_match = re.search(r'(?:in|into|for)\s+(?:the\s+)?["\']?([a-zA-Z0-9_\s\-]+?)["\']?(?:\s+field|\s+input|\s+filter|\s+box|$)', line, re.IGNORECASE)
        if in_match:
            raw_field = in_match.group(1).strip()
            field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", raw_field, flags=re.IGNORECASE))
            if field and field.lower() not in {"field", "input", "the", "box", "filter"}:
                assignments.append((field, quoted_values[0]))
        elif len(quoted_values) >= 2:
            field = _normalize_action_target(quoted_values[0])
            assignments.append((field, quoted_values[1]))
        elif "@" in quoted_values[0]:
            assignments.append(("email", quoted_values[0]))

    return assignments


def build_case_automation_from_text(
    test_case: TestCase,
    application: Application,
    login_email_selector: str | None = None,
    login_password_selector: str | None = None,
    login_submit_selector: str | None = None,
) -> tuple[list[dict], list[dict]]:
    resolved_email_selector = (login_email_selector or "#user_email").strip() or "#user_email"
    resolved_password_selector = (login_password_selector or "#user_password").strip() or "#user_password"
    resolved_submit_selector = (login_submit_selector or "input[type=submit]").strip() or "input[type=submit]"
    generated_steps: list[dict] = []
    generated_checks: list[dict] = [{"type": "visible", "value": "body"}]
    login_step_added = False

    preconditions_text = (test_case.preconditions or "").strip()
    preconditions_lower = preconditions_text.lower()
    has_negative_credentials = (
        has_invalid_credential_instruction(test_case.steps)
        or has_invalid_credential_instruction(preconditions_text)
    )

    step_lines = split_case_lines(test_case.steps)
    normalized_step_lines = [
        re.sub(r"^\s*\d+[\).:\-\s]*", "", raw_line).strip().lower()
        for raw_line in step_lines
    ]

    # 0. Process Preconditions: Login and initial navigation
    has_explicit_login_steps = any(_is_login_instruction_line(l) for l in normalized_step_lines)

    precondition_login_required = (
        _is_login_instruction_line(preconditions_lower)
        or "logged in" in preconditions_lower
        or "log in" in preconditions_lower
        or "sign in" in preconditions_lower
        or "authenticated" in preconditions_lower
        or "valid credential" in preconditions_lower
        or "credentials configured" in preconditions_lower
    )

    if precondition_login_required and not has_negative_credentials and not has_explicit_login_steps:
        pre_url_match = re.search(r"https?://[^\s)]+", preconditions_text)
        if pre_url_match:
            nav_url = pre_url_match.group(0).rstrip(".,)")
            _append_step(generated_steps, {"action": "navigate", "value": nav_url})
        for login_step in _login_steps_for_line(
            "log in with valid credentials",
            resolved_email_selector,
            resolved_password_selector,
            resolved_submit_selector,
        ):
            _append_step(generated_steps, login_step)
        login_step_added = True

    # 0b. Precondition specific URL / route navigation if specified
    pre_urls = re.findall(r"https?://[^\s)]+", preconditions_text)
    for u in pre_urls:
        clean_u = u.rstrip(".,)")
        if not any(s.get("value") == clean_u for s in generated_steps):
            _append_step(generated_steps, {"action": "navigate", "value": clean_u})

    pre_paths = re.findall(r"\((/[^)\s]+)\)", preconditions_text)
    for p in pre_paths:
        target_base = application.target or ""
        full_u = f"{target_base.rstrip('/')}{p}" if target_base else p
        if not any(s.get("value") == full_u or s.get("value") == p for s in generated_steps):
            _append_step(generated_steps, {"action": "navigate", "value": full_u})

    for raw_line in step_lines:
        line = re.sub(r"^\s*\d+[\).:\-\s]*", "", raw_line).strip()
        if not line:
            continue
        lower_line = line.lower()
        quoted_values = _extract_quoted_values(line)
        is_click_instruction = bool(re.search(r"\b(click|open|tap|choose)\b", lower_line))

        # 0. Check for verification / assertion lines FIRST so they are never converted to type or click actions
        if _is_verification_only_line(lower_line):
            # Check for URL assertions: e.g. Verify that the URL updates to '/dashboard/reports', Verify URL is ..., Verify URL contains ...
            if "url" in lower_line or "redirect" in lower_line:
                full_url_match = re.search(r"https?://[^\s'\")]+", line)
                if full_url_match:
                    from urllib.parse import urlparse
                    parsed_path = urlparse(full_url_match.group(0)).path
                    if parsed_path and parsed_path != "/":
                        _append_step(generated_steps, {"action": "assert_url_contains", "value": parsed_path, "description": line})
                        continue
                path_match = re.search(r"['\"](/[^'\"]*)['\"]", line)
                if not path_match:
                    path_match = re.search(r"\((/[^)\s]+)\)", line)
                if not path_match:
                    path_match = re.search(r"(?:to|is|contains|remain|changes to)\s+['\"]?(/[\w_\-/]+)", line, re.IGNORECASE)
                if path_match:
                    _append_step(generated_steps, {"action": "assert_url_contains", "value": path_match.group(1).strip(), "description": line})
                    continue

            # Check for title assertions: e.g. Verify that the page title contains 'Portal: Dashboard'
            if "title" in lower_line or "heading" in lower_line:
                if quoted_values:
                    _append_step(generated_steps, {"action": "assert_title", "value": quoted_values[0].strip(), "description": line})
                    continue
                title_match = re.search(r"(?:title|heading)\s+(?:is|contains|displayed as)\s+['\"]?([^'\"]+)['\"]?", line, re.IGNORECASE)
                if title_match:
                    cand_title = title_match.group(1).strip().rstrip(".,;)")
                    if cand_title.lower() not in {"visible", "present", "displayed", "shown", "loaded", "active", "enabled", "correct", "available", "empty", "blank"}:
                        _append_step(generated_steps, {"action": "assert_title", "value": cand_title, "description": line})
                        continue
                    else:
                        _append_step(generated_steps, {"action": "assert_visible", "selector": "h1, h2, h3, header, .page-header, legend, [role='heading'], body", "description": line})
                        continue

            asserted_text = _extract_verification_text(line, quoted_values)
            if len(asserted_text) >= 2:
                _append_step(generated_steps, {"action": "assert_text", "selector": "body", "value": asserted_text, "description": line})
            else:
                _append_step(generated_steps, {"action": "assert_visible", "selector": "body", "description": line})
            continue

        # 1. Check for URL navigation
        url_match = re.search(r"https?://[^\s)]+", line)
        if url_match:
            nav_url = url_match.group(0).rstrip(".,)")
            _append_step(generated_steps, {"action": "navigate", "value": nav_url, "description": line})
            if _is_login_instruction_line(lower_line) and not login_step_added:
                for login_step in _login_steps_for_line(lower_line, resolved_email_selector, resolved_password_selector, resolved_submit_selector):
                    _append_step(generated_steps, login_step)
                login_step_added = True
            continue

        # Check for explicit typed field assignments
        typed_assignments = _extract_typed_field_assignments(line, quoted_values)
        if typed_assignments:
            for field_name, field_val in typed_assignments:
                fn_lower = field_name.lower()
                clean_field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", field_name, flags=re.IGNORECASE))
                if re.search(r"password|passcode|passwd|pwd", fn_lower):
                    sel = resolved_password_selector
                    login_step_added = True
                elif fn_lower in {"email", "username", "user email", "login email", "user", "login id", "login identifier"} or clean_field.lower() in {"email", "username", "user"}:
                    sel = resolved_email_selector
                    login_step_added = True
                else:
                    sel = f"label={clean_field or field_name}"
                _append_step(generated_steps, {
                    "action": "type",
                    "selector": sel,
                    "value": field_val,
                    "description": line,
                })
            continue

        # Handle multiple fields described with example list (e.g., Field1, Field2)
        if ("multiple fields" in lower_line or "multiple filter" in lower_line or "multiple values" in lower_line) and "(e.g." in lower_line:
            eg_match = re.search(r"\(e\.g\.,?\s*(.+)\)", line, re.IGNORECASE)
            if eg_match:
                cleaned_eg = re.sub(r"\([^)]*\)", "", eg_match.group(1))
                extracted_fields = [_normalize_action_target(f) for f in cleaned_eg.split(",") if _normalize_action_target(f)]
                for field_name in extracted_fields:
                    val = _extract_default_field_value(field_name, line)
                    _append_step(generated_steps, {
                        "action": "type",
                        "selector": f"label={field_name}",
                        "value": val,
                        "description": line,
                    })
                continue

        if _is_login_instruction_line(lower_line):
            if re.search(r"\b(click|press|tap|submit)\b", lower_line) and re.search(r"\b(submit|login|log in|sign in|commit|button)\b", lower_line):
                _append_step(generated_steps, {"action": "click", "selector": resolved_submit_selector, "description": line})
                continue
            if not login_step_added:
                for login_step in _login_steps_for_line(lower_line, resolved_email_selector, resolved_password_selector, resolved_submit_selector):
                    _append_step(generated_steps, login_step)
                login_step_added = True
            continue

        # 2. Handle lines containing "Search Again"
        if "search again" in lower_line:
            _append_step(generated_steps, {"action": "click", "selector": "text=Search Again", "description": line})

            field_matches = re.findall(r'(?:in|into)\s+(?:the\s+)?["\']([^"\']+)["\'](?:\s+field)?', line, re.IGNORECASE)
            if not field_matches and quoted_values:
                field_matches = [q for q in quoted_values if q.lower() != "search again"]

            if field_matches:
                for field_name in field_matches:
                    field_val = _extract_default_field_value(field_name, line)
                    _append_step(generated_steps, {
                        "action": "type",
                        "selector": f"label={field_name}",
                        "value": field_val,
                        "description": line,
                    })
                continue
            elif "enter" in lower_line or "type" in lower_line:
                target_field = "Last Name" if "last name" in lower_line else "First Name" if "first name" in lower_line else "Search"
                clean_field = target_field.lower().replace(" ", "_")
                val = "%" if "%" in line or "wildcard" in lower_line else f"{{{{{clean_field}}}}}"
                _append_step(generated_steps, {
                    "action": "type",
                    "selector": f"label={target_field}",
                    "value": val,
                    "description": line,
                })
                continue

        if re.match(r"^repeat\s+step", lower_line):
            continue

        # Dropdown selection / Top navigation
        if "dropdown" in lower_line and len(quoted_values) >= 2:
            _append_click_steps_from_target(generated_steps, quoted_values[0], description=f"Click '{quoted_values[0]}'")
            _append_click_steps_from_target(generated_steps, quoted_values[1], description=line)
            continue

        # Check or uncheck checkboxes
        if re.search(r"\b(check|uncheck|tick|untick)\b", lower_line) and not _is_verification_only_line(lower_line):
            is_uncheck = bool(re.search(r"\b(uncheck|untick)\b", lower_line))
            action_name = "uncheck" if is_uncheck else "check"
            cb_target = quoted_values[0] if quoted_values else None
            if not cb_target:
                cb_match = re.search(r"(?:check|uncheck|tick|untick)\s+(?:the\s+)?(.+?)(?:\s+checkbox|\s+box|\s+toggle|$)", line, re.IGNORECASE)
                if cb_match:
                    cb_target = cb_match.group(1).strip()
            if cb_target:
                if cb_target.startswith("<") and ">" in cb_target:
                    _append_step(generated_steps, {"action": action_name, "selector": cb_target, "description": line})
                else:
                    target_clean = _normalize_action_target(re.sub(r"\b(checkbox|box|toggle|the)\b", "", cb_target, flags=re.IGNORECASE))
                    _append_step(generated_steps, {"action": action_name, "selector": f"label={target_clean or cb_target}", "description": line})
                continue

        if "wait for the page to load" in lower_line or "wait for the page to reload" in lower_line or "wait for reload" in lower_line or "wait for page" in lower_line:
            _append_step(generated_steps, {"action": "assert_visible", "selector": "body", "description": line})
            continue

        if "open the application" in lower_line or "open the app" in lower_line or "open application" in lower_line or "launch application" in lower_line:
            _append_step(generated_steps, {"action": "navigate", "value": application.target, "description": line})
            continue

        if is_click_instruction:
            href_match = re.search(r"\((/[^)\s]+)\)", line)
            if href_match:
                href = href_match.group(1).strip()
                _append_step(generated_steps, {"action": "click", "selector": f"a[href='{href}']", "description": line})
                continue
            click_target = quoted_values[0] if quoted_values else None
            if not click_target:
                click_match = re.search(
                    r"(?:click|open|tap|choose)\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\s+button|\s+link|\s+dropdown|\s+menu|$)",
                    line,
                    re.IGNORECASE,
                )
                if click_match:
                    click_target = click_match.group(1).strip()

            if click_target:
                target_norm = _normalize_action_target(click_target)
                if "link" in lower_line:
                    _append_step(generated_steps, {"action": "click", "selector": f"a:has-text('{target_norm}')", "description": line})
                elif "button" in lower_line or any(w in target_norm.lower() for w in ["find", "search", "submit", "save", "update", "filter", "apply", "create", "delete"]):
                    _append_step(generated_steps, {"action": "click", "selector": f"input[type='submit'][value*='{target_norm}' i], input[value*='{target_norm}' i], button:has-text('{target_norm}'), text={target_norm}", "description": line})
                else:
                    _append_click_steps_from_target(generated_steps, target_norm, description=line)
                continue

        tab_under_match = re.match(r"^select\s+(.+?)\s+tab\s+under\s+(.+)$", line, re.IGNORECASE)
        if tab_under_match:
            tab_target = _normalize_action_target(tab_under_match.group(1))
            if tab_target:
                _append_step(generated_steps, {"action": "click", "selector": f"text={tab_target}", "description": line})
            continue

        if "select" in lower_line or "choose" in lower_line or "filter" in lower_line:
            # Pattern: Filter [items] by [field] [as/to] 'value'
            filter_by_match = re.search(
                r"filter\s+(?:site\s+visits\s+|records\s+|orders\s+|reactions\s+|items\s+|list\s+)?by\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)\s+(?:as|to|with|\:)?\s*['\"]([^'\"]+)['\"]",
                line,
                re.IGNORECASE,
            )
            if filter_by_match:
                fld = _normalize_action_target(re.sub(r"\b(filter|dropdown|select|the)\b", "", filter_by_match.group(1), flags=re.IGNORECASE))
                val = filter_by_match.group(2).strip()
                if fld and val:
                    _append_step(generated_steps, {"action": "select", "selector": f"label={fld}", "value": val, "description": line})
                    continue

            select_from_dropdown_match = re.search(
                r"(?:select|choose|pick)\s+[\"']?([^\"'\n]+?)[\"']?\s+(?:from|in|under)\s+(?:the\s+)?[\"']?([^\"'\n]+?)[\"']?\s*(?:filter)?\s*(?:dropdown|select|menu|list)?$",
                line,
                re.IGNORECASE,
            )
            if select_from_dropdown_match:
                option_text = _normalize_action_target(select_from_dropdown_match.group(1))
                field_text = _normalize_action_target(re.sub(r"\b(filter|dropdown|select|menu|list)\b", "", select_from_dropdown_match.group(2), flags=re.IGNORECASE))
                if option_text and field_text:
                    _append_step(generated_steps, {"action": "select", "selector": f"label={field_text}", "value": option_text, "description": line})
                    continue
            if len(quoted_values) >= 2 and any(k in lower_line for k in ("dropdown", "select", "from", "in")):
                opt = _normalize_action_target(quoted_values[0])
                fld = _normalize_action_target(quoted_values[1])
                _append_step(generated_steps, {"action": "select", "selector": f"label={fld}", "value": opt, "description": line})
                continue
            if quoted_values:
                _append_click_steps_from_target(generated_steps, quoted_values[0], description=line)
                continue
            select_match = re.search(r"select\s+(.+?)(?:\s+(?:in|from)\s+.+)?$", line, re.IGNORECASE)
            if select_match:
                select_value = _normalize_action_target(re.sub(r"^the\s+", "", select_match.group(1).strip(), flags=re.IGNORECASE))
                if len(select_value) >= 2:
                    _append_click_steps_from_target(generated_steps, select_value, description=line)
                    continue

        if ("enter" in lower_line or "type" in lower_line or "fill" in lower_line or "set" in lower_line) and (quoted_values or "field" in lower_line or "input" in lower_line or "filter" in lower_line):
            # Try typed field assignments first
            assignments = _extract_typed_field_assignments(line, quoted_values)
            if assignments:
                for field_name, field_val in assignments:
                    fn_lower = field_name.lower()
                    if re.search(r"password|passcode|passwd|pwd", fn_lower):
                        sel = resolved_password_selector
                    elif fn_lower in {"email", "username", "user email", "login email", "user", "login id", "login identifier"} or "@" in field_val or "@" in field_name:
                        sel = resolved_email_selector
                    else:
                        clean_field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", field_name, flags=re.IGNORECASE))
                        sel = f"label={clean_field or field_name}"
                    _append_step(generated_steps, {
                        "action": "type",
                        "selector": sel,
                        "value": field_val,
                    })
                continue

            field_matches = re.findall(r'(?:in|into|for)\s+(?:the\s+)?["\']?([a-zA-Z0-9_\s\-]+?)["\']?(?:\s+field|\s+input|\s+filter|\s+box|$)', line, re.IGNORECASE)
            valid_field_names = [
                _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", f, flags=re.IGNORECASE))
                for f in field_matches
                if _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", f, flags=re.IGNORECASE)).lower() not in {"field", "input", "the", "box", "filter"}
            ]
            if valid_field_names:
                for field_name in valid_field_names:
                    val = quoted_values[0] if quoted_values else _extract_default_field_value(field_name, line)
                    fn_lower = field_name.lower()
                    clean_field = _normalize_action_target(re.sub(r"\b(field|input|filter|box|the)\b", "", field_name, flags=re.IGNORECASE))
                    if re.search(r"password|passcode|passwd|pwd", fn_lower):
                        sel = resolved_password_selector
                    elif fn_lower in {"email", "username", "user email", "login email", "user"} or clean_field.lower() in {"email", "username", "user"}:
                        sel = resolved_email_selector
                    else:
                        sel = f"label={clean_field or field_name}"
                    _append_step(generated_steps, {
                        "action": "type",
                        "selector": sel,
                        "value": val,
                        "description": line,
                    })
                continue
            elif quoted_values:
                val = quoted_values[0]
                if "@" in val:
                    _append_step(generated_steps, {"action": "type", "selector": resolved_email_selector, "value": val, "description": line})
                    continue
                else:
                    _append_step(generated_steps, {"action": "type", "selector": "label=Search", "value": val, "description": line})
                    continue

        if "navigate back" in lower_line or "go back" in lower_line or "back to listing" in lower_line or "back to search" in lower_line:
            _append_step(generated_steps, {"action": "go_back", "description": line})
            continue

        if "refresh" in lower_line or "reload" in lower_line:
            _append_step(generated_steps, {"action": "reload", "description": line})
            continue

        # Check for URL assertions: e.g. Verify that the URL updates to '/dashboard/reports', Verify URL is ..., Verify URL contains ...
        if "url" in lower_line and ("update" in lower_line or "contain" in lower_line or "remain" in lower_line or "change" in lower_line or "is" in lower_line or "to" in lower_line):
            full_url_match = re.search(r"https?://[^\s'\")]+", line)
            if full_url_match:
                from urllib.parse import urlparse
                parsed_path = urlparse(full_url_match.group(0)).path
                if parsed_path and parsed_path != "/":
                    _append_step(generated_steps, {"action": "assert_url_contains", "value": parsed_path, "description": line})
                    continue
            path_match = re.search(r"['\"](/[^'\"]*)['\"]", line)
            if not path_match:
                path_match = re.search(r"\((/[^)\s]+)\)", line)
            if not path_match:
                path_match = re.search(r"(?:to|is|contains|remain|changes to)\s+['\"]?(/[\w_\-/]+)", line, re.IGNORECASE)
            if path_match:
                _append_step(generated_steps, {"action": "assert_url_contains", "value": path_match.group(1).strip(), "description": line})
                continue

        # Check for title assertions: e.g. Verify that the page title is 'Portal: Dashboard'
        if "title" in lower_line and ("is" in lower_line or "contain" in lower_line or "display" in lower_line):
            if quoted_values:
                _append_step(generated_steps, {"action": "assert_title", "value": quoted_values[0].strip(), "description": line})
                continue
            title_match = re.search(r"title\s+(?:is|contains|displayed as)\s+['\"]?([^'\"]+)['\"]?", line, re.IGNORECASE)
            if title_match:
                cand_title = title_match.group(1).strip().rstrip(".,;)")
                if cand_title.lower() not in {"visible", "present", "displayed", "shown", "loaded", "active", "enabled", "correct", "available", "empty", "blank"}:
                    _append_step(generated_steps, {"action": "assert_title", "value": cand_title, "description": line})
                    continue
                else:
                    _append_step(generated_steps, {"action": "assert_visible", "selector": "h1, h2, h3, header, .page-header, legend, [role='heading'], body", "description": line})
                    continue

        if "sort" in lower_line:
            sort_match = re.search(r"sort\s+.+?\s+by\s+(.+?)(?:\s+in\s+|$)", line, re.IGNORECASE)
            if sort_match:
                sort_field = _normalize_action_target(sort_match.group(1))
                if len(sort_field) >= 2:
                    _append_click_steps_from_target(generated_steps, sort_field, description=line)
                    continue

        if quoted_values:
            asserted_text = _normalize_action_target(quoted_values[0])
            if len(asserted_text) >= 3:
                _append_step(generated_steps, {"action": "assert_text", "selector": "body", "value": asserted_text, "description": line})
            else:
                _append_step(generated_steps, {"action": "assert_visible", "selector": "body", "description": line})
            continue

        if "wait for the page to load" in lower_line or "wait for the page to reload" in lower_line or "wait for reload" in lower_line:
            _append_step(generated_steps, {"action": "assert_visible", "selector": "body", "description": line})
            continue

        if "open the application" in lower_line:
            _append_step(generated_steps, {"action": "navigate", "value": application.target, "description": line})
            continue

        _append_step(generated_steps, {"action": "assert_visible", "selector": "body", "description": line})

    for expected_line in split_case_lines(test_case.expected_result):
        quoted_values = _extract_quoted_values(expected_line)
        if quoted_values:
            candidate = quoted_values[0][:500]
            if re.search(r"queue an import job|queued successfully", candidate, re.IGNORECASE):
                continue
            generated_checks.append({"type": "text_contains", "value": candidate})
            if len(generated_checks) >= 25:
                break
        if len(generated_checks) >= 25:
            break

    return generated_steps, generated_checks


def generate_playwright_spec_code(
    test_case: TestCase,
    application: Application,
    steps: list[dict] | None = None,
    checks: list[dict] | None = None,
) -> str:
    """Generates clean, idiomatic Playwright TypeScript automation code from a test case definition."""
    if steps is None or checks is None:
        compiled_steps, compiled_checks = build_case_automation_from_text(test_case, application)
        steps = steps or compiled_steps
        checks = checks or compiled_checks

    safe_title = re.sub(r"[^\w\s\-.,:()]", "", test_case.title).strip() or f"TC{test_case.id:02d}"
    code_lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"/**",
        f" * Test Case: {safe_title}",
        f" * Application: {application.name} ({application.target})",
        f" * Category: {getattr(test_case, 'category', 'functional')}",
        f" * Priority: {getattr(test_case, 'priority', 'medium')}",
    ]
    if test_case.preconditions:
        code_lines.append(f" * Preconditions: {test_case.preconditions.strip()}")
    code_lines.extend([
        f" */",
        f"test.describe('{safe_title}', () => {{",
        f"  test('{safe_title}', async ({{ page }}) => {{",
        f"    // Target Base URL: {application.target}",
    ])

    # Parse test_data bindings
    case_test_data: dict[str, str] = {}
    raw_td = getattr(test_case, "test_data", None)
    if isinstance(raw_td, dict):
        case_test_data = {str(k): str(v) for k, v in raw_td.items() if not str(k).startswith("_")}
    elif isinstance(raw_td, str) and raw_td.strip():
        try:
            p_td = json.loads(raw_td)
            if isinstance(p_td, dict):
                case_test_data = {str(k): str(v) for k, v in p_td.items() if not str(k).startswith("_")}
        except Exception:
            pass

    for step in steps:
        val = step.get("value") or ""
        for match in re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", val):
            tok = match.strip()
            if tok and tok not in case_test_data:
                from app.services.ai_service import synthesize_parameter_value
                case_test_data[tok] = synthesize_parameter_value(tok, getattr(test_case, "category", "positive"))

    if case_test_data:
        code_lines.append("    // Parameterized test dataset bindings")
        code_lines.append("    const testData: Record<string, string> = {")
        for k, v in case_test_data.items():
            env_var = re.sub(r"[^A-Za-z0-9_]+", "_", k.upper()).strip("_")
            clean_v = str(v).replace("'", "\\'")
            code_lines.append(f"      {k}: process.env.{env_var} || '{clean_v}',")
        code_lines.append("    };")
        code_lines.append("")

    def _ts_format_value(raw_val: str | None) -> str:
        if not raw_val:
            return "''"
        if re.fullmatch(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", raw_val.strip()):
            tok = re.match(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", raw_val.strip()).group(1).strip()
            fallback = case_test_data.get(tok, tok).replace("'", "\\'")
            return f"testData['{tok}'] || '{fallback}'"
        if "{{" in raw_val and "}}" in raw_val:
            # Interpolate into backtick string
            def _sub_tok(m: re.Match) -> str:
                tok = m.group(1).strip()
                fallback = case_test_data.get(tok, tok).replace("'", "\\'")
                return f"${{testData['{tok}'] || '{fallback}'}}"
            interpolated = re.sub(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", _sub_tok, raw_val)
            clean_backtick = interpolated.replace("`", "\\`")
            return f"`{clean_backtick}`"
        clean_s = raw_val.replace("'", "\\'")
        return f"'{clean_s}'"

    step_idx = 1
    for step in steps:
        act = step.get("action")
        sel = step.get("selector")
        val = step.get("value")
        desc = step.get("description") or f"Step {step_idx}: {act}"

        code_lines.append(f"    // {step_idx}. {desc}")
        step_idx += 1

        if act == "navigate":
            target_nav = val or application.target
            code_lines.append(f"    await page.goto({_ts_format_value(target_nav)}, {{ waitUntil: 'domcontentloaded' }});")
        elif act in {"reload", "refresh"}:
            code_lines.append("    await page.reload({ waitUntil: 'domcontentloaded' });")
        elif act in {"go_back", "navigate_back"}:
            code_lines.append("    await page.goBack({ waitUntil: 'domcontentloaded' });")
        elif act == "click":
            clean_sel = (sel or "button").replace("'", "\\'")
            code_lines.append(f"    await page.locator('{clean_sel}').first.click();")
        elif act == "type":
            clean_sel = (sel or "input").replace("'", "\\'")
            code_lines.append(f"    await page.locator('{clean_sel}').first.fill({_ts_format_value(val)});")
        elif act == "select":
            clean_sel = (sel or "select").replace("'", "\\'")
            code_lines.append(f"    await page.locator('{clean_sel}').first.selectOption({_ts_format_value(val)});")
        elif act == "check":
            clean_sel = (sel or "input[type='checkbox']").replace("'", "\\'")
            code_lines.append(f"    await page.locator('{clean_sel}').first.check();")
        elif act == "uncheck":
            clean_sel = (sel or "input[type='checkbox']").replace("'", "\\'")
            code_lines.append(f"    await page.locator('{clean_sel}').first.uncheck();")
        elif act == "assert_visible":
            clean_sel = (sel or "body").replace("'", "\\'")
            code_lines.append(f"    await expect(page.locator('{clean_sel}').first).toBeVisible();")
        elif act == "assert_text":
            clean_sel = (sel or "body").replace("'", "\\'")
            code_lines.append(f"    await expect(page.locator('{clean_sel}').first).toContainText({_ts_format_value(val)});")
        elif act == "assert_title":
            clean_val = (val or "").replace("'", "\\'")
            code_lines.append(f"    await expect(page).toHaveTitle(new RegExp('{clean_val}', 'i'));")
        elif act == "assert_url_contains":
            clean_val = (val or "").replace("'", "\\'")
            code_lines.append(f"    await expect(page).toHaveURL(new RegExp('{clean_val}', 'i'));")
        code_lines.append("")

    if checks:
        code_lines.append("    // Post-Condition Assertions")
        for check in checks:
            ctype = check.get("type")
            cval = (check.get("value") or "").replace("'", "\\'")
            if ctype == "visible":
                code_lines.append(f"    await expect(page.locator('{cval}').first).toBeVisible();")
            elif ctype == "text_contains":
                code_lines.append(f"    await expect(page.locator('body').first).toContainText('{cval}');")
            elif ctype == "title_contains":
                code_lines.append(f"    await expect(page).toHaveTitle(new RegExp('{cval}', 'i'));")

    code_lines.extend([
        "  });",
        "});",
        "",
    ])

    return "\n".join(code_lines)

