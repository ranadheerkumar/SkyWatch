# Workspace Delivery Policy

## Automatic source-change publishing

When completing a requested change to frontend/UI code or application source code in this repository:

1. Select and increment the application SemVer in `frontend/package.json` for every pushed commit: patch for fixes and documentation/workflow changes, minor for backwards-compatible capabilities, and major for breaking changes. Keep `frontend/package-lock.json` synchronized and update `docs/Changelog.md`.
2. Run the narrowest relevant validation first, then the applicable repository gates. If the user explicitly asks to defer or ignore tests, prioritize the implementation and bug fix, skip test creation and test-suite execution unless needed to diagnose a concrete failure, and report the skipped tests. Lightweight compile, typecheck, lint, build, migration, security, and secret-safety checks may still be used when they directly protect the change.
3. Run `node scripts/verify-version.mjs --require-bump` before committing; CI enforces the committed version increase with `node scripts/verify-version.mjs --require-history-bump`.
4. Review `git status`, `git diff --check`, and `git diff --stat`.
5. Stage only the intended source, test, configuration, and documentation files.
6. Create a concise reviewable commit prefixed with the application SemVer (e.g. `vX.Y.Z: <type>(<scope>): <summary>` or `vX.Y.Z: <summary>`). Every commit message MUST explicitly include the version prefix matching `frontend/package.json` (e.g. `v2.0.1: ...`) to ensure release traceability, keep commit logs standardized, and prevent version hallucinations.
7. Push the commit to the current branch's configured upstream remote (`origin/develop` or `origin/AutomationTool_POC`). Do NOT sync, merge, or push changes to `AutomationTool_POC_lkurra`.
8. Confirm the local branch and configured upstream resolve to the same commit, then report the commit and validation results.

Do not automatically publish when the user explicitly asks to keep changes local, when validation exposes unresolved failures, when the branch has no configured upstream, or when authentication/conflict issues block a safe push. Report the blocker and exact next command instead.

Never stage or push secrets, `.env` files, credentials, tokens, generated databases, logs, screenshots, videos, traces, build output, local runtime data, or unrelated user changes. If unrelated changes are mixed into the worktree, preserve them and keep them out of the commit unless the user explicitly asks to publish them too.

## Development-first mode

When the user says to focus on development and fixes for now:

- Implement the requested behavior and repair the owning code path first.
- Do not add, expand, or run tests unless the user asks for them or a concrete failure cannot be diagnosed safely without one.
- Keep existing tests and contracts intact unless the implementation requires a necessary compatibility update.
- Report deferred test work clearly; this preference does not permit skipping security, secret handling, migration safety, compile correctness, or unrelated-change safeguards.

Documentation-only changes follow the normal commit workflow unless the user asks for immediate publication. Changes that include frontend/UI or application source code use the automatic publishing workflow above.

## Continuous instruction and documentation alignment

Always keep `.github/copilot-instructions.md` synchronized and updated as new features, architectural decisions, and APIs are introduced:
- Whenever new systems, engines, integrations, or workflows are added, update `.github/copilot-instructions.md` alongside the canonical documentation in `docs/`.
- Ground all conventions and contracts in `.github/copilot-instructions.md` so that future agent sessions stay aligned with existing patterns and never hallucinate deprecated, assumed, or non-existent interfaces.
- Ensure every commit message adheres to the version prefix rule (`vX.Y.Z: <type>(<scope>): <description>`).

## Current project contracts

- Treat `docs/` as the canonical documentation tree. Do not recreate the removed root `doc/` tree.
- Preserve application-scoped `application_id` context across test cases, automation, AI jobs, runs, evidence, defects, recommendations, suites, and reports.
- AI generation is Discovery-first, Planner-first, and Generator-batched: it uses uploaded requirements, bounded target discovery, and source anchors, persists durable job stages, and must not invent unrelated cases when source context is available.
- Execute Tests queues independent case runs with bounded one-to-five worker concurrency and isolated browser contexts. Use run IDs when diagnosing parallel activity; Redis/RQ needs multiple worker processes for equivalent throughput. Runs and batches support immediate user-initiated stopping/cancellation (`POST /api/v1/execution/{run_id}/cancel` and `POST /api/v1/execution/batch/{batch_id}/cancel`).
- AI generation runs as durable background jobs (`POST /api/v1/ai-generation/jobs`); the frontend maintains background polling across navigation and page switches so generation continues uninterrupted.
- A successful same-action locator repair is validated, persisted to the test case automation, recorded as an `auto_applied` healing recommendation, and audited. Never change business actions, assertions, credentials, or unrelated steps automatically.
- Existing and AI-generated test cases use the persisted numbered `steps` string and the interactive step editor. Preserve that API format when editing, adding, or deleting steps.
- Run History is the reference data surface for filters, sorting, pagination, status presentation, table density, and contained scrolling.
- Autonomous Orchestrator (`docs/AUTONOMOUS_TESTING_ENGINE.md`): Closed-loop orchestration coordinating Discover → Plan → Execute → Diagnose → Self-Heal → Learn → Report with parallel execution and adaptive circuit breakers.
- Visual Regression Engine (`docs/VISUAL_REGRESSION_ENGINE.md`): Baseline snapshot capture, structural DOM hashing, and pixel diff classification across responsive viewports (Desktop, Tablet, Mobile).
- API Testing Agent (`docs/API_TESTING_AGENT.md`): OpenAPI/Swagger auto-discovery, schema contract validation, negative/boundary payload generation, and latency profiling.
- Observability & Rate Limiting (`docs/OBSERVABILITY_GUIDE.md`): Token bucket rate limiting per endpoint group, circuit breaking, and aggregated metric telemetry (`/api/v1/observability/metrics`).
- Multi-LLM Architecture: Dynamic cascade supporting Google Gemini, GitHub Copilot, OpenAI, Anthropic, and Azure based on available environment credentials with zero generic fallback lock-in.
  - Google Gemini: Configured with active models (`gemini-flash-latest` [default], `gemini-pro-latest`, `gemini-3.7-flash`, `gemini-2.5-flash`, and `gemini-2.5-pro`). Never reference or default to deprecated models (`gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`) which return 404 NOT FOUND from Google's Generative Language API.
  - Live Model Discovery: `POST /api/v1/settings/ai-models` discovers models dynamically from provider endpoints.
  - Probe Token Budget: Connectivity probes must reserve at least 128 tokens to accommodate modern thinking/reasoning signatures before content completion.
  - Offline Mock Simulation: Local inference provider supports built-in simulation for credential-free local development and testing.
- Smart Test Data Generator Agent (`docs/TEST_DATA_GENERATOR_AGENT.md`): Synthesizes balanced, type-safe datasets covering valid, invalid, boundary, and edge/security scenarios with self-learning entity adaptation.
- Self-Learning Engine (`docs/SELF_LEARNING_ENGINE.md`): Continuously harvests verified locator resolutions, assertion outcomes, and domain entities from passing/healed executions into durable vector memory.
- Enterprise ALM Bridge (`docs/JIRA_QTEST_INTEGRATION_GUIDE.md`): Jira Cloud REST API v3 with Atlassian Document Format (ADF v1), bi-directional issue linking, multipart attachment uploads, and workflow transitions; Tricentis qTest SaaS Build API hierarchy (`/projects/{projectId}/builds`), auto-test-logs execution reporting, and dynamic custom field validation. Respect `ENABLE_JIRA_WRITE` and `ENABLE_QTEST_WRITE` safety controls.
- Local Application Startup & Service Topology:
  - Backend: FastAPI/Uvicorn on `http://127.0.0.1:8000` (`PYTHONPATH=. .venv/bin/python3 -m app.core.migration_bootstrap && PYTHONPATH=. .venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000`).
  - Frontend: Next.js on `http://localhost:3000` (`npm run dev` from `frontend/`).
  - Health & Metrics Endpoints: `GET /api/v1/observability/health` and `GET /api/v1/observability/metrics`.
- UI Navigation & Architecture:
  - Core navigation is consolidated into 7 focused product pillars: `dashboard`, `aiGenerator`, `systemMap`, `execution`, `runHistory`, `defects`, `reports`, and `settings` (with embedded audit and AI settings).
  - Legacy routes (`/projects`, `/applications`, `/test-cases`, `/test-suites`, `/evidence`, `/mapping`) resolve to their primary pillar sections to avoid empty wrapper pages.
- Build Report Parity & Canonical Backend Synchronization:
  - Post-execution build reports MUST query `GET /api/v1/execution/builds/{build_id}/detail` upon batch completion. Do not display diverged client-synthesized reports.
  - Build ID display across `CompleteBuildReportPanel` and `RunHistoryWorkspace` must strictly use `report.buildName` or 6-character uppercase hex slicing (`Build #${build_id.slice(-6).toUpperCase()}`).
- Scenario Generation Stay-in-Place & Grouped Consolidation:
  - Generating AI test scenarios does NOT auto-redirect to the Execute Tests screen. The user stays in the AI Scenario Studio (`aiGenerator`) to review, consolidate, and curate generated cases.
  - Generated cases support multi-select checkboxes, "Select All", and grouped consolidation actions:
    - `⚡ Consolidate Scenarios`: Combines 2+ selected scenarios into a unified end-to-end user journey with sequenced step renumbering.
    - `📁 Add to Suite`: Bulk-assigns selected scenarios to a target Test Suite.
    - `✓ Mark Ready`: Bulk-approves selected scenarios.
    - `🚀 Run Selected`: Executes only the selected subset of scenarios.
    - `📥 Export`: Exports selected scenarios as CSV or JSON.
    - `🗑 Delete`: Bulk-deletes selected draft scenarios.
- Test Case Row Action Cleanliness:
  - The redundant `v+` bump version button is removed from individual test case rows. Test case versioning is managed at the suite or application level.
- Dynamic Resilience:
  - Avoid hardcoded CSS selectors (e.g. `#user_email`). Always use resilient multi-selector fallback chains (`input[type=email], #email, [name=email]`, etc.).
  - Starter cases must dynamically reference the active application name and target URL.
