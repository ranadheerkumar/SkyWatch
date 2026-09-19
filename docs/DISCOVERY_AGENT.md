# Application Discovery Agent

**Current status:** Implemented bounded HTTP/Playwright discovery plus safe exploratory stage
**Definition:** [`.github/agents/application-discovery.agent.md`](../.github/agents/application-discovery.agent.md)
**Runtime:** `backend/app/services/ai_service.py::discover_application_context`

## Responsibility

The Application Discovery Agent builds a reusable map of an authorized target before planning or generation. It captures observable structure, performs a bounded read-only exploratory pass, and separates observed behavior from hypotheses that still require verification.

## Inputs

- selected application target URL;
- authorized target scope;
- bounded timeout and item limits;
- optional rendered target access.

## Outputs

- source URL and page title;
- headings, buttons, links, and input hints;
- same-origin observed route signals;
- bounded safe exploratory interactions and resulting state signals;
- exploratory hypotheses and follow-up charters for planning;
- fetch/render limitations;
- control, route, input, and exploratory metrics persisted in the generation job result.

## Guardrails

- Stay within the authorized target origin.
- Keep snapshots bounded and redact credentials or sensitive values.
- Treat discovery as supporting evidence; uploaded requirements remain authoritative.
- Exercise only safe same-origin navigation, tabs, menus, filters, and disclosure controls; never submit, save, delete, upload, approve, purchase, or log out.
- Do not mutate the target, test cases, or automation.
- Record failures as limitations so downstream agents can adjust confidence.

## Future hardening

Add richer authenticated multi-page exploration, role-aware workflow mapping, route graph persistence, change detection between snapshots, and approval for target scopes that could expand beyond the initial origin.
