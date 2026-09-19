# AI-QA-Engine · REST API Reference

The backend API is powered by FastAPI and available under the base prefix `/api/v1`.

---

## 1. Authentication & Users (`/api/v1/auth`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Register a new user account | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and retrieve JWT bearer token | Public |
| `GET` | `/api/v1/auth/me` | Fetch active user profile and roles | Authenticated |

---

## 2. Test Cases & Ingestion (`/api/v1/test-cases`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/test-cases` | List all test cases | Authenticated |
| `GET` | `/api/v1/test-cases/application/{id}` | List test cases for a specific application | Authenticated |
| `GET` | `/api/v1/test-cases/{id}` | Get details of a single test case | Authenticated |
| `POST` | `/api/v1/test-cases` | Create or update test case with priority/category/tags | Tester+ |
| `PUT` | `/api/v1/test-cases/{id}` | Update test case fields with audit tracking | Tester+ |
| `DELETE` | `/api/v1/test-cases/{id}` | Delete test case and attached automation | Tester+ |
| `POST` | `/api/v1/test-cases/{id}/clone` | Clone a test case | Tester+ |
| `POST` | `/api/v1/test-cases/{id}/version` | Bump test case version | Tester+ |
| `POST` | `/api/v1/test-cases/ingest` | Universal multi-format ingestion (Text, Markdown, CSV, JSON, OpenAPI, DDL) | Tester+ |
| `POST` | `/api/v1/test-cases/import/{app_id}` | Upload CSV or Excel test matrix file | Tester+ |
| `GET` | `/api/v1/test-cases/{id}/automation` | Get compiled automation steps and checks | Authenticated |
| `PUT` | `/api/v1/test-cases/{id}/automation` | Save custom Playwright automation steps | Tester+ |
| `GET` | `/api/v1/test-cases/application/{id}/automation-readiness` | Evaluate locator confidence and quality | Authenticated |
| `POST` | `/api/v1/test-cases/generate-ai` | Synchronous compatibility generation path | Tester+ |

## 3. Durable AI Generation (`/api/v1/ai-generation`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ai-generation/jobs?application_id={id}` | Create a durable AI generation job | Tester+ |
| `GET` | `/api/v1/ai-generation/jobs/{job_id}` | Poll an owned job and retrieve results | Tester+ |

---

## 4. Autonomous Agents (`/api/v1/agents`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/agents/recommendations` | List agent recommendations (pending, approved, rejected) | Authenticated |
| `POST` | `/api/v1/agents/analyze` | Run pre-execution readiness analysis on test cases | Authenticated |
| `POST` | `/api/v1/agents/recommendations/{id}/review` | Approve or reject an agent recommendation | Tester+ |

---

## 5. Test Execution Hub (`/api/v1/execution`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/execution/run` | Execute Playwright browser run | Tester+ |
| `POST` | `/api/v1/execution/test-case/{id}` | Execute specific test case with live streaming | Tester+ |
| `POST` | `/api/v1/execution/ingest-and-run` | Ingest scenario and execute immediately in single call | Tester+ |
| `POST` | `/api/v1/execution/plan/{plan_id}` | Execute all test cases in an execution plan | Tester+ |
| `POST` | `/api/v1/execution/{run_id}/cancel` | Immediately cancel and stop an active test run | Tester+ |
| `POST` | `/api/v1/execution/batch/{batch_id}/cancel` | Immediately cancel and stop an active batch of runs | Tester+ |
| `GET` | `/api/v1/execution/{run_id}` | Poll execution status, live state, and results | Authenticated |
| `GET` | `/api/v1/execution/{run_id}/case` | Get case execution details, steps, and artifacts | Authenticated |
| `GET` | `/api/v1/execution/cases/{app_id}` | Get case execution history for application | Authenticated |
| `GET` | `/api/v1/execution` | List recent execution runs | Authenticated |

---

## 6. Defect Management (`/api/v1/defects`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/defects` | List quality defects with external tracking links | Authenticated |
| `POST` | `/api/v1/defects` | Create a quality defect record | Tester+ |
| `PUT` | `/api/v1/defects/{id}` | Update defect status, priority, or severity | Tester+ |
| `POST` | `/api/v1/defects/{id}/export-jira` | Push defect directly to Jira and record external issue link | Tester+ |
| `POST` | `/api/v1/defects/{id}/export-qtest` | Push defect directly to qTest and record external issue link | Tester+ |
| `DELETE` | `/api/v1/defects/{id}` | Delete a defect record | Lead+ |

---

## 7. Visual Evidence Gallery (`/api/v1/evidence`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/evidence/gallery` | Retrieve catalog of step screenshots and video recordings | Authenticated |
| `GET` | `/api/v1/evidence/file/{filename}?run_id={run_id}` | Stream an artifact recorded on an owned run | Authenticated |

---

## 8. Execution Plans (`/api/v1/execution-plans`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/execution-plans` | List execution plans | Authenticated |
| `GET` | `/api/v1/execution-plans/application/{id}` | List plans for application | Authenticated |
| `GET` | `/api/v1/execution-plans/{id}` | Get execution plan details | Authenticated |
| `POST` | `/api/v1/execution-plans` | Create execution plan | Tester+ |
| `PUT` | `/api/v1/execution-plans/{id}` | Update execution plan | Tester+ |
| `DELETE` | `/api/v1/execution-plans/{id}` | Delete execution plan | Lead+ |

---

## 9. Test Data Datasets (`/api/v1/test-data`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/test-data` | List all test datasets | Authenticated |
| `GET` | `/api/v1/test-data/application/{id}` | List datasets for application | Authenticated |
| `GET` | `/api/v1/test-data/{id}` | Get test dataset details and rows | Authenticated |
| `POST` | `/api/v1/test-data` | Create test dataset | Tester+ |
| `PUT` | `/api/v1/test-data/{id}` | Update dataset rows/fixtures | Tester+ |
| `DELETE` | `/api/v1/test-data/{id}` | Delete test dataset | Lead+ |

---

## 10. Reports & Analytics (`/api/v1/reports`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/reports/executive/overview` | Release readiness score, risk score, quality score, coverage %, defect leakage rate | Authenticated |
| `GET` | `/api/v1/reports/engineering/analytics` | Failure classification breakdown, error logs, and stack traces | Authenticated |
| `GET` | `/api/v1/reports/application/{id}/overview` | Application-specific trends and pass rate | Authenticated |

---

## 11. AI Configuration & Settings (`/api/v1/settings`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/settings/ai-configuration` | Get active AI provider, model, endpoint, and status | Authenticated |
| `POST` | `/api/v1/settings/ai-configuration/test` | Test connectivity to configured LLM provider | Lead+ |

---

## 12. Jira and qTest Integrations (`/api/v1/integrations`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/integrations/connections` | List owned, masked local connection profiles | Authenticated |
| `POST` | `/api/v1/integrations/connections` | Create a local Jira or qTest profile | Tester+ |
| `GET` | `/api/v1/integrations/environment` | Return sanitized Jira/qTest environment configuration status | Authenticated |
| `PUT` | `/api/v1/integrations/environment` | Update local Jira/qTest environment settings; tokens are write-only | Tester+ |
| `GET` | `/api/v1/integrations/connections/{id}` | View a masked local profile | Authenticated |
| `PUT` | `/api/v1/integrations/connections/{id}` | Update a local profile or write-only credential | Tester+ |
| `DELETE` | `/api/v1/integrations/connections/{id}` | Delete only the local profile | Lead+ |
| `POST` | `/api/v1/integrations/connections/{id}/test` | Validate the profile with bounded GET requests | Tester+ |
| `POST` | `/api/v1/integrations/connections/{id}/activate` | Activate a tested local profile | Tester+ |
| `POST` | `/api/v1/integrations/connections/{id}/deactivate` | Deactivate a local profile | Tester+ |
| `GET` | `/api/v1/integrations/environment` | Return sanitized Jira/qTest environment configuration status | Authenticated |
| `GET` | `/api/v1/integrations/jira/{id}/requirements` | Read bounded Jira project issues as context | Authenticated |
| `GET` | `/api/v1/integrations/qtest/{id}/assets` | Read bounded qTest assets and metadata | Authenticated |

---

## 13. Audit Trail & Governance (`/api/v1/audit`)

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/audit` | Search and filter immutable audit records | Authenticated |
