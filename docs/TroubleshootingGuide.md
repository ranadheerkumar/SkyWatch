# AI-QA-Engine · Troubleshooting & Debugging Guide

## 1. Common Issues & Quick Solutions

### A. Port Conflict (`Port 3000 / 3001 already in use`)
- **Symptom:** Next.js fails to start with `EADDRINUSE: address already in use :::3000`.
- **Solution:** Pass custom port parameters to `start-local.ps1`:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -FrontendPort 3002 -BackendPort 8000
  ```

### B. Playwright Browser Installation Missing
- **Symptom:** Worker fails with `Executable doesn't exist at C:\Users\...\chromium\chrome.exe`.
- **Solution:** Install browser binaries inside the backend Python environment:
  ```powershell
  cd backend
  .\.venv\Scripts\python.exe -m playwright install chromium
  ```

### C. Stale Next.js Development Cache
- **Symptom:** Chunk load errors or stale React components.
- **Solution:** Clean `.next` and `.next-dev` directories:
  ```powershell
  cd frontend
  npm run clean:next
  ```

### D. Missing Authentication Credentials During Test Execution
- **Symptom:** Automated execution stops on login screen with invalid credentials error.
- **Solution:** Enable **Run login flow** and provide non-empty `login_email` and `login_password` runtime parameters in the execution UI:
  ```bash
  login_email=<authorized-user-email>
  login_password=<authorized-password>
  ```

---

## 2. Playwright Selector Debugging Tips

When an action step fails with a locator timeout:
1. Verify if the target application uses custom Web Components or shadow DOM.
2. Ensure you use the semantic prefix:
   - `label=Owner Last Name` for inputs with associated labels.
   - `text=Find Owner` for buttons or clickable text.
   - `#owner_last_name` for direct DOM IDs.
3. Switch execution mode to **Watch live (visible browser)** in the UI to visually trace the green highlight box on elements as they are clicked.
