import pytest
from app.models.application import Application
from app.models.test_case import TestCase
from app.api.v1.execution import _login_selector_error
from app.schemas.execution import Step
from app.services.automation_builder import (
    _extract_typed_field_assignments,
    build_case_automation_from_text,
)
from app.services.ai_service import _heuristic_dom_repair


def test_extract_typed_field_assignments():
    # Email into username field
    assignments = _extract_typed_field_assignments("Enter 'tscqaadmin@example.com' into username field", ["tscqaadmin@example.com"])
    assert len(assignments) == 1
    assert assignments[0][0] == "username"
    assert assignments[0][1] == "tscqaadmin@example.com"

    # Value into filter field
    assignments = _extract_typed_field_assignments("Type 'Bella' into the pet name filter", ["Bella"])
    assert len(assignments) == 1
    assert assignments[0][0] == "pet name"
    assert assignments[0][1] == "Bella"

    # Fill field with value
    assignments = _extract_typed_field_assignments("Fill in 'Barcode' with '123456'", ["Barcode", "123456"])
    assert len(assignments) == 1
    assert assignments[0][1] == "123456"


def test_build_case_automation_field_selectors():
    app = Application(id=1, name="Apollo", platform="web", target="https://app.example.com", created_by=1)
    tc = TestCase(
        id=1,
        application_id=1,
        title="Search Pet Flow",
        steps="1. Open the application\n2. Enter 'Bella' into pet name filter\n3. Click 'Find'\n4. Verify 'Bella' is displayed",
        expected_result="Search results show Bella",
    )
    steps, checks = build_case_automation_from_text(tc, app)
    
    # Verify step 2 is type with label=pet name and value=Bella
    type_step = next(s for s in steps if s.get("action") == "type")
    assert type_step["selector"] == "label=pet name"
    assert type_step["value"] == "Bella"

    # Verify click step is click with text=Find
    click_step = next(s for s in steps if s.get("action") == "click")
    assert "Find" in click_step["selector"]


def test_build_case_automation_keeps_compound_password_field_separate():
    app = Application(id=1, name="Apollo", platform="web", target="https://app.example.com", created_by=1)
    tc = TestCase(
        id=3,
        application_id=1,
        title="Login Flow",
        steps=(
            "1. Enter 'tester@example.com' into email field\n"
            "2. Enter 'secret' into user password field\n"
            "3. Click 'Sign In'"
        ),
    )

    steps, _ = build_case_automation_from_text(tc, app)

    type_steps = [step for step in steps if step.get("action") == "type"]
    assert type_steps == [
        {"action": "type", "selector": "#user_email", "value": "tester@example.com", "description": "Enter 'tester@example.com' into email field"},
        {"action": "type", "selector": "#user_password", "value": "secret", "description": "Enter 'secret' into user password field"},
    ]


def test_describe_step_action_human_alignment():
    from app.services.test_execution import _describe_step_action

    # Step with explicit description from test case step
    step1 = Step(action="click", selector="button:has-text('Submit')", description="1. Click Submit button")
    assert _describe_step_action(step1) == "Click Submit button"

    # Step with raw CSS selector without description
    step2 = Step(action="type", selector="#user_email, input[type=email]", value="{{login_email}}")
    assert _describe_step_action(step2) == "Entering email address into email address field"

    # Step with password selector
    step3 = Step(action="type", selector="#user_password, input[type=password]", value="{{login_password}}")
    assert _describe_step_action(step3) == "Entering password into password field"

    # Step with label selector and value
    step4 = Step(action="type", selector="label=Pet Name", value="Bella")
    assert _describe_step_action(step4) == "Entering 'Bella' into Pet Name field"

    # Step with dropdown select
    step5 = Step(action="select", selector="label=Office", value="Alameda, CA")
    assert _describe_step_action(step5) == "Selecting 'Alameda, CA' in Office dropdown"

    # Step with text assertion
    step6 = Step(action="assert_text", selector="body", value="Dashboard Overview")
    assert _describe_step_action(step6) == "Verifying text 'Dashboard Overview' is displayed"


def test_login_selector_contract_rejects_cross_field_mapping():
    duplicate_error = _login_selector_error([
        {"action": "type", "selector": "#user_email", "value": "{{login_email}}"},
        {"action": "type", "selector": "#user_email", "value": "{{login_password}}"},
    ])
    assert duplicate_error is not None
    assert "password step points to an email/username selector" in duplicate_error

    assert _login_selector_error([
        {"action": "type", "selector": "#user_email", "value": "{{login_email}}"},
        {"action": "type", "selector": "#user_password", "value": "{{login_password}}"},
    ]) is None


def test_heuristic_dom_repair():
    # Click button to visible link/button repair
    failed_click = Step(action="click", selector="button:has-text('Find')")
    repaired, reason = _heuristic_dom_repair(failed_click, "Timeout 250ms exceeded", "<body><a href='/pets'>Find</a></body>")
    assert repaired.action == "click"
    assert "a:has-text('Find')" in repaired.selector
    assert "Find" in reason

    # Type with email-like value in selector repair
    failed_type = Step(action="type", selector="label=tscqaadmin@example.com", value="tscqaadmin@example.com")
    repaired_type, reason_type = _heuristic_dom_repair(failed_type, "Timeout 250ms exceeded", "<body><input id='user_email'></body>")
    assert repaired_type.action == "type"
    assert "#user_email" in repaired_type.selector

    # Type with filter word in label repair
    failed_filter = Step(action="type", selector="label=barcode filter", value="123456")
    repaired_filter, reason_filter = _heuristic_dom_repair(failed_filter, "Timeout 250ms exceeded", "<body><input id='barcode'></body>")
    assert repaired_filter.action == "type"
    assert "input#barcode" in repaired_filter.selector


def test_convert_html_tag_checkbox_selectors():
    from app.services.test_execution import _convert_html_tag_to_selectors

    selectors = _convert_html_tag_to_selectors('<input type="checkbox" checked="">')
    assert "input[type='checkbox']:checked" in selectors
    assert "input[type='checkbox'][checked]" in selectors
    assert "input[type='checkbox']" in selectors

    raw_selectors = _convert_html_tag_to_selectors('<input id="agree_terms" type="checkbox">')
    assert "#agree_terms" in raw_selectors
    assert "input#agree_terms" in raw_selectors


def test_build_case_automation_checkbox_html():
    app = Application(id=1, name="Apollo", platform="web", target="https://app.example.com", created_by=1)
    tc = TestCase(
        id=2,
        application_id=1,
        title="Terms Checkbox Flow",
        steps='1. Open the application\n2. Check \'<input type="checkbox" checked="">\'\n3. Uncheck \'I agree to terms\'',
        expected_result="Checkbox toggled",
    )
    steps, _ = build_case_automation_from_text(tc, app)
    check_step = next(s for s in steps if s.get("action") == "check")
    assert check_step["selector"] == '<input type="checkbox" checked="">'

    uncheck_step = next(s for s in steps if s.get("action") == "uncheck")
    assert uncheck_step["selector"] == "label=I agree to terms"

    # Checkbox repair
    failed_cb = Step(action="check", selector="label=remember me checkbox")
    repaired_cb, reason_cb = _heuristic_dom_repair(failed_cb, "Timeout 250ms exceeded", "<body><input type='checkbox' id='remember_me'></body>")
    assert repaired_cb.action == "check"
    assert "input[type='checkbox']#remember_me" in repaired_cb.selector


def test_dynamic_parameter_extraction_for_unquoted_fields():
    from app.services.automation_builder import _extract_default_field_value

    assert _extract_default_field_value("Last Name", "Enter into Last Name search field") == "{{last_name}}"
    assert _extract_default_field_value("Barcode", "Filter by barcode") == "{{barcode}}"
    assert _extract_default_field_value("Pet Name", "Search by pet name") == "{{pet_name}}"
    assert _extract_default_field_value("Order ID", "Look up order id") == "{{order_id}}"
    # If explicit example given in text, keep example
    assert _extract_default_field_value("City", "Enter city (e.g., Austin)") == "Austin"


def test_build_case_automation_checkbox_actions():
    app = Application(id=1, name="Apollo", platform="web", target="https://app.example.com", created_by=1)
    tc = TestCase(
        id=2,
        application_id=1,
        title="Terms Checkbox Flow",
        steps="1. Open the application\n2. Check 'I agree to terms'\n3. Uncheck 'Send promotional emails'\n4. Click 'Register'",
        expected_result="Account registered",
    )
    steps, checks = build_case_automation_from_text(tc, app)

    check_step = next(s for s in steps if s.get("action") == "check")
    assert "I agree to terms" in check_step["selector"]

    uncheck_step = next(s for s in steps if s.get("action") == "uncheck")
    assert "Send promotional emails" in uncheck_step["selector"]
