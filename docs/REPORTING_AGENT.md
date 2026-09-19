# Reporting Agent

**Current status:** Implemented as read-only report and Run History aggregation; autonomous reporting agent is future work
**Runtime:** `backend/app/api/v1/reports.py`, `backend/app/services/report_service.py`, and frontend report/Run History surfaces

## Responsibility

The Reporting Agent boundary explains execution quality, coverage, risk, defects, trends, and run outcomes using application-scoped records. It should remain read-only with respect to business test cases and automation.

## Current behavior

- aggregates run status, pass rate, duration, failure, and defect signals;
- presents Run History with filtering, sorting, pagination, annotations, and direct detail navigation;
- renders application/project quality summaries and recent failures;
- preserves application and run context in report views;
- exposes report APIs for application, executive, and engineering analytics where implemented.

## Guardrails

- Never mix applications or workspaces in a report without an explicit scope.
- Label derived metrics and incomplete data clearly.
- Link summary outcomes to Run History and evidence details.
- Do not mutate test cases, automation, defects, or execution records as a reporting side effect.

## Future hardening

Implement a versioned analytics model, server-side filtering and pagination, scheduled reports, export packages, requirement-to-run traceability, anomaly/risk recommendations, cost budgets, and report-quality evaluation. Keep report generation auditable and read-only by default.
