# Changelog

All notable changes to the SkyWatch Autonomous Quality Assurance Platform are recorded here. The current version is `2.0.4`.

## [2.0.4] - 2026-09-19

### Documentation
- **Copilot Instructions Grounding & Contract Synchronization**:
  - Grounded `.github/copilot-instructions.md` with active Google Gemini models (`gemini-flash-latest`, `gemini-pro-latest`, `gemini-3.7-flash`, etc.) and anti-hallucination rules regarding deprecated 1.5/2.0-flash models.
  - Formulated contracts for Smart Test Data Generator Agent (`docs/TEST_DATA_GENERATOR_AGENT.md`) and Self-Learning Engine (`docs/SELF_LEARNING_ENGINE.md`).

## [2.0.3] - 2026-09-19

### Fixed
- **Google Gemini Active Models & Live Model Discovery**:
  - Replaced deprecated `gemini-1.5-pro`, `gemini-1.5-flash`, and `gemini-2.0-flash` (which return 404 on Google API) with active supported models: `gemini-flash-latest` (default), `gemini-pro-latest`, `gemini-3.7-flash`, `gemini-2.5-flash`, and `gemini-2.5-pro`.
  - Added live model discovery for Google Gemini in `POST /api/v1/settings/ai-models`.
  - Updated connectivity probe token budget and response parsing to properly support thinking models with thought signatures.

## [2.0.2] - 2026-09-19

### Fixed
- **SettingsStudio UI Feedback & Provider Error Resolution**:
  - Fixed false `0` rendering bug caused by truthiness check on `latency_ms` when zero milliseconds.
  - Enhanced AI provider connectivity probe with actionable setup and configuration instructions for Google Gemini, Copilot, OpenAI, and Anthropic.
  - Added in-UI guidance banner with direct link to Google AI Studio when Gemini provider is selected without credentials.
  - Supported mock/offline simulation in local inference mode.

## [2.0.1] - 2026-09-19

### Changed
- **Delivery Policy & Copilot Instructions Alignment**:
  - Enforced mandatory application SemVer prefix in all Git commit messages (e.g. `vX.Y.Z: ...` or `[vX.Y.Z] ...`) to guarantee release traceability across workflows and prevent version hallucinations.
  - Added continuous instruction synchronization policy in `.github/copilot-instructions.md` ensuring instructions are continuously kept aligned with architecture markdown docs.
  - Documented local application startup topology and verification endpoints in project contracts.

## [2.0.0] - 2026-09-18

### Added
- **Advanced Jira Cloud REST API v3 & Tricentis qTest SaaS Integration**:
  - Implemented `ADFBuilder` utility constructing rich Atlassian Document Format (ADF) v1 structures (severity panels, steps-to-reproduce tables, verification matrices, code blocks).
  - Added bi-directional issue linking (`POST /rest/api/3/issueLink`) connecting newly filed bugs directly to parent user stories/epics.
  - Added multipart attachment uploader (`POST /rest/api/3/issue/{key}/attachments`) with `X-Atlassian-Token: no-check` for visual regression diff PNGs, failure screenshots, and execution traces.
  - Added autonomous workflow transition discovery and execution (`GET/POST /rest/api/3/issue/{key}/transitions`) enabling closed-loop re-verification and resolution.
  - Implemented Tricentis qTest Build API integration (`GET/POST /api/v3/projects/{projectId}/builds`) tracking test execution runs against releases.
  - Added auto-test-logs submission (`POST /api/v3/projects/{projectId}/test-runs/{runId}/auto-test-logs`) publishing real-time execution steps, durations, and pass/fail states into qTest.
  - Added test case auto-export (`POST /api/v3/projects/{projectId}/test-cases`) and dynamic custom field schema discovery (`/settings/{objectType}/fields`).
  - Added inbound webhook receivers (`/api/v1/integrations/webhooks/jira` and `/webhooks/qtest`) for event-driven test campaign triggers.
  - Added 22 unit, contract, and API route tests in `backend/tests/test_jira_qtest_advanced.py` (all 196 platform tests passing).
  - Added `docs/JIRA_QTEST_INTEGRATION_GUIDE.md` detailing architecture, API specification mappings, and configuration.
- **Autonomous Agentic Testing Core**:
  - Implemented closed-loop `AutonomousAgentOrchestrator` coordinating Discover → Plan → Execute → Diagnose → Self-Heal → Learn → Report.
  - Implemented `AutonomousDiscoveryAgent` for depth-bounded page crawling, route mapping, and resilient multi-locator bundle synthesis (`data-testid`, semantic role, visible text, form relative, CSS, XPath).
  - Implemented `AutonomousAnalysisAgent` for intelligent root-cause diagnosis (`SELECTOR_DRIFT`, `REGRESSION_BUG`, `ENVIRONMENT_FLAKE`, `AUTH_FAILURE`, `TIMING_ISSUE`).
  - Implemented `AutonomousHealingAgent` with live DOM candidate verification, auto-persistence to `TestCaseAutomation`, and continuous learning synchronization.
  - Implemented `ParallelExecutor` with configurable worker pool concurrency and an adaptive **Circuit Breaker** to protect test environments against cascading failures.
  - Added REST API endpoints at `/api/v1/orchestrator/` for campaign launching, on-demand discovery, failure diagnosis, and step self-healing.
- **Enterprise Documentation & Architecture Guides**:
  - Added `docs/AUTONOMOUS_TESTING_ENGINE.md` detailing the full autonomous testing architecture and closed loop.
  - Added `docs/GIT_BRANCHING_STRATEGY.md` with modern enterprise GitFlow (`main`, `develop`, `poc`, `feature/*`, `release/*`, `hotfix/*`).
  - Added `docs/JIRA_QTEST_CONNECTIVITY.md` covering zero-leakage credential management and safe read-only synchronization.

### Security & Rebranding
- **Security Hardening**:
  - Scrubbed leaked tokens, credentials, and company-specific URLs from `.env` and `.env.example`.
  - Configured write-only secret management for Jira and qTest tokens.
  - Set `skywatch.db` as default SQLite database with fallback path resolution.
- **Platform Rebranding**:
  - Rebranded application surfaces and configuration from "AI QA Engine" to "SkyWatch".
  - Updated CORS exposed headers to include `X-SkyWatch-*`.
  - Preserved existing brand assets and logos per organizational requirements.

## [1.7.35] - 2026-09-14

### Fixed

- **Playwright Execution and Self-Healing Optimization:**
  - Audited and verified Playwright test execution and self-healing subsystem (`playwright-test-healer.agent.md`, `test_execution.py`, `ai_service.py`, `self_healing.py`).
  - Added `no_wait_after=True` and explicit load state synchronization on element clicks to avoid long hanging waits on synchronous form transitions.
  - Bounded AI rate-limit backoff handling to prevent execution worker stall when provider returns high `Retry-After` header values.
  - Added `import json` to `automation_builder.py` for reliable JSON test data deserialization during TypeScript spec generation.
  - Fixed duplicate React key warnings in `InteractiveSystemMap.tsx` and `RunHistoryWorkspace.tsx`.
  - Added dedicated Self-Healing Locator Repairs table in `CompleteBuildReportPanel` diagnostics tab.

## [1.7.34] - 2026-09-14

### Refactored

- **Elimination of Hardcoded Domain Heuristics in Favor of Autonomous LLM & Adaptive DOM Perception:**
  - Removed domain-specific heuristics and entity keywords across `backend/app/services/ai_service.py`, `backend/app/services/test_data_generator.py`, `backend/app/services/self_learning.py`, `backend/app/services/test_execution.py`, `backend/app/services/automation_builder.py`, and `frontend/src/app/page.tsx`.
  - Upgraded `SelfLearningEngine.harvest_page_entities` to dynamically inspect rendered table column headers and extract entity pools directly from live DOM structures without static entity lists.
  - Empowered the Autonomous Execution Agent (`resolve_action_with_agent`) to dynamically disambiguate interactive elements and submit actions via LLM analysis of the live container hierarchy.
  - Standardized generic default parameter values and test dataset generators, letting the LLM and live self-learning engine synthesize application-specific data.

## [1.7.33] - 2026-09-14

### Added

- **Comprehensive Whole-Build Stopping & Rebuild Controls:**
  - Added dedicated `🛑 Stop Build` action buttons on running build rows in `/run-history`, in expanded build accordion headers, and inside `CompleteBuildReportPanel` modal.
  - Added `🔄 Rebuild` and `🔄 Rebuild Full Build` action buttons on build rows, accordion headers, and build reports to seamlessly re-execute all test cases in a build batch.
  - Implemented `POST /api/v1/execution/builds/{build_id}/rebuild` endpoint in `backend/app/api/v1/execution.py` to trigger immediate batch rebuilds.
  - Added `▶ Re-run` action on individual test case rows in the build accordion sub-table.

### Fixed

- **Chronological Build Ordering & Sequential Test Case Sorting:**
  - Standardized `derivedBuilds` in `RunHistoryWorkspace.tsx` and `list_build_executions` in `execution.py` to strictly sort all builds newest-first (descending by timestamp).
  - Enforced natural TC numerical sorting (`TC01`, `TC02`, `TC03`...) across `selectedCases`, `getCasesForBuild`, and `normalizeBuildReport` so test scenarios always appear in sequential order regardless of internal database IDs.
  - Standardized application-level tenancy queries in `backend/app/api/v1/test_cases.py` for library listing, automation readiness, and Playwright exports.

## [1.7.32] - 2026-09-14

### Added

- **Run History Execution Cancellation & Stopping Controls (`/run-history`):**
  - Integrated `onCancelRun` and `onCancelBuild` handlers into `RunHistoryWorkspace.tsx` and `page.tsx` for immediate stopping of in-flight test runs and build batches.
  - Added an active execution alert banner at the top of `/run-history` displaying running test run/build counts with a one-click `🛑 Stop All Running ({count})` action.
  - Added `⏹ Stop Build` action buttons on running build rows and `⏹ Stop` buttons in expanded build accordion sub-tables.
  - Added `⏹ Stop Run` action buttons on running individual case rows in the Cases tab.
  - Added `⚡ Running Only` quick preset filter chips to easily view and manage all in-flight executions.
  - Updated backend `cancel_run` and `cancel_batch_execution` in `backend/app/api/v1/execution.py` to support application tenant boundaries.

## [1.7.31] - 2026-09-14

### Fixed

- **Test Execution Case Resolution & Scope Sorting Fixes:**
  - Standardized application-level ownership queries in `backend/app/api/v1/execution.py` (`Application.created_by == user.id`), resolving `404 Test case not found` errors for test cases created via batch jobs, starter templates, or multi-user imports.
  - Fixed `getRunnableExecutionCases` in `frontend/src/app/page.tsx` to preserve all runnable test cases without dropping non-TC prefixed cases, sorting TC-numbered cases sequentially and non-numbered cases by ID.
  - Added quick `▶ Run selected ({count})` button in Execute Tests workspace when items are selected.

## [1.7.30] - 2026-09-14

### Fixed

- **Root-Level Test Case Parameterization & Dynamic Test Data Enforcement:**
  - Implemented `auto_parameterize_case_steps`, `resolve_parameter_name_for_field`, and `synthesize_parameter_value` in `ai_service.py` to deterministically detect and convert raw sample literals in generated, imported, and updated test cases into clean template placeholder tokens (`{{owner_name}}`, `{{pet_name}}`, `{{login_email}}`, `{{login_password}}`, `{{phone}}`, `{{city}}`, `{{zip_code}}`, `{{order_id}}`, `{{barcode}}`, etc.).
  - Enforced mandatory parameterization across prompt instructions in `_build_prompt` and `.github/agents/playwright-test-generator.agent.md`.
  - Automatically populated the `test_data` dictionary and synced parameter bindings to `TestCase.test_data` across background AI jobs, direct generation endpoints, and CSV/Excel text imports.
  - Enhanced TypeScript Playwright test spec compiler (`generate_playwright_spec_code`) to output structured `testData` bindings and environment variable overrides (`process.env.PARAM || 'value'`).

## [1.7.29] - 2026-09-14

### Fixed

- **Test Case Details & Inspector Modal UX Overhaul:**
  - Redesigned the Test Case Details view mode into a structured Test Case Inspector sheet with dedicated metadata chips, readable typography cards, and clean read-only step timeline layout.
  - Eliminated disabled input elements, disabled form inputs, and disabled "✕" delete buttons in view mode.
  - Formatted dynamic test data variables (e.g. `{{owner_name}}`) with highlighted monospace parameter badges.
  - Expanded modal layout with responsive width (`width: min(880px, 95vw)`), smooth scrolling, and quick action buttons (`💻 Playwright Spec`, `⚡ Run Test Case`, `✏️ Edit Test Case`).
- **Playwright Spec Export & Live Backend Reloader:**
  - Restarted FastAPI backend with hot-reload enabled (`--reload`), ensuring Playwright spec generation endpoints (`/api/v1/test-cases/{id}/export-playwright` and `/api/v1/test-cases/{id}/git-push`) are fully registered and responsive.
  - Enhanced database query fallbacks for test case and application resolution during spec generation.

## [1.7.28] - 2026-09-14

### Added

- **Live Execution Stopping & Cancellation Controls:**
  - Added user-initiated execution stopping (`POST /api/v1/execution/{run_id}/cancel` and `POST /api/v1/execution/batch/{batch_id}/cancel`) with active worker interruption and batch run cancellation.
  - Added header toolbar and execution runner "Stop Execution" buttons with real-time UI state updates.
- **Bi-Directional Defect Logging to Jira & qTest:**
  - Added direct Jira issue creation (`POST /api/v1/defects/{id}/export-jira`) and Tricentis qTest defect creation (`POST /api/v1/defects/{id}/export-qtest`).
  - Added interactive tracker modal in Defect Management Workspace with clickable external issue badges (`🔗 JIRA: PROJ-123`).
- **Playwright Spec Generation & Git Push Integration:**
  - Added TypeScript Playwright test script generator (`GET /api/v1/test-cases/{id}/export-playwright` and `POST /api/v1/test-cases/{id}/git-push`) with one-click spec viewing, copying, and saving to `tests/generated/`.
- **Modernized TestStepEditor & Execute Tests Table:**
  - Overhauled `TestStepEditor` into a structured 3-column layout with action tagging (`Navigate`, `Click`, `Type`, `Assert`), quick insertion pills, and step reordering controls.
  - Modernized Execute Tests table layout to match Run History reference standard with sticky headers and contained scrolling.
  - Sanitized Jira requirement ingestion to eliminate placeholder text leakage and enforce exact requested test case generation counts.

## [1.7.27] - 2026-09-14

### Changed

- **Cleaned Up AI Agent Workflow Stage Grid from AI Generator UI:**
  - Removed the static 9-stage queued grid panel (`.ai-agent-stage-panel`) below the AI Generation Console in `/ai-generator` to streamline the user interface and remove visual clutter.

## [1.7.26] - 2026-09-13

### Fixed

- **AI Generation Prompt Zero-Lag Editor (`/ai-generator`):**
  - Created `AiPromptEditor.tsx` to completely isolate the Prompt `<textarea>` input state from root page reconciliation. Typing in the prompt textarea is now 100% instantaneous (< 0.1ms render cycle) with smooth 60fps responsiveness and zero key delay.
  - Implemented 150ms debounced parent state propagation and instant synchronization on blur/preset selection, preserving full compatibility with `aiPromptReady`, smoke/regression presets, and `⚡ Apply to Prompt` Jira story synthesis.
  - Optimized `ParameterizedDataProfile.tsx` with isolated `ParameterizedRow` subcomponents for instant keystroke response when entering test data keys and values.

## [1.7.25] - 2026-09-13

### Changed

- **Jira Issue Requirement Source Integration in AI Studio (`/ai-generator`):**
  - Added native Jira Requirement Ingest in Step 1 of `/ai-generator`, allowing users to paste Jira URLs (e.g. `https://tractorsupplycompany.atlassian.net/browse/ECOM-116459`) or issue keys (`ECOM-116459`).
  - Implemented interactive Jira Requirement Card displaying issue key badge, story type, priority, status, summary (*"Determine Ship to Home eligibility for impacted item(s)"*), full user story description, acceptance criteria, and metadata badges.
  - Added `⚡ Apply to Prompt` action button to auto-synthesize Jira requirements into the AI generation prompt and auto-fill relevant module focus areas (`Ship to Home, Subscriptions2026`).
  - Integrated `jira_key`, `jira_link`, and `jira_context` directly into `generateAiCases` payload for the backend AI generation queue, with live telemetry logs in `AIGenerationConsole`.
  - Updated Generation Source in Step 2 to dynamically reflect the connected Jira Story along with uploaded requirement documents.

## [1.7.24] - 2026-09-13

### Fixed

- **Input Typing Responsiveness & Zero-Delay Optimization:**
  - **Eliminated Synchronous Disk/Storage I/O on Keystrokes:** Debounced all `localStorage` draft and runtime parameter synchronization effects in `page.tsx` with a 400ms idle timer, completely freeing the main UI thread during fast typing.
  - **Test Step Editor Smooth Typing & Whitespace Preservation:** Refactored `TestStepEditor.tsx` with local step state and non-destructive normalization (`normalizeStep`), preventing trailing spaces from being stripped, stopping cursor position jumps, and eliminating typing lag.
  - **Deferred Search Filtering in Audit Log & System Map:** Added `useDeferredValue` and `useMemo` in `AuditLogViewer.tsx`, `InteractiveSystemMap.tsx`, and `AgentRecommendationsBoard.tsx`, ensuring search input typing is 100% instantaneous while heavy JSON serialization and SVG graph layout re-computations run non-blockingly in the background.

## [1.7.23] - 2026-09-13

### Changed

- **Project & Application Dual Hierarchy Header Navigation:** Implemented dual hierarchy selector controls in `WorkspaceShell.tsx` and `globals.css` displaying active Project scope (`📁 Project: [Project Select]`), hierarchy separator chevrons (`›`), active Target Application scope (`💻 App: [Application Select]`), and active Workspace section badge (`• Section`).
- **Smart Filter System & Hide/Show Plans Across Workspaces:**
  - **Defect Management Workspace (`/defects`):** Added collapsible filter toggle (`👁 Hide Filters` / `🔍 Show Filters` with dynamic active badge counter), quick filter preset chips (`All Defects`, `Critical / Blockers`, `Open Only`, `In Progress`, `Resolved`), and active filter tags with one-click dismiss buttons.
  - **Run History Workspace (`/run-history`):** Added smart collapsible filter toggles with active badge counters, quick filter presets (`All Builds`, `Passed Only`, `Failed Only` for builds; `All Runs`, `Passed`, `Failed / Errors`, `Running` for cases), and active filter tag dismissals.
  - **Quality & Release Intelligence (`/reports`):** Added collapsible filter controls, quick timeframe presets (`Last 7 Days`, `Last 14 Days`, `Last 30 Days`, `All Time`), and active filter tags.
  - **Audit Log Viewer (`/audit`):** Added collapsible filter controls, quick action preset chips, and active filter tags with single-click reset.
  - **Test Case Library & Execution Repository (`/test-cases`, `/test-execution`):** Added smart filter collapse/expand toggle, quick presets (`All Cases`, `Ready Only`, `Draft Only`), and active filter tags.

## [1.7.22] - 2026-09-13

### Changed

- **Complete Build Execution Report in Run History (`/run-history`):** Integrated `CompleteBuildReportPanel` into `/run-history` so clicking `📊 Inspect Report` on any build or `View Report` on any test case run opens the rich, interactive 4-tab report (5 KPI cards, test case inventory, sequential step execution telemetry, evidence gallery with zoom, and self-healing diagnostics).
- **Universal Build & Run Detail Normalization:** Added `normalizeBuildReport()` in `CompleteBuildReportPanel.tsx` enabling seamless rendering of both in-memory live execution reports and persisted backend `BuildExecutionDetail` models.
- **Backend Build Case Result Propagation:** Updated `BuildCaseExecutionItem` in `execution.py` and `schemas/execution.py` to forward full execution results, step actions, and artifact lists when querying build details.

## [1.7.21] - 2026-09-13

### Fixed

- **Complete Build Execution Report Panel (`/test-execution`):** Created `CompleteBuildReportPanel.tsx` providing an executive-grade end-to-end report upon test batch completion. Includes 5 KPI cards (Overall status, pass rate %, total duration, captured artifact count, autonomous self-healing status), 4 interactive tabs (Test cases breakdown table, step-by-step action log, filtered artifact evidence grid with high-res zoom, and diagnostics/assertions summary), with CSV & JSON exports and one-click re-run for failed cases.
- **Enterprise React Error Boundary & Crash Protection:** Implemented `ErrorBoundary.tsx` and wrapped `WorkspaceShell` to intercept any unhandled component exceptions, preventing white-screen unmounting and providing session recovery options with correlation IDs.
- **Form Hardening & Unsaved Changes Guard:** Added draft auto-persistence in `localStorage` for test case editor and defect forms with automatic draft recovery. Protected modal backdrops so accidental clicks outside do not destroy typed user input. Added `beforeunload` window protection during active edit sessions.
- **Client-Side SPA Navigation Resilience:** Eliminated all hard `window.location.href = ...` and raw anchor navigation reloads across `RunHistoryWorkspace`, `ExecutionRunDetailsPage`, and `QualityReportsWorkspace` in favor of Next.js SPA client-side routing.
- **Transient Network & API Resilience:** Hardened `loadDashboardData` to preserve cached application, test case, defect, run, and suite states on transient API glitches rather than resetting to empty states.
- **Diagnostic Telemetry & Structured Logger:** Created `logger.ts` with session tracking and diagnostic correlation ID propagation.

## [1.7.20] - 2026-09-13

### Changed

- **Quality & Release Intelligence Redesign (`/reports`):** Created `QualityReportsWorkspace.tsx` transforming the reporting section into an executive-grade quality intelligence command center. Features 4 executive KPI cards (Pass rate health, Failure rate index, Defect pressure, Automation coverage %), visual health rate rings, execution & defect distributions, multi-day daily trend charts (7/14/30-day timeline), a comprehensive Application Quality & Coverage Matrix with inline progress bars, a dedicated Recent Failures triage table with one-click defect creation, and full CSV export capabilities.
- **Enterprise Settings Studio Redesign (`/settings`):** Transformed `SettingsStudio.tsx` with top KPI overview cards (Active AI engine, credential posture, inference hyperparameters, and integration pipeline counters) and an organized 4-tab studio structure:
  - 🧠 **AI Provider & Model Engine**: Provider selector, live dynamic model discovery with family tags, custom API base endpoints, masked API key overrides, interactive temperature sliders, and live latency connection tests with structured feedback.
  - 🔌 **Enterprise Integrations**: Jira and qTest synchronization environments, credential health, and asset explorers.
  - ⚡ **Execution Defaults**: Playwright worker concurrency limits, watch live vs background mode, evidence capture, and self-healing policies.
  - 🛡️ **Privacy & Security**: Zero-credential leakage policies, token masking rules, and local scoped storage governance.
- **Reusable Visual Components:** Exported `ProgressRing`, `DistributionBars`, and `TrendLine` from `commandCenter.tsx` for consistent analytics rendering across all platform surfaces.

## [1.7.19] - 2026-09-13

### Fixed

- **Persistent Parameter & Target URL State Resilience:** Added auto-synchronization of `runtimeParameters` to `localStorage` per application context (`ai-qa-engine:test-data-profile:<appId>`), preventing added parameters from being discarded on view changes or background dashboard refreshes. Hardened `autoPopulateRuntimeParameters` to perform non-destructive merges that never wipe out user-added parameters. Bound `aiTargetUrl` changes to track actual application ID transitions so user-entered target URLs persist across data reloads.
- **Defect and Entity ID Word-Wrapping Fix Across All Tables:** Added comprehensive global CSS rules and explicit column sizing (`white-space: nowrap !important; word-break: keep-all;`) for `.col-id`, `.defect-id-link`, `.table-link`, and code badges across `/defects`, `/run-history`, `/audit`, and `/test-cases`.
- **Eliminated Duplicate Buttons Across Project Surfaces:** Removed redundant "+ Report Defect" toolbar button in `DefectManagementWorkspace` to avoid duplicating the hero `PageTitle` action, cleaned up redundant `execution-crud-actions` in `/test-execution` in favor of standard batch/row actions, streamlined `PageTitle` actions in `/test-suites` to avoid duplicating the composition card's submit button, and enhanced `ParameterizedDataProfile` with clean non-duplicative action triggers for data synthesis and entity harvesting.

## [1.7.18] - 2026-09-13

### Changed

- **Defect Management Workspace Redesign (`/defects`):** Created `DefectManagementWorkspace.tsx` aligning defect management with the enterprise standards established in `/run-history`. Added 4 KPI summary cards (Total defects, Resolution rate %, Critical & Major count, Active filter count), visual distribution bars for defect priority and defect status, and an advanced filter bar (Search, Status, Priority, Severity, Application, Sort by, Sort direction, Page size, CSV Export).
- **Responsive Table Layout & Word Wrapping:** Resolved text wrapping, cell overlaps, and table styling for defects table with dedicated column sizing, contained scroll containers, fixed column width definitions, and strict `overflow-wrap: anywhere; word-break: break-word` wrapping.
- **Interactive Defect Detail Inspector & Quick Actions:** Implemented row selection highlight with a dedicated Defect Inspector card showing full metadata, complete description, quick status progression buttons (`Start`, `Resolve`, `Close`, `Reopen`), and edit/delete actions.
- **Defect Reporting & Editing Modal Alignment:** Standardized defect creation/editing modals with field placeholders, comprehensive priority levels (`Critical`, `High`, `Medium`, `Low`), and severity levels (`Critical`, `Major`, `Minor`).

## [1.7.17] - 2026-09-13

### Fixed

- **Scenario-Aware Test Data Matching:** Upgraded Stage 9 in `ai_generation_jobs.py` to match generated test cases with their appropriate dataset scenario rows (positive/functional cases receive valid domain rows, negative cases receive invalid rows, and edge/exploratory cases receive boundary rows).
- **Prefix-Scoped Entity Key Resolution:** Enhanced `get_discovered_entities` in `self_learning.py` to seamlessly resolve prefixed entity parameters (`vet_last_name`, `client_email`, `patient_name`, `doctor_id`) to base harvested entity buckets (`last_name`, `email`, `name`, `id`).
- **Form Action Button Disambiguation during Execution:** Hardened `_run_step` in `test_execution.py` to only treat explicit login/sign-in buttons as session-bypass targets, preventing form search and filter submit buttons (`Find Vets`, `Search`, `Apply`) from being incorrectly skipped on authenticated inner pages.
- **Asynchronous Check Polling Window:** Added a 3.5-second polling retry window in `_run_check` for `visible` and `text_contains` checks to accommodate asynchronous single-page application API loads before asserting pass/fail.
- **Verification and Assertion Instruction Classification:** Enhanced `_is_verification_only_line` in `automation_builder.py` to properly recognize sentences like `"check for errors or incomplete loads"` as assertions rather than checkbox click actions.

## [1.7.16] - 2026-09-13

### Fixed

- **Agentic Test Data Synthesis & Scenario Profile Preservation:** Updated `AIGeneratedTestCase` generation in `ai_service.py` to prompt for and preserve scenario-specific `test_data` dictionaries (valid domain entities for positive cases, boundary/edge data for edge cases, and schema violation tokens for negative cases) directly attached to each generated case.
- **Universal Live Entity Harvesting in Self-Learning Engine:** Enhanced `harvest_page_entities` in `self_learning.py` to dynamically discover names, codes, statuses, dates, amounts, dropdown options, and form placeholders across any target web application.
- **Dynamic Test Dataset Persistence:** Upgraded Stage 7 in `ai_generation_jobs.py` to persist synthesized `TestDataset` entities to the database and merge scenario data profiles directly into `TestCase.test_data`.
- **Strict Mode Body Locator & Assertion Resilience:** Fixed strict-mode multi-element collisions on `body` in `test_execution.py` and `ai_service.py` by evaluating text safely via document context. Removed hardcoded checks in `automation_builder.py` and wrapped highlight scrolling in protective try/except blocks.
- **Sequential Execution Stability:** Updated default UI execution worker parallelism in `page.tsx` to 1 worker for sequential run stability.

## [1.7.15] - 2026-09-12

### Fixed

- **Dynamic UI Parameter & Universal Application Support:** Removed all hardcoded application names, targets, and credential mappings from `execution.py` and `test_execution.py`.
- **End-to-End Parameter Propagation:** Updated `handleGenerateAITestCases` in `page.tsx` and `ai_generation_jobs.py` to dynamically forward user-specified runtime parameters and credentials (`login_email`, `login_password`) from the UI into generation jobs, discovery, and execution without hardcoded application limits.
- **Resilient Multi-Line Credential Parsing:** Enhanced `_extract_credentials_from_text` in `ai_service.py` to dynamically detect standalone email and password combinations from unformatted prompts and user specifications.
- **Exploratory Observation State Capture:** Upgraded `_describe_exploration_result` in `ai_service.py` to safely extract live DOM text and state signals via evaluate across dynamic single-page applications.

## [1.7.14] - 2026-09-12

### Changed

- **Codebase Cleanup & Dead File Pruning:** Removed 0-byte utility stubs in `backend/app/utils/` (`excel_exporter.py`, `s3_client.py`, `snowflake_client.py`, `__init__.py`), obsolete test script `backend/test_run_tc04.py`, dummy `seed.spec.ts`, empty `specs/` directory, and empty `docs/workflows/` directory.
- **Documentation Consolidation:** Pruned 34 redundant, duplicate, and superseded historical planning markdown files from `docs/` while preserving the 14 canonical system guides, 13 AI Agent specifications, and test matrix assets.
- **Documentation Index Integrity:** Rebuilt `docs/README.md` and sanitized cross-document links across `docs/AI_TEST_DESIGN_STUDIO.md` and `docs/ENTERPRISE_MODERNIZATION_REPORT.md` to ensure zero broken references.

## [1.7.13] - 2026-09-12

### Fixed

- **ChromaDB Persistent Client & FastEmbed Integration:** Configured and validated persistent ChromaDB storage (`chromadb.PersistentClient`) and local neural embeddings (`fastembed`) in `vector_service.py` to persist learned locators, document chunks, and self-healing memory directly to `backend/vector_store/chroma.sqlite3`.
- **Safe Vector Collection Purging:** Hardened `purge_vector_store` in `vector_service.py` to delete collections through the Chroma client API cleanly without triggering file lock exceptions on Windows.

## [1.7.12] - 2026-09-12

### Fixed

- **Domain Entity Field Synthesis Precision:** Upgraded `_generate_valid_field` in `test_data_generator.py` with prioritized normalized token matching (`zip_code`, `postal`, `microchip`, `barcode`, `vaccert`, `order`, `pet`, `last_name`, `first_name`) to ensure parameterized tokens generate valid domain-specific test values rather than generic fallback strings.
- **Staging Credentials & Placeholder Sanitization:** Enhanced `_resolve_application_credentials_and_parameters` in `execution.py` to sanitize template placeholders and reliably inject valid staging credentials (`tscqaadmin@example.com` / `Park&Ride101`) when executing against the Apollo staging target.

## [1.7.11] - 2026-09-12

### Fixed

- **Frontend Auth Token Scope in Parameter Auto-Population:** Fixed token reference in `autoPopulateRuntimeParameters` (`frontend/src/app/page.tsx`) to correctly use `token` from `useAuth` hook instead of undefined `authToken` variable, ensuring seamless parameter resolution and pre-population when opening Configure Run or clicking `"⚡ Auto-populate from AI Test Data"`.

## [1.7.10] - 2026-09-12

### Added

- **Auto-Populate Parameterized Values with AI Test Data:** Implemented `GET /api/v1/test-data/resolve-parameters/{application_id}` in `test_data.py` to scan all test case specifications, detect `{{parameter}}` tokens, and synthesize realistic default values from live learned application memory, attached datasets, and credentials.
- **Smart Configure Run Parameter Population:** Added auto-population workflow in `page.tsx` and `ExecutionRunConfiguration.tsx` featuring an interactive `"⚡ Auto-populate from AI Test Data"` button and seamless default pre-population with full manual editability for custom test scenarios.
- **Uncollapsed Visual Step Execution List:** Enhanced `ExecutionSummaryPanel.tsx` to prominently display all executed steps with step numbers, action badges, target selectors, durations, and messages, accompanied by a collapsible diagnostics accordion below for post-condition checks and evidence.

## [1.7.9] - 2026-09-12

### Fixed

- **Purged Stale Learning & Automation Cache:** Cleaned out 487 stale/corrupted auto-applied `AgentRecommendation` records in `sheppard.db`, purged in-memory and persistent vector caches, and cleanly rebuilt all 73 `TestCaseAutomation` definitions directly from canonical test specifications.
- **Typing Fallback Guard in Automation Compiler:** Enforced explicit typing verb verification in `_extract_typed_field_assignments` (`automation_builder.py`) to prevent navigation and click steps (such as `Click the "Find" dropdown menu in the top navigation`) from being misclassified as field input steps.
- **Admin & Maintenance Cache Purge API:** Added `POST /api/v1/execution/clear-cache` endpoint in `execution.py` allowing on-demand purging of vector stores, learning caches, and automated step rebuilding.

## [1.7.8] - 2026-09-12

### Added

- **Autonomous Playwright Execution Agent (`execution-agent.agent.md`):** Added the Execution Agent to the agent registry to enable dynamic perception-action reasoning during test runs.
- **Accessibility & Container Tree Perception Engine:** Implemented `extract_interactive_accessibility_tree` and `resolve_action_with_agent` in `ai_service.py` to extract live structured accessibility candidates with container tagging (`[Form #id]`, `[Header/Navigation]`, `[Main Content]`, `[Modal]`), empowering the LLM to disambiguate form submit controls from top navigation links dynamically.
- **Closed-Loop State Verification & Misclick Auto-Recovery:** Added real-time post-click state verification in `_run_step` (`test_execution.py`) that detects if a navigation dropdown was opened unintentionally during a form action, closes the stray menu, invokes the Execution Agent, and submits the in-form button.

## [1.7.7] - 2026-09-12

### Fixed

- **Universal Multi-Container Submit Button Resolution:** Enhanced `_find_element_with_fallback` in `test_execution.py` to match in-page action controls across `.container`, `.well`, `.panel`, and form wrappers (`input[type=submit]`, `input[type=button]`, `input.btn`, `button`, `.btn`) while strictly filtering out navbar dropdown toggles (`.dropdown-toggle`, `header a`, `nav a`).
- **Resilient Multi-Locator Synthesis in Automation Compiler:** Updated `automation_builder.py` so action words (`find`, `search`, `submit`, `save`, `update`, `filter`, `apply`) compile into multi-strategy resilient locators (`input[type='submit'][value*='...'], button:has-text('...'), text=...`) rather than fragile single text selectors.

## [1.7.6] - 2026-09-12

### Fixed

- **Root-Level Agent Discovery of Form Submit Buttons:** Upgraded `_TargetSnapshotParser` and `_collect_interactive_controls` in `ai_service.py` so the Application Discovery Agent accurately harvests `<input type="submit">`, `<input type="button">`, and `.btn` form action controls (e.g. `"Find Clinics"`, `"Find Owners"`, `"Find Pets"`, `"Find Vaccerts"`) using their `value` attributes and prevents classifying top navigation menu toggles (`Find ▾`) as form buttons.
- **Agent Planning & Generation Disambiguation Directives:** Updated `playwright-test-planner.agent.md`, `playwright-test-generator.agent.md`, and `_build_prompt` with explicit agent directives (Directive 25) to mandate that AI agents generate form actions targeting specific on-page submit buttons (e.g. `Click button "Find Clinics"`, `Click "Find Owners"`) rather than top navigation menu categories (e.g. `Find`).
- **Healer Agent Form Context Priority:** Updated `playwright-test-healer.agent.md` to instruct the Playwright Test Healer Agent to identify and repair failed click steps using form-scoped submit controls adjacent to entered inputs.

## [1.7.5] - 2026-09-12

### Fixed

- **Eliminated Header Navigation Click Hijacking:** Removed legacy hardcoded navigation dropdown loop in `_run_step` and strictly excluded top-level navigation dropdown toggles (`header a`, `nav a`, `.navbar a`, `.dropdown-toggle`, `[data-toggle="dropdown"]`) from matching in-page button and submit text actions.
- **Form-Scoped Submit & Action Button Precision:** Optimized `_find_element_with_fallback` to prioritize active form submit controls (`form input[type=submit]`, `form button`, `form .btn`, `main input[type=submit]`, `main .btn`) adjacent to entered inputs.
- **Enriched LLM Context with Element Classes & Container Hierarchy:** Upgraded `_capture_healing_page_context` to include full CSS classes (e.g. `[class='btn btn-primary']`) and preceding step context, enabling the LLM Playwright Test Healer to disambiguate in-page action buttons from header menu items.

## [1.7.4] - 2026-09-12

### Fixed

- **Form & Content-Scoped Action Button Resolution:** Fixed locator resolution to prioritize action buttons (`<button>`, `<input type="submit">`, `.btn`) inside active forms and main content over header navigation links, preventing navbar links from hijacking clicks after entering text in input fields.
- **Workflow Context-Aware Step Tracking:** Passed preceding step action and selector context into `_run_step` and `_find_element_with_fallback` (`context_hint`) so click actions following text inputs search within the active form/container before falling back to global page elements.
- **Hierarchical Container Context for LLM Reasoning:** Upgraded `_capture_healing_page_context` to annotate DOM elements with container hierarchy tags (`[Header/Navigation]`, `[Form #id]`, `[Main Content]`, `[Modal/Dialog]`), giving the Playwright Test Healer full structural awareness to disambiguate in-form buttons from top-level navbar links.
- **Enhanced LLM Healer Prompting:** Updated `generate_healing_step` system instructions and guidance with container-scoping rules to ensure LLM agent dynamically selects scoped form locators rather than relying on brittle hardcoded ID strings.
- **In-Memory Vector Store Fallback:** Added resilient `InMemoryCollection` fallback in `vector_service.py` ensuring self-healing memory and document indexing work seamlessly in environments without persistent ChromaDB binaries.

## [1.7.3] - 2026-09-11

### Added

- **Client Showcase Execution Mode:** Added a dedicated `showcase` speed profile preset to synchronize live Playwright DOM actions, high-visibility spotlight target highlighting, and voice-over narration in lockstep for client and customer presentations.
- **Lockstep Speech-Paced Dwell Engine:** Implemented word-count-based step dwell calculation in backend execution (`_calculate_step_speech_dwell_ms`) to hold each step between 1.8s–3.2s, ensuring voice narration finishes before advancing to the next step.
- **Adaptive Voice-Over Queue Management:** Upgraded frontend speech pump to prune stale backlog events during network latency, preventing queued speech from trailing behind current browser state.

## [1.7.2] - 2026-09-11

### Fixed

- **Adaptive Locator Timeout Allocation:** Replaced artificial 250ms locator timeout caps in `_find_element_with_fallback` with adaptive deadline allocation (2500ms for primary candidates) so page transitions and dynamic content loads do not prematurely time out.
- **Asynchronous Title & Text Polling:** Upgraded `assert_title` and `assert_text` to poll with 5-second deadline intervals across `page.title()`, `h1-h3`, `.page-header`, `legend`, and `body` text, preventing false assertion failures on asynchronous route updates.
- **Dropdown & Select Resolution:** Added automatic `<select>` and `<option>` tag handling for click actions and enhanced `automation_builder.py` with `filter by <field> '<value>'` compilation.
- **Unified Test Data Parameter Injection:** Connected `test_case.test_data` matrices to both single-case (`run_test_case`) and batch (`run_test_cases_batch`) execution endpoints.
- **Enhanced Failure Classification:** Added specific detection for HTTP 500/404 server errors and authentication gates to classify failures as `APPLICATION_DEFECT` or `AUTHENTICATION`.

### Added

- **Jira Filter 36396 Defect Coverage Analysis:** Comprehensive defect mapping and framework coverage assessment for all 50 defects in Jira Filter 36396 across Apollo, Schedule Meow, ASTA, and NetSuite data flows in `docs/JIRA_FILTER_36396_DEFECT_COVERAGE_ANALYSIS.md`.

## [1.7.1] - 2026-09-10

### Fixed

- **Jira Cloud API Connectivity & Environment Resolution:** Updated backend environment configuration handling and Jira integration service to support direct Jira Cloud API authentication without requiring a pre-set default project key or filter ID when fetching single issues or testing connection.
- **Jira Cloud Modern Search API Support:** Migrated Jira requirements queries to the modern `/rest/api/3/search/jql` endpoint with automatic fallback to `/rest/api/3/search` for legacy instances.
- **Direct Jira Issue & URL Resolution:** Verified end-to-end live resolution and context ingestion for Jira issues (including `QA-37489` and `https://tractorsupplycompany.atlassian.net/browse/QA-37489`).

## [1.7.0] - 2026-09-10

### Added

- **Jira Issue Context Import for AI Test Generation:** Enhanced the AI Generator Studio to accept Jira issue keys (e.g. `QA-37489`) or full issue URLs (e.g. `https://tractorsupplycompany.atlassian.net/browse/QA-37489`) to directly import story, defect, and acceptance criteria context for AI test generation.
- **Jira ADF Parser & Rich Metadata Extraction:** Implemented Atlassian Document Format (ADF) parsing, custom acceptance criteria extraction, and recent discussion integration in backend `JiraClient` and `/api/v1/integrations/jira/fetch-issue`.
- **Integrated AI Discovery & Planner Anchoring:** Seamlessly bound imported Jira requirement context with document analysis, intake signals, and planner/generator LLM prompts, ensuring generated test cases directly validate acceptance criteria and business rules.
- **Jira Issue Summary Card in Studio:** Added an interactive Jira issue card with issue type, status, priority, description preview, acceptance criteria display, and one-click prompt population.

## [1.6.13] - 2026-09-09

### Fixed

- **Execution Voice-Over Step Alignment:** Attached human-readable step descriptions directly to compiled automation steps so live voice-over announcements and video narration speak the actual natural test case steps (e.g. `Click 'Sign In' button`, `Enter valid login email address`, `Verify 'Dashboard' is visible`) instead of raw technical CSS/XPath queries and robotic selector code.
- **Natural Voice-Over Target Phrasing:** Upgraded `_describe_step_action` and `cleanExecutionSpeech` to clean raw selectors and technical tokens into natural phrasing across click, type, select, check, uncheck, and assertion actions.

## [1.6.12] - 2026-09-09

### Fixed

- **Login Credential Field Separation:** Fixed compound password field matching (`user password`, `login password`, `password`) taking strict precedence over broad username/user tokens, preventing password values from being entered into email/username fields.
- **Runtime Credential Selector & Type Validation:** Added semantic validation in Playwright execution ensuring password steps target password controls, learned locators are validated against expected credential kinds, and duplicate or cross-field email/password selectors are rejected before execution.
- **Configure Run Validation:** Added frontend and API validation rejecting identical email and password field selectors and ensuring safe defaults.

## [1.6.11] - 2026-09-08

### Fixed

- **Apollo Staging Test Data:** Captured verified staging identifiers for the affected owner, pet, vaccert, order, reaction, site visit, clinic, report, and current-clinic workflows so parameterized executions do not fall back to sample values.
- **Apollo Automation Selectors:** Replaced disproven generated selectors with selectors matched to the live staging DOM for login/logout, search forms, filters, detail links, and current-clinic navigation.
- **Failure Diagnostics:** Automatic and manual defect logging now includes plain-language failure guidance, page title, exact failed steps/checks, exception text, console/network diagnostics, and evidence artifact paths. Execution errors are also eligible for automatic defect capture.

## [1.6.10] - 2026-09-09

### Changed

- **Top Execution Monitor:** Moved live execution progress directly below the Execute Tests header so status, progress, active case, and pause/stop controls are visible before the case repository.
- **Execution Monitor Tabs:** Added compact `Overview`, `Case progress`, and `Live activity` tabs so large batches remain scannable without losing per-case diagnostics.

## [1.6.9] - 2026-09-09

### Fixed

- **Configure Run Login Defaults:** Added safe default email, password, and submit selectors and normalized blank legacy saved selectors, preventing authenticated execution from being rejected before reaching the backend.
- **Batch Login Preamble:** Applied the effective Configure Run selectors when compiling authenticated batch-case automation, so enabled login parameters now execute rather than only validating the form.

## [1.6.8] - 2026-09-09

### Fixed & Enhanced

- **Visible Parameterized Value Editor:** The `Add parameterized value` action now reveals editable key/value rows, including sensitive handling and removal, while preserving the shared runtime context used by generation and execution.
- **Responsive Parameter Editor Layout:** Added desktop and mobile layout rules for parameterized rows without restoring the removed profile panel.

## [1.6.7] - 2026-09-09

### Execution & Workspace Reliability

- **Execution Controls and Status Visibility:** Added pause, resume, and stop actions with persistent execution status/progress presentation in Execute Tests and Run History.
- **Complete Build Report Details:** Expanded build and batch execution detail loading so the latest report includes all case executions rather than only the visible client slice.
- **Step-Scoped Voice-over and Highlighted Evidence:** Restricted narration to actionable execution steps and exposed per-step highlighted screenshots in execution results.
- **Automatic Workspace Synchronization:** Added server-owned polling for execution/history state and removed redundant manual refresh controls across the main workspace surfaces.
- **Execution and Defect UI Resilience:** Improved pagination, long-text wrapping, contained action layouts, and parameterized-value editing for stable responsive use.

## [1.6.6] - 2026-09-09

### Performance & UI Responsiveness

- **Lazy Active Section Rendering:** Replaced eagerly evaluated view variables with lazy render functions (`renderDashboard`, `renderAiGeneratorView`, `renderCases`, etc.) in `frontend/src/app/page.tsx`, rendering only the active tab to eliminate all input lag and text editing freezes on the AI prompt textarea and settings fields.
- **Enhanced AI Prompt & Input Attributes:** Configured explicit element IDs, `name` attributes, `autoComplete="off"`, and `spellCheck="false"` across scenario prompt textareas, module focus textboxes, and target URL inputs.

## [1.6.5] - 2026-09-09

### Added & Enhanced

- **Dynamic Agent Test Data Parameterization:** Eliminated hardcoded test values across the framework, routing all business test inputs, credentials, and search keys through agent-managed template parameters (`{{key}}`).
- **Autonomous Agent Contract Enforcement:** Updated agent definitions (`test-data-generator`, `test-scenario`, `playwright-test-generator`, `low-code-authoring`) to explicitly govern test data generation dynamically via live application memory and synthetic profiles.
- **Runtime Test Data Auto-Resolution:** Enhanced Playwright execution fallback in `test_execution.py` to synthesize dynamic values using `TestDataGeneratorService` and `SelfLearningEngine` whenever parameter keys are unconfigured.

## [1.6.4] - 2026-09-09

### Fixed & Enhanced

- **HTML Tag & Checked Checkbox Selector Conversion:** Added `_convert_html_tag_to_selectors` in `backend/app/services/test_execution.py`, parsing raw HTML tag snippets like `<input type="checkbox" checked="">` and `<input id="..." type="checkbox">` into valid CSS selectors (`input[type='checkbox']:checked`, `input[type='checkbox'][checked]`, `#id`).
- **Resilient Checkbox State Toggle & Verification:** Enhanced `check`, `uncheck`, and `click` step handlers and `visible` check assertions to detect pre-checked states (`checked=""`), dispatch native `change`/`input` events, and prevent invalid CSS selector DOMException errors.
- **Natural Language Checkbox Step Compilation:** Updated `automation_builder.py` and `frontend/src/app/page.tsx` to preserve and correctly route raw HTML tag targets in checkbox action steps.

## [1.6.3] - 2026-09-09

### Fixed & Enhanced

- **React Rules of Hooks Order Enforcement:** Fixed conditional hook invocation in `frontend/src/app/page.tsx` by relocating authentication gate checks to the render phase following all hook declarations, preventing the React hook order mismatch error.
- **Continuous UI Stability:** Verified non-blocking input responsiveness and error-free re-renders across all authenticated and unauthenticated states.

## [1.6.2] - 2026-09-09

### Performance & UI Responsiveness

- **Non-Blocking UI Rendering & Comprehensive Memoization:** Wrapped all workspace, project, application, coverage, defect, execution trend, and validation metrics in `useMemo` in `frontend/src/app/page.tsx`, eliminating UI freezing on prompt text inputs, module search textboxes, and scenario strategy checkboxes.
- **Concurrent Non-Blocking AI Scenario Inputs:** Integrated React `useDeferredValue` for prompt text areas, module search fields, performance budget inputs, and live generation log search in `AIGenerationConsole.tsx`.
- **Expanded Scenario Strategy Toggles:** Added dedicated UI checkboxes for boundary scenarios, edge cases, and security scenarios in the AI Test Design Studio.

### Fixed & Enhanced

- **Resilient Multi-Selector Username & Password Autofill:** Expanded credential matching across `#user_email`, `#user_password`, `input[name='user[email]']`, `input[name='user[password]']`, `input[type='email']`, `input[type='password']`, `[aria-label*='email']`, and `[aria-label*='password']` in `test_execution.py`.
- **Authenticated Session Bypass & Step De-duplication:** Prevented duplicate login step injection in `automation_builder.py` and implemented non-blocking bypass of redundant login typing/clicks when running in already-authenticated application contexts.

## [1.6.1] - 2026-09-09

### Added & Enhanced

- **Automated Defect Lifecycle & Real-Failure Logging:** Implemented `DefectService` (`backend/app/services/defect_service.py`) automatically capturing confirmed test execution failures, step-level traces, check assertions, failure classifications, and console errors into deduplicated open defect records.
- **Synchronous Text Signal & Live Discovery Entity Harvesting:** Added `harvest_text_signals` in `SelfLearningEngine` to extract entity patterns (barcodes, orders, statuses, names) from discovery headings, controls, and route signals.
- **Enhanced Page Title & Heading Assertions:** Improved `_run_check` title and header evaluation with resilient multi-term and substring matching for dynamic SPA state changes.

## [1.6.0] - 2026-09-09

### Added & Enhanced

- **Test Data Generator Agent in Multi-Agent Pipeline:** Integrated `test_data_generator` as Stage 7 in `ai_generation_pipeline.py` and `ai_generation_jobs.py`, producing realistic valid, invalid, boundary, and edge datasets attached directly to generated test cases and job results.
- **Continuous Adaptive Entity Harvesting & Self-Learning Engine:** Implemented `SelfLearningEngine` entity harvesting (`harvest_page_entities`, `record_discovered_entities`, `get_discovered_entities`) backed by ChromaDB vector memory (`app_{id}_test_data_memory`), active during target discovery, execution, and healing.
- **Runtime Parameter Auto-Interpolation:** Enhanced Playwright test execution (`test_execution.py`) with automatic fallback to discovered live entities when runtime parameters are omitted.
- **REST Endpoints for Test Data Generation & Entity Discovery:** Added `POST /api/v1/test-data/generate/{application_id}` and `GET /api/v1/test-data/learned/{application_id}` in `backend/app/api/v1/test_data.py`.
- **UI Integration in Parameterized Data Studio:** Added "✨ Smart AI Data Generator" and "🧠 Auto-Learn from App" in `ParameterizedDataProfile.tsx` and `page.tsx` for one-click dataset generation and live entity population.
- **Step Parser Grammar Inversion Fix:** Gated `_is_verification_only_line` in `automation_builder.py` and `page.tsx` before typing and clicking heuristics, preventing verification assertions with multiple keywords (e.g. `Verify page title contains 'Apollo' or 'staging'`) from converting into typing actions.
- **Session-Aware Authentication Bypass & Login De-duplication:** Added authenticated state detection in `_run_step` and eliminated redundant login step injection when tests run within already-authenticated browser contexts.

## [1.5.1] - 2026-09-08

### Performance & Optimization

- **High-Performance Playwright Checkbox & Textbox Execution:** Added native `check` and `uncheck` step actions with `force=True` toggle to eliminate CSS pointer-interception stalls and label-double-toggle flakiness.
- **Fast-Path Textbox Value Entry:** Implemented direct `fill` with `contenteditable` and `evaluate` fallbacks for textboxes and rich inputs, bypassing sequential retry loops.
- **Eliminated Artificial Playwright Execution Delays:** Removed default 50ms slow-mo and 100ms action-highlight pauses in standard execution, and removed redundant 600ms `networkidle` stalls on link clicks for faster test throughput.
- **Concurrent Non-Blocking UI Inputs:** Integrated React `useDeferredValue` for search textboxes in `RunHistoryWorkspace` and `page.tsx`, and migrated table selection checkboxes to $O(1)$ set lookups, eliminating all input lag.

## [1.4.0] - 2026-09-08

### Added & Enhanced

- **Persistent Build Execution Records & Aggregation:** Added `BuildExecution` model (`backend/app/models/build_execution.py`) and schema migration (`20260904_build_executions`) tracking batch/build executions, KPIs, total cases, passed/failed/error counts, total duration, and trigger source.
- **Backend Build & Batch Execution APIs:** Added `POST /api/v1/execution/batch`, `GET /api/v1/execution/builds/{application_id}`, and `GET /api/v1/execution/builds/{build_id}/detail`, with automatic status and KPI synchronization upon test completion.
- **Run History Dual-View Workspace:** Implemented a segmented control in `RunHistoryWorkspace.tsx` offering instant toggling between `[ 📑 Build & Batch Executions ]` and `[ 📋 Individual Case Runs ]`.
- **Expandable Build Accordion Rows:** Added collapsible sub-tables for each build row displaying detailed case-by-case execution status, check counts, execution duration, failure reasons, and quick links to individual run reports.
- **Complete Build Execution Report Modal & Export:** Added drill-down modal with KPI summary cards, pass rate progress bar, case breakdowns, and single-click CSV report export.

## [1.3.6] - 2026-09-07

### Fixed & Enhanced

- **Extended Client Polling Timeout for Multi-Batch Generation:** Increased client-side AI generation polling timeout from 180 seconds to 15 minutes (`900_000ms`), preventing premature client timeouts during multi-batch generation of 30–50 test cases.
- **Safe Asynchronous Coroutine Execution:** Created `_run_coro_sync` in `ai_generation_jobs.py` with ThreadPoolExecutor fallback, eliminating `RuntimeError: This event loop is already running` across background agent stages.
- **Configurable AI Service Timeout Resolution:** Updated `_load_timeout_seconds` in `ai_service.py` to check both `AI_TIMEOUT_SECONDS` and `AI_QA_ENGINE_AI_TIMEOUT_SECONDS` with an increased default of 90 seconds per provider call.

## [1.3.5] - 2026-09-07

### Added & Enhanced

- **Multi-Tier Embedding Generator:** Added `generate_embeddings()` in `vector_service.py` supporting remote embeddings API (`text-embedding-3-small`), CPU-optimized FastEmbed (`BAAI/bge-small-en-v1.5`), and deterministic dense hash vectorizer fallback.
- **Application-Scoped ChromaDB Vector Store:** Implemented persistent vector collections for requirement documents (`app_{id}_documents`), test cases (`app_{id}_test_cases`), and locator repair memory (`app_{id}_healing_memory`).
- **Semantic Document Chunking & Ingestion:** Added recursive paragraph/sentence chunking in `document_analysis.py` with automatic vector indexing during AI Document Analysis.
- **Semantic Test Case Deduplication & Similarity API:** Integrated vector indexing upon test case creation/import and added `POST /api/v1/test-cases/application/{id}/check-similarity` for semantic duplicate detection.
- **Self-Healing Experience Vector Memory:** Indexed validated Playwright locator repairs into vector memory, automatically passing historical repair patterns to the Healer Agent during test execution.

## [1.3.4] - 2026-09-07

### Fixed & Enhanced

- **Dynamic Database Path Normalization:** Resolved relative SQLite URLs (`sqlite:///./sheppard.db`) to absolute file paths across both workspace root and backend directories, guaranteeing reliable database connections across processes.
- **Uvicorn Multi-Process Startup Stabilization:** Fixed PowerShell startup argument expansion in `start-local.ps1` by passing explicit `--app-dir` configuration, ensuring sub-10ms server initialization.

## [1.3.3] - 2026-09-07

### Performance & Optimization

- **SQLite High-Concurrency WAL Mode & Connection Tuning:** Enabled Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=15000`, and `PRAGMA temp_store=MEMORY` on all database connections, eliminating database lock contention during concurrent test execution and background worker polling.
- **Fast-Path Playwright Element Resolution:** Added instant visibility checks (`is_visible(timeout=40ms)`) across candidate locators before executing sequential wait loops, speeding up element discovery across 30+ fallback selectors from seconds down to <5ms.
- **Viewport-Optimized Screenshot Capture:** Switched step and highlight screenshot capture from costly `full_page=True` DOM stitching to viewport capture (`full_page=False`), cutting per-step screenshot latency by ~95% (from ~1000ms to ~35ms).
- **Adaptive Post-Click Navigation:** Optimized post-click load state waiting to prioritize `domcontentloaded` followed by bounded short `networkidle` checks, avoiding 2.5s networkidle stalls on dynamic pages.

## [1.3.2] - 2026-09-07

### Added

- **Interactive Live Execution Notification:** Added a real-time banner to the executive dashboard when tests are actively running, featuring animated pulse status, completed/passed/failed live counters, and one-click navigation to the execution monitor.
- **Bulk Test Case Actions & Interactive Management:** Integrated a floating batch action toolbar for selected test cases, allowing one-click bulk execution, bulk approval of draft cases, and batch deletion.
- **Unified Library Search & Pagination:** Enabled rich keyword search, status filtering (`All`, `Draft`, `Ready`), sorting, and page size controls across both Test Cases and Test Execution views.
- **Visual Feedback & Table Row Selection:** Added interactive `.row-selected` highlighting on chosen table rows and polished button focus states.

## [1.3.1] - 2026-09-07

### Removed

- Removed unwanted static promotional capability panel ("Autonomous Testing Engine / Enterprise AI QA Capabilities") from the Dashboard to eliminate static clutter.
- Cleaned up legacy unreferenced chart helpers (`CapabilityPanel`, `BarChart`, `Donut`) from frontend sources.

## [1.3.0] - 2026-09-07

### Added

- **Universal Multi-Project Dashboard Scope:** Enhanced the executive dashboard to support any enterprise project and target application with dual scope selector controls (Project Scope + Target Scope), live lifecycle status chips (`Active`, `Paused`, `Archived`), and project-level health indicators.
- **Dynamic Multi-Project Workspace Integration:** Removed static single-project constraints; all custom created and imported enterprise projects in the workspace are now first-class citizens with live target portfolios, test case suites, execution runs, and defect analytics.
- **Streamlined UI & Duplicate Content Removal:** Cleaned up duplicate inline forms and redundant text across the Dashboard, Projects, Applications, Test Cases, Execution, and AI Studio views.

## [1.2.11] - 2026-09-07

### Changed

- Relocated the AI Test Design Studio primary action toolbar (`.ai-simple-action-row`) to the top directly below the header hero banner for immediate discoverability and quick execution triggering.
- Streamlined Step 3 panel into a dedicated workflow trace and review console with clean summary metrics and agent stage monitors.

## [1.2.10] - 2026-09-04

### Added

- Added `docs/WORKFLOW.md` consolidating the unified multi-path workflow architecture:
  - **Path A:** Manual Test Generation from requirements and user stories to Excel/qTest export with review gates.
  - **Path B:** Low-Code Automation Conversion using token-efficient code skeletons and pre-commit review gates.
  - **Path C:** Freeform Context Test Generation applying formal black-box test design techniques (EP, BVA, DT, STT, Pairwise, E2E).
- Added GitHub Copilot prompt templates under `.github/copilot-prompts/` for test generation, automation conversion, framework analysis, and Git/qTest workflows.

### Changed

- Enhanced `docs/Testing-Strategy.md` with formal test design technique criteria (Equivalence Partitioning, Boundary Value Analysis, Decision Tables, State Transition Testing, Pairwise Combinations, and E2E Side Effects).
- Enriched `docs/AI_DOCUMENT_WORKFLOW.md` and `docs/AI_TEST_DESIGN_STUDIO.md` with named attachment context calibration (`functional-document`, `regression-tc-for-granularity-level-check`), chunked export resilience, and human review gates.
- Updated `docs/SCENARIO_AGENT.md`, `docs/USER_GUIDE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/Jira-Integration.md`, and `docs/qTest-Integration.md` to align with the enterprise multi-path quality engineering workflow.

## [1.2.9] - 2026-09-04

### Added

- Added an interactive **Smart AI Integration & Test Plan** popup dialog (`SmartAIPlanModal`) triggered when clicking `Analyze with AI` on application cards.
- Integrated a 4-stage interactive graphical navigation breadcrumb (Context & Intake, 8-Agent Pipeline, Coverage Matrix, Execution & Healing) with specification viewers and quality metrics.
- Added live coverage strategy selection (Dynamic AI, Smoke, Target, Extended, Deep Regression), configurable QA dimension toggles (Negative, A11y, API, Performance, Login), and direct execution launch options.

## [1.2.8] - 2026-09-04

### Fixed

- Removed duplicate status chip rendering between the active execution test card and the live case-by-case progress list.
- Removed duplicate pass/fail/error status text in execution progress KPIs, letting the live counter strip serve as the single source of count metrics.
- Removed redundant approved/rejected text from AI generation preview actions column.

## [1.2.7] - 2026-09-04

### Removed

- Removed the redundant `Library view` heading and `Filter and arrange the cases before choosing a run scope` subtitle block from the Execute Tests workspace filter panel.

### Changed

- Streamlined the Execute Tests filter toolbar into a clean, compact controls grid with an aligned reset action.

## [1.2.6] - 2026-09-04

### Fixed

- Resolved text and action button overlap on test case library tables by removing conflicting `td:last-child` sticky positioning and assigning fixed column widths exclusively to `th` headers (`.col-testcase`, `.col-precondition`, `.col-description`, `.col-stepnum`, `.col-steps`, `.col-expected`, `.col-status`, `.col-actions`).
- Removed duplicate and redundant `<h2>` section headings across pages (including replacing duplicate `Recent run history` with clean `<h3>Execution Records</h3>` and standardizing `Table` titles to `<h3>`).

### Removed

- Removed the redundant `Show case context columns` checkbox toggle from the Execute Tests workspace library view.
- Removed empty footer wrapper from test case library view options and aligned the reset action directly with filter status.

### Changed

- Standardized test case library tables across all sections to consistently display all context columns with stable layout and zero horizontal cell collision.

## [1.2.5] - 2026-09-04

### Added

- Merged and integrated automated local synchronization worker and script controls with branch synchronization.

## [1.2.4] - 2026-09-04

### Added

- Added a 30-minute local synchronization worker that fetches `AutomationTool_POC`, merges incoming changes into `AutomationTool_POC_lkurra`, and restarts the local services.
- Added start/stop script controls for changing the synchronization interval or disabling automatic synchronization.

## [1.2.3] - 2026-09-04

### Added

- Added canonical architecture and governance documentation across all 20 enterprise operational dimensions:
  - `docs/Future-State.md` (Enterprise target operating model)
  - `docs/Agent-Architecture.md` (12-agent autonomous testing framework)
  - `docs/AI-Architecture.md` (Provider contracts, context budgeting, inference safety)
  - `docs/Scalability.md` (Distributed execution, clustering, 100k test scale)
  - `docs/Security.md` (Zero-trust integration policies, write-only credentials, RBAC)
  - `docs/Observability.md` (Structured telemetry, correlation IDs, live event streaming)
  - `docs/Jira-Integration.md` (Read-only sync & defect governance)
  - `docs/qTest-Integration.md` (Read-only asset synchronization)
  - `docs/Navigation-Strategy.md` (7-pillar information architecture & design standards)

### Fixed

- Enhanced Next.js clean script resilience for concurrent local development file handles.

## [1.2.2] - 2026-09-04

### Fixed

- Queued voice-over narration from cumulative execution events so every execution step is announced without rapid updates canceling one another.
- Made execution report export functional and improved Steps table header semantics for assistive technology.

## [1.2.1] - 2026-09-04

### Added

- Added an application-scoped test data profile for reusable login and business values such as identifiers, dates, and search inputs.
- Redacted sensitive profile values from AI generation context and excluded them from local profile persistence.

### Changed

- Removed the redundant source-format selector from AI Test Design Studio; source context is now summarized automatically from the prompt and uploaded documents.
- Simplified generation settings around coverage, module focus, target, API/performance scope, and approved parameter usage.

## [1.2.0] - 2026-09-04

### Added

- Complete enterprise UI/UX transformation across all application workflows and presentation layers.
- Standardized Enterprise Design System v6: elevated card systems, modern typography hierarchy, high-contrast status chips, smooth micro-interactions, and refined color token architecture.
- Autonomous Testing Engine showcase on the Dashboard highlighting Discovery, Scenario Planning, Parallel Execution, and Self-Healing capabilities.
- Modernized Dashboard Hero with executive metadata chips, environment scope switcher, and one-click quick actions.
- Interactive KPI cards with top gradient accent indicators, bold typographic scale, and hover elevation.
- Standardized table surfaces (`workspace-table-surface`) with contained dual-direction scroll synchronization, clean uppercase column headers, and structured action buttons.
- Enhanced AI Test Design Studio console with pulsing live status indicators, log-level filters, and export utilities.
- Polished Execution Progress Monitor with live step timers, audio voice feedback controls, and active runner animations.

### Changed

- Enhanced navigation shell and top header bar with glassmorphic backdrop filter, refined application selector, and polished user profile menu.
- Optimized whitespace and visual hierarchy across all screens for executive customer demonstrations and sales presentations.

### Removed

- Removed unused 0-byte component placeholders (`DashboardStats.tsx`, `DefectList.tsx`, `ExecutionHistory.tsx`, `Layout.tsx`, `TestCaseTable.tsx`, and empty `components/ui/*` directory).

## [1.1.10] - 2026-09-04

### Changed

- Moved protected-target login credentials to sensitive per-run UI runtime parameters and made target-specific selectors configurable in the UI.
- Removed login credential and selector environment fallbacks from application execution and AI discovery.
- Removed optional OpenAI fallback and staging login values from local and deployment environment templates.

## [1.1.9] - 2026-09-04

### Fixed

- Prevented integration profile forms from submitting both a credential and a secret reference; entering one now clears the other before save.

## [1.1.8] - 2026-09-04

### Added

- Added a Settings editor for local Jira and qTest environment configuration, including write-only token replacement and refreshed sanitized status.

### Security

- Preserved strict external read-only behavior: environment updates change only the local backend `.env`; Jira and qTest create, update, and delete operations remain disabled.

## [1.1.7] - 2026-09-04

### Added

- Added API contract and performance scenario controls to AI Test Design Studio, including OpenAPI/performance source formats and optional measurable performance budgets.
- Added persisted API/performance coverage categories and safe prompt guidance for bounded non-UI test design.

## [1.1.6] - 2026-09-04

### Changed

- Made Jira and qTest connection settings environment-backed, with automatic non-persistent profiles and sanitized configuration status in Settings.
- Enforced strict GET/HEAD-only external integration access and removed the Jira defect creation path; external create, update, and delete operations are disabled.

## [1.1.5] - 2026-09-03

### Added

- Added explicit test-case Create, View, Edit, and Delete controls to the Execute Tests workspace, including create and read-only detail modes in the existing numbered-step editor.

## [1.1.4] - 2026-09-03

### Changed

- Enhanced Run History with browser, application, and device detail columns, including searchable and sortable values plus column customization support.

## [1.1.3] - 2026-09-03

### Changed

- Removed project-specific demo bootstrap records so fresh workspaces create only the configured initial administrator; applications, projects, cases, defects, suites, and runs are user-owned data.
- Made dashboard coverage and automation fallback behavior derive from user-provided test-case categories and values instead of a fixed sample application.

### Added

- Added protected single-case and bulk test-case deletion with dependent-record cleanup and active-run safeguards.

## [1.1.2] - 2026-09-03

### Fixed

- Added a local Save configuration action for Execute Tests and grouped Configure run beside Run all cases in the execution header.

## [1.1.1] - 2026-09-03

### Changed

- Added a canonical application version contract, version verification gates, and a visible `Version 1.1.1` label beside the shared Application selector, including at the top of `/ai-generator`.

## [Unreleased]

### Added

- Added bounded safe exploratory discovery before AI planning: same-origin navigation, tabs, menus, filters, and disclosure controls are exercised without destructive actions; observations, hypotheses, exploratory charters, and stage metrics are persisted and passed to generation.
- Added governed Jira and qTest integration profiles with encrypted or secret-provider credentials, role-scoped CRUD, GET-only connection validation, bounded read-only asset retrieval, explicit confirmed Jira defect creation, idempotent external links, and redacted audit events.
- Added strict explicit AI provider selection and removed retired local-provider, automatic provider ordering, and deterministic replacement-generation paths from runtime, UI, deployment defaults, scripts, tests, and documentation.
- Added current and future agent architecture documentation plus focused Planner, Discovery, Scenario, Execution, Evidence, Reporting, and Orchestration contracts.
- Added a current agent architecture report that maps real Discovery, Planner, Generator, Validation, Repository, Healer, execution, evidence, and reporting boundaries and identifies remaining standalone-agent gaps.
- Added bounded self-healing and self-learning: successful same-action locator repairs are persisted to future automation, recorded as redacted `auto_applied` recommendations, and written to the audit trail.
- Updated agent guidance and the Autonomous Agent Framework documentation with current application-scoping, source-grounded, parallel execution, healing, learning, persistence, and delivery contracts.
- Added bounded parallel execution for selected test cases with configurable one-to-five worker concurrency, isolated browser runs, per-case progress, and concurrency regression coverage.
- Added interactive test-step editing for existing and AI-generated cases with independent add/delete controls while preserving the existing numbered `steps` API format.
- Added a workspace delivery policy requiring validated frontend/UI and application source-code changes to be committed and pushed to the current branch's configured upstream, with safeguards for local-only requests, unresolved validation, secrets, generated files, and unrelated changes.
- Consolidated the legacy `doc/` documentation tree and duplicate workbook assets into the canonical `docs/` tree after duplicate-content, drift, hash, and repository-reference checks.
- Added a phased documentation consolidation plan that establishes `docs/` as the single source of truth, classifies duplicate and drifted legacy files, and defines link, binary asset, deprecation, rollback, and validation gates.
- Added a repository-wide UI audit report and Run History table alignment standard covering duplicate actions, whitespace, tables, responsive behavior, and remaining product capability gaps.
- Added the AI Test Design Studio document workflow with bounded PDF, DOCX, TXT, CSV, XLSX, JSON, and Markdown analysis, aggregate requirement metrics, module and warning extraction, and prompt-only fallback behavior.
- Added durable eight-stage AI test-design metadata with a first-class Application Discovery snapshot, server-owned progress, validation metrics, versioned agent-definition provenance, and a visible frontend stage dashboard.
- Added a real AI Planner call followed by AI Generator continuation batches, with planner-derived case targets, duplicate avoidance, provider call telemetry, and audit provenance.
- Added focused document-parser contract tests and canonical AI workflow documentation.
- Added an execution-details deduplication plan to keep the preferred execution summary canonical while preserving unique timeline and operational diagnostics.
- Added a shared execution summary renderer so the post-run result and View Details route use the same failure callouts, KPI metrics, evidence cards, healer status, and checks format.
- Added a navigation module retirement plan for removing Projects and Execution Plans from the primary sidebar while preserving direct routes, APIs, data, migration, and rollback safety.
- Added a page-heading and content-density plan covering shared spacing, route-level priorities, responsive alignment, accessibility, and measurable acceptance criteria.
- Added an enterprise remediation and optimization roadmap covering verified current state, alignment debt, execution lifecycle, AI maturity, security, scalability, observability, documentation, and quality gates.
- Added a run-history cleanup plan covering selected-application scope, terminal-run safety, dependent records, evidence deletion, audit retention, confirmation, and retention operations.
- Added an interactive Agents recommendation review workspace with searchable/filterable recommendations, full step and validation inspection, masked values, review notes, and contextual test-case navigation.
- Added a Settings Studio redesign plan covering provider/model hierarchy, discovery states, credential safety, responsive layout, accessibility, and validation.
- Added a documented contribution workflow requiring changelog updates and validated commits for build-affecting changes.
- Embedded redacted execution narration in recorded videos with male/female voice selection and audio status reporting.
- Moved run-detail video playback before the step-by-step execution timeline.
- Canonical documentation index, security guide, and testing strategy.
- Push and pull-request CI workflow covering frontend checks, backend checks, and dependency audits.
- Root validation targets in `Makefile` for frontend, backend, and security checks.
- CI migration upgrade and metadata-consistency validation against a temporary SQLite database.
- User-centered execution plan covering individual cases, selected tests, reusable suites, execution plans, preflight, live progress, cancellation, resume, retries, AI healing, evidence, and defect aggregation.
- Enhanced export and failure-to-defect plan covering redacted JSON/CSV/ZIP packages, local defect occurrences, deduplication, evidence links, and future Jira synchronization.
- Collapsed-sidebar layout plan covering overlap prevention, compact spacing, shared route integration, icon accessibility, and visual regression checks.

### Changed

- Updated backend container build contexts to package the shared `.github/agents/` definitions and made agent-definition resolution work in both repository and container layouts.
- Reworked Execute Tests around a compact Run History-style structure with aligned configuration controls, explicit filters and sorting, stable checkbox rows, bounded scope summaries, mobile stacking, and non-overlapping table action columns.
- Added visible parallel-worker status to execution confirmation and live progress so users can understand the active throughput limit.
- Standardized generic, Projects, Applications, Audit, project detail, execution diagnostics, and Run History table surfaces around the compact Run History layout with bounded scrolling, stable density, consistent headers, and responsive overflow.
- Aligned Run History identifiers with default table text color while preserving hover and keyboard focus states.
- Updated the AI Generator hero with module-specific test-design content and a direct link into the generation workflow instead of unrelated agent-analysis messaging.
- Removed duplicate Session recording / Browser video and Final evidence / Screenshot and trace sections from View Details; those artifacts now appear once in the canonical execution summary while step evidence remains in the action timeline.
- Reduced shared page-content wrapper whitespace across workspace routes by consolidating duplicate rules, widening the desktop content cap to `1760px`, and preserving compact mobile gutters.
- Removed visible navigation section labels from the desktop sidebar and mobile navigation drawer for a cleaner icon-and-item navigation layout.
- Restored vertical scrolling for bounded test-case tables, loaded test cases page by page during workspace refresh, and stopped the Test case library from hiding persisted cases with matching content.
- Standardized project, application, and test-case table action groups so buttons keep intrinsic widths and do not wrap on desktop or tablet layouts; mobile table actions retain intentional stacking.
- Removed duplicate self-referencing login credential keys from development and production Compose services.
- Simplified Settings Studio model selection to one catalog-backed control and removed the duplicate exact-model text input.
- Removed verbose provider/model copy and replaced exposed credential fragments with a safe configured/not-configured status.
- Aligned shared page-content gutters and responsive card grids across section pages, and removed the legacy visual pulse strip.
- Upgraded the frontend to Next.js `16.3.4`, with the corresponding lockfile update.
- Upgraded FastAPI, Starlette, `python-multipart`, and PyJWT to audited fixed releases.
- Added a frontend `typecheck` script and corrected the Copilot setup workflow to run from `frontend/`.
- Documented the production-oriented Docker Compose baseline and the absence of Kubernetes manifests in this repository.
- Made private-target access opt-in in environment examples and aligned the documented video-capture default with the runtime contract.

### Security

- Production dependency audit is clean after the Next.js/PostCSS upgrade.
- CI now fails on high or critical production npm advisories and Python dependency audit findings.
