# Jira & qTest Enterprise Integration & Connectivity Guide

## 1. Overview & Security Architecture

SkyWatch integrates seamlessly with enterprise issue trackers and test management systems (**Atlassian Jira** and **Tricentis qTest**) while enforcing strict security guarantees:

1. **Zero Credential Exposure**: Tokens, passwords, and private company URLs are **never hardcoded** in source code, committed files, or git history.
2. **Environment & Secret Provider Storage**: Credentials are read dynamically from runtime environment variables or vault secret backends.
3. **Write-Only Security in UI**: The Settings management UI allows updating API tokens without ever returning or exposing existing secrets back over API responses.
4. **Read-Only Safety Guardrails**: External reads (asset sync, requirement import, test status lookup) are permitted, while write operations (creating/mutating defects) require explicit user confirmation or can be globally restricted via `SKYWATCH_INTEGRATIONS_READ_ONLY=true`.

---

## 2. Configuration Parameters

Set these parameters in your local ignored `backend/.env` or deployment environment:

### Jira Integration
| Variable | Description | Example |
| :--- | :--- | :--- |
| `JIRA_BASE_URL` | Base URL of Jira instance | `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | Account email associated with the API token | `qa-bot@company.com` |
| `JIRA_API_TOKEN` | Secret Jira personal access token / API token | *(Secret)* |
| `JIRA_PROJECT_KEY` | Target Jira project key | `PROJ` |
| `JIRA_FILTER_ID` | Optional numeric filter ID for scoping issues | `10042` |

### qTest Integration
| Variable | Description | Example |
| :--- | :--- | :--- |
| `QTEST_BASE_URL` | Base URL of Tricentis qTest instance | `https://company.qtestnet.com` |
| `QTEST_TOKEN` | Bearer token for qTest REST API | *(Secret)* |
| `QTEST_PROJECT_ID` | Numeric qTest project identifier | `98421` |
| `QTEST_PROJECT_NAME` | Project display name | `Digital Channel QA` |

### Safety Flags
| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SKYWATCH_INTEGRATIONS_READ_ONLY` | `true` | Restricts background synchronization to non-destructive GET requests. |
| `ENABLE_JIRA_WRITE` | `false` | Enables export of verified defects to Jira on explicit user request. |
| `ENABLE_QTEST_WRITE` | `false` | Enables export of test run executions and defects to qTest. |

---

## 3. Connectivity Verification

SkyWatch provides non-destructive GET-only connection tests to verify enterprise connectivity without mutating external state.

### Testing Jira Connectivity
```http
GET /api/v1/integrations/jira/test-connection
Authorization: Bearer <skywatch-token>
```

**Verification Flow:**
1. Issues a secure HTTP GET to `${JIRA_BASE_URL}/rest/api/3/myself` (or `/rest/api/2/serverInfo`).
2. Validates that HTTP 200 OK is returned.
3. Sanitizes and masks the response (returning username and server version, but suppressing all authorization headers).

### Testing qTest Connectivity
```http
GET /api/v1/integrations/qtest/test-connection
Authorization: Bearer <skywatch-token>
```

**Verification Flow:**
1. Issues a secure HTTP GET to `${QTEST_BASE_URL}/api/v3/projects/${QTEST_PROJECT_ID}`.
2. Validates HTTP 200 OK and project metadata.
3. Confirms read permissions and asset sync readiness.

---

## 4. Defect Export Workflow

When SkyWatch's Autonomous Testing Engine or an automated Playwright test uncovers a verified regression defect:

1. **Defect Review**: Defect is logged locally in SkyWatch with step trace, screenshot evidence, error logs, and root cause classification.
2. **Export Action**: A QA engineer or lead clicks **Export to Jira** or **Export to qTest** (or triggers via CI policy).
3. **Payload Construction**:
   - Issue Type: `Bug` / `Defect`
   - Summary: `[SkyWatch Regression] <Test Title> failed at step <N>`
   - Description: Markdown formatted reproduction steps, selector details, and failure diagnosis.
   - Attachments: Playwright screenshot PNG and execution log trace.
4. **Idempotent Linking**: The external issue key (e.g. `PROJ-1428`) is saved in `external_issue_links` to prevent duplicate ticket generation.
