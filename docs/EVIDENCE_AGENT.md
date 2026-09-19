# Evidence Agent

**Current status:** Implemented as an execution-owned evidence capability; standalone agent is future work
**Runtime:** `backend/app/services/test_execution.py` and `frontend/src/components/ExecutionSummaryPanel.tsx`

## Responsibility

The Evidence Agent boundary captures and presents the proof of execution: screenshots, highlighted target screenshots, video, traces, console diagnostics, network failures, timings, and failed-step context.

## Current behavior

- captures step and final screenshots when enabled;
- preserves highlighted target screenshots before overlay cleanup;
- records video and optional redacted narration audio;
- captures Playwright traces according to `off`, `on_failure`, or `always` policy;
- records console and network diagnostics on the run result;
- serves artifacts only through owned run and recorded filename checks;
- presents evidence before the step timeline in run details.

## Guardrails

- Scope every artifact to its run and application.
- Never include credentials or secret values in screenshots, narration, logs, or recommendations.
- Keep artifact paths controlled and access-authorized.
- Preserve evidence on failure for diagnosis and cleanup according to retention policy.

## Future hardening

Promote evidence collection to a durable agent with an artifact manifest, requirement/scenario/step links, object storage, encryption, signed access, retention classes, deletion verification, and evidence-quality checks.
