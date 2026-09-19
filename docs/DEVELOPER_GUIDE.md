# AI QA Engine - Developer Guide

## 1. Prerequisites

- Windows 10/11
- Node.js 20.9+ and npm 9+
- Python 3.11+
- Playwright Chromium

## 2. Local setup

From repo root:

```powershell
cd "C:\path\to\ai-qa-automation-platform"
```

Frontend:

```powershell
cd frontend
npm install
cd ..
```

Backend:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
cd ..
```

## 3. Run services

One-command local startup:

```powershell
.\scripts\start-local.ps1
```

One-command stop:

```powershell
.\scripts\stop-local.ps1
```

`start-local.ps1` starts both the FastAPI backend and Next.js frontend services.
Use `-DisableAutoSync` for direct local development without background branch syncing. The standard stop script (`.\scripts\stop-local.ps1`) cleanly stops both services.

### Execution Control & Concurrency

Execute Tests supports immediate user-initiated stopping/cancellation of active test runs or full batches via `POST /api/v1/execution/{run_id}/cancel` and `POST /api/v1/execution/batch/{batch_id}/cancel`.

The run configuration defaults to 1 worker (sequential execution) for deterministic stability and allows up to five parallel workers. Each case uses its own queued run and isolated browser context.

The local queue starts one worker thread per queued run. Redis/RQ deployments need multiple worker processes consuming the same queue to realize parallel throughput; size that worker pool and browser resource limits for the environment. Background mode is preferred for larger parallel batches because Watch live opens a visible browser for each active run.

Backend terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend terminal:

```powershell
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Health checks:

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -I http://127.0.0.1:3000
```

## 4. Environment variables

Backend AI generation:

- `AI_QA_ENGINE_AI_PROVIDER=github_copilot` (select one explicit provider: `github_copilot`, `openai`, `azure_openai`, `anthropic`, `gemini`, or `local`)
- `AI_QA_ENGINE_AI_OPENAI_API_KEY=<key>` (required when provider is `openai`)
- `AI_QA_ENGINE_AI_OPENAI_MODEL=gpt-4.1` (optional)
- `AI_QA_ENGINE_AI_OPENAI_BASE_URL=https://api.openai.com/v1` (optional)
- `AI_QA_ENGINE_AI_TIMEOUT_SECONDS=45` (optional)

Provider failures are surfaced to the caller. The generation service does not switch providers or fabricate replacement cases.

Execution login parameters:

- Supply `login_email` and `login_password` as sensitive runtime parameters in the UI.
- Configure target-specific login selectors in the execution or AI Generator UI.
- `AI_QA_ENGINE_SECRET_PROVIDER=env` (`env` or `vault`)
- `AI_QA_ENGINE_VAULT_ADDR` (required for `vault`)
- `AI_QA_ENGINE_VAULT_TOKEN` (required for `vault`)
- `AI_QA_ENGINE_VAULT_PATH=secret/data/ai-qa-engine` (optional for `vault`)

Execution timing:

- `AI_QA_ENGINE_STEP_SETTLE_MS=1200` (default delay between steps)
- `AI_QA_ENGINE_QUEUE_BACKEND=local` (`local` or `redis`)
- `AI_QA_ENGINE_QUEUE_NAME=ai-qa-engine-runs` (optional)
- `AI_QA_ENGINE_REDIS_URL=redis://127.0.0.1:6379/0` (required when queue backend is `redis`)

Execution video audio:

- `capture_audio=true` embeds redacted step narration in captured WebM videos.
- `voice_gender=male` or `voice_gender=female` selects the available system TTS voice.
- `pyttsx3` and `imageio-ffmpeg` are installed from `backend/requirements.txt`; the Docker image also installs `espeak-ng` for Linux TTS.
- Set `AI_QA_ENGINE_FFMPEG_PATH` when a custom FFmpeg executable must be used.
- The execution result reports `audio_status`: `embedded`, `unavailable`, or `disabled`.

## 5. Core code map

- Frontend app workflow: `frontend/src/app/page.tsx`
- Frontend styling: `frontend/src/app/globals.css`
- Frontend API helper: `frontend/src/lib/api.ts`
- Test-case API: `backend/app/api/v1/test_cases.py`
- Execution API: `backend/app/api/v1/execution.py`
- AI service: `backend/app/services/ai_service.py`
- Automation synthesis: `backend/app/services/automation_builder.py`
- Playwright runtime: `backend/app/services/test_execution.py`

## 6. AI generation flow (developer view)

1. Frontend creates `POST /api/v1/ai-generation/jobs?application_id={id}` and polls the owned job.
2. Backend validates request + target URL and persists a durable job.
3. The AI worker:
   - tries provider-backed structured generation
   - falls back to deterministic rule-based generation on provider issues
   - applies quality gate normalization
4. Generated test cases are persisted with duplicate safeguards and job metadata.
5. Automation/check scaffolding is auto-attached for generated cases when derivable.
6. Frontend optionally triggers immediate execution for generated web cases after the job completes.
7. Readiness endpoint (`GET /api/v1/test-cases/application/{application_id}/automation-readiness`) provides confidence scoring and manual-review recommendations.

## 7A. RBAC + audit baseline

- Roles: `viewer`, `tester`, `qa_lead`, `admin`
- New auth endpoints:
  - `GET /api/v1/auth/me`
  - `PUT /api/v1/auth/users/{user_id}/role` (admin only)
- New audit endpoint:
  - `GET /api/v1/audit` (`qa_lead`/`admin`)
- Sensitive mutations (create/update/delete/generate/run) now record audit events in `audit_logs`.

## 7. Execution flow (developer view)

1. Frontend queues case runs through `POST /api/v1/execution/test-case/{id}`.
2. Backend loads saved automation (or derives fallback automation if missing).
3. Run is queued and executed by Playwright worker.
4. Frontend polls `GET /api/v1/execution/{run_id}` until terminal status.
5. The worker finalizes the video with redacted narration audio when enabled and the media toolchain is available.
6. Results/logs/artifacts are rendered and persisted; run details show the video before the step timeline.

## 8. Validation commands

From the repository root, the canonical CI sequence is:

```powershell
make ci
```

On Windows environments without `make`, run the equivalent commands below.

Frontend build:

```powershell
cd frontend
npm run typecheck
npm run build
npm audit --omit=dev --audit-level=high
```

Backend compile smoke:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall -q app
```

Database migrations:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

For an existing pre-Alembic SQLite database, take a backup and verify its schema before using `alembic stamp 20260901_ai_jobs`; stamping records the version and does not apply missing changes.

Backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests
```

Redis worker startup (only when `AI_QA_ENGINE_QUEUE_BACKEND=redis`):

```powershell
cd backend
$env:AI_QA_ENGINE_QUEUE_BACKEND="redis"
$env:AI_QA_ENGINE_REDIS_URL="redis://127.0.0.1:6379/0"
.\.venv\Scripts\python.exe -m app.worker
```

CI gate:

- `.github/workflows/ci.yml` runs frontend type checking, unit tests, production build, npm audit, backend compile, migration validation, backend tests, and pip-audit on push/PR.
- CI applies the complete Alembic chain to a temporary SQLite database and runs `alembic check` before backend tests.

## 9. Troubleshooting

- **Next.js EINVAL readlink on Windows:** stop dev server, delete `frontend\.next`, rerun build.
- **401 from API:** token expired; sign in again.
- **No generated AI provider output:** verify the selected explicit provider, credentials, endpoint, and model in `AI_QA_ENGINE_AI_*` values.
- **Run opens/closes quickly:** confirm `AI_QA_ENGINE_STEP_SETTLE_MS` and case steps/checks.
- **Protected login fails:** verify selector values and login env vars.
- **Run stuck in queued (redis mode):** verify Redis is reachable and `app.worker` is running.

## 10. Safe extension guidelines

- Keep API contracts backward-compatible unless UI/backend are updated together.
- Do not log plaintext credentials.
- Prefer reusable helpers for automation synthesis logic.
- Validate behavior with targeted build/compile checks after each change.

## 11. Change, Changelog, and Commit Policy

Every build-affecting change must update the relevant documentation and the canonical [Changelog.md](Changelog.md) before it is committed. After validation, review `git status` and `git diff --stat`, stage only intended source/docs/test/configuration files, create a commit, and push frontend/UI or application source-code changes to the current branch's configured upstream. Never stage `.env` files, credentials, tokens, generated databases, logs, screenshots, videos, traces, or build output. Keep documentation-only changes local unless publication is requested. See [CONTRIBUTING.md](CONTRIBUTING.md) and the workspace [copilot-instructions.md](../.github/copilot-instructions.md) for the complete workflow.
