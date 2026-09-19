import asyncio

from app.schemas.test_case import AIGeneratedTestCase, AIGeneratedTestCaseSet
from app.services import ai_service
from app.services.ai_generation_pipeline import agent_definition_manifest, build_context_snapshot, initial_agent_stages


def test_application_discovery_is_first_class_in_the_agent_workflow() -> None:
    stages = initial_agent_stages()
    manifest = agent_definition_manifest()
    context = build_context_snapshot(
        application_name="Test app",
        platform="web",
        target="https://example.test",
        prompt="Cover checkout",
        document_context="Users must submit a checkout request.",
        reference_cases=[],
        discovery_snapshot={
            "headings": ["Checkout"],
            "buttons": ["Submit order"],
            "links": ["Orders"],
            "input_hints": ["card number"],
            "observed_routes": ["https://example.test/checkout"],
        },
    )

    discovery_stage = next(stage for stage in stages if stage["key"] == "application_discovery")
    discovery_definition = next(item for item in manifest if item["key"] == "application_discovery")
    assert discovery_stage["name"] == "Application Discovery Agent"
    assert discovery_definition["source"] == ".github/agents/application-discovery.agent.md"
    assert context["discovered_heading_count"] == 1
    assert context["discovered_control_count"] == 2
    assert context["discovered_route_count"] == 1


def test_test_data_generator_is_first_class_in_the_agent_workflow() -> None:
    stages = initial_agent_stages()
    manifest = agent_definition_manifest()

    data_stage = next(stage for stage in stages if stage["key"] == "test_data_generator")
    data_definition = next(item for item in manifest if item["key"] == "test_data_generator")
    assert data_stage["name"] == "Test Data Generator Agent"
    assert data_definition["source"] == ".github/agents/test-data-generator.agent.md"


def test_generator_prompt_prioritizes_uploaded_requirements() -> None:
    prompt = ai_service._build_prompt(
        application_name="Test app",
        platform="web",
        target="https://example.test",
        user_prompt="Cover the returns workflow",
        max_cases=2,
        min_steps_per_case=2,
        max_steps_per_case=8,
        include_negative_scenarios=True,
        include_accessibility_checks=False,
        include_api_validations=False,
        module_focus="Returns",
        target_context="Observed UI: Home\nSupplemental reference case: Old login case",
        document_context="DOCUMENT: returns.md\nUsers must request a return within 30 days.",
        planner_context="Return workflow plan",
    )

    assert "AUTHORITATIVE DOCUMENT & REQUIREMENTS CONTEXT" in prompt
    assert "Users must request a return within 30 days." in prompt
    assert "Live UI context and existing cases are supporting evidence only." in prompt
    assert "Old login case" in prompt


def test_quality_gate_rejects_cases_unrelated_to_source() -> None:
    generated = AIGeneratedTestCaseSet(
        summary="batch",
        test_cases=[
            AIGeneratedTestCase(title="Returns request", steps="1. Open returns\n2. Submit request", expected_result="Return is created"),
            AIGeneratedTestCase(title="Login flow", steps="1. Open login\n2. Sign in", expected_result="Dashboard opens"),
        ],
    )

    result = ai_service._quality_gate_generated_cases(
        generated,
        max_cases=10,
        min_steps_per_case=2,
        max_steps_per_case=8,
        target_url="https://example.test",
        source_anchors=["returns"],
    )

    assert len(result.test_cases) == 1
    assert "Returns" in result.test_cases[0].title


def test_ai_planner_drives_generator_continuation_batches(monkeypatch) -> None:
    provider_settings = ai_service.AIProviderSettings(
        provider="test",
        api_key="test",
        model="test-model",
        base_url="http://provider.test/v1",
        timeout_seconds=10,
    )
    calls = {"planner": 0, "generator": 0}

    async def fake_json(settings, prompt, *, system_content, agent_key="healer"):
        calls[agent_key] += 1
        assert agent_key == "planner"
        assert "AI Playwright Planner Agent" in prompt
        return {
            "summary": "Plan twelve distinct workflows",
            "recommended_case_count": 12,
            "coverage_matrix": [{"area": "Checkout", "scenarios": ["Valid purchase", "Invalid payment"]}],
        }

    async def fake_generation(settings, prompt):
        calls["generator"] += 1
        assert "GENERATOR AGENT GUIDANCE" in prompt
        batch = calls["generator"]
        return AIGeneratedTestCaseSet(
            summary="batch",
            test_cases=[
                AIGeneratedTestCase(
                    title=f"Flow batch {batch} case {index}",
                    steps="1. Open the checkout workflow\n2. Verify the checkout outcome",
                    expected_result="Expected outcome is visible",
                )
                for index in range(1, 8)
            ],
        )

    async def fake_capture(target):
        return ai_service.TargetUIContext(
            source_url=target,
            title="Test app",
            headings=["Checkout"],
            buttons=["Submit"],
            links=[],
            input_hints=[],
            observed_routes=[target],
            fetch_note="fake",
        )

    monkeypatch.setattr(ai_service, "_load_provider_settings", lambda **kwargs: [provider_settings])
    monkeypatch.setattr(ai_service, "_request_provider_json", fake_json)
    monkeypatch.setattr(ai_service, "_request_provider_generation", fake_generation)
    monkeypatch.setattr(ai_service, "_capture_target_ui_context", fake_capture)

    result = asyncio.run(
        ai_service.generate_ai_test_cases(
            application_name="Test app",
            platform="web",
            target="https://example.test",
            user_prompt="Cover checkout",
            max_cases=None,
            include_authenticated_snapshot=False,
            login_email_selector=None,
            login_password_selector=None,
            login_submit_selector=None,
            min_steps_per_case=2,
            max_steps_per_case=15,
            include_negative_scenarios=True,
            include_accessibility_checks=True,
            include_api_validations=False,
            module_focus="Checkout",
            provider="test",
            model="test-model",
        )
    )

    assert len(result.test_cases) == 12
    assert result.planner_used is True
    assert result.planner_case_target == 12
    assert result.generator_call_count == 2
    assert calls == {"planner": 1, "generator": 2}


def test_extract_credentials_from_user_prompt_and_document() -> None:
    email, password = ai_service._extract_credentials_from_text(
        "Please generate tests for the admin portal. username: test.admin@example.com password: SecretPassword123!"
    )
    assert email == "test.admin@example.com"
    assert password == "SecretPassword123!"

    email2, password2 = ai_service._extract_credentials_from_text(
        "Test with login as admin@domain.org and pass: MyPass99"
    )
    assert email2 == "admin@domain.org"
    assert password2 == "MyPass99"

    prompt3 = (
        "URL: https://staging-apollo-web.calmwave-160b5d92.eastus2.azurecontainerapps.io/\n\n"
        "Username: tscqaadmin@example.com\n\n"
        "PW: Park&Ride101"
    )
    extracted_url = ai_service._extract_target_url_from_text(prompt3)
    email3, password3 = ai_service._extract_credentials_from_text(prompt3)
    assert extracted_url == "https://staging-apollo-web.calmwave-160b5d92.eastus2.azurecontainerapps.io/"
    assert email3 == "tscqaadmin@example.com"
    assert password3 == "Park&Ride101"


def test_extract_intake_signals_with_ai_fallback() -> None:
    prompt = (
        "URL: https://staging-apollo-web.calmwave-160b5d92.eastus2.azurecontainerapps.io/\n\n"
        "Username: tscqaadmin@example.com\n\n"
        "PW: Park&Ride101"
    )
    res = asyncio.run(ai_service.extract_intake_signals_with_ai(prompt, ""))
    assert res["target_url"] == "https://staging-apollo-web.calmwave-160b5d92.eastus2.azurecontainerapps.io/"
    assert res["username"] == "tscqaadmin@example.com"
    assert res["password"] == "Park&Ride101"


def test_exploratory_charters_and_scenario_categories() -> None:
    plan = ai_service._normalize_planner_output(
        {"summary": "Test plan", "recommended_case_count": 10},
        max_cases=10,
        context_snapshot=None,
    )
    assert len(plan["exploratory_charters"]) >= 1
    assert "observation" in plan["exploratory_charters"][0]

    from app.services.ai_generation_pipeline import build_scenario_snapshot
    scenario_snapshot = build_scenario_snapshot(
        {"include_positive_scenarios": True},
        context={"modules": ["Billing"]},
        planner_plan=plan,
    )
    assert "exploratory" in scenario_snapshot["categories"]
    assert len(scenario_snapshot["exploratory_charters"]) >= 1
