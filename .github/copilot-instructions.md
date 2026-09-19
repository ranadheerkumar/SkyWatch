# Workspace Delivery Policy

## Automatic source-change publishing

When completing a requested change to frontend/UI code or application source code in this repository:

1. Select and increment the application SemVer in `frontend/package.json` for every pushed commit: patch for fixes and documentation/workflow changes, minor for backwards-compatible capabilities, and major for breaking changes. Keep `frontend/package-lock.json` synchronized and update `docs/Changelog.md`.
2. Run the narrowest relevant validation first, then the applicable repository gates. If the user explicitly asks to defer or ignore tests, prioritize the implementation and bug fix, skip test creation and test-suite execution unless needed to diagnose a concrete failure, and report the skipped tests. Lightweight compile, typecheck, lint, build, migration, security, and secret-safety checks may still be used when they directly protect the change.
3. Run `node scripts/verify-version.mjs --require-bump` before committing; CI enforces the committed version increase with `node scripts/verify-version.mjs --require-history-bump`.
4. Review `git status`, `git diff --check`, and `git diff --stat`.
5. Stage only the intended source, test, configuration, and documentation files.
6. Create a concise reviewable commit.
7. Push the commit to the current branch's configured upstream remote (`origin/AutomationTool_POC`). Do NOT sync, merge, or push changes to `AutomationTool_POC_lkurra`.
8. Confirm the local branch and configured upstream resolve to the same commit, then report the commit and validation results.

Do not automatically publish when the user explicitly asks to keep changes local, when validation exposes unresolved failures, when the branch has no configured upstream, or when authentication/conflict issues block a safe push. Report the blocker and exact next command instead.

Never stage or push secrets, `.env` files, credentials, tokens, generated databases, logs, screenshots, videos, traces, build output, local runtime data, or unrelated user changes. If unrelated changes are mixed into the worktree, preserve them and keep them out of the commit unless the user explicitly asks to publish them too.

## Development-first mode

When the user says to focus on development and fixes for now:

- Implement the requested behavior and repair the owning code path first.
- Do not add, expand, or run tests unless the user asks for them or a concrete failure cannot be diagnosed safely without one.
- Keep existing tests and contracts intact unless the implementation requires a necessary compatibility update.
- Report deferred test work clearly; this preference does not permit skipping security, secret handling, migration safety, compile correctness, or unrelated-change safeguards.

Documentation-only changes follow the normal commit workflow unless the user asks for immediate publication. Changes that include frontend/UI or application source code use the automatic publishing workflow above.

## Current project contracts

- Treat `docs/` as the canonical documentation tree. Do not recreate the removed root `doc/` tree.
- Preserve application-scoped `application_id` context across test cases, automation, AI jobs, runs, evidence, defects, recommendations, suites, and reports.
- AI generation is Discovery-first, Planner-first, and Generator-batched: it uses uploaded requirements, bounded target discovery, and source anchors, persists durable job stages, and must not invent unrelated cases when source context is available.
- Execute Tests queues independent case runs with bounded one-to-five worker concurrency and isolated browser contexts. Use run IDs when diagnosing parallel activity; Redis/RQ needs multiple worker processes for equivalent throughput. Runs and batches support immediate user-initiated stopping/cancellation (`POST /api/v1/execution/{run_id}/cancel` and `POST /api/v1/execution/batch/{batch_id}/cancel`).
- AI generation runs as durable background jobs (`POST /api/v1/ai-generation/jobs`); the frontend maintains background polling across navigation and page switches so generation continues uninterrupted.
- A successful same-action locator repair is validated, persisted to the test case automation, recorded as an `auto_applied` healing recommendation, and audited. Never change business actions, assertions, credentials, or unrelated steps automatically.
- Existing and AI-generated test cases use the persisted numbered `steps` string and the interactive step editor. Preserve that API format when editing, adding, or deleting steps.
- Run History is the reference data surface for filters, sorting, pagination, status presentation, table density, and contained scrolling.
- Autonomous Orchestrator (`docs/AUTONOMOUS_TESTING_ENGINE.md`): Closed-loop orchestration coordinating Discover → Plan → Execute → Diagnose → Self-Heal → Learn → Report with parallel execution and adaptive circuit breakers.
- Visual Regression Engine (`docs/VISUAL_REGRESSION_ENGINE.md`): Baseline snapshot capture, structural DOM hashing, and pixel diff classification across responsive viewports (Desktop, Tablet, Mobile).
- API Testing Agent (`docs/API_TESTING_AGENT.md`): OpenAPI/Swagger auto-discovery, schema contract validation, negative/boundary payload generation, and latency profiling.
- Observability & Rate Limiting (`docs/OBSERVABILITY_GUIDE.md`): Token bucket rate limiting per endpoint group, circuit breaking, and aggregated metric telemetry (`/api/v1/observability/metrics`).
- Multi-LLM Architecture: Dynamic cascade supporting Google Gemini, GitHub Copilot, OpenAI, Anthropic, and Azure based on available environment credentials with zero generic fallback lock-in.
- Enterprise ALM Bridge (`docs/JIRA_QTEST_INTEGRATION_GUIDE.md`): Jira Cloud REST API v3 with Atlassian Document Format (ADF v1), bi-directional issue linking, multipart attachment uploads, and workflow transitions; Tricentis qTest SaaS Build API hierarchy (`/projects/{projectId}/builds`), auto-test-logs execution reporting, and dynamic custom field validation. Respect `ENABLE_JIRA_WRITE` and `ENABLE_QTEST_WRITE` safety controls.
