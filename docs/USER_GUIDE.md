# AI QA Engine - User Guide

## 1. What this app does

This app helps you:

- connect test applications
- generate or import test cases
- run automated web tests
- review execution results and defects

## 2. Sign in

1. Open `http://127.0.0.1:3000`
2. Enter your account credentials
3. Click **Sign in**

### Start locally with one command (Windows)

From project root:

```powershell
.\scripts\start-local.ps1
```

To stop both frontend and backend:

```powershell
.\scripts\stop-local.ps1
```

### Presentation mock mode (for demos)

If you need full sample content on every page for a showcase:

1. Open `http://127.0.0.1:3000/?mock=1` (or any page route with `?mock=1`)
2. Click **Enable mock mode** in the header (shows **Mock mode: ON** when active)
3. Navigate across all tabs to present preloaded demo applications, cases, runs, reports, and defects

Notes:
- Mock mode is read-only and safe for demos.
- To return to live backend data, click **Mock mode: ON** to disable it.

## 3. Select your application

Use the **Application** dropdown (Overview/Test cases/Test execution/AI generator).  
The selected app is shared across pages.

## 4. Add applications

Go to **Applications**:

- **Web app**: add name + target URL
- **Android/iOS app**: upload `.apk` or `.ipa` artifact

## 5. Manage test cases

Go to **Test cases**:

- upload CSV/XLSX to import cases
- review rows in library format
- use **Clear drafts** to remove only draft cases

## 6. AI Generator workflow

Go to **AI generator**:

1. Select application
2. Enter target URL (web)
3. Enter prompt
4. Set case count and advanced options
5. Click **Generate comprehensive suite**

Options:

- Replace existing drafts
- Open Test cases after generation
- Open Test execution after generation
- Run generated test cases immediately (web only)

After generation:

- review in **Generated case preview**
- download generated template CSV
- open **Test cases** or **Test execution**

## 7. Run automated tests

Go to **Test execution**:

1. Select application
2. Run all module cases or run latest generated cases
3. Watch status progress (queued/running/passed/failed/error)
4. Review run details and logs

## 8. Reports and Test suites

- **Reports**: application-level run totals, pass/fail trends, and defect load
- **Test suites**: candidate grouping view by application and case readiness

## 9. Best practices

- Keep prompts specific (module names + expected behaviors)
- Use real target URLs
- Configure and test one explicit AI provider before clicking Generate AI
- Keep draft cleanup before major re-generation
- Review generated rows before production-signoff runs

## 10. Common issues

- **No AI output**: check the selected provider, credentials, endpoint, and model in AI Settings
- **401/Session expired**: sign in again
- **Execution fails at login**: verify backend login secrets and selectors
- **UI misalignment**: hard refresh (`Ctrl+F5`)







***********************************************


