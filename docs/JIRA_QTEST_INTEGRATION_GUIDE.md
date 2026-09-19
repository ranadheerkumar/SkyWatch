# SkyWatch Advanced Jira Cloud & Tricentis qTest Integration Guide

> Comprehensive architectural guide for closed-loop quality management connecting SkyWatch Autonomous Testing with Atlassian Jira Cloud REST API v3 and Tricentis qTest SaaS.

---

## 1. Executive Architecture

SkyWatch integrates seamlessly with enterprise Application Lifecycle Management (ALM) systems to bridge requirement analysis, autonomous execution, and defect tracking.

```mermaid
graph TD
    subgraph "Jira Cloud REST API v3"
        J_Req[Requirements & Stories]
        J_Bug[Bugs & Defects]
        J_Link[Issue Links]
        J_Att[Multipart Attachments]
        J_Tran[Workflow Transitions]
        J_Hook[Webhook Subscriptions]
    end

    subgraph "SkyWatch Autonomous Platform"
        SW_Disc[Spec & DOM Discovery]
        SW_Orch[Autonomous Orchestrator]
        SW_Agents[Visual, API & E2E Agents]
        SW_Bridge[Enterprise ALM Bridge]
        SW_HookReceiver[Webhook Event Processor]
    end

    subgraph "Tricentis qTest SaaS"
        Q_Rel[Releases]
        Q_Bld[Builds API: /projects/{id}/builds]
        Q_TC[Test Design: Test Cases]
        Q_TR[Test Execution: Test Runs]
        Q_Log[Auto-Test-Logs Submission]
        Q_Def[Linked Defects]
    end

    J_Hook -->|Webhook: issue status changed| SW_HookReceiver
    SW_HookReceiver --> SW_Orch
    J_Req -->|Ingest Story Scope| SW_Disc
    SW_Disc --> SW_Orch
    SW_Orch --> SW_Agents
    SW_Agents --> SW_Bridge

    SW_Bridge -->|1. Create Build under Release| Q_Bld
    Q_Rel -.-> Q_Bld
    SW_Bridge -->|2. Export Test Cases| Q_TC
    SW_Bridge -->|3. Submit Auto-Test-Logs| Q_Log
    Q_TR -.-> Q_Log

    SW_Bridge -->|4. File Rich ADF Defect| J_Bug
    SW_Bridge -->|5. Upload Diff Images| J_Att
    SW_Bridge -->|6. Link Bug to Story| J_Link
    SW_Bridge -->|7. Auto-Transition Resolved| J_Tran
    SW_Bridge -->|8. Link Defect to Run| Q_Def
```

---

## 2. Jira Cloud REST API v3 Integration

### 2.1 Atlassian Document Format (ADF) Engine
Jira Cloud REST API v3 mandates structured JSON for description and comment fields. SkyWatch includes an `ADFBuilder` utility that constructs rich, formatted defect payloads:
- **Severity Alert Panel**: Color-coded callouts (Warning / Error) indicating the autonomous detection agent and metadata (viewport, browser, route).
- **Steps to Reproduce Table**: Formatted tabular presentation of reproduction steps with step number, action, and expected behavior.
- **Verification Results Table**: Clear side-by-side comparison of expected vs. actual behavior.
- **Diagnostic Trace Code Block**: Syntax-highlighted stack traces, Playwright error snippets, and API contract payloads.

```json
{
  "version": 1,
  "type": "doc",
  "content": [
    {
      "type": "panel",
      "attrs": {"panelType": "error"},
      "content": [
        {
          "type": "paragraph",
          "content": [{"type": "text", "text": "Defect identified autonomously by SkyWatch Quality Engine."}]
        }
      ]
    },
    {
      "type": "heading",
      "attrs": {"level": 3},
      "content": [{"type": "text", "text": "Steps to Reproduce"}]
    },
    {
      "type": "table",
      "attrs": {"isNumberColumnEnabled": false},
      "content": [ ... ]
    }
  ]
}
```

### 2.2 Bi-Directional Issue Linking (`POST /rest/api/3/issueLink`)
When SkyWatch discovers a regression while testing a user story, it creates an issue link between the newly created Bug and the parent Story:
- **Link Types**: `Relates`, `Blocks`, `Causes`.
- **Traceability**: Ensures product owners and developers can immediately trace which requirement was impacted by which test run.

### 2.3 Multipart Attachment Uploader (`POST /rest/api/3/issue/{key}/attachments`)
Visual regression diff images, DOM snapshots, and test failure screenshots are directly uploaded to the Jira ticket:
- Header: `X-Atlassian-Token: no-check` (protects against XSRF blocks).
- Format: `multipart/form-data`.

### 2.4 Autonomous Workflow Transitions (`GET/POST /rest/api/3/issue/{key}/transitions`)
- **Query Transitions**: Dynamically discovers available transition IDs (`Resolve Issue`, `In Progress`, `Done`) based on project workflows.
- **Closed-Loop Resolution**: When an automated test suite verifies that a previously failing test case now passes on a new build, SkyWatch can autonomously transition the ticket to `Resolved` with an audit comment.

---

## 3. Tricentis qTest SaaS Integration

### 3.1 Builds & Releases Management (`GET / POST /api/v3/projects/{projectId}/builds`)
Per the Tricentis qTest Build API specification:
- **Field Discovery**: `GET /api/v3/projects/{projectId}/settings/builds/fields` inspects project-specific required fields.
- **Release Builds**: `GET /api/v3/projects/{projectId}/builds?releaseId={releaseId}` lists existing builds.
- **Build Registration**: `POST /api/v3/projects/{projectId}/builds` registers each SkyWatch test execution run under the active Release version.

### 3.2 Auto-Test-Logs Submission (`POST /api/v3/projects/{projectId}/test-runs/{runId}/auto-test-logs`)
Publishes execution results directly into qTest Test Runs:
- Status: `PASSED`, `FAILED`, `BLOCKED`, `INCOMPLETE`.
- Timestamps: `exe_start_date` and `exe_end_date`.
- Step logs: Comprehensive breakdown of test assertion steps.
- Defect linking: Automatically associates logged qTest defects with failed runs.

### 3.3 Test Case Export (`POST /api/v3/projects/{projectId}/test-cases`)
Exports SkyWatch AI-generated test cases (from OpenAPI specs or visual crawl routes) directly into qTest Test Design modules with preconditions and test steps.

---

## 4. REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/integrations/jira/issues/{key}/attachments` | `POST` | Upload screenshot/diff artifact to Jira issue |
| `/api/v1/integrations/jira/issues/{key}/links` | `POST` | Create bi-directional issue link |
| `/api/v1/integrations/jira/issues/{key}/transitions` | `GET` | List available workflow transitions |
| `/api/v1/integrations/jira/issues/{key}/transitions` | `POST` | Execute workflow state transition |
| `/api/v1/integrations/jira/issues/{key}/comments` | `POST` | Post ADF execution comment |
| `/api/v1/integrations/qtest/builds` | `GET` | List builds under a release |
| `/api/v1/integrations/qtest/builds` | `POST` | Register a new build under a release |
| `/api/v1/integrations/qtest/test-runs/{run_id}/logs` | `POST` | Submit auto-test-logs to test run |
| `/api/v1/integrations/qtest/test-cases/export` | `POST` | Export test case to qTest test design |
| `/api/v1/integrations/webhooks/jira` | `POST` | Inbound Jira webhook receiver |
| `/api/v1/integrations/webhooks/qtest` | `POST` | Inbound qTest webhook receiver |

---

## 5. Security and Configuration

All write mutations strictly respect organizational safety guards configured in environment variables:

```bash
# Set to true to permit outbound Jira mutations (bug filing, links, attachments, transitions)
ENABLE_JIRA_WRITE=false

# Set to true to permit outbound qTest mutations (build creation, test logs, test case export)
ENABLE_QTEST_WRITE=false

# Automation toggles
JIRA_AUTO_LINK_ISSUES=true
JIRA_AUTO_ATTACH_DIFFS=true
JIRA_AUTO_TRANSITION_RESOLVED=false
QTEST_AUTO_REGISTER_BUILDS=true
QTEST_DEFAULT_RELEASE_ID=
INTEGRATIONS_WEBHOOK_SECRET=
```
