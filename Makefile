.PHONY: version-check version-bump-check frontend-install frontend-typecheck frontend-test frontend-build backend-install backend-migrate backend-compile backend-test security-audit ci

version-check:
	node scripts/verify-version.mjs

version-bump-check:
	node scripts/verify-version.mjs --require-bump

frontend-install:
	npm --prefix frontend ci

frontend-typecheck:
	npm --prefix frontend run typecheck

frontend-test:
	npm --prefix frontend run test

frontend-build:
	npm --prefix frontend run build

backend-install:
	python -m pip install -r backend/requirements-dev.txt

backend-migrate:
	cd backend && python -m app.core.migration_bootstrap

backend-compile:
	python -m compileall -q backend/app

backend-test:
	python -m pytest -q backend/tests

security-audit:
	npm --prefix frontend audit --omit=dev --audit-level=high
	python -m pip_audit -r backend/requirements.txt

ci: version-check frontend-typecheck frontend-test frontend-build backend-migrate backend-compile backend-test security-audit
