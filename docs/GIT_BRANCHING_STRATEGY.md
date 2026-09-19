# SkyWatch Git Branching Strategy & Workflow Guide

## 1. Overview & Principles

SkyWatch utilizes an enterprise Git branching strategy inspired by GitFlow and modernized for continuous delivery. This model ensures:
- **Zero broken builds on `main`**: Production code is strictly protected and deployable at all times.
- **Controlled Integration on `develop`**: The primary staging and integration branch where features merge after testing.
- **Isolated Exploration on `poc`**: A dedicated sandbox branch for rapid architectural prototyping, AI research, and exploratory proofs-of-concept without destabilizing release tracks.
- **Structured Feature Tracks**: Short-lived, focused feature branches branched from and merged back into `develop`.

---

## 2. Branch Hierarchy

```
main (Production, Stable, Tagged Releases)
  │
  ├── poc (Experimental Proof of Concepts & Sandboxing)
  │
  └── develop (Integration Branch for Active Iterations)
        │
        ├── feature/security-cleanup
        ├── feature/agentic-automation
        ├── feature/visual-regression
        ├── feature/api-testing-agent
        ├── release/v2.0.0 (Pre-Release Stabilization)
        └── hotfix/v2.0.1 (Direct Production Emergency Fixes)
```

### Core Branches

| Branch | Purpose | Protection Rules | Direct Commits? |
| :--- | :--- | :--- | :--- |
| **`main`** | Production source of record. Every commit is tagged with semantic versioning (`v2.0.0`). | Requires PR, 2 approvals, passing CI tests, linear history. | ❌ Strictly Prohibited |
| **`develop`** | Active integration branch. Contains latest merged features ready for QA and staging testing. | Requires PR, passing CI tests, code review. | ❌ Strictly Prohibited |
| **`poc`** | Experimental branch for cutting-edge agentic prototypes, architectural trials, and benchmark spikes. | Standard safety protections, allows fast-paced push for prototyping. | ⚠️ Permitted for POC spikes |

---

## 3. Supporting Branch Naming Conventions

### 1. Feature Branches (`feature/*`)
- **Source**: `develop`
- **Destination**: `develop`
- **Naming format**: `feature/<component>-<short-description>`
- **Examples**:
  - `feature/agentic-automation`
  - `feature/security-cleanup`
  - `feature/visual-regression-engine`
  - `feature/jira-qtest-connectivity`

### 2. Bugfix Branches (`bugfix/*`)
- **Source**: `develop`
- **Destination**: `develop`
- **Naming format**: `bugfix/<issue-id>-<description>`
- **Examples**:
  - `bugfix/selector-cache-ttl`
  - `bugfix/playwright-slowmo-leak`

### 3. Release Branches (`release/*`)
- **Source**: `develop`
- **Destination**: `develop` AND `main`
- **Naming format**: `release/v<major>.<minor>.<patch>`
- **Examples**:
  - `release/v2.0.0`
- **Lifecycle**: Only bug fixes, documentation updates, and release metadata changes are committed here. Once validated, merged into `main` (tagged) and back-merged into `develop`.

### 4. Hotfix Branches (`hotfix/*`)
- **Source**: `main`
- **Destination**: `main` AND `develop`
- **Naming format**: `hotfix/v<version>-<description>`
- **Examples**:
  - `hotfix/v2.0.1-auth-token-refresh`

---

## 4. Standard Workflow Walkthrough

### Step 1: Start a New Feature
```bash
# Update local develop
git checkout develop
git pull origin develop

# Branch feature
git checkout -b feature/agentic-automation
```

### Step 2: Implement & Test Locally
```bash
# Verify backend unit tests
PYTHONPATH=. .venv/bin/pytest tests/

# Verify frontend types and build
npm --prefix frontend run typecheck
```

### Step 3: Commit with Conventional Commits
Format: `<type>(<scope>): <summary>`
- `feat(orchestrator): add autonomous discovery agent and state graph builder`
- `fix(healing): resolve selector race condition during live validation`
- `security(config): scrub leaked credentials and default to skywatch.db`
- `docs(architecture): add autonomous testing engine technical specifications`

```bash
git add .
git commit -m "feat(orchestrator): implement closed-loop autonomous testing engine"
git push -u origin feature/agentic-automation
```

### Step 4: Open Pull Request
- Target branch: `develop`
- Title format matches conventional commit.
- Link relevant design documents or issues.
- Require all CI checks to pass before merging.

### Step 5: Merge Strategy
- **Feature -> Develop**: `Squash and Merge` (keeps commit history clean and atomic).
- **Release -> Main**: `Merge Commit` (preserves explicit branch release boundaries).
- **Hotfix -> Main & Develop**: `Merge Commit`.

---

## 5. Branch Strategy Comparison (SkyWatch vs. Legacy)

| Dimension | Legacy Model | SkyWatch Smart Git Strategy |
| :--- | :--- | :--- |
| **Branch Structure** | Single `main` branch with ad-hoc commits | `main` (Prod) + `develop` (Staging) + `poc` (Experimental) |
| **Feature Isolation** | Uncontrolled changes directly on main | Dedicated `feature/*` branches with PR gates |
| **Credential Hygiene** | Environment files and credentials committed | Strict `.gitignore`, write-only tokens, zero secrets tracked |
| **Release Management** | Manual tagging without release branches | Formal `release/vX.Y.Z` hardening cycle |
| **Hotfix Pipeline** | Commits placed directly on top of dev work | Clean cherry-pick hotfixes directly targeting `main` and `develop` |
