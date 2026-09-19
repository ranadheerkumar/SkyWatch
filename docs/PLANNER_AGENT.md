# Planner Agent

**Current status:** Implemented provider-backed stage
**Definition:** [`.github/agents/playwright-test-planner.agent.md`](../.github/agents/playwright-test-planner.agent.md)
**Runtime:** `backend/app/services/ai_service.py::generate_ai_test_plan`

## Responsibility

The Planner Agent converts application, discovery, document, reference-case, and prompt context into a structured risk-based test plan. It selects entry points, navigation paths, coverage areas, risks, and a target case count before the Generator runs.

## Inputs

- selected `application_id` context;
- bounded Application Discovery snapshot;
- uploaded requirement context;
- existing reference cases;
- requested coverage flags, module focus, and step bounds;
- provider/model configuration.

## Outputs

- recommended case count;
- authentication and session plan with `{{login_email}}` and `{{login_password}}` placeholders;
- requirements and source signals;
- coverage matrix across positive, negative, boundary, edge, security, and accessibility;
- navigation paths and entry points;
- exploratory charters (observations, hypotheses, safe exploratory actions, and expected verification);
- risk areas;
- provider/model and definition provenance.

## Guardrails

- Return structured JSON validated by the service contract.
- Every planned scenario must trace to requirements, discovery evidence, or an explicit prompt signal.
- Do not invent controls, roles, pages, or business rules.
- Do not mutate cases or automation; Repository owns persistence.
- Apply provider timeout/error policy and preserve the plan or failure state in the durable job result.

## Future hardening

Add plan versioning, plan-quality evaluation sets, cost budgets, explicit requirement-to-plan references, retries/circuit breakers, and a human approval checkpoint for high-risk scope.
