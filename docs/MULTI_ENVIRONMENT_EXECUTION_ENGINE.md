# SkyWatch Multi-Environment, Cloud-Neutral & Agentic Execution Engine

**Version:** 2.6.0  
**Status:** Codified Architecture & Implementation  
**Compliance:** Master Architectural Charter & Section 46 Multi-Environment Execution

---

## 1. Executive Summary

SkyWatch's **Multi-Environment Execution Engine** provides a single, unified, cloud-neutral testing infrastructure capable of orchestrating quality automation across:
* **Local Machines** (first-class, completely offline, zero-cloud dependency).
* **Docker Containers** (isolated, reproducible local or server instances).
* **Remote Cloud Grids** (Sauce Labs real-device cloud, LambdaTest Smart Automation grid).
* **Enterprise Cloud Containers** (Azure Container Apps / ACI, GCP Cloud Run Jobs, AWS ECS Fargate).
* **CI/CD Pipelines** (GitHub Actions, GitLab CI, Jenkins).

All execution occurs through a **single canonical execution model** and **standardized provider contract** (`ExecutionProvider`). There is zero duplicate runner code and zero vendor lock-in.

---

## 2. Core Architectural Principles

### A. The Zero-Regression Local Guarantee
Local execution is a first-class citizen and must continue to operate out of the box with **zero cloud credentials**, **zero external accounts**, and **100% offline capability**. If remote grid credentials are not configured or are unreachable, the engine gracefully falls back to the `LocalExecutionProvider` with responsive device emulation.

### B. Single Canonical Execution Contract
All execution requests—regardless of whether they target local Chromium, an iPhone on Sauce Labs, or a container in Azure—are expressed via `CanonicalExecutionRequest`. All results and evidence are normalized into `CanonicalExecutionResult`.

```text
User / Agent / Pipeline
        │
        ▼
CanonicalExecutionRequest (Platform-Neutral)
        │
        ▼
ExecutionProviderRegistry
        │
        ├──► LocalExecutionProvider (Playwright Chromium / Firefox / WebKit)
        ├──► SauceLabsExecutionProvider (Playwright CDP / Real Device Farm)
        ├──► LambdaTestExecutionProvider (Playwright Smart Grid / Mobile)
        └──► CloudContainerExecutionProvider (Docker / Azure / GCP / AWS)
        │
        ▼
CanonicalExecutionResult (Normalized Evidence, Checks, Steps, Logs)
```

---

## 3. Canonical Execution Schemas

Located in [`backend/app/schemas/canonical_execution.py`](file:///Users/rana/git_projects/SkyWatch/backend/app/schemas/canonical_execution.py):

* **`ExecutionMode`**: `local | remote | cloud | ci | hybrid`
* **`ProviderType`**: `local | sauce_labs | lambdatest | azure | gcp | aws | docker | ci`
* **`BrowserType`**: `chromium | firefox | webkit | chrome | edge`
* **`PlatformType`**: `web | mobile | api | desktop`
* **`ProviderCapabilities`**: Advertising of supported browsers, platforms, real devices, live video, network tracing, tunnels, and concurrency limits.
* **`ProviderHealthStatus`**: Real-time health status (`healthy | degraded | unreachable | unconfigured`), probe latency, and error diagnostics.
* **`CanonicalExecutionRequest`**: Complete execution payload containing URL, steps, checks, browser, device profile, parameters, and self-healing policies.
* **`CanonicalExecutionResult`**: Unified output containing status (`passed | failed | error | cancelled`), duration, remote session IDs, dashboard URLs, artifacts, and AI self-healing results.

---

## 4. Execution Providers Matrix

| Provider ID | Provider Name | Type | Key Capabilities | Auth Requirements |
| :--- | :--- | :--- | :--- | :--- |
| `local` | **Local Playwright Runner** | `local` | Chromium, Firefox, WebKit, Audio/Video Narration, AI Healer | None (100% Offline) |
| `sauce_labs` | **Sauce Labs Cloud Grid** | `sauce_labs` | Real iOS/Android devices, US/EU datacenters, Sauce Connect tunnels | `SAUCE_USERNAME`, `SAUCE_ACCESS_KEY` |
| `lambdatest` | **LambdaTest Smart Grid** | `lambdatest` | 3000+ OS/browser matrices, real devices, SmartUI, UnderTunnel | `LT_USERNAME`, `LT_ACCESS_KEY` |
| `docker` | **Docker Container Runner** | `docker` | Ephemeral local containers, high isolation | Local Docker daemon |
| `azure` | **Azure Container Apps** | `azure` | Scalable containerized cloud workers in Azure | `AZURE_CONTAINER_APP_URL` |
| `gcp` | **GCP Cloud Run Jobs** | `gcp` | Serverless container execution in Google Cloud | `GCP_CLOUD_RUN_JOB` |
| `aws` | **AWS ECS Fargate** | `aws` | Serverless container execution in AWS | `AWS_ECS_CLUSTER` |

---

## 5. Dynamic Agentic Provider Selection

Located in [`backend/app/services/capability_orchestrator.py`](file:///Users/rana/git_projects/SkyWatch/backend/app/services/capability_orchestrator.py), the `select_execution_provider()` method replaces static `if/else` assignments with dynamic agentic reasoning:

1. **Explicit Selection**: If a user, CI workflow, or policy specifies a provider, the orchestrator verifies availability and assigns it.
2. **Device-Driven Reasoning**:
   * If the test objective requests mobile platforms (e.g. *"Verify checkout flow on iPad Safari"*), the agent searches for real-device providers (`lambdatest` or `sauce_labs`).
   * If credentials are present, the cloud grid is assigned.
   * If credentials are not present, the agent automatically falls back to `local` with responsive mobile viewport emulation and logs a transparent explanatory rationale.
3. **Container Isolation Reasoning**:
   * If the objective specifies isolated execution, the agent selects `docker` or the configured cloud container runner.
4. **Browser Matrix Reasoning**:
   * Safari/WebKit requests dynamically resolve to `BrowserType.WEBKIT`.
   * Firefox requests resolve to `BrowserType.FIREFOX`.
   * Chrome/Edge requests resolve to `BrowserType.CHROMIUM`.
5. **Zero-Overhead Default**:
   * Standard web test runs default to the high-speed `LocalExecutionProvider` for sub-millisecond dispatch and zero cloud cost.

---

## 6. REST API Endpoints

### 1. List Providers & Capabilities
* **Endpoint**: `GET /api/v1/execution/providers`
* **Description**: Returns the full catalog of registered execution providers, their configuration state, capabilities, and live health status.

### 2. Test Provider Connection
* **Endpoint**: `POST /api/v1/execution/providers/{provider_id}/test-connection`
* **Description**: Pings the provider's API or local runtime, returning latency in milliseconds and status diagnostics.

### 3. Agentic Provider Recommendation
* **Endpoint**: `POST /api/v1/execution/agentic-select`
* **Payload**:
  ```json
  {
    "objective": "Run cross-browser test suite across Chrome, Firefox, and iPad Safari",
    "target": { "browser": "webkit", "platform": "mobile" }
  }
  ```
* **Response**:
  ```json
  {
    "selected_provider_id": "lambdatest",
    "provider_name": "LambdaTest Smart Automation Grid",
    "rationale": "Selected LambdaTest Smart Automation Grid for real mobile device testing and cross-browser cloud matrix.",
    "recommended_browser": "webkit",
    "recommended_platform": "mobile",
    "is_cloud_grid": true,
    "fallback_provider_id": "local"
  }
  ```

---

## 7. Configuration Reference

Configure via `backend/.env` or environment variables:

```bash
# Default Execution Provider (local | sauce_labs | lambdatest | docker | azure | gcp | aws)
SKYWATCH_EXECUTION_PROVIDER=local

# Sauce Labs Cloud Grid
SAUCE_USERNAME=your-sauce-username
SAUCE_ACCESS_KEY=your-sauce-access-key
SAUCE_REGION=us-west-1
SAUCE_TUNNEL_IDENTIFIER=

# LambdaTest Automation Grid
LT_USERNAME=your-lambdatest-username
LT_ACCESS_KEY=your-lambdatest-access-key
LT_TUNNEL=false

# Container Runner Target (docker | azure | gcp | aws)
CLOUD_RUNNER_TARGET=docker
AZURE_CONTAINER_APP_URL=
GCP_CLOUD_RUN_JOB=
AWS_ECS_CLUSTER=
```

---

## 8. Frontend Integration

In `frontend/src/components/SettingsStudio.tsx`:
* **Execution Providers Card**: Real-time status cards for each provider with live latency indicators and "Test Connection & Health" triggers.
* **Agentic Provider Selection Engine**: Interactive prompt tester allowing QA engineers to submit execution objectives and view the orchestrator's reasoning in real time.
