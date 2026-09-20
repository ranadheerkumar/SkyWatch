"""SkyWatch Enterprise Capabilities and Tool Registry API Endpoints.

Exposes capability discovery, tool catalog introspection, and dynamic agentic planning.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.capabilities import CapabilityCategory, PlatformCapability, default_capability_registry
from app.core.tool_registry import default_tool_registry
from app.services.capability_orchestrator import default_capability_orchestrator

router = APIRouter(tags=["capabilities-and-tools"])


class AgenticPlanRequest(BaseModel):
    objective: str = Field(..., description="Natural language objective for the quality agent")
    application_id: int | None = Field(default=None, description="Optional target application ID")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context or requirements")


@router.get("/capabilities", summary="List Platform Capabilities")
async def list_capabilities(
    category: CapabilityCategory | None = Query(None, description="Filter by category"),
    available_only: bool = Query(False, description="Filter to only currently available capabilities"),
) -> dict[str, Any]:
    """Return all canonical platform capabilities registered in SkyWatch."""
    caps = default_capability_registry.list_capabilities(category=category, available_only=available_only)
    return {
        "total": len(caps),
        "capabilities": [c.to_dict() for c in caps],
    }


@router.get("/capabilities/taxonomy", summary="Platform Capability Taxonomy")
async def get_capability_taxonomy() -> dict[str, Any]:
    """Return capability categories and associated capability identifiers."""
    taxonomy: dict[str, list[dict[str, str]]] = {}
    for cat in CapabilityCategory:
        caps = default_capability_registry.list_capabilities(category=cat)
        taxonomy[cat.value] = [{"capability": c.capability.value, "name": c.name} for c in caps]
    return {
        "categories": [c.value for c in CapabilityCategory],
        "taxonomy": taxonomy,
    }


@router.get("/tools", summary="List Standardized Enterprise Tools")
async def list_tools(
    capability: PlatformCapability | None = Query(None, description="Filter by capability"),
    available_only: bool = Query(False, description="Filter to only available tools"),
) -> dict[str, Any]:
    """Return catalog of all registered enterprise tools with schemas and metadata."""
    tools = default_tool_registry.list_tools(capability=capability, available_only=available_only)
    return {
        "total": len(tools),
        "tools": [t.to_dict() for t in tools],
    }


@router.get("/tools/{tool_id:path}", summary="Get Tool Specification")
async def get_tool(tool_id: str) -> dict[str, Any]:
    """Return complete specification, parameters, and schemas for a specific tool."""
    tool = default_tool_registry.get(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_id}' is not registered in the Enterprise Tool Registry.",
        )
    return tool.descriptor.to_dict()


@router.post("/orchestrator/agentic-plan", summary="Generate Dynamic Agentic Plan")
async def generate_agentic_plan(payload: AgenticPlanRequest) -> dict[str, Any]:
    """Dynamically discover capabilities and formulate an execution plan for a user objective."""
    plan = default_capability_orchestrator.plan_objective(
        objective=payload.objective,
        application_id=payload.application_id,
        context=payload.context,
    )
    return plan.to_dict()


@router.post("/orchestrator/agentic-execute", summary="Execute Dynamic Agentic Plan")
async def execute_agentic_plan(payload: AgenticPlanRequest) -> dict[str, Any]:
    """Formulate and immediately execute a capability-orchestrated agent plan."""
    plan = default_capability_orchestrator.plan_objective(
        objective=payload.objective,
        application_id=payload.application_id,
        context=payload.context,
    )
    executed_plan = await default_capability_orchestrator.execute_plan(plan)
    return executed_plan.to_dict()
