# Workspace Delivery Policy

> [!IMPORTANT]
> **MANDATORY COMMIT MESSAGE CONVENTION**:
> Every commit message in this repository MUST start with the application SemVer prefix matching `frontend/package.json`:
> **`v<MAJOR>.<MINOR>.<PATCH>: <type>(<scope>): <summary>`** (e.g. `v2.1.0: feat(arch): modularize page.tsx, add telemetry, allure reporting, and connection pooling`).
> **NEVER omit the `vX.Y.Z:` prefix** from any commit message. Automated release pipelines, version verification scripts (`node scripts/verify-version.mjs --require-history-bump`), and Git changelog history strictly enforce this prefix.

## Automatic source-change publishing

When completing a requested change to frontend/UI code or application source code in this repository:

1. Select and increment the application SemVer in `frontend/package.json` for every pushed commit: patch for fixes and documentation/workflow changes, minor for backwards-compatible capabilities, and major for breaking changes. Keep `frontend/package-lock.json` synchronized and update `docs/Changelog.md`.
2. Run the narrowest relevant validation first, then the applicable repository gates. If the user explicitly asks to defer or ignore tests, prioritize the implementation and bug fix, skip test creation and test-suite execution unless needed to diagnose a concrete failure, and report the skipped tests. Lightweight compile, typecheck, lint, build, migration, security, and secret-safety checks may still be used when they directly protect the change.
3. Run `node scripts/verify-version.mjs --require-bump` before committing; CI enforces the committed version increase with `node scripts/verify-version.mjs --require-history-bump`.
4. Review `git status`, `git diff --check`, and `git diff --stat`.
5. Stage only the intended source, test, configuration, and documentation files.
6. Create a concise reviewable commit strictly prefixed with the application SemVer: **`vX.Y.Z: <type>(<scope>): <summary>`** (e.g. `v2.1.0: feat(...): ...`). Every commit message MUST explicitly include the version prefix matching `frontend/package.json` to ensure release traceability, keep commit logs standardized, and prevent version hallucinations. Commits omitting `vX.Y.Z:` will fail CI and violate delivery policy.
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

## Zero regression & functionality preservation policy

> [!IMPORTANT]
> **NEVER BREAK EXISTING FUNCTIONALITY WHEN ENHANCING OR REFACTORING**:
> 1. **Preserve All Capabilities**: It is completely acceptable and encouraged to enhance, style, optimize, modernize, and compact layouts. However, existing functionality, data flows, CRUD capabilities (adding/editing/deleting projects, registering/editing applications, creating/editing test cases, organizing suites, executing tests, inspecting runs, viewing evidence, and reporting/updating defects) MUST REMAIN 100% OPERATIONAL.
> 2. **Never Collapse Functional Views**: NEVER suppress, bypass, or collapse dedicated functional views (`projects`, `applications`, `cases`, `suites`, `evidence`) into fallbacks or redirects (`views.projects: dashboard`, `views.applications: dashboard`, etc.). Every section MUST render its dedicated, fully functional surface component.
> 3. **Modal & Action Accessibility**: Action triggers and modals (e.g. `+ New Project`, `+ Add App`, `Log Defect`, edit forms) must remain directly accessible, visible, and fully functional across both dedicated views and global context bars. Modals that can be triggered from anywhere must be mounted at the shell level so they open seamlessly regardless of active view.
> 4. **Bidirectional Route Mapping**: Route mappings (`pathSections`) and reverse paths (`sectionPaths`) must faithfully route each URL (`/projects`, `/applications`, `/test-cases`, `/test-suites`, `/evidence`) to its corresponding section, never collapsing them into `dashboard` or `execution`.
> 5. **Pre-flight CRUD Verification**: Always verify that adding and managing projects and applications work end-to-end before shipping any changes.

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
  - Backend: FastAPI/Uvicorn on `http://0.0.0.0:8000` / `http://127.0.0.1:8000` (`PYTHONPATH=. .venv/bin/python3 -m app.core.migration_bootstrap && PYTHONPATH=. .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`).
  - Frontend: Next.js on `http://localhost:3000` (`npm run dev` from `frontend/`).
  - Health & Metrics Endpoints: `GET /api/v1/observability/health` (publicly accessible deep health probe, no auth required) and `GET /api/v1/observability/metrics` (authenticated metrics).
- UI Navigation & Architecture:
  - SkyWatch delivers full-featured, dedicated product surfaces for `dashboard`, `projects`, `applications`, `cases` (Test Cases repository), `suites` (Test Suites), `aiGenerator` (Scenario Generator), `systemMap` (Traceability Map), `execution` (Execute Tests), `runHistory` (Run History), `evidence` (Evidence Gallery), `defects` (Defect Tracking), `reports` (Reports & Analytics), and `settings` (with embedded AI settings, integrations, and audit logs).
  - Every route (`/`, `/projects`, `/applications`, `/test-cases`, `/test-suites`, `/test-execution`, `/run-history`, `/evidence`, `/defects`, `/reports`, `/ai-generator`, `/agents`, `/system-map`, `/settings`, `/audit`) resolves to its corresponding functional workspace view.
  - Quick action triggers for creating projects (`+ Project`) and adding applications (`+ App`) are readily accessible from the header hierarchy bar and dashboard action row.
  - Audit logs are maintained as a dedicated tab inside `SettingsStudio.tsx` (`"ai" | "integrations" | "execution" | "security" | "audit"`), while retaining direct `/audit` route resolution to Settings Studio.
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
- Autonomous Audits & Campaigns Studio (`frontend/src/components/AutonomousAuditsStudio.tsx`):
  - Accessible via "🎯 Autonomous Audits & Campaigns" tab in AI Recommendations / Agents Workspace or directly on `/audit`.
  - Visual Regression Audits: Invokes `POST /api/v1/orchestrator/visual-audit` across Desktop (`1920x1080`), Tablet (`768x1024`), and Mobile (`375x812`) viewports with DOM tree structural hashing and pixel diff analysis.
  - API Contract Testing Audits: Invokes `POST /api/v1/orchestrator/api-audit` to validate OpenAPI schema conformance, boundary payload resilience, and SLA response time benchmarking.
  - Autonomous QA Campaigns: Invokes `POST /api/v1/orchestrator/campaigns` and tracks progress via `GET /api/v1/orchestrator/campaigns/{id}` with 1-5 parallel agent workers, auto-healing, and visual audit toggles.
- 100% Open-Source LLM Architecture (Zero Third-Party Lock):
  - SkyWatch natively supports local open-source inference servers (Ollama on `http://127.0.0.1:11434/v1`, vLLM, and LocalAI) with open-source foundation models (`llama3.2`, `mistral`, `deepseek-coder`, `qwen2.5-coder`).
  - A deterministic built-in open-source test synthesizer (`offline-simulator`) enables complete offline test case design with structured step parameterization without requiring external third-party accounts, proprietary SDKs, or paid subscriptions.
  - Dynamic provider auto-detection automatically defaults to `local` open-source mode when external API keys are not detected in the environment.
- Enterprise-Grade E2E Test Suite (`backend/tests/test_enterprise_e2e.py`):
  - Enforces continuous automated validation of the end-to-end QA lifecycle: deep health checks, application creation, open-source scenario generation, single and full-suite TypeScript Playwright compilation, execution lifecycle tracking, and ALM defect logging.
- UI Simplification & Anti-Clutter Policy:
  - Quality Reports & Release Intelligence (`reportsView`) must remain an uncluttered executive surface focused on release health, pass rates, defect density, and execution runs.
  - Low-level developer plumbing (e.g. raw token bucket tables, endpoint group rate limiter distributions) must never clutter business report views; it is housed under `SettingsStudio` with collapsible route details.
  - Do not proliferate new top-level navigation items or redundant wrapper sub-views; maintain a tight, enterprise-grade, clean layout that is simple and intuitive to operate.
- Dynamic Resilience:
  - Avoid hardcoded CSS selectors (e.g. `#user_email`). Always use resilient multi-selector fallback chains (`input[type=email], #email, [name=email]`, etc.).
  - Starter cases must dynamically reference the active application name and target URL.
- OpenTelemetry Distributed Tracing (`backend/app/core/telemetry.py`):
  - Provides lightweight, non-blocking distributed tracing via `trace_span(name, attributes)` context manager and `@traced(span_name)` decorator.
  - Features an automatic zero-dependency in-memory timing fallback with structured JSON telemetry logging if the OpenTelemetry SDK is unconfigured.
  - Active instrumentation spans AI scenario generation jobs (`generate_scenarios_job`), test execution orchestration (`execute_test_case`), and LLM provider invocations (`_generate_with_retry`).
- Allure 2 Test Execution Reporting (`backend/app/services/allure_reporter.py` & `GET /api/v1/execution/{run_id}/allure`):
  - Industry-standard test reporting export endpoint generating Allure 2 JSON results.
  - Captures test parameters, status mapping (`passed`, `failed`, `broken`, `skipped`), sub-second step timings, error messages, and attachments (Playwright traces, browser logs, console output).
- High-Performance LLM Connection Pooling (`backend/app/services/llm_client.py`):
  - Uses pooled `httpx.AsyncClient` instances configured with `httpx.Limits(max_connections=20, max_keepalive_connections=10)` to eliminate connection churn during high-concurrency scenario synthesis.
- GZip Middleware & OpenAPI Schema Enhancements (`backend/app/main.py`):
  - Fast GZip response compression enabled with `minimum_size=1000` to optimize data transfer for large test suites, Playwright scripts, and batch run histories.
  - Rich OpenAPI 3.1.0 metadata with descriptive operational tagging and automatic SemVer reflection.
- Modularized Frontend Architecture (`frontend/src/lib/` & `frontend/src/components/`):
  - Monolithic `frontend/src/app/page.tsx` is modularized into specialized modules to guarantee maintainability and separation of concerns:
    - `frontend/src/lib/runtimeParameters.ts`: Execution parameters, test data parsing, and runtime environment resolution.
    - `frontend/src/lib/distributions.ts`: Status, category, priority, and timing distribution analytics for release dashboards.
    - `frontend/src/lib/speech.ts`: Web Speech API synthesis for natural voice execution announcements.
    - `frontend/src/lib/testCaseHelpers.ts`: Test case step numbering, formatting, validation, and cloning helpers.
    - `frontend/src/lib/api-client.ts`: Unified typed client wrappers for execution, runs, suites, and reports.
    - `frontend/src/components/ui/DashboardWidgets.tsx`: Reusable KPI cards, distribution charts, and timeline widgets.
    - `frontend/src/components/ExecutionDiagnosticsPanel.tsx`: Live console log streaming, step telemetry, and run diagnostics.
- Enterprise Logging & AI Generation Observability Subsystem (`docs/LOGGING_AND_OBSERVABILITY.md`):
  - Persistent AI Generation Logs: `GenerationLogger` (`app/services/generation_logger.py`) records all lifecycle events (intake, target DOM discovery, planner blueprints, LLM tokens/latency, 429 rate limit progressive backoffs, test data synthesis, and case persistence). Stored persistently in `job.result["logs"]` and accessible via `GET /api/v1/ai-generation/jobs/{job_id}/logs`.
  - Rotating File Handlers: `backend/logs/skywatch.log` (5MB, 5 backups), `backend/logs/ai_generation.log` (10MB, 5 backups), and `backend/logs/errors.log` (5MB, 5 backups).
  - Security & Credential Redaction: `SecretMaskingFilter` automatically redacts Gemini keys (`AIza...`, `AQ....`), OpenAI/Anthropic keys (`sk-...`), GitHub tokens (`ghp_...`), Bearer tokens, and JSON passwords across all log handlers.
  - In-Memory Ring Buffer & Observability API: `RingBufferLogHandler` retains the latest 1,000 application log records in memory, queryable via `GET /api/v1/observability/logs`.
  - Frontend UI Consoles: `GenerationLogViewer` in AI Scenario Studio for live streaming generation logs, and `SystemLogViewer` under `SettingsStudio` ("🖥️ System Logs") for real-time server diagnostics.
- Enterprise Layout, Header & Filter Density Architecture Standards:
  - Header Constraint: `.app-header` height is strictly 48px (`--header-height: 48px`), `.header-left` has `flex-wrap: nowrap;` and `overflow-x: auto` with hidden scrollbars to prevent header ballooning or vertical layout jitter across laptops and zoomed displays.
  - Logo Preservation: `TractorSupplyLogo` (`frontend/src/components/navigation/TractorSupplyLogo.tsx`) must never be modified or replaced.
  - High-Density Filter Toolbars: All listing and analytics pages must use single-row compact filter toolbars (38px-40px height) rather than tall stacked form grids.
  - Executive Header Strips: Page hero banners must remain sleek (max 48px-52px height) with inline right-aligned primary actions to maximize above-the-fold data visibility.
  - Settings & Audits Hierarchy: Tab navigation must always be positioned at the top of the workspace.

