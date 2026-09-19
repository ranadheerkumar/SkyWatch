"""AI QA Engine Backend Services Package."""

from app.services.agent_definitions import (
    AGENT_FILE_MAP,
    AGENTS_DIRECTORY,
    AgentDefinition,
    AgentDefinitionError,
    build_agent_guidance_block,
    get_agent_trace_metadata,
    load_agent_definition,
)
from app.services.ai_generation_jobs import (
    enqueue_ai_generation,
)
from app.services.ai_generation_pipeline import (
    AGENT_STAGE_DEFINITIONS,
    agent_definition_manifest,
    build_context_snapshot,
    build_planner_snapshot,
    build_scenario_snapshot,
    build_validation_snapshot,
    initial_agent_stages,
    initial_workflow_result,
)
from app.services.ai_service import (
    AIServiceError,
    auto_parameterize_case_steps,
    discover_application_context,
    generate_ai_test_cases,
    generate_ai_test_plan,
    generate_healing_step,
    resolve_parameter_name_for_field,
    synthesize_parameter_value,
)
from app.services.automation_builder import (
    build_case_automation_from_text,
)
from app.services.self_learning import (
    SelfLearningEngine,
)
from app.services.test_data_generator import (
    TestDataGeneratorService,
)
from app.services.test_execution import (
    execute_web_target,
)
from app.services.vector_service import (
    VectorStoreService,
)

__all__ = [
    "AGENT_FILE_MAP",
    "AGENTS_DIRECTORY",
    "AGENT_STAGE_DEFINITIONS",
    "AgentDefinition",
    "AgentDefinitionError",
    "AIServiceError",
    "SelfLearningEngine",
    "TestDataGeneratorService",
    "VectorStoreService",
    "agent_definition_manifest",
    "build_case_automation_from_text",
    "build_context_snapshot",
    "build_planner_snapshot",
    "build_scenario_snapshot",
    "build_validation_snapshot",
    "discover_application_context",
    "enqueue_ai_generation",
    "execute_web_target",
    "generate_ai_test_cases",
    "generate_ai_test_plan",
    "generate_healing_step",
    "get_agent_trace_metadata",
    "initial_agent_stages",
    "initial_workflow_result",
    "load_agent_definition",
]
