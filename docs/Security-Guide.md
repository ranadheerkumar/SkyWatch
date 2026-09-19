# Security Guide

This guide defines the security baseline for local development, staging, and production operation of AI QA Engine. It complements the [enterprise modernization report](ENTERPRISE_MODERNIZATION_REPORT.md) and should be updated with every security-sensitive release.

## Security Boundary

AI QA Engine can fetch and automate web targets, handle uploaded mobile packages, call external AI providers, and serve execution evidence. Treat all four capabilities as security-sensitive. Run tests only against applications owned by the organization or explicitly authorized for testing.

## Required Production Controls

- Set a unique high-entropy `SECRET_KEY`; never use the example or development value.
- Use PostgreSQL and Redis through the production deployment contract.
- Provide AI and target-application credentials through the configured secret provider, not test definitions or source control.
- Keep `ALLOW_PRIVATE_TARGETS=false` unless an explicit, reviewed network allowlist and egress policy are in place.
- Restrict the API behind TLS, an authenticated ingress, and network policy.
- Run frontend and backend containers as non-root users with CPU, memory, and ephemeral-storage limits.
- Store screenshots, videos, traces, logs, and uploaded packages in access-controlled storage with retention and deletion policies.
- Apply rate limits and quotas to login, AI generation, execution, upload, and artifact endpoints.
- Enable centralized audit logs, correlation IDs, dependency scanning, secret scanning, and container scanning.

## Authentication and Authorization

The current API uses JWT bearer authentication, PBKDF2 password hashing, and role checks for protected operations. JWT storage and revocation remain hardening work: browser local storage is not an acceptable long-term token strategy for an enterprise deployment, and compromised tokens need revocation or session-version invalidation.

Every resource read or mutation must authorize the relationship between the principal and the resource. In particular, artifact access must verify run ownership or an explicit project-level permission; a filename or opaque artifact ID is not an authorization decision.

## Target Network Policy

Target validation blocks private and reserved network ranges by default. A production allowlist should additionally constrain:

- approved schemes and ports;
- DNS resolution and redirect destinations;
- private, loopback, link-local, and metadata-service ranges;
- maximum response size and request duration;
- browser context permissions and downloaded content;
- per-project target ownership and environment.

Every blocked or overridden target attempt should create a security event with the principal, project, target classification, and correlation ID, without logging credentials.

## Secrets and Sensitive Data

Never commit passwords, API keys, access tokens, private keys, or production connection strings. Do not put secrets in test titles, steps, expected results, screenshots, videos, traces, prompts, provider responses, or exception text. Redact sensitive values before persistence and before sending logs to a third-party provider.

Rotate any credential that has appeared in source control, logs, screenshots, terminal output, or a shared prompt. Environment example files may contain placeholders only.

## Uploads and Evidence

Validate upload size, MIME type, extension, storage path, and malware policy before persisting mobile packages or imported data. Keep user uploads and execution artifacts outside the source tree. Serve artifacts through an authorization-aware endpoint or signed, short-lived object-storage URL. Apply content-disposition and content-type headers deliberately; do not execute uploaded content.

Define retention by project and artifact type. Delete expired objects and associated metadata through an auditable job rather than manual filesystem cleanup.

## Incident Response

1. Disable or rotate the affected credential or signing key.
2. Revoke active sessions or increment the session version.
3. Preserve correlation IDs, audit events, queue records, and artifact metadata needed for investigation.
4. Restrict target egress and artifact access while scope is assessed.
5. Patch dependencies and redeploy from a known-good commit.
6. Record the event, affected resources, containment, recovery, and follow-up controls.

## Release Checklist

- [ ] No default production secrets are present.
- [ ] `npm audit --omit=dev --audit-level=high` passes.
- [ ] `pip-audit -r backend/requirements.txt` passes.
- [ ] Authentication, authorization, SSRF, upload, and artifact tests pass.
- [ ] Migration and backup/restore checks pass.
- [ ] Secret, SAST, and container scans pass.
- [ ] Retention and incident contacts are documented for the deployment.
