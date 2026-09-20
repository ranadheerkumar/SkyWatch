"""SkyWatch Dynamic Capability Orchestrator.

Implements the dynamic Agentic Orchestration loop from Section 3 of the Master Architecture:
User Objective → Context → Agent Orchestrator → Planning → Capability Discovery → Tool Selection → Execution.
Eliminates hardcoded technology workflows by discovering capabilities and selecting tools dynamically.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.capabilities import CapabilityRegistry, PlatformCapability, default_capability_registry
from app.core.tool_registry import EnterpriseToolRegistry, default_tool_registry

logger = logging.getLogger("skywatch.services.capability_orchestrator")


@dataclass
class AgenticPlanStep:
    """An individual step in a dynamically orchestrated agent plan."""
    step_id: str
    goal: str
    capability: str
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "planned"  # planned, executing, completed, failed, skipped
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgenticPlan:
    """A complete plan dynamically formulated by the capability orchestrator."""
    plan_id: str
    objective: str
    application_id: int | None = None
    capabilities_discovered: list[str] = field(default_factory=list)
    tools_selected: list[str] = field(default_factory=list)
    steps: list[AgenticPlanStep] = field(default_factory=list)
    status: str = "ready"  # ready, in_progress, completed, failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "application_id": self.application_id,
            "capabilities_discovered": self.capabilities_discovered,
            "tools_selected": self.tools_selected,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class AgenticProviderSelection:
    """Agentic decision structure for dynamic execution provider and environment selection."""
    selected_provider_id: str
    provider_name: str
    rationale: str
    recommended_browser: str
    recommended_platform: str
    is_cloud_grid: bool
    fallback_provider_id: str = "local"
    capabilities_matched: list[str] = field(default_factory=list)
    provider_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityOrchestrator:
    """Agent orchestrator that plans and executes based on dynamically discovered capabilities."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        tool_registry: EnterpriseToolRegistry | None = None,
    ) -> None:
        self._capabilities = capability_registry or default_capability_registry
        self._tools = tool_registry or default_tool_registry

    def plan_objective(
        self,
        objective: str,
        application_id: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgenticPlan:
        """Formulate a dynamic capability-based plan for a user objective."""
        plan_id = f"plan-{uuid.uuid4().hex[:10]}"
        ctx = context or {}
        lowered_obj = objective.casefold()

        # Step 1: Discover available capabilities
        available_caps = [c.capability for c in self._capabilities.list_capabilities(available_only=True)]
        discovered_cap_names = [c.value for c in available_caps]

        steps: list[AgenticPlanStep] = []
        tools_selected: list[str] = []

        # Step 2: Dynamically map requirements & objective to capabilities & tools
        step_idx = 1

        # Check if requirement analysis is needed
        if "spec" in lowered_obj or "requirement" in lowered_obj or "document" in lowered_obj or ctx.get("document_path"):
            doc_tools = self._tools.list_tools(capability=PlatformCapability.REQUIREMENT_ANALYSIS, available_only=True)
            if doc_tools:
                tool = doc_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal="Analyze requirements document and extract user stories",
                        capability=PlatformCapability.REQUIREMENT_ANALYSIS.value,
                        tool_id=tool.tool_id,
                        arguments={"file_path": ctx.get("document_path", "uploaded_requirements.md")},
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Check if test data generation is needed
        if "data" in lowered_obj or "dataset" in lowered_obj or "synthetic" in lowered_obj:
            data_tools = self._tools.list_tools(capability=PlatformCapability.TEST_DATA_GENERATION, available_only=True)
            if data_tools:
                tool = data_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal="Synthesize balanced test datasets with boundary and valid values",
                        capability=PlatformCapability.TEST_DATA_GENERATION.value,
                        tool_id=tool.tool_id,
                        arguments={"application_id": application_id or 1, "count": 10},
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Check if API automation is requested
        if "api" in lowered_obj or "endpoint" in lowered_obj or "rest" in lowered_obj:
            api_tools = self._tools.list_tools(capability=PlatformCapability.API_AUTOMATION, available_only=True)
            if api_tools:
                tool = api_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal="Execute API schema validation and endpoint resilience checks",
                        capability=PlatformCapability.API_AUTOMATION.value,
                        tool_id=tool.tool_id,
                        arguments={"url": ctx.get("api_url", "http://127.0.0.1:8000/api/v1/observability/health"), "method": "GET"},
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Check if UI browser automation or script generation is requested
        if "browser" in lowered_obj or "script" in lowered_obj or "ui" in lowered_obj or "e2e" in lowered_obj or not steps:
            gen_tools = self._tools.list_tools(capability=PlatformCapability.UI_BROWSER_AUTOMATION, available_only=True)
            if gen_tools:
                tool = gen_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal="Generate multi-framework automation test scripts",
                        capability=PlatformCapability.UI_BROWSER_AUTOMATION.value,
                        tool_id=tool.tool_id,
                        arguments={"framework": ctx.get("framework", "playwright"), "application_id": application_id},
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Check if Git commit/push is requested
        if "git" in lowered_obj or "commit" in lowered_obj or "push" in lowered_obj or ctx.get("git_repo"):
            git_tools = self._tools.list_tools(capability=PlatformCapability.SOURCE_CONTROL, available_only=True)
            if git_tools:
                tool = git_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal="Commit test suite to remote source control repository",
                        capability=PlatformCapability.SOURCE_CONTROL.value,
                        tool_id=tool.tool_id,
                        arguments={"action": "commit_suite", "repo": ctx.get("git_repo", "")},
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Check if test execution is requested
        if "run" in lowered_obj or "execute" in lowered_obj or "verify" in lowered_obj:
            exec_tools = self._tools.list_tools(capability=PlatformCapability.TEST_EXECUTION, available_only=True)
            if exec_tools:
                provider_selection = self.select_execution_provider(objective, target=ctx, requested_provider=ctx.get("provider"))
                tool = exec_tools[0]
                steps.append(
                    AgenticPlanStep(
                        step_id=f"step-{step_idx}",
                        goal=f"Execute tests dynamically via {provider_selection.provider_name} ({provider_selection.rationale})",
                        capability=PlatformCapability.TEST_EXECUTION.value,
                        tool_id=tool.tool_id,
                        arguments={
                            "url": ctx.get("target_url", "https://example.com"),
                            "provider": provider_selection.selected_provider_id,
                            "browser": provider_selection.recommended_browser,
                        },
                    )
                )
                tools_selected.append(tool.tool_id)
                step_idx += 1

        # Always include Quality Intelligence / Reporting as final step
        report_tools = self._tools.list_tools(capability=PlatformCapability.REPORTING, available_only=True)
        if report_tools:
            tool = report_tools[0]
            steps.append(
                AgenticPlanStep(
                    step_id=f"step-{step_idx}",
                    goal="Compile Allure 2 execution reports and release quality metrics",
                    capability=PlatformCapability.REPORTING.value,
                    tool_id=tool.tool_id,
                    arguments={"run_id": ctx.get("run_id", "latest")},
                )
            )
            tools_selected.append(tool.tool_id)

        return AgenticPlan(
            plan_id=plan_id,
            objective=objective,
            application_id=application_id,
            capabilities_discovered=discovered_cap_names,
            tools_selected=list(dict.fromkeys(tools_selected)),
            steps=steps,
        )

    def select_execution_provider(
        self,
        objective: str,
        target: dict[str, Any] | None = None,
        requested_provider: str | None = None,
    ) -> AgenticProviderSelection:
        """
        Agentic reasoning engine that evaluates testing goals, device requirements,
        cloud availability, and execution context to dynamically assign the optimal provider.
        Always maintains a guaranteed zero-regression fallback to LocalExecutionProvider.
        """
        from app.services.execution_providers.registry import execution_registry

        ctx = target or {}
        lowered = f"{objective} {ctx.get('browser', '')} {ctx.get('platform', '')} {ctx.get('device', '')}".casefold()

        # 1. If explicitly requested by user or policy, verify and assign
        if requested_provider:
            clean_req = requested_provider.strip().lower()
            prov = execution_registry.get(clean_req)
            if prov and (clean_req == "local" or prov.is_configured()):
                return AgenticProviderSelection(
                    selected_provider_id=prov.provider_id,
                    provider_name=prov.name,
                    rationale=f"Directly requested provider '{prov.name}' assigned by user/pipeline configuration.",
                    recommended_browser=ctx.get("browser", "chromium"),
                    recommended_platform=ctx.get("platform", "web"),
                    is_cloud_grid=clean_req in ("sauce_labs", "lambdatest"),
                    capabilities_matched=[c.value for c in prov.get_capabilities().supported_platforms],
                )

        # 2. Real Mobile / iOS / iPad / Android reasoning
        is_mobile_req = any(kw in lowered for kw in ("mobile", "ios", "iphone", "ipad", "android", "galaxy", "real device"))
        if is_mobile_req:
            lt = execution_registry.get("lambdatest")
            if lt and lt.is_configured():
                return AgenticProviderSelection(
                    selected_provider_id="lambdatest",
                    provider_name=lt.name,
                    rationale="Selected LambdaTest Smart Automation Grid for real mobile device testing and cross-browser cloud matrix.",
                    recommended_browser=ctx.get("browser", "chromium"),
                    recommended_platform="mobile",
                    is_cloud_grid=True,
                    capabilities_matched=["MOBILE_AUTOMATION", "REAL_DEVICES", "VIDEO_RECORDING"],
                    provider_config={"device_name": ctx.get("device", "iPhone 15"), "is_real_mobile": True},
                )
            sauce = execution_registry.get("sauce_labs")
            if sauce and sauce.is_configured():
                return AgenticProviderSelection(
                    selected_provider_id="sauce_labs",
                    provider_name=sauce.name,
                    rationale="Selected Sauce Labs Cloud Grid for real iOS/Android device farm execution.",
                    recommended_browser=ctx.get("browser", "chromium"),
                    recommended_platform="mobile",
                    is_cloud_grid=True,
                    capabilities_matched=["MOBILE_AUTOMATION", "REAL_DEVICES", "SAUCE_TUNNEL"],
                    provider_config={"device_name": ctx.get("device", "iPhone 14")},
                )
            # Safe local fallback with emulation
            local = execution_registry.get("local")
            return AgenticProviderSelection(
                selected_provider_id="local",
                provider_name=local.name,
                rationale="Real device cloud credentials not configured. Gracefully falling back to Local Playwright Runner with responsive viewport emulation.",
                recommended_browser=ctx.get("browser", "chromium"),
                recommended_platform="web",
                is_cloud_grid=False,
                fallback_provider_id="local",
                capabilities_matched=["EMULATED_MOBILE", "LOCAL_VIEWPORT"],
                provider_config={"emulate_mobile": True},
            )

        # 3. Cloud Container / Isolation reasoning
        if any(kw in lowered for kw in ("container", "docker", "isolated", "headless cluster")):
            for pid in ("docker", "azure", "gcp", "aws"):
                prov = execution_registry.get(pid)
                if prov and prov.is_configured():
                    return AgenticProviderSelection(
                        selected_provider_id=prov.provider_id,
                        provider_name=prov.name,
                        rationale=f"Selected {prov.name} for ephemeral containerized test execution.",
                        recommended_browser=ctx.get("browser", "chromium"),
                        recommended_platform="web",
                        is_cloud_grid=pid in ("azure", "gcp", "aws"),
                        capabilities_matched=["CONTAINER_EXECUTION", "PARALLEL_RUNNER"],
                    )

        # 4. Cross-browser matrix reasoning (e.g. WebKit / Safari or Firefox)
        if "safari" in lowered or "webkit" in lowered:
            browser_choice = "webkit"
        elif "firefox" in lowered or "gecko" in lowered:
            browser_choice = "firefox"
        else:
            browser_choice = ctx.get("browser", "chromium")

        # 5. Default First-Class Local Execution
        local = execution_registry.get("local")
        return AgenticProviderSelection(
            selected_provider_id="local",
            provider_name=local.name,
            rationale="Selected Local Playwright Runner for ultra-low latency, zero cloud dependency, live browser visibility, and AI self-healing.",
            recommended_browser=browser_choice,
            recommended_platform="web",
            is_cloud_grid=False,
            capabilities_matched=["LOCAL_PLAYWRIGHT", "DOM_INSPECTION", "AUDIO_VIDEO_NARRATION", "SELF_HEALING"],
        )

    async def execute_plan(self, plan: AgenticPlan) -> AgenticPlan:
        """Execute the steps of an AgenticPlan and collect observations."""
        plan.status = "in_progress"
        for step in plan.steps:
            step.status = "executing"
            res = await self._tools.execute(step.tool_id, step.arguments, call_id=step.step_id)
            if res.success:
                step.status = "completed"
                step.result = res.data
            else:
                step.status = "failed"
                step.error = res.error
                plan.status = "failed"
                break
        if plan.status != "failed":
            plan.status = "completed"
        return plan


# Global singleton orchestrator
default_capability_orchestrator = CapabilityOrchestrator()
