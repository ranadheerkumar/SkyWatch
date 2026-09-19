# Testing Strategy

The goal of testing is to keep the application, API contracts, execution workers, AI workflow, evidence controls, and release packaging trustworthy as the platform grows.

## Current Baseline

- Backend API contract tests live in `backend/tests/test_api_contracts.py`.
- Backend syntax is checked with `python -m compileall -q backend/app`.
- Frontend type checking and production build run from `frontend/`.
- The repository contains a Playwright seed template, but a complete frontend browser regression suite is still planned.
- The local process worker is useful for development; production queue behavior must be tested with Redis/RQ.

## Test Pyramid

### Unit tests

Cover pure parsing, validation, selectors, status mapping, redaction, retry policy, bounded concurrency, report calculations, and domain services. Unit tests should not require a browser, network target, AI provider, or shared database.

### API and integration tests

Cover authentication, role checks, project and application CRUD, test-case lifecycle, AI job states, queue transitions, execution persistence, artifact authorization, pagination, and migrations. Use isolated databases and deterministic provider/worker fakes.

### Browser tests

Cover login, navigation, application onboarding, proposal review, case approval, execution controls, run details, evidence access, and responsive layouts. Browser tests should use an owned local fixture target and avoid real third-party applications.

### Operational tests

Cover Redis unavailable behavior, worker restart and pool sizing, duplicate idempotency keys, cancellation, timeouts, retry limits, parallel execution resource limits, artifact retention, PostgreSQL upgrade/restore, container health, and resource limits.

## Local Validation

From the repository root, use the canonical targets when `make` is available:

```powershell
make ci
```

Equivalent commands on Windows without `make`:

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
npm audit --omit=dev --audit-level=high

cd ..\backend
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m pytest -q tests
pip-audit -r requirements.txt
```

The frontend build cleans generated Next.js output before compiling. Run one development or production Next.js process at a time on Windows to avoid file-lock and stale chunk issues.

## CI Gates

`.github/workflows/ci.yml` runs on push and pull request and currently enforces:

1. frontend dependency installation;
2. frontend type checking;
3. frontend production build;
4. npm production dependency audit;
5. backend dependency installation;
6. backend compile smoke;
7. Alembic upgrade and metadata consistency check against temporary SQLite;
8. backend tests;
9. Python dependency audit.

Future gates should add migration upgrade/downgrade tests, integration tests, Playwright browser smoke, secret/SAST scanning, container scanning, documentation link validation, and generated-file checks.

## Test Data and Secrets

Use synthetic accounts and owned fixture applications. Never place real credentials, tokens, private URLs, or customer data in fixtures, screenshots, traces, snapshots, test output, or CI logs. Redact failure output before attaching it to an issue.

## Release Policy

A release requires passing type, build, backend, security, and migration gates. A known high or critical finding requires remediation or an explicit documented risk acceptance with an owner and expiry date. New user-visible workflows require a browser or API regression test; exceptions must be recorded in the pull request and this strategy.

## Source-Control Gate

Every build-affecting change must include a `docs/Changelog.md` update and must be committed after the applicable validation gates pass. A successful local build that remains uncommitted is not a completed handoff. Use [CONTRIBUTING.md](CONTRIBUTING.md) for staging, secret exclusion, and automatic source-change publishing rules.
