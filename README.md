# AI-Powered QA Automation Platform

AI QA Engine is a quality-assurance workspace for connecting application targets, organizing test cases, running browser checks, and reviewing defects. The current repository contains a working frontend prototype and an initial FastAPI + Playwright web runner.

For product scope and full project documentation, see [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md). For architecture details, see [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md). For the approved modernization assessment, see [`docs/ENTERPRISE_MODERNIZATION_REPORT.md`](docs/ENTERPRISE_MODERNIZATION_REPORT.md). For end-user workflows, see [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md). For setup, local development, and validation commands, see [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md). For security and test policy, see [`docs/Security-Guide.md`](docs/Security-Guide.md) and [`docs/Testing-Strategy.md`](docs/Testing-Strategy.md).

Contribution workflow, changelog requirements, and commit rules are documented in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

For frontend/UI and application source-code changes, the workspace delivery policy requires validation, a reviewable commit, and a push to the current branch's configured upstream unless the user explicitly asks to keep the change local or a safe push is blocked. See [`.github/copilot-instructions.md`](.github/copilot-instructions.md).

## Current status

### Implemented

- Responsive Next.js dashboard based on the supplied AI QA Engine PDF mock
- Project, application, test-case, test-execution, and defect views
- Web application registration with URL validation
- Android `.apk` and iOS `.ipa` drag-and-drop capture in the browser
- Application More actions on mobile and labeled icon actions on desktop
- SQLite persistence for users, applications, test cases, defects, and execution runs
- Authenticated web login steps with run-only credentials
- Live queued/running/completed execution progress and worker logs
- CSV/XLSX test-case import and APK/IPA mobile artifact upload
- FastAPI health endpoint
- Playwright web execution endpoint with title, selector, and text checks
- JWT registration/login and protected application/run endpoints
- SQLite/PostgreSQL-compatible persistence for users, applications, and runs
- Background run worker with status polling and execution logs
- Multi-step web actions: click, type, select, navigate, and assertions
- Appium adapter contracts for Android UiAutomator2 and iOS XCUITest providers
- Full-page screenshot capture and structured execution results
- Voice-over narration embedded into recorded WebM execution videos with male/female voice selection

### Not production-ready yet

- Authentication + RBAC baseline are implemented for the current API; token rotation and account recovery remain
- Users, applications, test cases, defects, and runs are persisted locally
- Test Execution calls the backend Playwright runner for web targets
- Android and iOS execution requires a configured Appium provider and device/emulator
- Durable queueing requires Redis worker deployment and operational monitoring
- Docker Compose and Dockerfiles provide a runnable baseline (frontend, backend, Redis queue worker); Kubernetes manifests are not included in this repository

## Repository layout

```text
backend/       FastAPI API, Playwright service, schemas, and future service boundaries
frontend/      Next.js App Router UI and responsive workspace
docs/          Canonical product, architecture, security, and testing documentation
project AI QA Engine.drawio.pdf
```

## Requirements

- Node.js 20.9 or newer
- npm 9 or newer
- Python 3.11+ (Python 3.13 works with the current Playwright release)
- Chromium for Playwright web execution

## Run the frontend

```bash
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. For a production-style local server:

```bash
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Use one Next.js process at a time. Development uses `.next-dev` and production builds use `.next`, preventing dev/build chunk collisions. If a stale development bundle remains, stop the servers, remove `frontend/.next-dev`, and restart one process.

## Simplified local start (one command)

From repository root, run:

```powershell
.\scripts\start-local.ps1
```

This starts the backend and frontend services automatically.

To start the services without periodic synchronization:

```powershell
.\scripts\start-local.ps1 -DisableAutoSync
```

Stopping the services with `stop-local.ps1` stops both backend and frontend processes.
To stop started local services:

```powershell
.\scripts\stop-local.ps1
```

## Run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -m app.core.migration_bootstrap
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check the service:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Workspace initialization

On startup, the backend ensures that the configured initial administrator exists and has the `admin` role. It does not create a default project, application, test case, defect, suite, or execution run. Create applications from the UI or API, then import or generate the test cases that belong to each application.

Set `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` before the first start so the initial administrator is owned by your environment.

## Read-only Jira and qTest

Jira and qTest settings are backend environment configuration. Copy the integration section from [backend/.env.example](backend/.env.example) into the ignored `backend/.env` file and set the initial URLs, project or filter identifiers, and tokens there. The Settings page reports sanitized configuration status and lets an authenticated user update those local environment values through a write-only form without exposing credentials.

External integrations are strictly read-only for now. Search, connection tests, and bounded metadata retrieval use GET/HEAD requests only; external create, update, and delete operations are blocked with HTTP 405. Local connection-profile CRUD changes only AI-QA-Engine configuration.

## Run with Docker Compose

Local baseline stack (frontend + backend + Redis + queue worker):

```bash
docker compose up --build
```

Production-oriented compose scaffold:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

## Execute a web test

The runner accepts an HTTP or HTTPS URL and optional checks. It launches Playwright Chromium (visible in `watch_live` mode or headless in `background` mode), waits for DOM content and network idle, evaluates checks, and optionally writes a screenshot to `/tmp/ai-qa-engine-runs`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/execution/run \
	-H 'content-type: application/json' \
	-d '{
		"url": "https://your-app.example.com/",
		"checks": [
			{"type": "title_contains", "value": "Your Application"},
			{"type": "visible", "value": "body"},
			{"type": "text_contains", "value": "Log In"}
		],
		"timeout_ms": 30000,
		"capture_screenshot": true,
		"capture_video": true
	}'
```

Supported check types:

| Type | Value |
| --- | --- |
| `title_contains` | Case-insensitive text expected in the page title |
| `visible` | CSS selector that must be visible |
| `text_contains` | Case-insensitive text expected in the page body |

The response includes `run_id`, `status` (`passed`, `failed`, or `error`), page title, duration, individual check results, screenshot/video/trace artifacts, and an error message when execution fails. Test Execution renders authenticated screenshot and video previews and provides trace ZIP downloads in the selected run details. Local development may use the process-local worker; production Compose requires Redis/RQ.

## API reference

### `GET /health`

Returns service availability.

### `POST /api/v1/execution/run`

Request fields:

- `url`: required HTTP(S) URL
- `checks`: zero to 25 checks
- `execution_mode`: `watch_live` (visible browser) or `background` (headless)
- `slow_mode`: `normal` or `demo`
- `trace_mode`: `off`, `on_failure`, or `always`
- `timeout_ms`: 1,000 to 120,000 milliseconds; defaults to 30,000
- `capture_screenshot`: defaults to `true`
- `capture_video`: defaults to `true`
- `capture_audio`: defaults to `true` when video capture is enabled; embeds redacted execution narration
- `voice_gender`: `male` or `female`; selects the available system TTS voice profile
- `keep_browser_open_seconds`: post-run visible-browser hold window
- `keep_browser_open_on_failure`: keep browser open on failure for inspection

Run creation returns `202` and a `run_id`; poll `GET /api/v1/execution/{run_id}` for the terminal result. The status response includes `live_state` and `current_action` sourced from real Playwright execution events. Recorded videos are finalized with a redacted narration audio track when TTS and FFmpeg are available; the result exposes `audio_status` as `embedded`, `unavailable`, or `disabled`. The run-details page presents the video before the step timeline. The current worker is process-local. Do not expose it publicly without stronger SSRF protection, rate limiting, egress controls, and resource limits.

## Using the UI

1. Open **Applications**.
2. Choose **Web**, **Android**, or **iOS**.
3. Enter a name and, for Web, a complete URL such as `https://your-app.example.com/`.
4. For mobile, drop an `.apk` or `.ipa` package into the upload area.
5. Save the application. It becomes available to the test-case and execution views.
6. Use the application row actions to generate tests, view details, or delete the target.

### Import test cases

Open **Test cases** for the selected application and choose a `.csv` or `.xlsx` file. The first row must include `Title`, `Test Case`, `Test Case Name`, or `Name`. Optional columns are `Description`, `Precondition`, `Steps`, and `Expected Result`. Imported rows are stored as draft test cases. Spreadsheet text is persisted as test-case documentation; executable browser actions require structured selectors/actions and are not inferred from arbitrary prose.

### AI generation (explicit provider)

AI generation requires one configured provider. Set `AI_QA_ENGINE_AI_PROVIDER` to an explicit supported value such as `github_copilot`, `openai`, `azure_openai`, `anthropic`, `gemini`, or `local`. Provider errors are returned to the caller; the platform does not switch providers or fabricate cases when the selected provider is unavailable.

#### Improving AI Test Generation Accuracy

**For Better Results: Configure an explicit provider**

1. Choose a supported provider in Administration > AI & Settings.
2. Enter the provider credential and model there; provider credentials are not stored in generated test cases.
3. Restart the backend service only when changing deployment-level configuration.
4. Generated test cases use the selected provider and the source context supplied in the UI.

**Best Practices for Test Case Descriptions**

Regardless of AI provider, write test case steps clearly and specifically:

❌ **Bad:** "Login to the app"  
✅ **Good:** "Click the 'Sign In' button, enter email into email field, enter password into password field, click 'Login' button"

❌ **Bad:** "Navigate to control panel"  
✅ **Good:** "Click 'Dashboard' link, then click 'Control Panel' from the menu"

❌ **Bad:** "Check if the page loaded"  
✅ **Good:** "Verify page title contains 'Dashboard', verify 'Welcome' message is visible"

Detailed, step-by-step descriptions help AI generate more accurate selectors and assertions.

The UI creates durable jobs through `POST /api/v1/ai-generation/jobs?application_id=<id>` and polls `GET /api/v1/ai-generation/jobs/<job_id>` until completion. The synchronous endpoint below remains available for compatibility consumers.

`POST /api/v1/test-cases/{application_id}/generate-ai` returns these response headers:

- `X-AI-QA-Engine-AI-Generation-Mode` (`provider`)
- `X-AI-QA-Engine-AI-Provider`
- `X-AI-QA-Engine-AI-Provider-Configured`
- `X-AI-QA-Engine-AI-Generation-Note`

### Real-Time Execution Visibility

**Watch Live Mode (Recommended)**

By default, test execution runs in **watch_live mode**, which displays the browser window during execution. This allows you to:

- **See each step execute** in real-time
- **Debug failing steps** as they happen
- **Inspect element selections** before clicks or assertions
- **Monitor page transitions** and loading states

Configure in frontend settings or `backend/.env`:
```bash
AI_QA_ENGINE_EXECUTION_MODE=watch_live
```

**Background Mode (Headless)**

For CI/CD pipelines or unattended execution, use background mode:
```bash
AI_QA_ENGINE_EXECUTION_MODE=background
```

Test execution runs headless (no browser window), completing faster but with no visual feedback.

**Execution Evidence**

Both modes automatically capture:
- **Screenshots** at each step (enabled by default)
- **Video recording** (optional; enable in execution settings for slow playback analysis)
- **Execution logs** with step-by-step timing and selector details
- **Playwright trace** (on failure) for debugging element interactions

### Run a protected web application

Open **Test execution**, select the protected web application, and enable **Run login flow**. Enter `login_email` and `login_password` in the Login parameters section, then provide the target-specific selectors for the email field, password field, and submit control. Credentials are sent only with the current run, are not written to local browser configuration, and are not stored in saved run steps. The progress panel reports submission, queue, worker, and final result states.

The supplied protected target can be tested with credentials you are authorized to use. Do not commit those credentials or place them in environment files. Login selectors are configured in the UI because they vary by target application. AI discovery uses unauthenticated target context; the configured login flow is applied when generated cases are executed.

Web applications and uploaded mobile artifacts are persisted by the backend. Mobile package upload records the artifact under `backend/uploads/`; actual Android/iOS execution still requires a configured Appium provider and device/emulator.

## Troubleshooting

### Test Execution Timeout

**Symptom:** "Execution Timeout - Test execution exceeded the maximum time limit" with 0% pass rate

**Cause:** Frontend polling window exhausted before test completed. Tests typically take 60-120 seconds for login + navigation + assertions.

**Solution:**
1. Ensure backend is running and responsive: `curl http://localhost:8000/health`
2. Check backend logs for failed selectors or element not found errors
3. Verify login credentials are correct: `python backend/login_visible_check.py --keep-open-seconds 5`
4. Increase test timeout in execution settings if backend is slow
5. If port 8000 is already in use, kill the process: `Get-Process -Name python | Where-Object {$_.Path -like "*backend*"} | Stop-Process -Force`

### Port Already in Use (Error 10048)

**Symptom:** `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): only one usage of each socket address (protocol/network address/port) is normally permitted`

**Cause:** Previous backend process still occupying port 8000

**Solution:**
```powershell
# Option 1: Run the cleanup script
.\scripts\stop-local.ps1

# Option 2: Manual cleanup
Get-Process -Name python | Where-Object {$_.Path -like "*backend*"} | Stop-Process -Force
# Wait 5-10 seconds for socket to release (Windows TIME_WAIT state)
```

### AI Generation Not Accurate

**Symptom:** Generated test cases have incorrect selectors or skip important steps

**Cause:** The selected provider returned generic output or the test case description is too vague

**Solutions:**

1. **Verify the selected provider:** Configure an explicit provider and API key (see AI Generation section above)
2. **Improve test descriptions:** Use specific, step-by-step language instead of high-level prose
3. **Start with simple tests:** Test 3-5 step cases before complex workflows
4. **Check generation headers:** Look at response headers from AI generation endpoint to see which provider was used

### Playwright Window Not Visible During Execution

**Symptom:** Tests run silently in background; can't see what's happening

**Cause:** Execution mode set to "background" (headless)

**Solution:**
1. In UI: Open Execution Settings panel
2. Change **Execution Mode** to **watch_live**
3. Run test again—browser window should appear

Or in `backend/.env`:
```bash
AI_QA_ENGINE_EXECUTION_MODE=watch_live
```

### Element Selector Not Found

**Symptom:** Step fails with "element not found" or timeout

**Cause:** CSS/XPath selector doesn't match actual page element; selector changed in UI

**Solutions:**
1. Enable watch_live mode to see what's on screen
2. Inspect target page with browser DevTools to find correct selector
3. Check for dynamic IDs (change on page load) or dynamic classes
4. Update test case step with new selector
5. Verify page fully loaded: wait for spinners to disappear

### Backend Logs Show "login failed"

**Symptom:** Login test steps fail; backend logs show authentication errors

**Cause:** Credentials incorrect or login URL changed

**Solution:**
```powershell
cd backend
python login_visible_check.py --keep-open-seconds 10
# A browser window will open; try logging in manually to verify credentials
```

### Port 3000 Already in Use (Frontend)

**Symptom:** Frontend fails to start: "Address already in use :::3000"

**Solution:**
```powershell
Get-Process -Name node | Stop-Process -Force
# Or specify a different port
cd frontend
npm run dev -- -p 3001
```

### High Memory Usage or Slow Tests

**Cause:** Multiple browser instances accumulating; insufficient system resources

**Solution:**
1. Stop all running tests: Click "Stop" on active execution
2. Verify no orphaned browsers: `Get-Process -Name chrome* | Stop-Process -Force`
3. Close other applications to free memory
4. Restart frontend and backend

## Production path

Before production deployment, implement these in order:

1. Complete PostgreSQL-first migrations (Alembic), backup/restore jobs, and restore drills.
2. Add token refresh, token rotation, and account recovery flows on top of current JWT + RBAC.
3. Deploy Redis workers with durability/monitoring and autoscaling for high-throughput execution.
4. Add protected artifact storage for screenshots, logs, APKs, and IPAs with retention policies.
5. Add strict SSRF controls + outbound egress policy enforcement for target URLs.
6. Expand automated API/integration/browser/worker test coverage in CI.
7. Productionize observability (centralized logs, metrics dashboards, tracing, alerts).
8. Replace scaffold Docker/Kubernetes configuration with reviewed production manifests and secrets integration.

## Validation

Frontend build:

```bash
cd frontend
npm run build
```

Backend syntax and health check:

```bash
cd backend
.venv/bin/python -m compileall -q app
.venv/bin/python -c 'from fastapi.testclient import TestClient; from app.main import app; print(TestClient(app).get("/health").json())'
```

## Security and test-target policy

Only run AI QA Engine against applications you own or are explicitly authorized to test. Store credentials in a secret manager and never put passwords, tokens, or private keys in test definitions, screenshots, logs, or source control.
