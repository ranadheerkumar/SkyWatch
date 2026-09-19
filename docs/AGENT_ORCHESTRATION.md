# Agent Orchestration

**Current status:** Durable server-owned orchestration for AI test design
**Runtime:** `backend/app/services/ai_generation_jobs.py` and `backend/app/services/ai_generation_pipeline.py`

## Current orchestration

The durable AI generation job controls stage order and persists every transition:

1. Document Analysis
2. Application Discovery
3. Context Builder
4. Playwright Planner
5. Test Scenario
6. Test Case Generator
7. Test Data Generator
8. Validation
9. Repository

The Planner and Generator use the configured provider boundary. Discovery uses bounded HTTP/Playwright inspection and exercises safe same-origin controls for exploratory state observations; authenticated discovery is reused by Planner and Generator, and harvests live DOM entities for the Self-Learning Engine. Context, Scenario, Test Data Generator, Validation, and Repository form deterministic and adaptive reliability boundaries. Each job stores stage status, progress, details, metrics, timestamps, definition versions, and checksums, including exploratory observation and charter counts.

## Execution orchestration

After Repository produces business cases and compiled automation, Execute Tests creates independent run IDs. The UI schedules up to five cases concurrently, while each worker owns one browser context, status stream, evidence set, and failure record. Run History is the detailed outcome surface.

## Event and provenance contract

Every stage or operational handoff should carry:

- `application_id` and user ownership;
- durable job or run ID;
- agent key, definition version, and checksum;
- status, phase, timestamps, metrics, and warnings;
- source/document/plan/case/artifact references;
- redaction and authorization context.

The current job persists structured snapshots and the console polls those snapshots. Execution also emits `LIVE_EVENT` lines for compatibility; structured event storage is a future hardening step.

## Failure policy

- Provider failures are surfaced as stage errors; no stage silently substitutes another provider or invents output.
- Discovery limitations are recorded as warnings and lower context confidence.
- Validation failures prevent unsafe repository output.
- Healing can auto-apply only a validated same-action locator repair.
- Business-flow, assertion, credential, test-data, or destructive changes require human review.
- A failure in one parallel execution case must not corrupt sibling run records.

## Future orchestration

Add an explicit agent event envelope, durable event stream, per-agent retry/budget/circuit-breaker policy, cancellation, dead-letter handling, workflow resume, and requirement-to-evidence traceability. Do not introduce a second orchestration framework beside the current durable job and agent-definition registry.
