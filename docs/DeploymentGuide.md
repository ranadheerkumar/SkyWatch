# AI-QA-Engine · Deployment & Operations Guide

## 1. Local Development Deployment

### Prerequisites
- Python 3.11+
- Node.js 20.9+
- npm 9+
- PowerShell 5.1+ (Windows) or Bash (Linux/macOS)

### One-Command Startup
From the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -FrontendPort 3002 -BackendPort 8000
```

- **Frontend Portal:** `http://127.0.0.1:3002`
- **Backend API:** `http://127.0.0.1:8000`
- **Interactive Swagger Docs:** `http://127.0.0.1:8000/docs`

### Stopping Services
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

---

## 2. Docker & Container Deployment

### Docker Compose
```bash
docker compose up -d --build
```

Services started:
- `frontend`: Next.js production web server on port 3000
- `backend`: FastAPI API server on port 8000
- `redis`: Redis job queue broker on port 6379
- `worker`: Background RQ Playwright execution worker

---

## 3. Production Deployment Status

The repository currently provides a production-oriented Docker Compose baseline in `docker-compose.prod.yml`. Kubernetes manifests are not included; a Kubernetes deployment should be created only after the migration, artifact-storage, secrets, and worker-readiness contracts in the modernization report are approved.

The backend and queue worker build from the repository root so `.github/agents/` is available inside the image. This keeps Planner, Discovery, Generator, Validator, Repository, and Healer definition provenance consistent between local source execution and Compose deployments.

---

## 4. Environment Variables Checklist

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite:///./ai-qa-engine.db` | Main database connection string (SQLite or PostgreSQL) |
| `SECRET_KEY` | `change-me-before-production` | JWT signing secret |
| `AI_PROVIDER` | `github_copilot` | Explicit LLM inference provider (`github_copilot`, `openai`, `azure_openai`, `anthropic`, `gemini`, or `local`) |
| `AI_MODEL` | `gpt-4.1` | Model name |
| `AI_API_KEY` | `""` | API key for cloud inference |
| `AI_ENDPOINT` | `https://api.openai.com/v1` | Base API URL |
| `ALLOW_PRIVATE_TARGETS` | `false` | Allow localhost / private test targets; keep disabled unless an explicit allowlist is configured |
