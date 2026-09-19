"""Autonomous Agent Orchestration API Endpoints for SkyWatch.

Exposes REST interfaces for:
- Launching closed-loop autonomous QA campaigns
- Querying live campaign status, quality scores, and healing records
- Triggering on-demand application discovery and UI graph mapping
- On-demand root cause failure diagnosis
- On-demand step self-healing
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agent.analysis_agent import AutonomousAnalysisAgent
from app.agent.autonomous_orchestrator import AutonomousAgentOrchestrator
from app.agent.discovery_agent import AutonomousDiscoveryAgent
from app.agent.healing_agent import AutonomousHealingAgent
from app.api.dependencies import DbSession, current_user
from app.models.application import Application
from app.models.user import User

logger = logging.getLogger("skywatch.api.orchestrator")

router = APIRouter(prefix="/orchestrator", tags=["autonomous-orchestrator"])

# In-memory storage for active and completed campaigns
_CAMPAIGNS: dict[str, dict[str, Any]] = {}
_ACTIVE_ORCHESTRATORS: dict[str, AutonomousAgentOrchestrator] = {}


class CampaignLaunchRequest(BaseModel):
    application_id: int
    target_url: str | None = None
    objective: str = Field(default="Perform complete autonomous smoke, regression, and quality audit")
    max_concurrency: int = Field(default=3, ge=1, le=10)
    auto_heal_enabled: bool = True
    credentials: dict[str, str] | None = None
    login_selectors: dict[str, str] | None = None


class DiscoveryRequest(BaseModel):
    target_url: str
    max_depth: int = Field(default=2, ge=1, le=4)
    max_pages: int = Field(default=10, ge=1, le=30)
    credentials: dict[str, str] | None = None
    login_selectors: dict[str, str] | None = None


class DiagnoseRequest(BaseModel):
    action: str
    selector: str | None = None
    error_message: str
    page_url: str | None = None
    dom_snippet: str | None = None
    status_code: int | None = None
    duration_ms: float = 0.0


class HealStepRequest(BaseModel):
    application_id: int
    test_id: str
    step_index: int
    action: str
    failing_selector: str
    candidate_selectors: list[str] = Field(default_factory=list)


@router.post("/campaigns", status_code=status.HTTP_202_ACCEPTED)
async def launch_campaign(
    payload: CampaignLaunchRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Launch an autonomous testing campaign across discovery, planning, execution, and healing."""
    app = db.query(Application).filter(Application.id == payload.application_id).first()
    target_url = payload.target_url or (app.url if app else None)
    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid target URL must be provided or configured on the application.",
        )

    orchestrator = AutonomousAgentOrchestrator(
        max_concurrency=payload.max_concurrency,
        auto_heal_enabled=payload.auto_heal_enabled,
    )
    campaign_id = orchestrator.campaign_id
    _ACTIVE_ORCHESTRATORS[campaign_id] = orchestrator

    _CAMPAIGNS[campaign_id] = {
        "campaign_id": campaign_id,
        "application_id": payload.application_id,
        "target_url": target_url,
        "objective": payload.objective,
        "status": "queued",
        "created_by": user.id,
        "report": None,
    }

    async def _run_campaign_task():
        try:
            report = await orchestrator.run_autonomous_campaign(
                application_id=payload.application_id,
                target_url=target_url,
                objective=payload.objective,
                credentials=payload.credentials,
                login_selectors=payload.login_selectors,
            )
            _CAMPAIGNS[campaign_id]["status"] = "completed"
            _CAMPAIGNS[campaign_id]["report"] = report
        except Exception as ex:
            logger.exception("Autonomous campaign %s failed", campaign_id)
            _CAMPAIGNS[campaign_id]["status"] = "failed"
            _CAMPAIGNS[campaign_id]["error"] = str(ex)

    background_tasks.add_task(_run_campaign_task)

    return {
        "campaign_id": campaign_id,
        "status": "queued",
        "target_url": target_url,
        "objective": payload.objective,
        "message": "Autonomous QA campaign initiated successfully.",
    }


@router.get("/campaigns")
async def list_campaigns(
    application_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    """List recent autonomous QA campaigns."""
    campaigns = list(_CAMPAIGNS.values())
    if application_id is not None:
        campaigns = [c for c in campaigns if c.get("application_id") == application_id]
    return campaigns[-limit:]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retrieve details, status, and intelligence report for an autonomous campaign."""
    campaign = _CAMPAIGNS.get(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found.",
        )
    return campaign


@router.post("/discover")
async def discover_application_structure(
    payload: DiscoveryRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Run on-demand autonomous discovery and return page blueprints and resilient element locators."""
    agent = AutonomousDiscoveryAgent(max_depth=payload.max_depth, max_pages=payload.max_pages)
    result = await agent.discover_application(
        base_url=payload.target_url,
        login_credentials=payload.credentials,
        login_selectors=payload.login_selectors,
    )
    return result


@router.post("/diagnose")
async def diagnose_step_failure(
    payload: DiagnoseRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Classify a test execution failure into root causes with recommended remediation."""
    agent = AutonomousAnalysisAgent()
    diagnosis = await agent.diagnose_failure(
        action=payload.action,
        selector=payload.selector,
        error_message=payload.error_message,
        page_url=payload.page_url,
        dom_snippet=payload.dom_snippet,
        status_code=payload.status_code,
        duration_ms=payload.duration_ms,
    )
    return {
        "category": diagnosis.category.value,
        "confidence": diagnosis.confidence,
        "root_cause": diagnosis.root_cause,
        "suggested_fix": diagnosis.suggested_fix,
        "evidence": diagnosis.evidence,
        "candidate_selectors": diagnosis.candidate_selectors,
    }


@router.post("/heal-step")
async def heal_test_step(
    payload: HealStepRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Trigger autonomous self-healing for a failing step selector."""
    agent = AutonomousHealingAgent()
    record = await agent.attempt_heal_step(
        app_id=payload.application_id,
        test_id=payload.test_id,
        step_index=payload.step_index,
        action=payload.action,
        failing_selector=payload.failing_selector,
        candidate_selectors=payload.candidate_selectors,
    )
    if not record:
        return {
            "healed": False,
            "message": "No confident candidate selector found to heal this step.",
        }

    return {
        "healed": True,
        "original_selector": record.original_selector,
        "healed_selector": record.healed_selector,
        "strategy": record.strategy,
        "confidence": record.confidence,
        "validated_live": record.validated_live,
        "duration_ms": record.duration_ms,
    }
