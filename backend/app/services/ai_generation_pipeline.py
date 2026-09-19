import json
import re
from datetime import datetime, timezone
from typing import Any

from app.services.agent_definitions import AgentDefinitionError, get_agent_trace_metadata


AGENT_WORKFLOW_VERSION = "1.3"


AGENT_STAGE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "key": "document_analysis",
        "name": "Document Analysis Agent",
        "responsibility": "Extract requirements, features, business rules, risks, and testable statements.",
        "definition_file": ".github/agents/document-analysis.agent.md",
    },
    {
        "key": "application_discovery",
        "name": "Application Discovery Agent",
        "responsibility": "Inspect authorized target pages and perform bounded safe exploratory interactions for workflow signals.",
        "definition_file": ".github/agents/application-discovery.agent.md",
    },
    {
        "key": "context_builder",
        "name": "Context Builder Agent",
        "responsibility": "Combine application, document, reference-case, and exploratory workflow context for downstream planning.",
        "definition_file": ".github/agents/context-builder.agent.md",
    },
    {
        "key": "playwright_planner",
        "name": "Playwright Planner Agent",
        "responsibility": "Use observed and exploratory evidence to define entry points, coverage boundaries, and exit criteria.",
        "definition_file": ".github/agents/playwright-test-planner.agent.md",
    },
    {
        "key": "scenario_agent",
        "name": "Test Scenario Agent",
        "responsibility": "Balance positive, negative, boundary, edge, exploratory, security, and accessibility coverage.",
        "definition_file": ".github/agents/test-scenario.agent.md",
    },
    {
        "key": "test_case_generator",
        "name": "Test Case Generator Agent",
        "responsibility": "Generate structured cases from source and exploratory charters with explicit outcomes.",
        "definition_file": ".github/agents/playwright-test-generator.agent.md",
    },
    {
        "key": "test_data_generator",
        "name": "Test Data Generator Agent",
        "responsibility": "Synthesize realistic positive, negative, boundary, and edge test datasets informed by live application entities.",
        "definition_file": ".github/agents/test-data-generator.agent.md",
    },
    {
        "key": "validation_agent",
        "name": "Validation Agent",
        "responsibility": "Check duplicates, step completeness, coverage signals, and review needs before persistence.",
        "definition_file": ".github/agents/test-case-validator.agent.md",
    },
    {
        "key": "repository",
        "name": "Repository Agent",
        "responsibility": "Persist approved workflow output and attach executable automation definitions.",
        "definition_file": ".github/agents/repository.agent.md",
    },
)

AGENT_STAGE_AGENT_KEYS = {
    "document_analysis": "document_analysis",
    "application_discovery": "discovery",
    "context_builder": "context_builder",
    "playwright_planner": "planner",
    "scenario_agent": "scenario",
    "test_case_generator": "generator",
    "test_data_generator": "test_data",
    "validation_agent": "validator",
    "repository": "repository",
}


def agent_definition_manifest() -> list[dict[str, str | None]]:
    try:
        loaded_definitions = {
            item["key"]: item
            for item in get_agent_trace_metadata(list(AGENT_STAGE_AGENT_KEYS.values()))
        }
    except AgentDefinitionError:
        loaded_definitions = {}
    manifest: list[dict[str, str | None]] = []
    for definition in AGENT_STAGE_DEFINITIONS:
        loaded = loaded_definitions.get(AGENT_STAGE_AGENT_KEYS[definition["key"]])
        manifest.append({
            "key": definition["key"],
            "name": definition["name"],
            "source": f".github/agents/{loaded['file_name']}" if loaded else definition["definition_file"],
            "version": loaded["version"] if loaded else AGENT_WORKFLOW_VERSION,
            "checksum": loaded["checksum_sha256"] if loaded else None,
        })
    return manifest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initial_agent_stages() -> list[dict[str, Any]]:
    return [
        {
            **definition,
            "status": "queued",
            "progress": 0,
            "detail": "Queued for the generation workflow.",
            "started_at": None,
            "finished_at": None,
            "metrics": {},
        }
        for definition in AGENT_STAGE_DEFINITIONS
    ]


def initial_workflow_result() -> dict[str, Any]:
    return {
        "workflow_version": AGENT_WORKFLOW_VERSION,
        "agent_definitions": agent_definition_manifest(),
        "agent_stages": initial_agent_stages(),
    }


def update_agent_stages(
    stages: list[dict[str, Any]],
    active_key: str,
    *,
    status: str,
    detail: str,
    progress: int,
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    timestamp = _now()
    for stage in stages:
        next_stage = dict(stage)
        if stage.get("key") == active_key:
            next_stage["status"] = status
            next_stage["detail"] = detail
            next_stage["progress"] = max(0, min(100, progress))
            next_stage["metrics"] = {**(stage.get("metrics") or {}), **(metrics or {})}
            if status == "running" and not stage.get("started_at"):
                next_stage["started_at"] = timestamp
            if status in {"completed", "failed", "skipped"}:
                next_stage["finished_at"] = timestamp
        updated.append(next_stage)
    return updated


def _unique(values: list[str], limit: int = 30) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip(" -:#*\t`\"'")
        if len(normalized) < 2 or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        result.append(normalized[:120])
        if len(result) >= limit:
            break
    return result


def build_context_snapshot(
    *,
    application_name: str,
    platform: str,
    target: str,
    prompt: str,
    document_context: str,
    reference_cases: list[str],
    discovery_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    discovery_text = json.dumps(discovery_snapshot or {}, ensure_ascii=True)
    corpus = "\n".join([prompt, document_context, discovery_text, *reference_cases])
    lines = [line.strip() for line in corpus.splitlines() if line.strip()]
    modules: list[str] = []
    for line in lines:
        match = re.match(r"(?:module|area|feature|component|screen|page|epic|service|topic)\s*[:\-]\s*(.+)", line, re.IGNORECASE)
        if match:
            modules.append(match.group(1))
        elif line.startswith(("#", "===")):
            clean_head = re.sub(r"^[#=\s]+", "", line).strip()
            if len(clean_head) >= 3 and len(clean_head) < 80 and not clean_head.lower().startswith("document:"):
                modules.append(clean_head)
    if not modules:
        for candidate, label in (
            ("login|sign in|authentication|password", "Authentication"),
            ("search|filter|query|lookup", "Search and filtering"),
            ("dashboard|home|navigation|menu", "Navigation and dashboard"),
            ("report|analytics|export", "Reporting and analytics"),
            ("user|owner|profile|account", "User and account management"),
            ("api|openapi|endpoint|request|response|schema", "API contracts"),
            ("performance|latency|throughput|concurrency|load|capacity", "Performance and capacity"),
        ):
            if re.search(candidate, corpus, re.IGNORECASE):
                modules.append(label)
    requirements = [
        line for line in lines
        if re.search(r"\b(requirement|req|user story|acceptance criteria|shall|must|required|should|given|when|then|as a|i want|so that|validate|verify|ensure|test case|scenario|rule)\b", line, re.IGNORECASE)
    ]
    workflows = [
        line for line in lines
        if re.search(r"\b(navigate|login|sign in|click|select|submit|create|search|filter|save|workflow|open|view|edit|delete)\b", line, re.IGNORECASE)
    ]
    risks = [
        line for line in lines
        if re.search(r"\b(error|invalid|failure|security|permission|timeout|empty|boundary|duplicate|risk|denied|unauthorized)\b", line, re.IGNORECASE)
    ]
    return {
        "application": application_name,
        "platform": platform,
        "target": target,
        "modules": _unique(modules, limit=30),
        "requirements_found": max(len(requirements), 1 if document_context.strip() else 0),
        "workflow_signals": max(len(workflows), 1 if document_context.strip() else 0),
        "risk_signals": _unique(risks, limit=16),
        "reference_case_count": len(reference_cases),
        "document_context_chars": len(document_context),
        "discovery": discovery_snapshot or {},
        "discovered_heading_count": len((discovery_snapshot or {}).get("headings") or []),
        "discovered_control_count": len((discovery_snapshot or {}).get("buttons") or []) + len((discovery_snapshot or {}).get("links") or []),
        "discovered_route_count": len((discovery_snapshot or {}).get("observed_routes") or []),
        "exploratory_observations": (discovery_snapshot or {}).get("exploratory_observations") or [],
        "exploratory_hypotheses": (discovery_snapshot or {}).get("exploratory_hypotheses") or [],
        "exploratory_observation_count": len((discovery_snapshot or {}).get("exploratory_observations") or []),
        "exploratory_hypothesis_count": len((discovery_snapshot or {}).get("exploratory_hypotheses") or []),
        "authenticated_snapshot": bool((discovery_snapshot or {}).get("authenticated_snapshot")),
    }


def build_planner_snapshot(*, target: str, context: dict[str, Any]) -> dict[str, Any]:
    modules = context.get("modules") or ["Core application workflow"]
    return {
        "entry_points": [target],
        "exit_points": ["Expected result and configured validation checks"],
        "navigation_plan": [f"Explore {module} workflows" for module in modules[:24]],
        "coverage_plan": ["Positive paths", "Negative and validation paths", "Boundary and edge paths", "Exploratory safe state transitions"],
        "risk_based_plan": context.get("risk_signals") or ["Review authentication, navigation, and failure handling"],
        "exploratory_observations": list(context.get("exploratory_observations") or [])[:12],
        "exploratory_hypotheses": list(context.get("exploratory_hypotheses") or [])[:12],
        "exploratory_charter_required": True,
    }


def build_scenario_snapshot(
    payload: dict[str, Any],
    context: dict[str, Any],
    planner_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    categories: list[str] = []
    if payload.get("include_positive_scenarios", True):
        categories.append("positive")
    if payload.get("include_negative_scenarios", True):
        categories.append("negative")
    if payload.get("include_boundary_scenarios", True):
        categories.append("boundary")
    if payload.get("include_edge_cases", True):
        categories.append("edge")
    if payload.get("include_security_scenarios", True):
        categories.append("security")
    if payload.get("include_accessibility_checks", True):
        categories.append("accessibility")
    if payload.get("include_api_validations", False):
        categories.append("api")
    if payload.get("include_performance_scenarios", False):
        categories.append("performance")
    categories.append("exploratory")
    exploratory_charters = list((planner_plan or {}).get("exploratory_charters") or [])[:12]
    return {
        "categories": categories,
        "module_count": len(context.get("modules") or []),
        "suggestion": "Generate independent scenarios with observable outcomes and no duplicate journeys; include bounded exploratory charters across critical state boundaries.",
        "exploratory_observation_count": len(context.get("exploratory_observations") or []),
        "exploratory_hypothesis_count": len(context.get("exploratory_hypotheses") or []),
        "exploratory_charters": exploratory_charters,
        "safe_exploration_only": True,
        "performance_budget": str(payload.get("performance_budget") or "").strip()[:500],
    }


def build_validation_snapshot(test_cases: list[Any], *, min_steps: int, max_steps: int) -> dict[str, Any]:
    title_keys: set[str] = set()
    duplicate_count = 0
    incomplete_count = 0
    review_count = 0
    for case in test_cases:
        title = re.sub(r"^TC\s*\d+\s*[-:]\s*", "", (getattr(case, "title", "") or "")).strip().casefold()
        if title in title_keys:
            duplicate_count += 1
        title_keys.add(title)
        step_count = len([line for line in (getattr(case, "steps", "") or "").splitlines() if line.strip()])
        if not getattr(case, "title", "") or not getattr(case, "steps", "") or not getattr(case, "expected_result", ""):
            incomplete_count += 1
        if step_count < min_steps or step_count > max_steps:
            review_count += 1
    total = len(test_cases)
    coverage_score = 0 if not total else max(0, min(100, 100 - (duplicate_count * 20) - (incomplete_count * 15) - (review_count * 5)))
    return {
        "coverage_score": coverage_score,
        "total_candidates": total,
        "duplicate_count": duplicate_count,
        "incomplete_count": incomplete_count,
        "review_count": review_count,
        "status": "passed" if duplicate_count == 0 and incomplete_count == 0 else "needs_review",
    }
