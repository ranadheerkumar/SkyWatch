# SkyWatch — Current-State Execution Analysis & Multi-Environment Map

**Assessment Date:** September 2026  
**Status:** Architectural Baseline Analysis (Requirement 46)  

---

## A. Current Execution Architecture

Today, SkyWatch's test execution occurs primarily through a **local Playwright runner** orchestrated either synchronously or via a background worker queue:

```text
User / Frontend
      │
      ▼
REST API (POST /api/v1/execution/run OR POST /api/v1/execution/test-case/{id})
      │
      ▼
app/services/run_queue.py
      │ (Enqueues into Redis or dispatches via asyncio in-memory loop)
      ▼
app/services/test_execution.py::execute_web_target()
      │
      ▼
playwright.async_api::async_playwright()
      │
      ▼
playwright.chromium.launch()  <-- Hardcoded strictly to local Chromium
      │
      ▼
BrowserContext -> Page -> Steps/Checks Execution Loop
      │
      ├── Element interactions (click, type, select)
      ├── Evidence Capture (Screenshots, Video, Traces in /tmp/ai-qa-engine-runs)
      ├── Dynamic Action Highlighting & Speech Narration (espeak/pyttsx3)
      └── AI Self-Healing (generate_healing_step if step fails)
      │
      ▼
ExecutionResponse (CheckResult, StepResult, ExecutionArtifact)
      │
      ▼
Database (TestRun, CaseExecution, BuildExecution) + Allure 2 Reporter
```

---

## B. Current Dependencies

### Execution & Browser
- `playwright >= 1.49.0`: Core automation library. Defaults exclusively to local Chromium.
- `appium-python-client` (Optional): Basic driver stub in `app/services/mobile_execution.py`.
- `espeak-ng / libespeak1 / pyttsx3`: System narration and synthetic voice-over.
- `imageio-ffmpeg`: Video stitching and audio overlay for execution evidence.

### Service & Infrastructure
- `FastAPI / Uvicorn`: HTTP API layer on port 8000.
- `SQLAlchemy / Alembic`: Local SQLite default (`/data/ai-qa-engine.db`) or PostgreSQL (`psycopg`).
- `Redis / RQ`: Background task queue (`ai-qa-engine-runs`), with an in-memory fallback if Redis is unreachable.
- `Docker / Docker Compose`: Multi-container topology (`redis`, `backend`, `worker`, `frontend`).

### Cloud Dependencies
- Zero mandatory cloud dependencies for local execution.
- LLMs support Google Gemini, GitHub Copilot, OpenAI, Anthropic, Azure OpenAI, and Local (Ollama/vLLM) with offline simulation fallbacks.

---

## C. Current Hardcoded Behaviors

1. **Browser Engine Hardcoded to Chromium**:
   - `test_execution.py:2236`: `browser = await playwright.chromium.launch(...)`.
   - Firefox and WebKit are not selectable in the execution request.
2. **Local Machine Display & Headless Logic**:
   - `test_execution.py:53`: `_should_run_headless()` checks `os.name != "nt" and os.getenv("DISPLAY") is None`.
3. **Hardcoded Evidence Storage Path**:
   - `test_execution.py:39`: `SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "ai-qa-engine-runs"`.
   - Artifacts are saved to local disk only, without native abstraction for cloud object storage (S3, Azure Blob, GCS) or cloud grids (Sauce Labs, LambdaTest).
4. **Execution Mode Limited to Local Process**:
   - `ExecutionRequest.execution_mode` only accepts `"watch_live"` or `"background"`.
   - No concept of `"local"`, `"remote_grid"`, `"cloud"`, `"sauce_labs"`, or `"lambdatest"`.
5. **No Remote WebDriver / Grid Connector**:
   - Playwright's `connect()` or `connect_over_cdp()` to remote grids (Sauce Labs, LambdaTest, Selenium 4 Grid, Moon/Selenoid) is not plumbed into `test_execution.py`.

---

## D. Current Execution Paths

```mermaid
flowchart TD
    UI[Frontend: Workspace / Table Row / Studio] -->|HTTP POST| API[API: /api/v1/execution/run]
    API -->|Validate URL & Steps| RQ[Run Queue: enqueue_run]
    RQ -->|Local Thread or Redis| Worker[Worker: process_run]
    Worker --> TE[test_execution.py: execute_web_target]
    TE --> PW[Local Chromium Browser Instance]
    PW --> Page[Web Application Under Test]
    Page --> DOM[DOM Events & Screenshot Capture]
    DOM --> Artifacts[Local /tmp Filesystem]
    DOM --> DB[(SQLite / Postgres DB)]
    DB --> UI_Poller[Frontend Polling: /execution/runs & /execution/{id}]
```

---

## E. Duplication & Divergence

- `test_execution.py` contains monolithic step execution logic mixed with browser lifecycle management, evidence generation, audio narration, and self-healing.
- `mobile_execution.py` has a separate disconnected `execute_mobile_target()` that directly creates an Appium `webdriver.Remote()` without hooking into the main event stream, evidence collector, or Allure reporter.
- `ai_service.py` launches a separate ad-hoc Playwright instance for application discovery and DOM snapshotting instead of using a unified session manager.

---

## F. Risks to Local Execution & Mitigation Strategy

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Breaking Local Playwright Launch** | Local tests fail if cloud or remote dependencies are required. | **Zero-Dependency Local Fallback**: `LocalExecutionProvider` is the default provider. If no provider is specified or cloud credentials are missing, local execution runs identically to today. |
| **Schema Breaking Changes** | Existing frontend API calls fail if payload parameters change. | **Additive Schemas**: All new fields (`execution_provider`, `browser`, `device`, `provider_config`) have sensible defaults (`provider="local"`, `browser="chromium"`). |
| **Remote Network Latency in Live Mode** | Watch-live interactive streaming lags on remote cloud grids. | Distinguish `watch_live` on local vs. asynchronous batch runs on remote grids (Sauce/LambdaTest). |
| **Credential Exposure** | Cloud or grid access keys leak into logs or execution artifacts. | Redact `SAUCE_ACCESS_KEY`, `LT_ACCESS_KEY`, and cloud tokens via `SecretMaskingFilter`. |

---

## G. Migration Plan (Incremental, Non-Destructive)

1. **Step 1: Canonical Execution Contract & Provider Interface**:
   - Define `ExecutionProvider` abstract base class with standardized lifecycle:
     - `validate_request()`, `check_health()`, `prepare_environment()`, `execute()`, `collect_artifacts()`, `cleanup()`.
   - Define `CanonicalExecutionRequest` and `CanonicalExecutionResult`.
2. **Step 2: Encapsulate Local Execution Provider**:
   - Refactor current local Chromium/Firefox/WebKit execution into `LocalExecutionProvider` implementing `ExecutionProvider`.
   - Guarantees 100% parity with existing local behavior.
3. **Step 3: Remote Grid Adapters (Sauce Labs & LambdaTest)**:
   - Implement `SauceLabsExecutionProvider` connecting via Playwright CDP or Selenium Grid protocol.
   - Implement `LambdaTestExecutionProvider` with cross-browser and mobile device matrix capabilities.
4. **Step 4: Cloud Execution Adapters (Azure, GCP, AWS)**:
   - Implement containerized execution dispatchers for Azure Container Apps, GCP Cloud Run, and AWS ECS.
5. **Step 5: Execution Provider Registry & Factory**:
   - Implement `ExecutionProviderRegistry` with capability advertising and health probes.
6. **Step 6: Dynamic Agentic Provider Selection**:
   - Enhance `CapabilityOrchestrator` so agents can reason over execution requirements (e.g. "iPad Safari" &rarr; selects Sauce Labs or LambdaTest).
7. **Step 7: Frontend Studio & Settings Integration**:
   - Add Execution Provider configuration cards and runtime target dropdowns in the frontend.

---

## H. Test & Verification Strategy

- **Unit Tests**:
  - `test_execution_providers.py`: Verifies provider registration, capability filtering, configuration defaults, and error mapping.
  - `test_execution_contract.py`: Verifies that Local, Sauce Labs, LambdaTest, and Cloud providers adhere to the exact same input/output contract.
  - `test_agentic_provider_selection.py`: Verifies agent decisions (browser/platform compatibility, fallback logic, policy compliance).
- **Contract Tests**:
  - Validate mock responses for Sauce Labs and LambdaTest REST APIs without requiring live credentials in CI.
- **Local Parity & Regression Tests**:
  - Verify existing Playwright suite (`test_script_generators.py`, `test_enterprise_e2e.py`) continues to pass with 0 regressions.
