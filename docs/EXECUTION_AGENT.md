# Execution Agent

**Current status:** Implemented as a governed operational worker; independent AI-agent contract is future work
**Runtime:** `backend/app/services/run_queue.py` and `backend/app/services/test_execution.py`

## Responsibility

The Execution Agent boundary prepares and runs independently scoped test cases, monitors their run IDs, reports outcomes, and hands evidence and failures to downstream surfaces. It is intentionally operational today rather than an LLM decision-maker.

## Current behavior

- queues one run per test case;
- supports bounded one-to-five parallel workers in Execute Tests;
- uses isolated Playwright browser contexts;
- applies runtime parameters and protected secret resolution;
- emits live execution events;
- records step/check results, failure classification, and run timing;
- invokes bounded locator healing when enabled;
- leaves business assertions and test intent unchanged.

## Inputs and outputs

Inputs include application target, compiled automation, checks, runtime parameters, execution mode, evidence settings, and healing policy. Outputs include a run record, per-case status, diagnostics, artifacts, failure category, and optional learned locator recommendation.

## Guardrails

- Require an owned application and authorized target.
- Keep each case, browser context, evidence set, and run ID isolated.
- Bound worker concurrency and browser/resource usage.
- Never log credentials or replace a failed assertion with a weaker one.
- Preserve `application_id`, test-case ID, run ID, and audit context.

## Future hardening

Promote the boundary to a durable Execution Agent with environment/data preparation contracts, retries and cancellation, worker heartbeat, idempotency, queue health, capacity limits, and structured agent events. Keep the Playwright executor deterministic and observable beneath that agent.
