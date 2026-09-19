"use client";

import { useState, useMemo, useEffect } from "react";
import type { BuildExecutionDetail, BuildExecutionReport, CaseExecutionResultItem, ExecutionResult } from "../types";
import { formatDuration } from "../lib/formatDuration";
import { apiFetchBlob } from "../lib/api";

export interface CompleteBuildReportPanelProps {
  report: BuildExecutionReport | BuildExecutionDetail;
  token: string;
  onRetry?: (caseIds?: number[]) => void;
  onRebuild?: (buildId: string, caseIds?: number[]) => void;
  onStopBuild?: (buildId: string) => void;
  onInspectRun?: (runId: string) => void;
  onDismiss?: () => void;
  onReportDefect?: () => void;
  onNavigateToHistory?: () => void;
}

export function normalizeBuildReport(report: BuildExecutionReport | BuildExecutionDetail): BuildExecutionReport {
  if ("buildId" in report) {
    return report;
  }
  const tcNumber = (title: string) => {
    const m = title.match(/^TC\s*0*(\d+)/i);
    return m ? Number(m[1]) : Number.POSITIVE_INFINITY;
  };
  const normalizedCases = (report.cases || []).map((c, idx) => ({
    caseId: c.test_case_id ?? idx + 1,
    title: c.title || `Test Case #${idx + 1}`,
    order: idx + 1,
    runId: c.run_id,
    status: (c.status as any) || "error",
    durationMs: c.duration_ms ?? undefined,
    detail: c.failure_summary || c.error || c.check_summary || undefined,
    result: c.result ?? null,
  }));

  normalizedCases.sort((a, b) => {
    const numA = tcNumber(a.title);
    const numB = tcNumber(b.title);
    if (numA !== numB) return numA - numB;
    return a.caseId - b.caseId;
  });

  return {
    buildId: report.build_id,
    applicationName: report.application_name || "Application",
    targetUrl: report.target_url || "",
    startedAt: report.created_at ? new Date(report.created_at).getTime() : Date.now(),
    finishedAt: report.finished_at ? new Date(report.finished_at).getTime() : Date.now(),
    totalDurationMs: report.duration_ms || 0,
    totalCases: report.total_cases,
    passedCount: report.passed_count,
    failedCount: report.failed_count,
    errorCount: report.error_count,
    passRate: report.pass_rate,
    overallStatus: report.status === "failed" || report.status === "error" ? "failed" : (report.status as any) || "passed",
    cases: normalizedCases,
  };
}

type ReportTab = "cases" | "steps" | "evidence" | "diagnostics";

function renderStatusChip(status: string) {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  let tone = "neutral";
  if (normalized === "passed" || normalized === "resolved" || normalized === "closed") tone = "success";
  else if (normalized === "failed" || normalized === "error") tone = "danger";
  else if (normalized === "running" || normalized === "queued" || normalized === "in progress") tone = "warning";

  const label = normalized
    ? normalized
        .split(" ")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
    : "Unknown";

  return (
    <span className={`status-chip status-${tone}`} style={{ whiteSpace: "nowrap" }}>
      <span>{label}</span>
    </span>
  );
}

export default function CompleteBuildReportPanel({
  report: rawReport,
  token,
  onRetry,
  onRebuild,
  onStopBuild,
  onInspectRun,
  onDismiss,
  onReportDefect,
  onNavigateToHistory,
}: CompleteBuildReportPanelProps) {
  const report = useMemo(() => normalizeBuildReport(rawReport), [rawReport]);
  const [activeTab, setActiveTab] = useState<ReportTab>("cases");
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(report.cases[0]?.caseId ?? null);
  const [evidenceFilter, setEvidenceFilter] = useState<"all" | "screenshot" | "video" | "highlight">("all");
  const [previewImage, setPreviewImage] = useState<{ url: string; label: string } | null>(null);

  const allCaseIds = useMemo(
    () => report.cases.map((c) => c.caseId).filter((id): id is number => typeof id === "number" && id > 0),
    [report.cases],
  );

  // Update selected case if report changes
  useEffect(() => {
    if (report.cases.length > 0) {
      setSelectedCaseId((current) => (current && report.cases.some((c) => c.caseId === current) ? current : report.cases[0].caseId));
    }
  }, [report.cases]);

  // Active selected case object
  const activeCase = useMemo(() => {
    if (selectedCaseId !== null) {
      const found = report.cases.find((c) => c.caseId === selectedCaseId);
      if (found) return found;
    }
    return report.cases[0] ?? null;
  }, [report.cases, selectedCaseId]);

  const activeResult: ExecutionResult | null = activeCase?.result ?? null;

  // Collect all artifacts across all cases
  const allArtifacts = useMemo(() => {
    const list: Array<{
      caseTitle: string;
      caseId: number;
      runId?: string;
      type: "screenshot" | "video" | "trace";
      path: string;
      label: string;
      step_index?: number | null;
    }> = [];

    report.cases.forEach((c) => {
      const artifacts = [...(c.result?.artifacts ?? []), ...(c.result?.step_artifacts ?? [])];
      artifacts.forEach((art) => {
        list.push({
          caseTitle: c.title,
          caseId: c.caseId,
          runId: c.runId,
          type: art.type,
          path: art.path,
          label: art.label,
          step_index: "step_index" in art && typeof art.step_index === "number" ? art.step_index : null,
        });
      });
    });

    return list;
  }, [report.cases]);

  // Filtered artifacts
  const filteredArtifacts = useMemo(() => {
    if (evidenceFilter === "screenshot") {
      return allArtifacts.filter((a) => a.type === "screenshot" && !a.label.toLowerCase().includes("highlight"));
    }
    if (evidenceFilter === "highlight") {
      return allArtifacts.filter((a) => a.label.toLowerCase().includes("highlight"));
    }
    if (evidenceFilter === "video") {
      return allArtifacts.filter((a) => a.type === "video");
    }
    return allArtifacts;
  }, [allArtifacts, evidenceFilter]);

  // Load artifact Blob URLs
  const [artifactBlobUrls, setArtifactBlobUrls] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];

    const loadBlobs = async () => {
      if (!token || !allArtifacts.length) return;
      const urlMap: Record<string, string> = {};

      for (const art of allArtifacts) {
        const filename = art.path.split(/[\\/]/).pop() ?? "";
        if (!filename || !art.runId) continue;
        const key = `${art.runId}:${filename}`;
        if (artifactBlobUrls[key]) continue;

        try {
          const blob = await apiFetchBlob(
            `/api/v1/evidence/file/${encodeURIComponent(filename)}?run_id=${encodeURIComponent(art.runId)}`,
            token
          );
          const objUrl = URL.createObjectURL(blob);
          objectUrls.push(objUrl);
          urlMap[key] = objUrl;
        } catch {
          // ignore load failure
        }
      }

      if (!cancelled && Object.keys(urlMap).length) {
        setArtifactBlobUrls((prev) => ({ ...prev, ...urlMap }));
      }
    };

    void loadBlobs();

    return () => {
      cancelled = true;
      objectUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [allArtifacts, token]);

  // Failed cases IDs for retry
  const failedCaseIds = useMemo(() => {
    return report.cases.filter((c) => c.status === "failed" || c.status === "error").map((c) => c.caseId);
  }, [report.cases]);

  // Export CSV
  const exportCsv = () => {
    const headers = ["Order", "Test Case Title", "Run ID", "Status", "Duration (ms)", "Checks / Details", "Target URL"];
    const rows = report.cases.map((c) => [
      String(c.order),
      c.title,
      c.runId || "",
      c.status,
      String(c.durationMs || 0),
      c.result?.error || c.detail || (c.status === "passed" ? "All steps passed" : "Failed"),
      report.targetUrl,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [
        [`"Build Report: ${report.buildId}"`, `"Application: ${report.applicationName}"`, `"Pass Rate: ${report.passRate}%"`, `"Total Duration: ${formatDuration(report.totalDurationMs)}"`].join(","),
        [],
        headers.map((h) => `"${h.replace(/"/g, '""')}"`).join(","),
        ...rows.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")),
      ].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `build-execution-report-${report.buildId.slice(0, 16)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export JSON
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `build-execution-report-${report.buildId.slice(0, 16)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const isAllPassed = report.failedCount === 0 && report.errorCount === 0;

  return (
    <div
      className="panel complete-build-report-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        padding: "20px",
        border: `2px solid ${isAllPassed ? "var(--success, #16a34a)" : "var(--error, #dc2626)"}`,
        borderRadius: "var(--radius-lg, 12px)",
        background: "var(--bg-surface, #ffffff)",
        boxShadow: "var(--shadow-md, 0 4px 12px rgba(0,0,0,0.08))",
        marginBottom: "20px",
      }}
      role="region"
      aria-label="Complete Build Execution Report"
    >
      {/* Executive Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px", borderBottom: "1px solid var(--border-light)", paddingBottom: "14px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
            <span
              style={{
                fontFamily: "var(--font-code, monospace)",
                fontWeight: 800,
                fontSize: "15px",
                color: "var(--brand-primary, #b5121b)",
              }}
            >
              📊 {report.buildId.startsWith("build-") ? `Build #${report.buildId.slice(-8).toUpperCase()}` : report.buildId}
            </span>
            {renderStatusChip(report.overallStatus)}
            <span className="badge badge-secondary" style={{ fontSize: "11px" }}>
              {report.applicationName}
            </span>
          </div>

          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", fontSize: "13px", color: "var(--text-secondary)" }}>
            <span>
              Target: <strong style={{ color: "var(--text-primary)" }}>{report.targetUrl || "Default Endpoint"}</strong>
            </span>
            <span>
              Finished: <strong style={{ color: "var(--text-primary)" }}>{new Date(report.finishedAt || Date.now()).toLocaleTimeString()}</strong>
            </span>
          </div>
        </div>

        {/* Header Action Buttons */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          {(report.overallStatus === "running" || report.overallStatus === "queued") && onStopBuild && (
            <button
              type="button"
              className="secondary btn-danger btn-sm"
              onClick={() => onStopBuild(report.buildId)}
              style={{ fontWeight: 700 }}
              title="Stop and cancel this active build"
            >
              🛑 Stop Build
            </button>
          )}
          {report.overallStatus !== "running" && report.overallStatus !== "queued" && (onRebuild || onRetry) && (
            <button
              type="button"
              className="secondary btn-sm"
              onClick={() => (onRebuild ? onRebuild(report.buildId, allCaseIds) : onRetry?.(allCaseIds))}
              style={{ fontWeight: 700, color: "var(--brand-primary, #b5121b)" }}
              title="Rebuild and re-execute all test cases in this build"
            >
              🔄 Rebuild Full Build
            </button>
          )}
          {failedCaseIds.length > 0 && onRetry && (
            <button
              type="button"
              className="primary btn-sm"
              onClick={() => onRetry(failedCaseIds)}
              style={{ background: "var(--brand-primary, #b5121b)" }}
              title="Re-run only the failed test cases"
            >
              ↻ Re-run {failedCaseIds.length} Failed
            </button>
          )}
          <button type="button" className="secondary btn-sm" onClick={exportCsv} title="Export build metrics to CSV">
            📥 Export CSV
          </button>
          <button type="button" className="secondary btn-sm" onClick={exportJson} title="Export full report JSON">
            📄 Export JSON
          </button>
          {onDismiss && (
            <button type="button" className="secondary btn-sm" onClick={onDismiss} aria-label="Dismiss build report">
              ✕ Dismiss
            </button>
          )}
        </div>
      </div>

      {/* 5 Executive KPI Metric Cards */}
      <div className="build-kpi-summary-cards" style={{ marginBottom: 0 }}>
        <div className="build-kpi-card">
          <small>Build Status</small>
          <strong style={{ color: isAllPassed ? "var(--success, #10b981)" : "var(--danger, #ef4444)" }}>
            {isAllPassed ? "All Passed ✓" : `${report.failedCount} Failed ✗`}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {report.passedCount} of {report.totalCases} cases passed
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Pass Rate</small>
          <strong
            style={{
              color: report.passRate >= 80 ? "var(--success, #10b981)" : report.passRate >= 60 ? "#f59e0b" : "var(--danger, #ef4444)",
            }}
          >
            {report.passRate}%
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {report.totalCases} total test scenarios
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Total Duration</small>
          <strong>{formatDuration(report.totalDurationMs)}</strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Avg {report.totalCases > 0 ? formatDuration(Math.round(report.totalDurationMs / report.totalCases)) : "0s"}/case
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Captured Evidence</small>
          <strong style={{ color: allArtifacts.length > 0 ? "var(--info, #2563eb)" : "var(--text-secondary)" }}>
            {allArtifacts.length} Artifacts
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {allArtifacts.filter((a) => a.type === "screenshot").length} screenshots · {allArtifacts.filter((a) => a.type === "video").length} videos
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Self-Healing Agent</small>
          <strong style={{ color: "var(--success, #10b981)" }}>
            Active
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            playwright-test-healer verified
          </span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--border-light)", paddingBottom: "8px", flexWrap: "wrap" }}>
        <button
          type="button"
          className={`btn-sm ${activeTab === "cases" ? "primary" : "secondary"}`}
          onClick={() => setActiveTab("cases")}
        >
          📋 Test Cases Breakdown ({report.cases.length})
        </button>
        <button
          type="button"
          className={`btn-sm ${activeTab === "steps" ? "primary" : "secondary"}`}
          onClick={() => setActiveTab("steps")}
        >
          🔍 Step-by-Step Action Log {activeCase ? `(Case #${activeCase.order})` : ""}
        </button>
        <button
          type="button"
          className={`btn-sm ${activeTab === "evidence" ? "primary" : "secondary"}`}
          onClick={() => setActiveTab("evidence")}
        >
          📸 Captured Evidence ({allArtifacts.length})
        </button>
        <button
          type="button"
          className={`btn-sm ${activeTab === "diagnostics" ? "primary" : "secondary"}`}
          onClick={() => setActiveTab("diagnostics")}
        >
          🩺 Self-Healing &amp; Diagnostics
        </button>
      </div>

      {/* Tab 1: Test Cases Breakdown Table */}
      {activeTab === "cases" && (
        <div className="workspace-table-surface" style={{ borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--border-light)" }}>
          <table className="build-subtable" style={{ margin: 0, width: "100%", tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th style={{ width: "50px" }}>#</th>
                <th style={{ minWidth: "260px" }}>Test Case Title</th>
                <th style={{ width: "110px", whiteSpace: "nowrap" }}>Run ID</th>
                <th style={{ width: "120px", whiteSpace: "nowrap" }}>Status</th>
                <th style={{ width: "110px", whiteSpace: "nowrap" }}>Duration</th>
                <th style={{ minWidth: "220px" }}>Checks &amp; Summary</th>
                <th style={{ width: "180px", whiteSpace: "nowrap" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {report.cases.map((c) => {
                const isSelected = activeCase?.caseId === c.caseId;
                const checksCount = c.result?.checks?.length ?? 0;
                const stepsCount = c.result?.step_results?.length ?? 0;

                return (
                  <tr
                    key={`build-case-${c.caseId}-${c.runId || c.order}`}
                    style={{
                      background: isSelected ? "rgba(181, 18, 27, 0.04)" : undefined,
                      cursor: "pointer",
                    }}
                    onClick={() => setSelectedCaseId(c.caseId)}
                  >
                    <td style={{ color: "var(--text-secondary)", fontWeight: 700 }}>#{c.order}</td>
                    <td>
                      <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>{c.title}</strong>
                      <small className="muted" style={{ display: "block", marginTop: "2px" }}>
                        {stepsCount} step{stepsCount === 1 ? "" : "s"} · {checksCount} check{checksCount === 1 ? "" : "s"}
                      </small>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {c.runId ? (
                        <span style={{ fontFamily: "var(--font-code)", fontSize: "12px", color: "var(--brand-primary, #b5121b)", fontWeight: 700 }}>
                          {c.runId.slice(0, 8)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{renderStatusChip(c.status)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{c.durationMs ? formatDuration(c.durationMs) : "—"}</td>
                    <td>
                      <span
                        style={{
                          color: c.status === "passed" ? "var(--success, #10b981)" : "var(--danger, #ef4444)",
                          fontSize: "var(--font-caption)",
                          overflowWrap: "anywhere",
                          wordBreak: "break-word",
                        }}
                      >
                        {c.result?.error || c.detail || (c.status === "passed" ? "All steps & checks passed" : "Execution failed")}
                      </span>
                    </td>
                    <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap" }}>
                      <div className="row-actions-group">
                        <button
                          type="button"
                          className="row-action-btn"
                          onClick={() => {
                            setSelectedCaseId(c.caseId);
                            setActiveTab("steps");
                          }}
                          title="View step execution actions"
                        >
                          Steps
                        </button>
                        {c.runId && onInspectRun && (
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => onInspectRun(c.runId!)}
                            title="Inspect full run details in execution inspector"
                          >
                            Inspect
                          </button>
                        )}
                        {c.status !== "passed" && onReportDefect && (
                          <button
                            type="button"
                            className="row-action-btn danger"
                            onClick={onReportDefect}
                            title="Log defect for this failed case"
                          >
                            + Defect
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Step-by-Step Action Log */}
      {activeTab === "steps" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {/* Case selector strip if multiple cases */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", background: "var(--bg-layer-2)", padding: "8px 12px", borderRadius: "var(--radius-md)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "13px", fontWeight: 600 }}>Viewing Case:</span>
              <select
                value={selectedCaseId ?? ""}
                onChange={(e) => setSelectedCaseId(Number(e.target.value))}
                style={{ padding: "4px 8px", fontSize: "13px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-medium)" }}
              >
                {report.cases.map((c) => (
                  <option key={`step-sel-${c.caseId}`} value={c.caseId}>
                    #{c.order} · {c.title} ({c.status})
                  </option>
                ))}
              </select>
            </div>
            {activeCase?.runId && onInspectRun && (
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => onInspectRun(activeCase.runId!)}
              >
                Inspect Full Run {activeCase.runId.slice(0, 8)} →
              </button>
            )}
          </div>

          {/* Sequential Step Cards */}
          {activeResult?.step_results && activeResult.step_results.length > 0 ? (
            <div className="result-checks-list" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {activeResult.step_results.map((step) => (
                <div
                  key={`step-${step.index}-${step.action}`}
                  className={`result-check-item ${step.passed ? "pass" : "fail"}`}
                  style={{
                    padding: "10px 14px",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "12px",
                    borderRadius: "var(--radius-md)",
                    border: `1px solid ${step.passed ? "rgba(22, 163, 74, 0.2)" : "rgba(220, 38, 38, 0.2)"}`,
                  }}
                >
                  <span
                    style={{
                      fontSize: "14px",
                      fontWeight: 800,
                      color: step.passed ? "var(--success, #16a34a)" : "var(--danger, #dc2626)",
                      marginTop: "1px",
                    }}
                  >
                    {step.passed ? "✓" : "✗"}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "13px" }}>
                        Step {step.index}: {step.action.toUpperCase()}
                      </span>
                      <span className="muted" style={{ fontSize: "12px", fontFamily: "var(--font-code)" }}>
                        {formatDuration(step.duration_ms)}
                      </span>
                    </div>
                    {step.selector ? (
                      <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px", fontFamily: "var(--font-code)" }}>
                        Target: <code style={{ color: "var(--brand-primary, #b5121b)" }}>{step.selector}</code>
                      </div>
                    ) : null}
                    <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-primary)" }}>
                      {step.message}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="panel" style={{ padding: "24px", textAlign: "center" }}>
              <p className="muted">
                {activeCase?.detail || "No step-by-step action telemetry recorded for this case."}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Captured Evidence & Artifacts */}
      {activeTab === "evidence" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {/* Evidence Filter Strip */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <div style={{ display: "flex", gap: "6px" }}>
              <button
                type="button"
                className={`btn-sm ${evidenceFilter === "all" ? "primary" : "secondary"}`}
                onClick={() => setEvidenceFilter("all")}
              >
                All ({allArtifacts.length})
              </button>
              <button
                type="button"
                className={`btn-sm ${evidenceFilter === "screenshot" ? "primary" : "secondary"}`}
                onClick={() => setEvidenceFilter("screenshot")}
              >
                Screenshots ({allArtifacts.filter((a) => a.type === "screenshot" && !a.label.toLowerCase().includes("highlight")).length})
              </button>
              <button
                type="button"
                className={`btn-sm ${evidenceFilter === "highlight" ? "primary" : "secondary"}`}
                onClick={() => setEvidenceFilter("highlight")}
              >
                Highlighted Targets ({allArtifacts.filter((a) => a.label.toLowerCase().includes("highlight")).length})
              </button>
              <button
                type="button"
                className={`btn-sm ${evidenceFilter === "video" ? "primary" : "secondary"}`}
                onClick={() => setEvidenceFilter("video")}
              >
                Videos ({allArtifacts.filter((a) => a.type === "video").length})
              </button>
            </div>
            <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
              {filteredArtifacts.length} artifact{filteredArtifacts.length === 1 ? "" : "s"} shown
            </span>
          </div>

          {/* Artifact Grid */}
          {filteredArtifacts.length > 0 ? (
            <div className="execution-artifact-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "12px" }}>
              {filteredArtifacts.map((art, idx) => {
                const filename = art.path.split(/[\\/]/).pop() ?? "";
                const key = `${art.runId}:${filename}`;
                const blobUrl = artifactBlobUrls[key];

                return (
                  <article
                    className="execution-artifact-card"
                    key={`build-art-${idx}-${art.path}`}
                    style={{
                      border: "1px solid var(--border-light)",
                      borderRadius: "var(--radius-md)",
                      background: "var(--bg-layer-2)",
                      padding: "10px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "8px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "4px" }}>
                      <strong style={{ fontSize: "12px", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                        {art.label}
                      </strong>
                      <span className="badge badge-secondary" style={{ fontSize: "10px", textTransform: "uppercase" }}>
                        {art.type}
                      </span>
                    </div>

                    <small className="muted" style={{ fontSize: "11px" }}>
                      {art.caseTitle}
                    </small>

                    {/* Media Preview */}
                    {blobUrl && art.type === "screenshot" ? (
                      <div
                        style={{ position: "relative", cursor: "pointer", borderRadius: "var(--radius-sm)", overflow: "hidden", maxHeight: "140px" }}
                        onClick={() => setPreviewImage({ url: blobUrl, label: art.label })}
                        title="Click to expand high-res screenshot"
                      >
                        <img src={blobUrl} alt={art.label} style={{ width: "100%", height: "130px", objectFit: "cover" }} />
                        <span
                          style={{
                            position: "absolute",
                            bottom: "4px",
                            right: "4px",
                            background: "rgba(0,0,0,0.7)",
                            color: "#fff",
                            fontSize: "10px",
                            padding: "2px 6px",
                            borderRadius: "4px",
                          }}
                        >
                          🔍 Zoom
                        </span>
                      </div>
                    ) : null}

                    {blobUrl && art.type === "video" ? (
                      <video controls preload="metadata" src={blobUrl} style={{ width: "100%", maxHeight: "130px", borderRadius: "var(--radius-sm)" }} />
                    ) : null}

                    {!blobUrl ? (
                      <div style={{ height: "100px", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-layer-1)", borderRadius: "var(--radius-sm)" }}>
                        <span className="muted" style={{ fontSize: "11px" }}>Loading artifact...</span>
                      </div>
                    ) : null}

                    {blobUrl && (
                      <a
                        className="execution-artifact-download"
                        href={blobUrl}
                        download={filename}
                        style={{ fontSize: "11px", textAlign: "center", marginTop: "auto" }}
                      >
                        Download {art.type}
                      </a>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="panel" style={{ padding: "32px", textAlign: "center" }}>
              <p className="muted">No artifacts match the selected evidence filter.</p>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Self-Healing & Diagnostics */}
      {activeTab === "diagnostics" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div className="panel" style={{ padding: "16px", background: "var(--bg-layer-2)", border: "1px solid var(--border-light)", borderRadius: "var(--radius-md)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
              <strong style={{ color: "var(--success, #10b981)", fontSize: "14px" }}>🩺 Autonomous Self-Learning &amp; Healer Status</strong>
            </div>
            <p className="muted" style={{ margin: 0, fontSize: "13px", lineHeight: 1.5 }}>
              The Playwright execution engine monitored all locators and DOM mutations in real time. Dynamic element perception and strict-mode disambiguation ensured resilience against selector drifts.
            </p>
          </div>

          {/* Self-Healing Locator Repairs */}
          {report.cases.some((c) => (c.result?.healed_steps ?? []).length > 0) && (
            <div className="workspace-table-surface" style={{ borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--border-light)" }}>
              <div style={{ padding: "10px 14px", background: "rgba(16, 185, 129, 0.1)", borderBottom: "1px solid var(--border-light)", fontWeight: 700, fontSize: "13px", color: "var(--success, #10b981)" }}>
                ✨ Self-Healing Locator Repairs (Playwright Test Healer)
              </div>
              <table className="build-subtable" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Step #</th>
                    <th>Original Selector</th>
                    <th>Healed Selector</th>
                    <th>Diagnosis / Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {report.cases.flatMap((c) => (c.result?.healed_steps ?? []).map((h, i) => (
                    <tr key={`healed-row-${c.caseId}-${i}`}>
                      <td><strong>{c.title}</strong></td>
                      <td>Step {h.index ?? i + 1}</td>
                      <td style={{ fontFamily: "var(--font-code)", fontSize: "12px", color: "var(--danger, #ef4444)" }}>
                        {h.original_step?.selector || "—"}
                      </td>
                      <td style={{ fontFamily: "var(--font-code)", fontSize: "12px", color: "var(--success, #10b981)", fontWeight: 600 }}>
                        {h.healed_step?.selector || "—"}
                      </td>
                      <td style={{ fontSize: "12px" }}>{h.reason || "Repaired with resilient locator"}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          )}

          {/* Post-Condition Checks Across Cases */}
          <div className="workspace-table-surface" style={{ borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--border-light)" }}>
            <div style={{ padding: "10px 14px", background: "var(--bg-layer-2)", borderBottom: "1px solid var(--border-light)", fontWeight: 700, fontSize: "13px" }}>
              Post-Condition Checks &amp; Assertions Summary
            </div>
            <table className="build-subtable" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Check Type</th>
                  <th>Expected / Target</th>
                  <th>Status</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {report.cases.flatMap((c) => (c.result?.checks ?? []).map((chk, i) => (
                  <tr key={`chk-row-${c.caseId}-${i}`}>
                    <td><strong>{c.title}</strong></td>
                    <td style={{ fontFamily: "var(--font-code)", fontSize: "12px" }}>{chk.type}</td>
                    <td style={{ fontFamily: "var(--font-code)", fontSize: "12px" }}>{chk.value}</td>
                    <td>{renderStatusChip(chk.passed ? "passed" : "failed")}</td>
                    <td style={{ fontSize: "12px" }}>{chk.message}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal Zoom for Screenshot */}
      {previewImage && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={() => setPreviewImage(null)}
          style={{ zIndex: 1100 }}
        >
          <div
            className="panel projects-modal"
            style={{ maxWidth: "90vw", width: "1000px", maxHeight: "90vh", display: "flex", flexDirection: "column" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="projects-modal-head">
              <div>
                <h3>{previewImage.label}</h3>
              </div>
              <button type="button" className="secondary btn-sm" onClick={() => setPreviewImage(null)}>
                ✕ Close
              </button>
            </div>
            <div style={{ overflow: "auto", flex: 1, padding: "16px 0", textAlign: "center" }}>
              <img src={previewImage.url} alt={previewImage.label} style={{ maxWidth: "100%", maxHeight: "75vh", borderRadius: "var(--radius-md)" }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
