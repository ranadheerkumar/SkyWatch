# AI QA Engine QA backend

This service provides authenticated application management and queued web execution powered by Playwright Chromium. It also exposes Appium adapters for Android and iOS providers.

## Authenticate

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"qa@example.com","password":"correct-horse-battery-staple"}'
```

Use the returned `access_token` as `Authorization: Bearer <token>`.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -m alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alembic is the database schema authority. Run `python -m alembic upgrade head` from `backend` before starting a fresh local database or deploying a new version. Existing databases created before the migration baseline must be inspected and backed up before they are stamped; do not run the baseline upgrade against a database that already contains the tables.

On startup, `app.main` ensures that only the configured initial administrator exists or is normalized to the `admin` role. No project, application, test case, defect, suite, or execution data is seeded; create those records through the authenticated API or frontend.

## Read-only Jira and qTest configuration

Set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and either `JIRA_PROJECT_KEY` or numeric `JIRA_FILTER_ID` for Jira. Set `QTEST_BASE_URL`, `QTEST_TOKEN`, and either `QTEST_PROJECT_ID` or `QTEST_PROJECT_NAME` for qTest. These values are read from `backend/.env`; tokens are never returned in API responses. Keep `AI_QA_ENGINE_INTEGRATIONS_READ_ONLY=true`, `ENABLE_JIRA_WRITE=false`, and `ENABLE_QTEST_WRITE=false`.

`GET /api/v1/integrations/environment` returns sanitized configuration status. An authenticated tester, QA lead, or admin can use `PUT /api/v1/integrations/environment` to update the local `backend/.env` values; token fields are write-only. External search, connection tests, and asset reads use GET/HEAD only. External mutation methods return HTTP 405; local connection/profile environment CRUD does not modify Jira or qTest.

## Execute a web smoke run

```bash
curl -X POST http://127.0.0.1:8000/api/v1/execution/run \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer <token>' \
  -d '{
    "url": "https://your-app.example.com/",
    "checks": [
      {"type": "title_contains", "value": "Your Application"},
      {"type": "visible", "value": "body"}
    ],
    "capture_screenshot": true
  }'
```

Supported checks are `title_contains`, `visible` (CSS selector), and `text_contains`.
The response returns `202` with a `run_id`. Poll `GET /api/v1/execution/{run_id}` until the status is `passed`, `failed`, or `error`. Steps support `click`, `type`, `select`, `navigate`, `assert_visible`, `assert_text`, `assert_title`, and `assert_url_contains`. Use `secret_name` for sensitive values so the server reads them from environment variables.

Execution behavior controls:

- `execution_mode`: `watch_live` (visible browser) or `background` (headless).
- `slow_mode`: `normal` or `demo` (slower visible actions for walkthroughs).
- `trace_mode`: `off`, `on_failure`, or `always`.
- `keep_browser_open_seconds`: keep the browser open briefly after execution for inspection.
- `keep_browser_open_on_failure`: keep browser visible after failures during the hold window.

`GET /api/v1/execution/{run_id}` includes `live_state` and `current_action` fields sourced from real Playwright execution events.

## Secret providers

- `AI_QA_ENGINE_SECRET_PROVIDER=env` (default) reads from environment variables.
- `AI_QA_ENGINE_SECRET_PROVIDER=vault` reads from Vault HTTP API using:
  - `AI_QA_ENGINE_VAULT_ADDR`
  - `AI_QA_ENGINE_VAULT_TOKEN`
  - `AI_QA_ENGINE_VAULT_PATH` (default: `secret/data/ai-qa-engine`)

## RBAC and audit

- Roles: `viewer`, `tester`, `qa_lead`, `admin`.
- `GET /api/v1/auth/me` returns the current user profile and role.
- `PUT /api/v1/auth/users/{user_id}/role` updates role (admin only).
- `GET /api/v1/audit` returns audit history (`qa_lead` and `admin`).

## Reporting endpoints

- `GET /api/v1/reports/application/{application_id}/overview` returns pass/fail trend + quality summary.
- `GET /api/v1/reports/executive/overview` returns cross-application executive snapshot.
- `GET /api/v1/execution/metrics/summary` returns run status and duration metrics.

## Evidence access

Evidence file URLs are scoped to the owning run, for example `/api/v1/evidence/file/<filename>?run_id=<run_id>`. The API verifies that the authenticated user owns the run and that the filename is recorded in its result before serving the artifact.

## Queue backends

Execution queue backend is selected by environment variable:

- `AI_QA_ENGINE_QUEUE_BACKEND=local` (default) uses in-process thread worker.
- `AI_QA_ENGINE_QUEUE_BACKEND=redis` uses Redis + RQ for external workers.

Redis mode settings:

- `AI_QA_ENGINE_REDIS_URL=redis://127.0.0.1:6379/0`
- `AI_QA_ENGINE_QUEUE_NAME=ai-qa-engine-runs` (optional)

Start the Redis worker:

```bash
python -m app.worker
```

## AI test case generation

Configure these environment variables before creating a durable job with `POST /api/v1/ai-generation/jobs?application_id=<id>`:

- `AI_QA_ENGINE_AI_PROVIDER=github_copilot` (select one explicit provider: `github_copilot`, `openai`, `azure_openai`, `anthropic`, `gemini`, or `local`)
- `AI_QA_ENGINE_AI_OPENAI_API_KEY=<provider-key>` (required when `openai` is selected)
- `AI_QA_ENGINE_AI_OPENAI_MODEL=gpt-4.1` (optional)
- `AI_QA_ENGINE_AI_OPENAI_BASE_URL=https://api.openai.com/v1` (optional)
- `AI_QA_ENGINE_AI_TIMEOUT_SECONDS=45` (optional)
- Login credentials are supplied as sensitive `login_email` and `login_password` runtime parameters in the UI; target-specific selectors are configured there as well.

Provider strategy:

- Select exactly one provider for each environment.
- Provider failures are surfaced as actionable errors; no alternate provider or generated substitute is selected automatically.
- `local` is reserved for an explicitly configured OpenAI-compatible inference endpoint.

Legacy generic variables (`AI_QA_ENGINE_AI_API_KEY`, `AI_QA_ENGINE_AI_MODEL`, `AI_QA_ENGINE_AI_BASE_URL`) remain accepted for explicit provider modes.

Then run the backend and create a job. Poll `GET /api/v1/ai-generation/jobs/{job_id}` until its status is `completed` or `failed`. The completed result includes the persisted case IDs and generation metadata. The synchronous `POST /api/v1/test-cases/{application_id}/generate-ai` endpoint remains available for compatibility.
When `include_authenticated_snapshot=true` (default), the backend logs in with configured secrets, captures post-login UI context, and samples a few same-origin authenticated routes to improve case relevance for dashboard/menu-driven apps. The generator also captures rendered DOM context (Playwright) when static HTML has low signal, then blends that with existing uploaded case patterns for more application-specific output.

The endpoint accepts JSON:

```json
{
  "prompt": "Generate end-to-end coverage for login and clinic discovery",
  "max_cases": 12,
  "replace_existing_drafts": true,
  "include_authenticated_snapshot": true,
  "login_email_selector": "#user_email",
  "login_password_selector": "#user_password",
  "login_submit_selector": "input[type=submit]"
}
```

Responses are validated against a strict structured schema before persistence.
Response headers expose generation source diagnostics:

- `X-AI-QA-Engine-AI-Generation-Mode` (`provider`)
- `X-AI-QA-Engine-AI-Provider`
- `X-AI-QA-Engine-AI-Provider-Configured`
- `X-AI-QA-Engine-AI-Generation-Note`

Use `GET /api/v1/test-cases/application/{application_id}/automation-readiness` to retrieve automation confidence score and manual selector review recommendations per case.

## Important limitations

- The worker is process-local; use Redis/Celery for durable production queueing.
- Token rotation and account recovery remain future enhancements.
- Mobile execution needs an Appium provider URL and an actual device/emulator.
- Screenshot files are written to `/tmp/ai-qa-engine-runs` and need production artifact storage.
- Before exposing this API, add SSRF protection, rate limits, network egress controls, and per-run resource limits.
