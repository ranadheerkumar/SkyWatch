# Tractor Supply QA Automation Platform - Project Architecture

## 1) Scope and intent

This document describes the **current implemented architecture** of the Tractor Supply QA Automation Platform codebase, including:

- frontend shell and state model
- backend API/service boundaries
- execution queue and worker flow
- AI test-generation pipeline
- persistence model
- current implementation gaps and production hardening priorities

> Note: The codebase still uses legacy `ai-qa-engine` naming in several environment keys, localStorage keys, and internal labels. New code should use the canonical vocabulary in the modernization report.

---

## 2) System context (high-level)

The platform provides a QA workspace to:

1. Register web/mobile applications
2. Import/create/generate test cases
3. Convert case text to executable automation steps/checks
4. Queue and run web automation with Playwright
5. Track runs, defects, and readiness metrics
6. Export case progress and execution history

### Architecture overview

```text
Browser (Next.js UI)
   |
   | HTTPS/JSON (JWT bearer token)
   v
FastAPI API (/api/v1/*)
   |
   +--> SQLAlchemy -> SQLite/PostgreSQL (users/apps/cases/runs/defects/audit)
   |
  +--> AI service (explicit configured provider)
   |
   +--> Queue layer
          |- local in-process thread worker (default)
          |- Redis + RQ worker (optional)
                    |
                    v
               Playwright execution runtime
```

---

## 3) Repository architecture

```text
frontend/
  src/app/                   Next.js App Router entry + section shell
  src/components/            reusable UI cards + application capture
  src/lib/api.ts             API client, retry policy, and auth-expiry handling
  src/lib/auth.ts            session-scoped authentication token boundary
  src/types/                 shared frontend domain contracts
  scripts/clean-next.cjs     Windows-safe .next cleanup helper

backend/
  app/main.py                FastAPI bootstrap and initial-admin normalization
  alembic/                   versioned database migrations
  app/api/v1/                REST endpoints
  app/services/              AI, discovery, execution, queue, healing, automation synthesis, secrets
  app/models/                SQLAlchemy entities
  app/schemas/               Pydantic request/response contracts
  app/core/                  database + security primitives
  app/worker.py              Redis RQ worker bootstrap

docs/
  PROJECT_DOCUMENTATION.md   broad product/technical guide
  PROJECT_ARCHITECTURE.md    (this file) architecture-specific view
```

---

## 4) Frontend architecture

### 4.1 UI composition model

- Primary shell is centralized in [`frontend/src/app/page.tsx`](../frontend/src/app/page.tsx).
- Route files such as `src/app/projects/page.tsx`, `src/app/test-cases/page.tsx`, and `src/app/reports/page.tsx` now use explicit section adapters; feature behavior is still composed by the root workspace page.
- Shared authentication and domain contracts are centralized in `src/lib/auth.ts` and `src/types/index.ts`; feature ownership extraction remains in progress.
- Section rendering is selected from a `views` map keyed by section id (`dashboard`, `projects`, `applications`, `cases`, `execution`, `defects`, `suites`, `reports`, `aiGenerator`).

### 4.2 State and navigation model

- Shared in-memory UI state lives inside the single root page component.
- Section route mapping is controlled by `src/components/navigation/navigationConfig.ts` (`sectionPaths` and `pathSections`).
- Selected application context is persisted in localStorage key `ai-qa-engine:selected-app`.
- Mock mode can be enabled via query (`?mock=1`) and persisted in `ai-qa-engine:mock-mode`.

### 4.3 Auth and API interaction

- JWT token is held in memory and session storage under `ai-qa-engine:token`; a legacy local-storage token is migrated once and removed.
- API helper [`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts):
  - injects an `Authorization` bearer header for authenticated requests
  - applies timeout, abort, and safe-read retry policies
  - parses JSON/text responses into typed API errors
  - on `401`, clears token and emits `ai-qa-engine:auth-expired` browser event

### 4.4 Frontend execution + AI workflows

- Test execution UI:
  - queues app-level or case-level runs
  - polls run status
  - renders step timeline, diagnostics, logs, and artifacts
- AI generator UI:
  - captures prompt/settings/optional target URL updates
  - creates `POST /api/v1/ai-generation/jobs?application_id={id}` and polls the owned job
  - presents persisted results and can optionally transition directly to execution flow
- The durable AI job runs Application Discovery before Context Builder, persists the bounded target snapshot, and reuses it for Planner and Generator calls. The worker learns only validated same-action locator repairs and records `auto_applied` recommendations and audit events.

---

## 5) Backend architecture

### 5.1 FastAPI bootstrap

Entry point: [`backend/app/main.py`](../backend/app/main.py)

- mounts `/api/v1` routers
- enables CORS for local frontend origins
- expects schema creation and changes to be applied by Alembic before the API starts
- ensures the configured initial administrator exists and is assigned the `admin` role
- leaves projects, applications, test cases, defects, suites, and runs empty until users create them
- exposes `/health`

The backend Docker image is built from the repository root in Compose so the shared `.github/agents/` definitions are packaged with the runtime. Local source execution and container execution resolve the same definitions through the agent registry.

### 5.2 API surface

Router composition: [`backend/app/api/v1/router.py`](../backend/app/api/v1/router.py)

- `auth.py` - register/login/me/role update
- `applications.py` - web/mobile app CRUD + mobile upload
- `test_cases.py` - list/create/import/export/delete/legacy-generate-ai/automation-readiness
- `ai_generation.py` - durable AI generation job creation and polling
- `execution.py` - queue runs, run by case, status/detail/history/metrics/export
- `defects.py` - defect CRUD subset
- `reports.py` - app and executive metrics summaries
- `mobile.py` - mobile run request bridge
- `audit.py` - audit event query endpoint

### 5.3 Service layer responsibilities

- [`services/test_execution.py`](../backend/app/services/test_execution.py)
  - Playwright orchestration
  - target validation (SSRF guard against private/reserved networks by default)
  - step execution, check execution, screenshot/artifact capture, diagnostics
- [`services/run_queue.py`](../backend/app/services/run_queue.py)
  - queue backend selection (`local` development mode, `redis` production mode)
  - explicit queue failure when Redis mode is unavailable
  - run + case_execution status/log persistence
- [`app/worker.py`](../backend/app/worker.py)
  - standalone RQ worker process for Redis queue mode
- [`services/ai_service.py`](../backend/app/services/ai_service.py)
  - target context capture (HTTP + optional authenticated Playwright snapshot)
  - prompt construction
  - provider-backed generation through one explicit configured provider
  - post-generation quality gate and top-up merge
- [`services/ai_generation_jobs.py`](../backend/app/services/ai_generation_jobs.py)
  - durable AI generation worker and job lifecycle persistence
- [`services/automation_builder.py`](../backend/app/services/automation_builder.py)
  - heuristic conversion of prose steps into structured automation steps/checks
- [`services/automation_quality.py`](../backend/app/services/automation_quality.py)
  - confidence scoring and selector-review hints
- [`services/secrets.py`](../backend/app/services/secrets.py)
  - env/vault secret resolution for credential-backed runs

### 5.4 Data layer

- SQLAlchemy models live in [`backend/app/models/`](../backend/app/models/).
- Local default DB: SQLite (`sqlite:///./ai-qa-engine.db`); production Compose uses PostgreSQL and runs `alembic upgrade head` before the API starts.
- Core persisted entities:
  - users
  - applications
  - test_cases
  - test_case_automations
  - test_runs
  - case_executions
  - defects
  - audit_logs
  - ai_generation_jobs

---

## 6) Key runtime flows

### 6.1 Application onboarding flow

1. Frontend capture form (`ApplicationCapture`) collects web URL or mobile artifact.
2. Backend validates:
   - web target URL + SSRF rules
   - mobile artifact extension + upload size
3. Application row persisted and audit event logged.

### 6.2 AI case generation flow

1. Frontend submits a durable AI job with coverage settings.
2. Backend validates app + target + step constraints and returns `202` with a job ID.
3. The worker captures context and builds the provider prompt.
4. If the provider fails or is unavailable, the generation job fails with an actionable provider error.
5. Validated cases are deduplicated, persisted, and receive automation steps/checks when derivable.
6. Frontend polls the owned job until completion and refreshes the persisted case records.

### 6.3 Execution flow (web)

1. Frontend queues execution request (`/execution/run` or `/execution/test-case/{id}`).
2. Run saved with redacted sensitive typed values.
3. Queue backend enqueues:
   - local in-process worker thread, or
   - Redis/RQ queue
4. Worker runs Playwright step/check pipeline.
5. `test_runs` + `case_executions` status/log/result are updated.
6. Frontend polls and renders terminal result + diagnostics.

---

## 7) Security architecture (current baseline)

- Password hashing: PBKDF2 (`hashlib.pbkdf2_hmac`) in [`core/security.py`](../backend/app/core/security.py)
- Auth: JWT bearer tokens (`HS256`)
- RBAC roles: `viewer`, `tester`, `qa_lead`, `admin`
- Audit logging for key mutating operations
- Secrets for login steps resolved at backend runtime (env or Vault)
- URL validation blocks private/reserved target networks unless explicitly allowed

---

## 8) Current implementation gaps (observed)

These are present in current repository state and should be treated as known gaps:

1. **Production database migration drills remain**
  - Fresh databases use [`backend/alembic/`](../backend/alembic/); local pre-Alembic databases use the guarded [`migration_bootstrap.py`](../backend/app/core/migration_bootstrap.py) after schema verification. PostgreSQL upgrade, backup, and restore drills remain required.
2. **Several repository/service utility modules are placeholders**
   - empty modules exist under `backend/app/repositories/`, plus service placeholders such as `defect_service.py` and `report_service.py`.
3. **Some frontend scaffolding files are placeholders**
  - `frontend/src/hooks/useToast.ts` and `src/lib/validations.ts` are now implemented; `src/lib/utils.ts` and the UI component placeholders still need implementation or removal. Shared types, auth, API policy, navigation, and icon rendering are implemented.
4. **Configuration compatibility aliases remain**
  - The public environment key is `ACCESS_TOKEN_EXPIRE_MINUTES`; internal compatibility aliases and legacy `AI_QA_ENGINE_*` provider keys should be documented and retired over time.
5. **Runtime stability caveat in this environment**
   - Windows + OneDrive pathing has shown intermittent Next.js cache/readlink issues; cleaned startup scripts mitigate but do not fully eliminate environment-specific behavior.

---

## 9) Production hardening priorities

1. Complete migration adoption for existing databases and remove remaining schema-version ambiguity.
2. Harden session lifecycle beyond session storage with revocation and rotation.
3. Productionize Redis worker deployment + queue observability.
4. Add automated test coverage (API/service/UI execution paths).
5. Extract feature route ownership from the root client page.
6. Tighten secrets lifecycle/rotation and environment configuration consistency.
7. Expand execution guardrails (rate limits, quotas, stronger egress policy).

---

## 10) Quick traceability map

- Frontend shell/orchestration: `frontend/src/app/page.tsx`
- Frontend styling: `frontend/src/app/globals.css`
- Frontend API helper: `frontend/src/lib/api.ts`
- Backend bootstrap: `backend/app/main.py`
- API router composition: `backend/app/api/v1/router.py`
- AI generation service: `backend/app/services/ai_service.py`
- Execution runtime: `backend/app/services/test_execution.py`
- Queue adapter: `backend/app/services/run_queue.py`
- Redis worker entry: `backend/app/worker.py`

---

## 11) Architecture evolution blueprint (aligned with master prompt)

The current system should evolve in-place (not be rebuilt) using this guiding model:

1. Preserve validated existing modules (API, queue, and execution)
2. Introduce an explicit deterministic orchestration layer for AI QA workflow control
3. Keep AI as proposal/reasoning only; deterministic services remain source of truth
4. Validate each stage before persisting or promoting outputs to execution-ready state

### Target workflow shape

```text
Discovery
  -> Planning
  -> Test case validation
  -> Automation generation
  -> Automation validation
  -> Execution
  -> Failure classification
  -> Healing proposal
  -> Safe re-validation
  -> Re-execution
  -> Knowledge update
```

This is intentionally an **evolution path** from current architecture, not a destructive rewrite.

---

## 12) Agent architecture and definition layer

The master prompt expects three built-in specialist agents:

- Planner agent (what to test)
- Generator agent (how to automate)
- Healer agent (safe repair path)

### Current repository fact

- `.github/agents/` files are **not present** in the current repo snapshot.

### Recommended implementation shape

- Add source-controlled agent definition files under `.github/agents/`
- Build a lightweight loader/versioning layer so runtime does not re-parse markdown blindly for every request
- Persist agent execution metadata (agent name/version/model/timestamp/snapshot linkage) for traceability

---

## 13) Deterministic validation and safety gates

The architecture should enforce these non-negotiable guardrails:

1. **No false passes**: do not weaken/skip assertions to force green runs.
2. **AI output is not trusted by default**: validate before accept/persist/run.
3. **Failure-first healing**: classify failure category before repair proposal.
4. **Safe repair lifecycle**: propose -> validate -> dry run -> re-execute -> confirm.

### Pipeline-level checkpoints

- Test case generation: schema + evidence + duplicate validation
- Automation generation: locator resolution + syntax + Playwright dry-run validation
- Healing: only for appropriate automation-related failure categories (not product-defect masking)

---

## 14) Frontend and API evolution direction

### Frontend

Current implementation is a centralized shell in `frontend/src/app/page.tsx` with section routing and shared state.
Near-term architecture should:

- incrementally decompose by feature/domain (without breaking existing URLs)
- reduce root-component state concentration over time
- keep route semantics aligned with major product sections
- keep UX transparency around real workflow stage state (avoid fake progress)

### API

Current API is functional and typed (`FastAPI + Pydantic + TypeScript client types` pattern).
Evolution should add workflow-oriented endpoints gradually (discover/plan/validate/generate/heal) while preserving existing contracts until consumers are migrated.

---

## 15) Prioritized implementation roadmap

This roadmap is adapted from the master prompt and mapped to practical incremental delivery:

1. Audit existing behavior and contracts
2. Stabilize current functionality and close known gaps
3. Add deterministic AI QA orchestrator
4. Integrate planner/generator/healer agent workflows
5. Expand real browser discovery + application knowledge persistence
6. Add structured validation engines (test + automation)
7. Add failure classification and safe healing lifecycle
8. Continue frontend decomposition and UX transparency improvements
9. Production hardening (migrations, PostgreSQL, Redis workers, artifact security, observability)
10. Full real-workflow regression of end-to-end platform behavior

---

## 16) Controlled naming migration strategy (legacy `ai-qa-engine`)

The repo currently uses `ai-qa-engine` keys in:

- localStorage keys (`ai-qa-engine:*`)
- environment variables (`AI_QA_ENGINE_*`)
- file/database naming

Recommended migration approach:

1. Introduce new Tractor-Supply-prefixed aliases for new integrations
2. Continue reading legacy keys for backward compatibility
3. Emit clear deprecation notes in docs/release notes
4. Remove legacy keys only after verified cutover

Avoid global rename/big-bang migration.

---

## 17) Development vs production architecture profile

### Development-optimized baseline (current-friendly)

- SQLite
- local queue worker (or optional Redis)
- local browser runtime
- mock mode for demos

### Production target baseline

- PostgreSQL with formal migrations (Alembic)
- Redis-backed queue with dedicated workers
- secure artifact storage + retention controls
- structured observability and alerting
- rate limiting, execution quotas, and stronger egress control

Development shortcuts must not silently become production defaults.

---

## 18) Final master prompt alignment (August 2026 update)

This architecture also incorporates the user-provided **FINAL MASTER IMPLEMENTATION + AI QA + UI/UX REDESIGN PROMPT** as strategic guidance.
It is treated as an evolution blueprint for the current codebase, not as a destructive rewrite directive.

### Governing principle model

- AI = reasoning/proposal
- Playwright/discovery/evidence = runtime facts
- validators = source of truth
- orchestrator = workflow control
- database/queue = persistence and scalability
- UI = human oversight and control

---

## 19) Canonical end-to-end workflow contract

```text
URL input
  -> SSRF + target validation
  -> discovery (browser-first)
  -> versioned application snapshot
  -> planner agent
  -> scenario validation + dedupe
  -> generator agent
  -> automation validation + dry run
  -> execution + evidence capture
  -> failure classification
  -> healer proposal (eligible failures only)
  -> repair validation + re-execution
  -> result persistence (defects/reports)
```

Rules:

1. Do not invent unsupported application functionality.
2. Do not run unvalidated AI output.
3. Preserve reproducibility by linking generated outputs to snapshot + agent version metadata.

---

## 20) UI/UX architecture contract (cross-page consistency)

- Major product flow should be visibly connected across: Applications -> Discovery -> AI Generator -> Test Cases -> Automation -> Execution -> Results -> Defects -> Reports.
- Every page should answer: where am I, what context is loaded, what can I do next.
- Required states per major surface: loading, empty, error, success.
- Large datasets should use container-level scrolling/pagination/filtering with no page-breaking overflow.
- Metrics and progress indicators must be data-backed; no fabricated confidence, coverage, or success states.
- Accessibility and responsive behavior are baseline requirements (keyboard navigation, focus states, reduced motion, semantic structure).

---

## 21) Expanded deterministic validation and healing contract

### Planning and case validation

- Validate schema completeness, evidence grounding, workflow consistency, and duplicates.
- Scenario states should include: `VALID`, `NEEDS_REVIEW`, `INVALID`, `DUPLICATE`.

### Automation validation pipeline

```text
Generated automation
  -> schema validation
  -> locator validation
  -> Playwright syntax validation
  -> browser dry run
  -> executable
```

### Failure classification taxonomy

- `LOCATOR`, `TIMING`, `NAVIGATION`, `AUTHENTICATION`, `TEST_DATA`, `ENVIRONMENT`, `NETWORK`, `ASSERTION`, `APPLICATION_DEFECT`, `AUTOMATION_DEFECT`, `UNKNOWN`.

### Safe healing lifecycle

```text
Failure -> evidence -> classification -> repair proposal -> deterministic validation -> dry run -> re-execution -> confirmed repair | needs review
```

A healing flow must never hide a real product defect or convert failures into artificial passes.

---

## 22) Detailed phase sequence (implementation control)

In addition to the prioritized roadmap in section 15, use this finer-grained sequence:

0. Repository audit and contract baseline
1. Foundation stabilization
2. Database migration foundation (Alembic)
3. Application discovery hardening
4. Agent runtime foundation (definitions + versions)
5. AI orchestrator integration
6. Planner + scenario validation
7. Generator + automation validation
8. Execution hardening
9. Failure intelligence/classification
10. Healer + safe re-execution
11. Frontend architecture decomposition
12. Full UI/UX redesign standardization
13. Security/performance/observability hardening
14. Production Docker/PostgreSQL/Redis hardening
15. Complete regression and acceptance verification

Do not advance phases while blocking defects in the current phase remain unresolved.

---

## 23) Definition-of-done checklist (architecture-level)

Work should not be considered complete until:

- AI: planner/generator/healer integration with version traceability and quality gates
- Discovery: real URL validation, controlled browser discovery, versioned snapshots
- Automation: structured generation, locator intelligence, validation, and dry run
- Execution: queue/worker reliability, evidence artifacts, accurate status/results
- Healing: classified failures, safe repair flow, explicit needs-review path
- UI: connected navigation context, clear CTAs, accessible and responsive enterprise design
- Platform: migrations, production queue, security controls, observability, containerized deployment
- Verification: backend/frontend/platform tests and real-flow checks passing without fake success signals

---

## 24) Verification reporting standard

Architecture delivery updates must distinguish:

- Tested
- Not tested
- Reason
- Remaining risk/actions

No implementation should be marked successful unless the relevant behavior has been verified in runtime tests or clearly documented as unverified due to environment constraints.
