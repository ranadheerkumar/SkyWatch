import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.execution import Step
from app.services.agent_definitions import load_agent_definition, AGENT_FILE_MAP
from app.services.ai_service import resolve_action_with_agent


def test_execution_agent_definition_is_registered() -> None:
    assert "execution" in AGENT_FILE_MAP
    assert AGENT_FILE_MAP["execution"] == "execution-agent.agent.md"
    definition = load_agent_definition("execution")
    assert definition.key == "execution"
    assert "Playwright Execution Agent" in definition.content
    assert "Container Hierarchy" in definition.content


@pytest.mark.anyio
async def test_resolve_action_with_agent_prioritizes_form_submit() -> None:
    # Mock page and evaluate to return a simulated accessibility & container tree
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=[
        {
            "candidate_id": 1,
            "container_type": "navigation",
            "tag": "a",
            "text": "Find",
            "classes": "dropdown-toggle",
            "suggested_selector": "nav a:has-text('Find')",
        },
        {
            "candidate_id": 2,
            "container_type": "form",
            "tag": "input",
            "type": "submit",
            "value": "Find Clinics",
            "text": "Find Clinics",
            "classes": "btn btn-primary",
            "suggested_selector": "form input[type='submit'][value*='Find Clinics' i]",
        },
    ])

    step = Step(action="click", selector="text=Find", description="Click 'Find Clinics'")
    previous_step = Step(action="type", selector="label=Zip", value="11111")

    resolved = await resolve_action_with_agent(
        page=mock_page,
        step=step,
        previous_step=previous_step,
        application_id=1,
    )

    assert resolved is not None
    assert resolved.action == "click"
    assert "Find Clinics" in resolved.selector or "submit" in resolved.selector
    assert "nav" not in resolved.selector
