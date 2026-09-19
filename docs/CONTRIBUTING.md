# Contribution and Source-Control Workflow

## Required Change Workflow

Every build-affecting change must be documented and committed as one reviewable unit.

1. Make the smallest focused code or configuration change.
2. Increment the application SemVer in `frontend/package.json` and synchronize `frontend/package-lock.json`.
3. Update the relevant technical or user documentation under `docs/`.
4. Update [Changelog.md](Changelog.md) in the same change. Use `Added`, `Changed`, `Fixed`, `Security`, or `Breaking` as appropriate.
5. Run `node scripts/verify-version.mjs --require-bump` before committing.
6. Run the narrowest relevant validation first, then the repository gates:
   - frontend typecheck, tests, and production build;
   - backend compile and focused/backend tests;
   - migration validation when schema or persistence changes;
   - dependency/security audits when manifests, containers, or security-sensitive code changes;
   - `git diff --check` and documentation link checks when documentation changes.
7. Review `git status` and `git diff --stat`. Do not stage `.env` files, credentials, tokens, generated databases, logs, screenshots, videos, traces, build output, or local runtime data.
8. Stage only the intended source, documentation, test, and configuration files.
9. Create a commit after validation. Do not leave a validated build change only in the working tree.
10. For frontend/UI or application source-code changes, push the validated commit to the current branch's configured upstream remote (`origin/AutomationTool_POC`). Do not sync or push to `AutomationTool_POC_lkurra`. Skip publication only when the user asks to keep changes local, validation has unresolved failures, no upstream is configured, or authentication/conflicts block a safe push.

## Versioning

`frontend/package.json` is the canonical application version. Every pushed commit must increase that version and update the lockfile. Use `node scripts/verify-version.mjs --require-bump` before a commit; CI compares the pushed commit with its parent using `--require-history-bump`.

## Commit Standard

Use a concise imperative commit subject that describes the change, for example:

```text
feat: expose generation lifecycle in AI console
fix: align responsive workspace panels
chore: update execution documentation
```

One commit may contain several tightly related files. Unrelated user changes must remain untouched and must not be folded into a commit without explicit confirmation.

## Changelog Standard

A changelog entry is required for:

- user-visible behavior or UI changes;
- API, schema, configuration, dependency, or deployment changes;
- security, reliability, performance, or operational changes;
- documentation or repository workflow changes that affect contributors.

The entry should state the outcome, not only the implementation detail. Keep `docs/Changelog.md` as the canonical release history; do not maintain a second release history outside `docs/`.

## Build and Commit Relationship

A successful build must be followed by the repository delivery policy for source changes. The expected lifecycle is:

```text
edit -> update docs/changelog -> validate -> review diff -> commit -> push source changes
```

CI validates commits after they are pushed or submitted in a pull request. It does not create commits or push local working-tree changes back to the repository.

## Exception Handling

If validation cannot run, record the unavailable command and reason in the handoff or pull request. Do not claim a clean build. If a changelog update or commit is intentionally deferred, record the reason and owner before handing off the work.
