# AI QA Engine frontend

The frontend is a Next.js 16 App Router workspace implementing the supplied AI QA Engine QA mock. Node.js 20.9 or newer is required.

## Commands

```bash
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
npm run typecheck
npm run test
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

## Main workflow

The main screen is implemented in `src/app/page.tsx`. It provides client-side navigation for:

- Overview dashboard
- Projects
- Applications
- Test cases
- Test execution
- Defects

Application registration is implemented in `src/components/ApplicationCapture.tsx`. Web targets require an HTTP(S) URL. Android and iOS targets accept `.apk` and `.ipa` files through a drag-and-drop or file-picker control. Authenticated application records and uploaded mobile artifacts are persisted by the backend API.

The Test Execution view calls `POST /api/v1/execution/run` for the selected Web application. The AI Generator creates durable jobs through `POST /api/v1/ai-generation/jobs`. Set `NEXT_PUBLIC_API_URL` when the backend is not running at `http://127.0.0.1:8000`. Android and iOS package records are persisted, but mobile execution still requires a configured Appium provider and device/emulator.

## Developer setup

From the repository root on Windows:

```powershell
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Run the backend separately from `backend` using the commands in [`docs/DEVELOPER_GUIDE.md`](../docs/DEVELOPER_GUIDE.md). The frontend uses `NEXT_PUBLIC_API_URL` when provided and otherwise defaults to `http://127.0.0.1:8000`.

For requested frontend/UI changes, run the relevant checks, commit only intended files, and push the validated commit to the current branch's configured upstream. Keep secrets, generated output, runtime data, and unrelated changes out of the commit. See the workspace [`copilot-instructions.md`](../.github/copilot-instructions.md) and [`docs/CONTRIBUTING.md`](../docs/CONTRIBUTING.md).