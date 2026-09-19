# Scenario Agent

**Current status:** Implemented deterministic scenario-planning boundary
**Definition:** [`.github/agents/test-scenario.agent.md`](../.github/agents/test-scenario.agent.md)
**Runtime:** `backend/app/services/ai_generation_pipeline.py::build_scenario_snapshot`

## Responsibility

The Scenario Agent turns the Planner and Context Builder outputs into balanced, independent coverage categories before business test cases are generated.

## Coverage

- positive and happy paths;
- negative and validation paths;
- boundary and edge conditions;
- exploratory charters and unscripted state resilience;
- security and authorization risks;
- accessibility and keyboard behavior;
- recovery and observable failure outcomes.

## Guardrails

- Preserve source and application scope.
- Avoid duplicate journeys and generic filler.
- Keep scenarios independently runnable for bounded parallel execution.
- State prerequisites, test data needs, cleanup, and expected outcomes.
- Do not compile selectors or mutate the repository; Test Design and Repository own those steps.

## Future hardening

Add explicit scenario IDs, requirement/risk links, coverage-gap scoring, data-isolation metadata, and evaluation against approved scenario libraries before promoting provider-backed scenario reasoning.
