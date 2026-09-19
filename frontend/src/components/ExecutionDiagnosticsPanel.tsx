"use client";

import type { CaseExecutionDetail } from "../types";
import { formatTimestamp, formatFailureTypeLabel } from "../lib/distributions";
import { formatDuration } from "../lib/formatDuration";
import { parseLiveEventsFromLog, formatLiveStateLabel, LIVE_EVENT_PREFIX } from "../lib/speech";
import { getStatusMeta } from "../lib/testCaseHelpers";
import { ExecutionArtifactPreview, ExecutionStepEvidence } from "./ui/DashboardWidgets";

function renderStatusChip(status?: string) {
  const meta = getStatusMeta(status);
  return (
    <span className={`status-chip status-${meta.tone}`}>
      <span className="status-chip-icon">{meta.icon}</span>
      <span>{meta.label}</span>
    </span>
  );
}

export default function ExecutionDiagnosticsPanel({
  detail,
  caseTitle,
  token,
}: {
  detail: CaseExecutionDetail;
  caseTitle?: string;
  token: string;
}) {
  const result = detail.result;
  const stepDiagnostics = result?.step_results ?? [];
  const stepArtifacts = result?.step_artifacts ?? [];
  const artifacts = result?.artifacts ?? [];
  const videoArtifacts = artifacts.filter((artifact) => artifact.type === "video");
  const otherArtifacts = artifacts.filter((artifact) => artifact.type !== "video");
  const checks = result?.checks ?? [];
  const consoleErrors = result?.console_errors ?? [];
  const networkErrors = result?.network_errors ?? [];
  const liveEvents = parseLiveEventsFromLog(detail.log);
  const workerLog = (detail.log ?? "")
    .split(/\r?\n/)
    .filter((line) => !line.startsWith(LIVE_EVENT_PREFIX))
    .join("\n")
    .trim();
  const plannedSteps = detail.steps ?? [];
  const timelineSteps = stepDiagnostics.length
    ? stepDiagnostics.map((step) => ({
      index: step.index,
      action: step.action,
      selector: step.selector ?? "—",
      passed: step.passed,
      durationMs: step.duration_ms,
      message: step.message,
      state: step.passed ? "passed" : "failed",
    }))
    : plannedSteps.map((step, index) => ({
      index: index + 1,
      action: step.action,
      selector: step.selector ?? step.value ?? "—",
      passed: false,
      durationMs: 0,
      message: "Result pending",
      state: "pending" as const,
    }));
  const maxStepDuration = Math.max(...timelineSteps.map((step) => step.durationMs), 1);
  const completedStepCount = timelineSteps.filter((step) => step.state !== "pending").length;
  const passedStepCount = timelineSteps.filter((step) => step.state === "passed").length;
  const failedStepCount = timelineSteps.filter((step) => step.state === "failed").length;
  const stepCompletionPercent = timelineSteps.length ? Math.round((completedStepCount / timelineSteps.length) * 100) : 0;

  return (
    <div className="panel execution-detail">
      <div className="panel-heading">
        <div>
          <h2>{caseTitle ? `${caseTitle}` : `Run ${detail.run_id.slice(0, 8)}`}</h2>
        </div>
        {renderStatusChip(detail.run_status)}
      </div>
      <div className="execution-summary-grid">
        <div><span className="detail-label">Run ID</span><strong>{detail.run_id}</strong></div>
        <div><span className="detail-label">Started</span><strong>{formatTimestamp(detail.created_at)}</strong></div>
        <div><span className="detail-label">Finished</span><strong>{formatTimestamp(detail.finished_at)}</strong></div>
        <div><span className="detail-label">Duration</span><strong>{formatDuration(result?.duration_ms)}</strong></div>
        <div><span className="detail-label">Target</span><strong>{result?.url ?? "—"}</strong></div>
        <div><span className="detail-label">Page title</span><strong>{result?.title ?? "—"}</strong></div>
        <div><span className="detail-label">Failure type</span><strong>{formatFailureTypeLabel(result?.failure_type)}</strong></div>
        <div><span className="detail-label">Failure summary</span><strong>{result?.failure_summary ?? "—"}</strong></div>
      </div>
      <div className="execution-step-overview">
        <div className="execution-step-overview-head">
          <div>
            <span className="detail-label">Step flow progress</span>
            <strong>{stepCompletionPercent}% complete</strong>
          </div>
          <div className="execution-step-kpis">
            <span>Steps <b>{timelineSteps.length}</b></span>
            <span className="pass">Passed <b>{passedStepCount}</b></span>
            <span className="fail">Failed <b>{failedStepCount}</b></span>
          </div>
        </div>
        <div className="execution-step-progress">
          <div className="execution-step-progress-fill" style={{ width: `${stepCompletionPercent}%` }} />
        </div>
      </div>
      <div className="execution-step-timeline">
        {timelineSteps.length ? timelineSteps.map((step) => (
          <article key={`${detail.run_id}-timeline-${step.index}`} className={`execution-step-node ${step.state}`}>
            <header>
              <span className="execution-step-index">Step {step.index}</span>
              <span className={`execution-step-state ${step.state}`}>
                {step.state === "passed" ? "Passed" : step.state === "failed" ? "Failed" : "Pending"}
              </span>
            </header>
            <strong>{step.action}</strong>
            <p>{step.selector}</p>
            <div className="execution-step-duration">
              <div className="execution-step-duration-fill" style={{ width: `${Math.max(8, Math.round((step.durationMs / maxStepDuration) * 100))}%` }} />
            </div>
            <small>{step.durationMs ? formatDuration(step.durationMs) : "Awaiting run result"}</small>
            <p className="execution-step-message">{step.message}</p>
          </article>
        )) : <p className="muted">No steps recorded for this run.</p>}
      </div>
      <ExecutionStepEvidence steps={timelineSteps} artifacts={stepArtifacts} token={token} runId={detail.run_id} />
      <section className="execution-recording" aria-label="Live execution recording">
        <div className="execution-recording-heading">
          <div>
            <span className="detail-label">Live recording</span>
            <strong>Play back the complete browser session</strong>
          </div>
          <span className="muted">Play, scrub, or download the recording.</span>
        </div>
        {videoArtifacts.length ? (
          <ExecutionArtifactPreview
            artifacts={videoArtifacts}
            token={token}
            runId={detail.run_id}
            showHeading={false}
          />
        ) : (
          <p className="muted execution-recording-empty">No recording is attached to this run. Enable Record video before starting the next execution.</p>
        )}
      </section>
      <div className="execution-diagnostics-columns">
        <div>
          <h3>Step diagnostics</h3>
          <div className="table-scroll">
            <table>
              <thead><tr><th>#</th><th>Action</th><th>Selector</th><th>Status</th><th>Duration</th><th>Message</th></tr></thead>
              <tbody>
                {stepDiagnostics.length ? stepDiagnostics.map((step) => (
                  <tr key={`step-${detail.run_id}-${step.index}`}>
                    <td>{step.index}</td>
                    <td>{step.action}</td>
                    <td>{step.selector ?? "—"}</td>
                    <td><span className={step.passed ? "pass" : "fail"}>{step.passed ? "Passed" : "Failed"}</span></td>
                    <td>{formatDuration(step.duration_ms)}</td>
                    <td>{step.message}</td>
                  </tr>
                )) : plannedSteps.length ? plannedSteps.map((step, index) => (
                  <tr key={`planned-${detail.run_id}-${index + 1}`}>
                    <td>{index + 1}</td>
                    <td>{step.action}</td>
                    <td>{step.selector ?? "—"}</td>
                    <td>—</td>
                    <td>—</td>
                    <td>Result pending</td>
                  </tr>
                )) : <tr><td colSpan={6} className="muted">No steps recorded for this run.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3>Run diagnostics</h3>
          <div className="execution-meta-stack">
            <div className="execution-diagnostics-block">
              <span className="detail-label">Checks</span>
              {checks.length ? checks.map((check) => <p key={`${detail.run_id}-${check.type}-${check.value}`} className={check.passed ? "pass" : "fail"}>{check.passed ? "PASS" : "FAIL"} {check.message}</p>) : <p className="muted">No checks configured.</p>}
            </div>
            <div className="execution-diagnostics-block">
              <span className="detail-label">Run artifacts</span>
              {otherArtifacts.length ? <ExecutionArtifactPreview artifacts={otherArtifacts} token={token} runId={detail.run_id} showHeading={false} /> : <p className="muted">No final artifacts captured.</p>}
            </div>
            <details className="execution-log-details" open={Boolean(result?.error)}>
              <summary><span>Console log</span><span>{consoleErrors.length} error{consoleErrors.length === 1 ? "" : "s"}</span></summary>
              <div className="execution-log-content">
                {consoleErrors.length ? consoleErrors.map((entry, index) => <p key={`${detail.run_id}-console-${index}`} className="fail">{entry}</p>) : <p className="muted">No console errors captured.</p>}
              </div>
            </details>
            <details className="execution-log-details">
              <summary><span>Live execution events</span><span>{liveEvents.length} event{liveEvents.length === 1 ? "" : "s"}</span></summary>
              <div className="execution-log-content">
                {liveEvents.length ? liveEvents.slice(-40).map((event, index) => (
                  <p key={`${detail.run_id}-live-event-${index}`}><b>{formatLiveStateLabel(event.state)}:</b> {event.message}</p>
                )) : <p className="muted">No live events captured.</p>}
              </div>
            </details>
            {result?.error && <div className="execution-diagnostics-block"><span className="detail-label">Run error</span><p className="fail">{result.error}</p></div>}
            {workerLog && (
              <details className="execution-log-details">
                <summary><span>Worker log</span><span>Raw output</span></summary>
                <div className="execution-log-content"><pre className="run-log">{workerLog}</pre></div>
              </details>
            )}
            <details className="execution-log-details" open={networkErrors.length > 0}>
              <summary><span>Network log</span><span>{networkErrors.length} failed request{networkErrors.length === 1 ? "" : "s"}</span></summary>
              <div className="execution-log-content">
                {networkErrors.length ? networkErrors.map((entry, index) => <p key={`${detail.run_id}-network-${index}`} className="fail">{entry}</p>) : <p className="muted">No failed network requests captured.</p>}
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>
  );
}
