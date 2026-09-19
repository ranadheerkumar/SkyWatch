# AI QA Engine - Complete Project Documentation

## 1) Project objective

This platform provides a single QA workspace to:

- onboard applications (Web, Android, iOS metadata/artifacts),
- generate or import test cases,
- execute web automation runs,
- track run outcomes and defects,
- and accelerate coverage with AI-assisted test design.

The main goal is to reduce manual QA effort while keeping flows understandable for non-AI and AI-assisted teams.

---

## 2) End-to-end architecture

### High-level flow

1. User signs in to frontend.
2. Frontend calls backend APIs for applications/test cases/execution.
3. Backend stores data in SQL database (SQLite default; PostgreSQL-compatible design).
4. AI generation is processed by one explicitly configured provider; provider failures are returned as actionable errors.
5. Web execution requests are queued:
   - local in-process worker (default), or
   - Redis/RQ queue worker (scalable mode).
6. Playwright runs browser actions/checks and returns result/logs/artifacts.
7. Frontend displays execution progress, reports, and defects.

### Major code surfaces

- Frontend shell and page orchestration: `frontend/src/app/page.tsx`
- API routes: `backend/app/api/v1/`
- AI generation service: `backend/app/services/ai_service.py`
- Execution engine: `backend/app/services/test_execution.py`
- Queue adapter: `backend/app/services/run_queue.py`
- Worker entrypoint (Redis mode): `backend/app/worker.py`
- DB/session core: `backend/app/core/database.py`
- Security/auth core: `backend/app/core/security.py`

---

## 3) Technology stack and why each technology is used

## 3.1 Frontend

### Next.js 14 (App Router)
- **Used for:** modern React web app, route-based UI, production build tooling.
- **Why chosen:** strong ecosystem, simple developer workflow, reliable production bundling, easy hosting options.
- **Project benefit:** fast UI iteration for dashboards/workflows and stable production builds.

### React 18
- **Used for:** interactive component/state-driven UI.
- **Why chosen:** mature standard for enterprise UI and large talent pool.
- **Project benefit:** maintainable and extensible QA workspace interactions.

### TypeScript 5
- **Used for:** typed frontend code and safer API interaction.
- **Why chosen:** catches integration errors early and improves refactor safety.
- **Project benefit:** fewer UI/runtime bugs, easier long-term maintenance.

### CSS (global + responsive layout)
- **Used for:** responsive behavior across mobile/desktop and demo-ready visuals.
- **Why chosen:** minimal dependency surface, easy to control exact layout behavior.
- **Project benefit:** predictable UI for presentation and operations.

## 3.2 Backend/API

### FastAPI
- **Used for:** REST API layer, request/response validation integration.
- **Why chosen:** high developer productivity, async support, clean OpenAPI behavior.
- **Project benefit:** quick delivery of robust API endpoints for QA workflows.

### Pydantic v2
- **Used for:** request/response schema validation and data normalization.
- **Why chosen:** strict typing + high performance + clear validation errors.
- **Project benefit:** stable contracts between frontend and backend.

### SQLAlchemy 2
- **Used for:** ORM/database access, model mapping, session lifecycle.
- **Why chosen:** production-proven ORM and DB portability.
- **Project benefit:** can start with SQLite and scale to PostgreSQL with minimal domain-model changes.

### Uvicorn
- **Used for:** ASGI server for FastAPI.
- **Why chosen:** standard, lightweight, performant runtime.
- **Project benefit:** reliable local/dev execution and production compatibility.

## 3.3 Database and persistence

### SQLite (default)
- **Used for:** local persistence during development/demo.
- **Why chosen:** zero-config startup, easy project sharing via zip.
- **Project benefit:** developers can run quickly without infrastructure setup.

### PostgreSQL-compatible approach
- **Used for:** production direction (via SQLAlchemy models and settings).
- **Why chosen:** enterprise-grade concurrency, reliability, ecosystem.
- **Project benefit:** smooth path from prototype to production DB.

## 3.4 Test execution and automation runtime

### Playwright
- **Used for:** browser launch, navigation, UI actions/checks, screenshots.
- **Why chosen:** robust modern browser automation with strong async Python support.
- **Project benefit:** deterministic web run execution and artifact capture.

### Internal automation synthesis logic
- **Used for:** converting generated/manual test text into executable scaffolds where possible.
- **Why chosen:** reduces setup friction and speeds execution readiness.
- **Project benefit:** faster “generate -> run” cycle.

## 3.5 Queueing and background processing

### Local in-process queue (thread + asyncio)
- **Used for:** default run queue in simple deployments.
- **Why chosen:** no external dependency required.
- **Project benefit:** one-command local development and demos.

### Redis + RQ (optional scalable mode)
- **Used for:** external queue and worker separation.
- **Why chosen:** simple, proven Python queue pattern for background jobs.
- **Project benefit:** horizontal scalability and improved durability compared to in-process queue.

## 3.6 Security and authentication

### JWT (PyJWT, HS256)
- **Used for:** stateless API authentication.
- **Why chosen:** standard pattern for SPA + API architecture.
- **Project benefit:** clean separation between frontend session state and backend authorization.

### PBKDF2 password hashing (`hashlib.pbkdf2_hmac`)
- **Used for:** secure password storage.
- **Why chosen:** strong built-in algorithm with salting and iteration control.
- **Project benefit:** avoids plaintext passwords and improves baseline credential security.

### Environment-driven secrets
- **Used for:** login credentials and provider configuration.
- **Why chosen:** keeps sensitive data out of source code and frontend payloads.
- **Project benefit:** safer operations and easier environment-based deployments.

## 3.7 AI generation layer

### Explicit provider-backed generation
- **Used for:** structured, application-aware test-case generation through the selected provider.
- **Why chosen:** provider provenance and failures remain visible and auditable.
- **Project benefit:** no silent provider switching or fabricated replacement cases.

---

## 4) Functional modules (what each page does)

- **Overview:** top-level project/application and summary visibility.
- **Applications:** create/manage Web/Android/iOS targets.
- **Test Cases:** author/import/edit/export test cases.
- **AI Generator:** prompt-driven, option-driven test case generation.
- **Test Execution:** run queued automation and track progress.
- **Defects:** issue tracking and QA defect lifecycle.
- **Reports:** pass/fail trends, execution summary, quality signals.
- **Test Suites:** grouped readiness and execution perspective.
- **AI visual analytics:** preview-level KPI cards and progress bars for action density, step depth, and automation confidence.
- **Execution step timeline:** per-step visual status cards, duration bars, and completion progress for demo-friendly playback diagnostics.

---

## 5) AI generation design (current)

1. Frontend creates `POST /api/v1/ai-generation/jobs?application_id={id}`.
2. Backend validates application + target and persists a durable job.
3. The worker collects context:
   - user prompt/options,
   - target page snapshot (title/headings/buttons/links/inputs when reachable),
   - authenticated dropdown hierarchy and route paths (`Parent > Child (/route)` when available),
   - recent existing test-case snippets as reference style.
4. Service calls the explicitly configured provider.
5. If the provider fails or is unavailable, the job fails with an actionable error and no replacement cases are fabricated.
6. Quality gate normalizes:
   - TC numbering,
   - min/max steps,
   - required fields and output shape.
7. Backend deduplicates, compiles automation, and persists cases plus job metadata.
8. Frontend polls the owned job and surfaces visual quality analytics (action density, step depth, automation confidence) to guide review before execution.

The synchronous `POST /api/v1/test-cases/{application_id}/generate-ai` endpoint remains available as a compatibility path for existing API consumers; new UI workflows use durable jobs.

Why this design:
- balances quality and traceability through an explicit provider path,
- keeps output stable for automation pipelines,
- and uses project-specific context to reduce generic test content.

---

## 6) Execution pipeline design

1. User starts run from Test Execution.
2. Backend stores run record (`queued`).
3. Queue router chooses backend:
   - local worker thread, or
   - Redis queue job.
4. Worker marks run `running`.
5. Playwright executes navigation/actions/assertions/checks.
6. Worker stores:
   - final status (`passed`/`failed`/`error`),
   - structured result payload,
   - logs,
   - optional screenshot artifact path.
7. Frontend polls run endpoint and updates status UI.

Why this design:
- async queue prevents API blocking,
- logs and artifacts support triage,
- queue backend switch supports both demo simplicity and scaling path.

---

## 7) Data model summary

Primary entities:
- `users`
- `applications`
- `test_cases`
- `test_case_automations`
- `test_runs`
- `case_executions`
- `defects`
- `audit_logs`

Why this model:
- separates test definition from run history,
- supports many runs per case/application,
- enables reporting and auditability.

---

## 8) Security model (current baseline)

- JWT access tokens for protected API routes.
- Role checks (`viewer`, `tester`, `qa_lead`, `admin`) at endpoint layer.
- Password hashing with PBKDF2 + per-user salt.
- Sensitive login values resolved from backend environment/secrets, not frontend.
- URL safety checks reject unsupported/non-public targets unless explicitly allowed.
- Sensitive step text redaction for seeded/default credentials.

---

## 9) Scalability and maintainability assessment

## What already supports scale
- Modular backend (API/services/core/models split).
- Optional Redis worker mode for distributed processing.
- DB portability through SQLAlchemy.
- Typed contracts (TypeScript + Pydantic) for safer refactoring.
- Scripted startup/stop flow for consistent local onboarding.

## What should be done for production scale
- Move fully to PostgreSQL + migrations workflow.
- Run multiple workers with monitoring/alerts.
- External artifact storage (not temp-dir only).
- stronger network egress policies and rate limits.
- deeper automated test coverage in CI.

Conclusion: architecture is scalable with planned operational hardening, and codebase is maintainable by standard engineering teams without AI dependency.

---

## 10) Explicit provider strategy

- Configure one provider per environment with `AI_QA_ENGINE_AI_PROVIDER`.
- Supported values are `github_copilot`, `openai`, `azure_openai`, `anthropic`, `gemini`, and `local`.
- Provider credentials and endpoint failures are surfaced to the user and audit trail.
- The platform does not silently switch providers or generate substitute cases.

---

## 11) Environment and operations quick reference

Common local commands:

```powershell
.\scripts\start-local.ps1
.\scripts\stop-local.ps1
```

Core docs:
- User operations: `docs/USER_GUIDE.md`
- Developer setup/run/debug: `docs/DEVELOPER_GUIDE.md`
- Team handover checklist: `docs/HANDOVER_CHECKLIST.md`

---

## 12) Why this stack is a good fit for your project

This project needs rapid feature iteration, UI-heavy workflows, reliable browser automation, and optional AI assistance without locking into paid providers.  
The selected stack (Next.js + FastAPI + SQLAlchemy + Playwright + explicit provider-backed AI + Redis/RQ option) matches those needs by giving:

- fast developer productivity,
- clean separation of concerns,
- reliable execution foundation,
- practical scaling path,
- and open-source-first AI capability.
