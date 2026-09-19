"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, apiFetchBlob } from "../lib/api";
import { formatDuration } from "../lib/formatDuration";
import { useAuth } from "../hooks/useAuth";
import ExecutionSummaryPanel from "./ExecutionSummaryPanel";
import WorkspaceShell from "./navigation/WorkspaceShell";
import { navigationGroups, navigationItems, sectionPaths } from "./navigation/navigationConfig";
import type { Section } from "../types";

type FailureType =
  | "LOCATOR"
  | "TIMING"
  | "NAVIGATION"
  | "AUTHENTICATION"
  | "TEST_DATA"
  | "ENVIRONMENT"
  | "NETWORK"
  | "ASSERTION"
  | "APPLICATION_DEFECT"
  | "AUTOMATION_DEFECT"
  | "UNKNOWN";

type ExecutionStep = {
  action: string;
  selector?: string;
  value?: string;
  secret_name?: string;
};

type StepResult = {
  index: number;
  action: string;
  selector?: string | null;
  passed: boolean;
  message: string;
  duration_ms: number;
};

type ExecutionArtifact = {
  type: "screenshot" | "video" | "trace";
  path: string;
  label: string;
  step_index?: number | null;
};

type ExecutionResult = {
  run_id: string;
  url: string;
  status: "passed" | "failed" | "error";
  failure_type?: FailureType | null;
  failure_summary?: string | null;
  title?: string;
  duration_ms: number;
  audio_status?: "embedded" | "unavailable" | "disabled";
  checks: Array<{ type: string; value: string; passed: boolean; message: string }>;
  step_results?: StepResult[];
  step_artifacts?: ExecutionArtifact[];
  artifacts?: ExecutionArtifact[];
  console_errors?: string[];
  network_errors?: string[];
  error?: string;
  healer_agent?: string | null;
  healed_steps?: Array<{ index: number; reason?: string }>;
};

type ExecutionDetail = {
  run_id: string;
  test_case_id?: number | null;
  status: "queued" | "running" | "passed" | "failed" | "error";
  run_status: "queued" | "running" | "passed" | "failed" | "error";
  application_id?: number;
  steps?: ExecutionStep[];
  created_at?: string;
  finished_at?: string;
  result?: ExecutionResult | null;
  log?: string;
  live_state?: string | null;
  current_action?: string | null;
};

function formatTimestamp(value?: string) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatFailureType(value?: FailureType | string | null) {
  if (!value) return "-";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function failureGuidance(value?: FailureType | string | null) {
  switch (value) {
    case "LOCATOR": return "The requested element was not found or was not visible. Verify the selector against the current page DOM.";
    case "TIMING": return "The page or element did not become ready before the wait expired. Check page load state, selector stability, and target responsiveness.";
    case "NAVIGATION": return "Navigation did not reach the expected page or URL. Verify the preceding action and session state.";
    case "AUTHENTICATION": return "The run was not authenticated as expected. Verify credentials, login state, and protected-page redirects.";
    case "TEST_DATA": return "The workflow reached a data-dependent step but the supplied value was missing, invalid, or not present in the target environment.";
    case "ENVIRONMENT": return "The browser or execution environment became unavailable before the run completed.";
    case "NETWORK": return "The target or a dependent request failed at the network layer. Check service availability and request diagnostics.";
    case "ASSERTION": return "The workflow reached an assertion, but the expected text, title, URL, or state was not present.";
    case "APPLICATION_DEFECT": return "The workflow completed far enough to expose behavior that does not match the expected application result.";
    case "AUTOMATION_DEFECT": return "The generated action or selector does not match the target page interaction.";
    default: return "The execution failed before a more specific failure category could be established.";
  }
}

function parseLiveEvents(log?: string) {
  return (log ?? "")
    .split(/\r?\n/)
    .filter((line) => line.startsWith("LIVE_EVENT|"))
    .map((line) => {
      const [, state, ...messageParts] = line.split("|");
      return { state: state || "EVENT", message: messageParts.join("|") || "" };
    });
}

function artifactFilename(path: string) {
  return path.split(/[\\/]/).pop() || "execution-artifact";
}

function ArtifactMedia({ artifact, token, runId }: { artifact: ExecutionArtifact; token: string; runId: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setUrl("");
    setError("");
    const filename = artifactFilename(artifact.path);
    if (!token || !filename || !runId) return () => undefined;

    void apiFetchBlob(`/api/v1/evidence/file/${encodeURIComponent(filename)}?run_id=${encodeURIComponent(runId)}`, token)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to load artifact.");
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifact.path, runId, token]);

  if (error) return <p className="fail">{error}</p>;
  if (!url) return <p className="muted">Loading {artifact.type}...</p>;
  if (artifact.type === "screenshot") {
    return <img className="execution-artifact-image" src={url} alt={artifact.label} />;
  }
  if (artifact.type === "video") return <video className="execution-artifact-video" controls preload="metadata" src={url} />;
  return <p className="muted">Playwright trace ZIP is ready.</p>;
}

function ArtifactDownload({ artifact, token, runId }: { artifact: ExecutionArtifact; token: string; runId: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    const filename = artifactFilename(artifact.path);
    if (!token || !filename || !runId) return () => undefined;
    void apiFetchBlob(`/api/v1/evidence/file/${encodeURIComponent(filename)}?run_id=${encodeURIComponent(runId)}`, token)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to prepare download.");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifact.path, runId, token]);

  if (error) return <span className="fail">{error}</span>;
  if (!url) return <span className="muted">Preparing download...</span>;
  return (
    <a className="execution-artifact-download" href={url} download={artifactFilename(artifact.path)}>
      Download {artifact.type}
    </a>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = normalized === "passed" ? "success" : normalized === "failed" || normalized === "error" ? "danger" : "info";
  return <span className={`execution-run-status execution-run-status-${tone}`}>{status}</span>;
}

export default function ExecutionRunDetailsPage() {
  const params = useParams<{ runId: string }>();
  const router = useRouter();
  const runId = String(params?.runId ?? "");
  const { token, clearToken } = useAuth();
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    if (!runId || !token) {
      setLoading(false);
      if (!token) setError("Sign in to inspect execution details.");
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const load = async () => {
      setLoading(true);
      try {
        const nextDetail = await apiFetch<ExecutionDetail>(`/api/v1/execution/${encodeURIComponent(runId)}/case`, {}, token);
        if (cancelled) return;
        setDetail(nextDetail);
        setError("");
        if (["queued", "running"].includes(nextDetail.run_status)) {
          timer = window.setTimeout(() => void load(), 1500);
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to load execution details.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runId, token]);

  const result = detail?.result ?? null;
  const stepResults = result?.step_results ?? [];
  const plannedSteps = detail?.steps ?? [];
  const steps = useMemo(() => {
    if (stepResults.length) {
      return stepResults.map((step) => ({
        index: step.index,
        action: step.action,
        selector: step.selector || "-",
        passed: step.passed,
        message: step.message,
        durationMs: step.duration_ms,
      }));
    }
    return plannedSteps.map((step, index) => ({
      index: index + 1,
      action: step.action,
      selector: step.selector || step.value || "-",
      passed: false,
      message: "Result pending",
      durationMs: 0,
    }));
  }, [plannedSteps, stepResults]);
  const stepArtifacts = result?.step_artifacts ?? [];
  const liveEvents = parseLiveEvents(detail?.log);
  const workerLog = (detail?.log ?? "")
    .split(/\r?\n/)
    .filter((line) => !line.startsWith("LIVE_EVENT|"))
    .join("\n")
    .trim();
  const screenshotByStep = new Map(stepArtifacts.filter((artifact) => artifact.step_index).map((artifact) => [artifact.step_index as number, artifact]));
  const detailNavigationGroups = navigationGroups.map((group) => ({
    id: group.id,
    label: group.label,
    items: navigationItems.filter((item) => group.sections.includes(item.id)),
  }));
  const navigateToSection = (section: string) => {
    const path = sectionPaths[section as Section];
    if (path) router.push(path);
  };
  const [loggedDefectId, setLoggedDefectId] = useState<number | null>(null);
  const [loggingDefect, setLoggingDefect] = useState(false);

  const handleLogDefectFromRun = async () => {
    if (!result || !token) return;
    setLoggingDefect(true);
    try {
      const failedSteps = result.step_results?.filter((s) => !s.passed) ?? [];
      const failedChecks = result.checks?.filter((c) => !c.passed) ?? [];
      const firstFailedStep = failedSteps[0];
      const failureReason = firstFailedStep?.message || result.error || result.failure_summary || "Step assertion failed";
      const failureCategory = result.failure_type || "ASSERTION";
      const evidence = [...(result.artifacts ?? []), ...(result.step_artifacts ?? [])]
        .slice(0, 12)
        .map((artifact) => `- **${artifact.label}:** \`${artifact.path}\``);

      const defectTitle = `[${failureCategory}] ${detail?.test_case_id ? `Test Case #${detail.test_case_id}` : "Execution Run"}: ${firstFailedStep ? `Step ${firstFailedStep.index} (${firstFailedStep.action}) failed` : "Checks failed"}`;

      const description = [
        `### Execution Failure Diagnosis`,
        `- **Target:** ${result.url}`,
        `- **Page title:** ${result.title || "Unavailable"}`,
        `- **Failure Category:** ${failureCategory}`,
        `- **What this means:** ${failureGuidance(failureCategory)}`,
        `- **Summary:** ${result.failure_summary || failureReason}`,
        `- **Duration:** ${result.duration_ms}ms`,
        `- **Run ID:** \`${detail?.run_id}\``,
        detail?.test_case_id ? `- **Test Case ID:** #${detail.test_case_id}` : "",
        ``,
        `### Failed Steps / Checks`,
        ...failedSteps.map((s) => `- **Step ${s.index} (${s.action}):** ${s.message} (Selector: \`${s.selector || "none"}\`, duration: ${s.duration_ms}ms)`),
        ...failedChecks.map((c) => `- **Check (${c.type}):** expected \`${c.value}\`; ${c.message}`),
        ``,
        result.error ? `### Error Details\n\`\`\`\n${result.error}\n\`\`\`` : "",
        result.console_errors?.length ? `### Console Errors\n${result.console_errors.slice(0, 5).map((error) => `- ${error}`).join("\n")}` : "",
        result.network_errors?.length ? `### Network Errors\n${result.network_errors.slice(0, 5).map((error) => `- ${error}`).join("\n")}` : "",
        evidence.length ? `### Evidence\n${evidence.join("\n")}` : "",
      ].filter(Boolean).join("\n");

      const created = await apiFetch<{ id: number }>(
        "/api/v1/defects",
        {
          method: "POST",
          body: JSON.stringify({
            title: defectTitle.slice(0, 200),
            description: description.slice(0, 4000),
            priority: "high",
            severity: failureCategory === "TIMING" || failureCategory === "AUTHENTICATION" ? "critical" : "major",
            status: "open",
          }),
        },
        token,
      );
      setLoggedDefectId(created.id);
    } catch {
      // ignore
    } finally {
      setLoggingDefect(false);
    }
  };

  const renderWithWorkspaceShell = (content: ReactNode) => (
    <WorkspaceShell
      brandTitle="AI QA Engine"
      section="execution"
      apps={[]}
      selectedApplication={null}
      mobileNavOpen={mobileNavOpen}
      navigationGroups={detailNavigationGroups}
      onMobileNavOpenChange={setMobileNavOpen}
      onSelectApplication={() => undefined}
      onNavigate={navigateToSection}
      onLogout={() => {
        clearToken();
        router.push("/");
      }}
      onNotify={() => undefined}
    >
      {content}
    </WorkspaceShell>
  );

  if (loading && !detail) {
    return renderWithWorkspaceShell(<div className="execution-run-details-page"><div className="panel execution-run-loading"><div className="progress-spinner" /><strong>Loading execution details...</strong><p>Fetching step results and captured evidence.</p></div></div>);
  }

  if (error && !detail) {
    return renderWithWorkspaceShell(
      <div className="execution-run-details-page">
        <div className="panel execution-run-error">
          <span className="detail-label">Execution details</span>
          <h1>Unable to load this run</h1>
          <p className="fail">{error}</p>
          <button
            type="button"
            className="primary"
            onClick={() => router.push("/test-execution")}
          >
            Back to Test Execution
          </button>
        </div>
      </div>
    );
  }

  return renderWithWorkspaceShell(
    <div className="execution-run-details-page">
      <div className="execution-run-details-nav">
        <button
          type="button"
          className="secondary btn-sm"
          onClick={() => router.push("/test-execution")}
        >
          ← Back to Test Execution
        </button>
        {detail?.run_status && <StatusBadge status={detail.run_status} />}
      </div>
      <section className="panel execution-run-hero">
        <div>
          <h1>{detail?.test_case_id ? `Test case #${detail.test_case_id}` : "Ad-hoc execution"}</h1>
        </div>
        <div className="execution-run-hero-meta">
          <span><b>Started</b>{formatTimestamp(detail?.created_at)}</span>
          <span><b>Finished</b>{formatTimestamp(detail?.finished_at)}</span>
          <span><b>Phase</b>{detail?.live_state || (detail?.run_status ?? "Unknown")}</span>
        </div>
      </section>

      {loggedDefectId && (
        <div className="panel" style={{ background: "rgba(16, 185, 129, 0.1)", border: "1px solid var(--success)", padding: "12px 16px", marginBottom: "16px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>✅ <strong>Defect logged successfully!</strong> Defect #{loggedDefectId} has been created for this execution failure.</span>
          <button
            type="button"
            className="secondary btn-sm"
            onClick={() => router.push("/defects")}
          >
            View Defects →
          </button>
        </div>
      )}

      {result ? (
        <ExecutionSummaryPanel
          result={result}
          token={token}
          onRetry={() => router.push("/test-execution")}
          onInspect={() => document.getElementById("execution-run-step-section")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          onLogDefect={handleLogDefectFromRun}
        />
      ) : null}

      <section className="execution-run-summary-grid">
        <article className="panel"><span className="detail-label">Target</span><strong>{result?.url || "-"}</strong></article>
        <article className="panel"><span className="detail-label">Page title</span><strong>{result?.title || "-"}</strong></article>
        <article className="panel"><span className="detail-label">Duration</span><strong>{formatDuration(result?.duration_ms)}</strong></article>
        <article className="panel"><span className="detail-label">Failure type</span><strong>{formatFailureType(result?.failure_type)}</strong></article>
      </section>

      <section className="panel execution-run-section" id="execution-run-step-section">
        <div className="execution-run-section-heading">
          <div><span className="detail-label">Step-by-step execution</span><h2>Action timeline</h2></div>
          <span className="muted">{steps.filter((step) => step.passed).length}/{steps.length} steps passed</span>
        </div>
        <div className="execution-run-step-list">
          {steps.length ? steps.map((step) => {
            const screenshot = screenshotByStep.get(step.index);
            return (
              <details className="execution-run-step" key={`${detail?.run_id}-step-${step.index}`}>
                <summary>
                  <span className="execution-run-step-index">Step {step.index}</span>
                  <strong>{step.action}</strong>
                  <span className={step.passed ? "pass" : "fail"}>{step.passed ? "Passed" : detail?.run_status === "running" ? "Pending" : "Failed"}</span>
                  <span className="execution-run-step-evidence">{screenshot ? "Screenshot" : "No screenshot"}</span>
                </summary>
                <div className="execution-run-step-body">
                  <div className="execution-run-step-copy">
                    <span className="detail-label">Selector</span>
                    <strong>{step.selector}</strong>
                    <p>{step.message}</p>
                    <span className="muted">Duration {formatDuration(step.durationMs)}</span>
                  </div>
                  <div className="execution-run-step-media">
                    {screenshot ? <><ArtifactMedia artifact={screenshot} token={token} runId={runId} /><ArtifactDownload artifact={screenshot} token={token} runId={runId} /></> : <p className="muted">Step screenshots are available for runs started with screenshot capture enabled.</p>}
                  </div>
                </div>
              </details>
            );
          }) : <p className="muted">No steps were recorded for this run.</p>}
        </div>
      </section>

      <section className="panel execution-run-section execution-run-diagnostics-section">
        <div className="execution-run-section-heading">
          <div><span className="detail-label">Observability</span><h2>Network, console, and worker diagnostics</h2></div>
          <span className="muted">Review details at the end of the run.</span>
        </div>
        <div className="execution-run-diagnostics-grid">
          <details open={Boolean(result?.network_errors?.length)}>
            <summary><span>Network log</span><span>{result?.network_errors?.length ?? 0} failed</span></summary>
            <div>{result?.network_errors?.length ? result.network_errors.map((entry, index) => <p className="fail" key={`network-${index}`}>{entry}</p>) : <p className="muted">No failed network requests captured.</p>}</div>
          </details>
          <details open={Boolean(result?.console_errors?.length)}>
            <summary><span>Console log</span><span>{result?.console_errors?.length ?? 0} errors</span></summary>
            <div>{result?.console_errors?.length ? result.console_errors.map((entry, index) => <p className="fail" key={`console-${index}`}>{entry}</p>) : <p className="muted">No console errors captured.</p>}</div>
          </details>
          <details>
            <summary><span>Live execution events</span><span>{liveEvents.length} events</span></summary>
            <div>{liveEvents.length ? liveEvents.map((event, index) => <p key={`event-${index}`}><b>{event.state}:</b> {event.message}</p>) : <p className="muted">No live events captured.</p>}</div>
          </details>
          <details>
            <summary><span>Checks and healer activity</span><span>{result?.healed_steps?.length ?? 0} healed</span></summary>
            <div>
              {result?.checks?.length ? result.checks.map((check, index) => <p className={check.passed ? "pass" : "fail"} key={`check-${index}`}>{check.passed ? "PASS" : "FAIL"} {check.message}</p>) : <p className="muted">No checks configured.</p>}
              {result?.healer_agent ? <p className="muted">Healer agent: {result.healer_agent}</p> : null}
              {result?.healed_steps?.map((step) => <p className="pass" key={`healed-${step.index}`}>Step {step.index} repaired{step.reason ? `: ${step.reason}` : "."}</p>)}
              {result?.error ? <p className="fail">{result.error}</p> : null}
            </div>
          </details>
          {workerLog ? <details><summary><span>Worker log</span><span>Raw output</span></summary><pre>{workerLog}</pre></details> : null}
        </div>
      </section>
    </div>
  );
}
