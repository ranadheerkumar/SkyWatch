"use client";

import { useEffect, useState } from "react";
import AppIcon from "./navigation/AppIcon";
import { apiFetchBlob } from "../lib/api";
import { formatDuration } from "../lib/formatDuration";

export type ExecutionSummaryArtifact = {
  type: "screenshot" | "video" | "trace";
  path: string;
  label: string;
  step_index?: number | null;
};

export type ExecutionSummaryResult = {
  run_id: string;
  url: string;
  status: "passed" | "failed" | "error" | "cancelled";
  failure_type?: string | null;
  failure_summary?: string | null;
  duration_ms: number;
  audio_status?: "embedded" | "unavailable" | "disabled";
  checks: Array<{ type: string; value: string; passed: boolean; message: string }>;
  step_results?: Array<{
    index: number;
    action: string;
    selector?: string | null;
    passed: boolean;
    message: string;
    duration_ms: number;
  }>;
  artifacts?: ExecutionSummaryArtifact[];
  console_errors?: string[];
  network_errors?: string[];
  error?: string | null;
  healer_agent?: string | null;
  healed_steps?: Array<unknown>;
  step_artifacts?: ExecutionSummaryArtifact[];
};

function formatFailureTypeLabel(failureType?: string | null) {
  if (!failureType) return "";
  return failureType
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function exportExecutionReport(result: ExecutionSummaryResult) {
  const report = {
    run_id: result.run_id,
    status: result.status,
    target: result.url,
    duration_ms: result.duration_ms,
    failure_type: result.failure_type ?? null,
    failure_summary: result.failure_summary ?? null,
    steps: result.step_results ?? [],
    checks: result.checks,
    artifacts: result.artifacts ?? [],
    step_artifacts: result.step_artifacts ?? [],
  };
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `execution-${result.run_id.slice(0, 12)}-report.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ExecutionArtifactPreview({
  artifacts,
  token,
  runId,
  showHeading = true,
  headingTitle = "Execution evidence",
  headingDescription = "Loaded securely from the test run",
}: {
  artifacts: ExecutionSummaryArtifact[];
  token: string;
  runId: string;
  showHeading?: boolean;
  headingTitle?: string;
  headingDescription?: string;
}) {
  const [artifactUrls, setArtifactUrls] = useState<Record<number, string>>({});
  const [artifactErrors, setArtifactErrors] = useState<Record<number, string>>({});
  const artifactSignature = artifacts.map((artifact) => `${artifact.type}:${artifact.path}`).join("|");

  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];
    setArtifactUrls({});
    setArtifactErrors({});
    if (!token || !artifacts.length) return () => undefined;

    const loadArtifacts = async () => {
      const loaded = await Promise.all(artifacts.map(async (artifact, index) => {
        const filename = artifact.path.split(/[\\/]/).pop() ?? "";
        if (!filename) return { index, url: "", error: "Artifact filename is unavailable." };
        try {
          const blob = await apiFetchBlob(`/api/v1/evidence/file/${encodeURIComponent(filename)}?run_id=${encodeURIComponent(runId)}`, token);
          const url = URL.createObjectURL(blob);
          objectUrls.push(url);
          return { index, url, error: "" };
        } catch (error) {
          return { index, url: "", error: error instanceof Error ? error.message : "Unable to load artifact." };
        }
      }));
      if (cancelled) return;
      setArtifactUrls(Object.fromEntries(loaded.filter((item) => item.url).map((item) => [item.index, item.url])));
      setArtifactErrors(Object.fromEntries(loaded.filter((item) => item.error).map((item) => [item.index, item.error])));
    };
    void loadArtifacts();

    return () => {
      cancelled = true;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [artifactSignature, runId, token]);

  if (!artifacts.length) return null;
  return (
    <section className="execution-artifacts" aria-label="Execution evidence">
      {showHeading ? (
        <div className="execution-artifacts-heading">
          <div>
            <span className="detail-label">{headingTitle}</span>
            <strong>{artifacts.length} captured artifact{artifacts.length === 1 ? "" : "s"}</strong>
          </div>
          <span className="muted">{headingDescription}</span>
        </div>
      ) : null}
      <div className="execution-artifact-grid">
        {artifacts.map((artifact, index) => {
          const artifactUrl = artifactUrls[index];
          const artifactError = artifactErrors[index];
          return (
            <article className="execution-artifact-card" key={`${runId}-artifact-preview-${index}`}>
              <div className="execution-artifact-card-head">
                <strong>{artifact.label}</strong>
                <span>{artifact.type}</span>
              </div>
              {artifactUrl && artifact.type === "screenshot" ? <img src={artifactUrl} alt={artifact.label} className="execution-artifact-image" /> : null}
              {artifactUrl && artifact.type === "video" ? <video className="execution-artifact-video" controls preload="metadata" src={artifactUrl} /> : null}
              {artifact.type === "trace" && artifactUrl ? <p className="muted">Playwright trace is ready to download.</p> : null}
              {!artifactUrl && !artifactError ? <p className="muted">Loading artifact...</p> : null}
              {artifactError ? <p className="fail">{artifactError}</p> : null}
              {artifactUrl ? (
                <a className="execution-artifact-download" href={artifactUrl} download={artifact.path.split(/[\\/]/).pop() ?? "execution-artifact"}>
                  Download {artifact.type}
                </a>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function ExecutionSummaryPanel({
  result,
  token,
  onRetry,
  onInspect,
  onLogDefect,
}: {
  result: ExecutionSummaryResult;
  token: string;
  onRetry?: () => void;
  onInspect?: () => void;
  onLogDefect?: () => void;
}) {
  const isTimeout = result.failure_type === "TIMING"
    || result.error?.toLowerCase().includes("timed out")
    || result.error?.toLowerCase().includes("timeout")
    || result.failure_summary?.toLowerCase().includes("timeout");
  const failedStepResults = result.step_results?.filter((step) => !step.passed) ?? [];
  const failedCheckResults = result.checks.filter((check) => !check.passed);
  const totalFailedCount = failedStepResults.length + failedCheckResults.length;
  const totalItemsCount = (result.step_results?.length ?? 0) + result.checks.length;
  const totalPassedCount = (result.step_results?.filter((step) => step.passed).length ?? 0) + result.checks.filter((check) => check.passed).length;
  const passRate = totalItemsCount > 0 ? Math.round((totalPassedCount / totalItemsCount) * 100) : result.status === "passed" ? 100 : 0;
  const failureTypeLabel = formatFailureTypeLabel(result.failure_type);

  return (
    <div className={`panel run-result ${result.status}`}>
      <div className="result-header-section">
        <div>
          <h2>{result.status === "passed" ? "All tests passed" : result.status === "failed" ? "Execution failed" : "Execution unavailable"}</h2>
          {isTimeout ? <p className="error-callout">Timeout detected in test execution</p> : null}
          {result.status !== "passed" && result.failure_type ? <p className="error-callout">Failure category: {failureTypeLabel}</p> : null}
          {result.status !== "passed" && result.failure_summary ? <p className="muted">{result.failure_summary}</p> : null}
        </div>
        <div className="result-kpis">
          <div className="result-kpi"><strong>{passRate}%</strong><span>Pass rate</span></div>
          <div className="result-kpi"><strong>{formatDuration(result.duration_ms)}</strong><span>Total time</span></div>
          {result.audio_status ? (
            <div className={`result-kpi execution-audio-result ${result.audio_status}`}>
              <strong>{result.audio_status === "embedded" ? "On" : result.audio_status === "unavailable" ? "Unavailable" : "Off"}</strong>
              <span>Video audio</span>
            </div>
          ) : null}
        </div>
      </div>

      {result.healer_agent ? (
        <div className="execution-healer-summary">
          <strong>{result.healer_agent} active</strong>
          <span>{result.healed_steps?.length ? `${result.healed_steps.length} step${result.healed_steps.length === 1 ? "" : "s"} repaired during this run.` : "No locator repairs were required."}</span>
        </div>
      ) : null}

        {(result.artifacts?.length || result.step_artifacts?.length) ? (
          <ExecutionArtifactPreview
            artifacts={[...(result.artifacts ?? []), ...(result.step_artifacts ?? [])]}
            token={token}
            runId={result.run_id}
          />
        ) : null}

      {isTimeout ? (
        <div className="error-detail-panel">
          <div className="error-header">
            <span className="error-icon"><AppIcon name="timeout" /></span>
            <div>
              <strong>Execution Timeout</strong>
              <p>Test execution exceeded time limit or element locator timed out</p>
            </div>
          </div>
          <div className="error-details">
            <div className="error-detail-item"><span className="error-label">Status:</span><span className="error-value">{result.failure_summary || "Timeout in test execution"}</span></div>
            <div className="error-detail-item"><span className="error-label">Failed steps:</span><span className="error-value">{totalFailedCount} step/check failure(s)</span></div>
            <div className="error-detail-item"><span className="error-label">Recommendation:</span><span className="error-value">Check target page availability, verify selectors, or ensure login credentials are valid</span></div>
          </div>
          <div className="error-actions" style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "10px" }}>
            {onRetry ? <button type="button" className="btn-primary btn-sm" onClick={onRetry}>Retry execution</button> : null}
            {onInspect ? <button type="button" className="btn-secondary btn-sm" onClick={onInspect}>Inspect steps</button> : null}
            {onLogDefect ? <button type="button" className="btn btn-secondary btn-sm danger" onClick={onLogDefect} style={{ color: "var(--danger)" }}>⚠️ Log as Defect</button> : null}
          </div>
        </div>
      ) : null}

      {!isTimeout && totalFailedCount > 0 ? (
        <div className="error-detail-panel error-minimal">
          <div className="error-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="error-icon"><AppIcon name="warning" /></span>
              <div><strong>{totalFailedCount} step/check failure(s)</strong><p>Review details below or log as defect for triage</p></div>
            </div>
            {onLogDefect ? (
              <button type="button" className="btn btn-secondary btn-sm danger" onClick={onLogDefect} style={{ color: "var(--danger)" }}>
                ⚠️ Log as Defect
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="result-checks">
        <div className="result-checks-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div>
            <strong style={{ fontSize: "1.05rem" }}>Complete Step Execution ({result.step_results?.length ?? 0} steps)</strong>
            <p className="muted" style={{ margin: "2px 0 0 0", fontSize: "0.85rem" }}>Sequential Playwright action steps executed during this run</p>
          </div>
          <span className="text-muted" style={{ fontWeight: 600 }}>
            {result.step_results?.filter((s) => s.passed).length ?? 0} passed · {result.step_results?.filter((s) => !s.passed).length ?? 0} failed
          </span>
        </div>
        <div className="result-checks-list">
          {result.step_results && result.step_results.length > 0 ? (
            result.step_results.map((step) => (
              <div
                key={`step-${step.index}-${step.action}`}
                className={`result-check-item ${step.passed ? "pass" : "fail"}`}
                style={{ padding: "10px 14px", display: "flex", alignItems: "flex-start", gap: "12px" }}
              >
                <span className="result-check-status" style={{ fontSize: "1rem", marginTop: "1px" }}>
                  {step.passed ? "\u2713" : "\u2717"}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      Step {step.index}: {step.action.toUpperCase()}
                    </span>
                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                      {formatDuration(step.duration_ms)}
                    </span>
                  </div>
                  {step.selector ? (
                    <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "2px", fontFamily: "var(--font-mono)" }}>
                      Target: {step.selector}
                    </div>
                  ) : null}
                  <p className="result-check-message" style={{ margin: "4px 0 0 0", fontSize: "0.88rem" }}>
                    {step.message}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <span className="text-muted">No step-by-step actions recorded for this run.</span>
          )}
        </div>
      </div>

      <details className="execution-summary-accordion" style={{ marginTop: "16px", border: "1px solid var(--border-light)", borderRadius: "var(--radius-md)", padding: "10px 14px", background: "var(--bg-layer-2)" }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Post-Condition Checks &amp; Diagnostics ({result.checks.length} check{result.checks.length === 1 ? "" : "s"})</span>
          <span className="muted" style={{ fontSize: "0.8rem" }}>Click to expand/collapse</span>
        </summary>
        <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
          {result.checks.length ? (
            result.checks.map((check, index) => (
              <div key={`check-${check.type}-${check.value}-${index}`} className={`result-check-item ${check.passed ? "pass" : "fail"}`}>
                <span className="result-check-status">{check.passed ? "\u2713" : "\u2717"}</span>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600 }}>Check: {check.type}</span>
                  <p className="result-check-message" style={{ margin: "2px 0 0 0" }}>{check.message}</p>
                </div>
              </div>
            ))
          ) : (
            <span className="text-muted">No post-condition checks configured.</span>
          )}
        </div>
      </details>

      <div className="result-footer" style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
        {result.status !== "passed" && onLogDefect ? (
          <button type="button" className="btn btn-secondary btn-sm danger" onClick={onLogDefect} style={{ color: "var(--danger)" }}>
            ⚠️ Log as Defect
          </button>
        ) : null}
        <button type="button" className="btn-secondary btn-sm" onClick={() => exportExecutionReport(result)}>Export report</button>
      </div>
    </div>
  );
}
