"use client";

import { useMemo, useState, useDeferredValue } from "react";
import type { Application, Defect, RunSummary, TestCase, BuildExecutionSummary } from "../types";
import { formatDuration } from "../lib/formatDuration";
import { AppCard, SectionHeader, EmptyState, ProgressRing, DistributionBars, TrendBlock, TrendLine } from "./commandCenter";

interface QualityReportsWorkspaceProps {
  appName: string;
  application?: Application | null;
  applications: Application[];
  testCases: TestCase[];
  runs: RunSummary[];
  defects: Defect[];
  builds?: BuildExecutionSummary[];
  loading?: boolean;
  onRefresh?: () => void;
  onNavigateToSection?: (section: string) => void;
  onInspectRun?: (runId: string) => void;
  onReportDefect?: () => void;
  notify: (msg: string) => void;
}

type TimeframeOption = "7" | "14" | "30" | "all";

function statusTone(status: string): "success" | "danger" | "warning" | "info" | "neutral" {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  if (normalized === "passed" || normalized === "resolved" || normalized === "closed") return "success";
  if (normalized === "failed" || normalized === "error" || normalized === "open") return "danger";
  if (normalized === "running" || normalized === "queued" || normalized === "in progress") return "warning";
  return "neutral";
}

function renderStatusChip(status: string) {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  const label = normalized
    ? normalized
        .split(" ")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
    : "Unknown";
  const tone = statusTone(status);
  return (
    <span className={`status-chip status-${tone}`} style={{ whiteSpace: "nowrap" }}>
      <span>{label}</span>
    </span>
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export default function QualityReportsWorkspace({
  appName,
  application,
  applications,
  testCases,
  runs,
  defects,
  builds = [],
  loading = false,
  onRefresh,
  onNavigateToSection,
  onInspectRun,
  onReportDefect,
  notify,
}: QualityReportsWorkspaceProps) {
  const [selectedAppScope, setSelectedAppScope] = useState<string>(application?.id ? String(application.id) : "all");
  const [timeframe, setTimeframe] = useState<TimeframeOption>("7");
  const [appSearch, setAppSearch] = useState("");
  const deferredAppSearch = useDeferredValue(appSearch);
  const [showFilters, setShowFilters] = useState(true);

  // App Lookup Map
  const appMap = useMemo(() => new Map(applications.map((a) => [a.id, a])), [applications]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (selectedAppScope !== "all") count++;
    if (timeframe !== "7") count++;
    if (appSearch.trim()) count++;
    return count;
  }, [selectedAppScope, timeframe, appSearch]);

  // Filter runs and defects by scope and timeframe
  const scopedData = useMemo(() => {
    const now = Date.now();
    const days = timeframe === "all" ? 99999 : parseInt(timeframe, 10);
    const cutoffTime = now - days * 24 * 60 * 60 * 1000;

    const filteredRuns = runs.filter((run) => {
      if (selectedAppScope !== "all" && String(run.application_id) !== selectedAppScope) return false;
      if (timeframe !== "all" && run.created_at) {
        const runTime = new Date(run.created_at).getTime();
        if (!Number.isNaN(runTime) && runTime < cutoffTime) return false;
      }
      return true;
    });

    const filteredDefects = defects.filter((defect) => {
      if (selectedAppScope !== "all" && String(defect.application_id) !== selectedAppScope) return false;
      if (timeframe !== "all" && defect.updated_at) {
        const dTime = new Date(defect.updated_at).getTime();
        if (!Number.isNaN(dTime) && dTime < cutoffTime) return false;
      }
      return true;
    });

    const filteredCases = testCases.filter((tc) => {
      if (selectedAppScope !== "all" && String(tc.application_id) !== selectedAppScope) return false;
      return true;
    });

    return {
      runs: filteredRuns,
      defects: filteredDefects,
      testCases: filteredCases,
    };
  }, [runs, defects, testCases, selectedAppScope, timeframe]);

  // Quality KPI Metrics
  const completedRuns = useMemo(
    () => scopedData.runs.filter((r) => ["passed", "failed", "error"].includes(r.status.toLowerCase())),
    [scopedData.runs]
  );
  const passedRunsCount = useMemo(
    () => completedRuns.filter((r) => r.status.toLowerCase() === "passed").length,
    [completedRuns]
  );
  const failedRunsCount = useMemo(
    () => completedRuns.filter((r) => ["failed", "error"].includes(r.status.toLowerCase())).length,
    [completedRuns]
  );
  const inFlightRunsCount = useMemo(
    () => scopedData.runs.filter((r) => ["queued", "running"].includes(r.status.toLowerCase())).length,
    [scopedData.runs]
  );

  const passRate = completedRuns.length > 0 ? Math.round((passedRunsCount / completedRuns.length) * 100) : 0;
  const failureRate = completedRuns.length > 0 ? Math.round((failedRunsCount / completedRuns.length) * 100) : 0;

  // Defect metrics
  const openDefectsCount = useMemo(
    () => scopedData.defects.filter((d) => ["open", "in progress", "inprogress"].includes(d.status.toLowerCase())).length,
    [scopedData.defects]
  );
  const resolvedDefectsCount = useMemo(
    () => scopedData.defects.filter((d) => ["resolved", "closed"].includes(d.status.toLowerCase())).length,
    [scopedData.defects]
  );
  const criticalDefectsCount = useMemo(
    () => scopedData.defects.filter((d) => ["critical", "high"].includes(d.priority.toLowerCase())).length,
    [scopedData.defects]
  );

  // Test Case Readiness metrics
  const readyCasesCount = useMemo(
    () => scopedData.testCases.filter((tc) => tc.status.toLowerCase() === "ready").length,
    [scopedData.testCases]
  );
  const coverageRate = scopedData.testCases.length > 0 ? Math.round((readyCasesCount / scopedData.testCases.length) * 100) : 0;

  // Distribution Bars data
  const runStatusDistribution = useMemo(() => {
    let passed = 0;
    let failed = 0;
    let error = 0;
    let queued = 0;
    scopedData.runs.forEach((r) => {
      const s = r.status.toLowerCase();
      if (s === "passed") passed++;
      else if (s === "failed") failed++;
      else if (s === "error") error++;
      else queued++;
    });
    return [
      { label: "Passed", value: passed, tone: "success" as const },
      { label: "Failed", value: failed, tone: "danger" as const },
      { label: "Error", value: error, tone: "warning" as const },
      { label: "Queued / Running", value: queued, tone: "info" as const },
    ];
  }, [scopedData.runs]);

  const defectDistribution = useMemo(() => {
    let critical = 0;
    let major = 0;
    let minor = 0;
    let resolved = 0;
    scopedData.defects.forEach((d) => {
      const s = d.status.toLowerCase();
      const p = d.priority.toLowerCase();
      if (s === "resolved" || s === "closed") resolved++;
      else if (p === "critical" || p === "high") critical++;
      else if (p === "medium") major++;
      else minor++;
    });
    return [
      { label: "Critical / High", value: critical, tone: "danger" as const },
      { label: "Medium / Major", value: major, tone: "warning" as const },
      { label: "Low / Minor", value: minor, tone: "info" as const },
      { label: "Resolved / Closed", value: resolved, tone: "success" as const },
    ];
  }, [scopedData.defects]);

  // Trend Generator (Daily timeline)
  const daysCount = timeframe === "all" ? 14 : parseInt(timeframe, 10);
  const executionTrend = useMemo(() => {
    const days = Math.min(daysCount, 30);
    const result: Array<{ label: string; executed: number; passed: number; failed: number }> = [];
    const now = new Date();

    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dayStr = d.toISOString().slice(0, 10);
      const label = d.toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" });

      const dayRuns = scopedData.runs.filter((r) => r.created_at && r.created_at.startsWith(dayStr));
      const passed = dayRuns.filter((r) => r.status.toLowerCase() === "passed").length;
      const failed = dayRuns.filter((r) => ["failed", "error"].includes(r.status.toLowerCase())).length;

      result.push({
        label,
        executed: dayRuns.length,
        passed,
        failed,
      });
    }
    return result;
  }, [scopedData.runs, daysCount]);

  const defectTrend = useMemo(() => {
    const days = Math.min(daysCount, 30);
    const result: Array<{ label: string; opened: number; closed: number }> = [];
    const now = new Date();

    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dayStr = d.toISOString().slice(0, 10);
      const label = d.toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" });

      const opened = scopedData.defects.filter((def) => def.updated_at && def.updated_at.startsWith(dayStr) && def.status.toLowerCase() === "open").length;
      const closed = scopedData.defects.filter((def) => def.updated_at && def.updated_at.startsWith(dayStr) && ["resolved", "closed"].includes(def.status.toLowerCase())).length;

      result.push({
        label,
        opened,
        closed,
      });
    }
    return result;
  }, [scopedData.defects, daysCount]);

  // Recent Failures Log
  const recentFailures = useMemo(() => {
    return scopedData.runs
      .filter((r) => ["failed", "error"].includes(r.status.toLowerCase()))
      .slice(0, 10);
  }, [scopedData.runs]);

  // Application Matrix Rows
  const applicationMatrixRows = useMemo(() => {
    const q = deferredAppSearch.trim().toLowerCase();
    return applications
      .filter((appItem) => {
        if (selectedAppScope !== "all" && String(appItem.id) !== selectedAppScope) return false;
        if (!q) return true;
        return (
          appItem.name.toLowerCase().includes(q) ||
          appItem.platform.toLowerCase().includes(q) ||
          (appItem.url && appItem.url.toLowerCase().includes(q))
        );
      })
      .map((appItem) => {
        const appRuns = runs.filter((r) => r.application_id === appItem.id);
        const appCompleted = appRuns.filter((r) => ["passed", "failed", "error"].includes(r.status.toLowerCase()));
        const appPassed = appCompleted.filter((r) => r.status.toLowerCase() === "passed").length;
        const appFailed = appCompleted.filter((r) => ["failed", "error"].includes(r.status.toLowerCase())).length;
        const appPassRate = appCompleted.length > 0 ? Math.round((appPassed / appCompleted.length) * 100) : 0;
        const appDefects = defects.filter((d) => d.application_id === appItem.id && ["open", "in progress"].includes(d.status.toLowerCase())).length;
        const appCases = testCases.filter((tc) => tc.application_id === appItem.id);
        const appReadyCases = appCases.filter((tc) => tc.status.toLowerCase() === "ready").length;
        const appCoverage = appCases.length > 0 ? Math.round((appReadyCases / appCases.length) * 100) : 0;

        let healthStatus: "Healthy" | "At Risk" | "Degraded" = "Healthy";
        if (appCompleted.length > 0 && appPassRate < 60) healthStatus = "Degraded";
        else if ((appCompleted.length > 0 && appPassRate < 80) || appDefects >= 3) healthStatus = "At Risk";

        return {
          app: appItem,
          totalRuns: appRuns.length,
          completedRuns: appCompleted.length,
          passedRuns: appPassed,
          failedRuns: appFailed,
          passRate: appPassRate,
          openDefects: appDefects,
          totalCases: appCases.length,
          readyCases: appReadyCases,
          coverage: appCoverage,
          healthStatus,
        };
      });
  }, [applications, selectedAppScope, deferredAppSearch, runs, defects, testCases]);

  const exportReportCsv = () => {
    if (!applicationMatrixRows.length && !scopedData.runs.length) {
      notify("No report data available to export.");
      return;
    }

    const headers = [
      "Application",
      "Platform",
      "Target URL",
      "Total Executions",
      "Pass Rate (%)",
      "Passed",
      "Failed / Error",
      "Open Defects",
      "Total Cases",
      "Ready Cases",
      "Coverage (%)",
      "Health Status",
    ];

    const rows = applicationMatrixRows.map((r) => [
      r.app.name,
      r.app.platform,
      r.app.url || "",
      r.totalRuns,
      `${r.passRate}%`,
      r.passedRuns,
      r.failedRuns,
      r.openDefects,
      r.totalCases,
      r.readyCases,
      `${r.coverage}%`,
      r.healthStatus,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [
        headers.map((h) => `"${h.replace(/"/g, '""')}"`).join(","),
        ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")),
      ].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `quality-matrix-report-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    notify("Exported Quality Matrix Report to CSV");
  };

  return (
    <div className="quality-reports-workspace" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Scope and Timeframe Toolbar */}
      <div className="panel run-history-toolbar">
        <div className="run-history-toolbar-heading">
          <div>
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Executive Quality &amp; Release Intelligence</h3>
            <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
              Multi-application execution posture, pass/fail trends, and defect pressure
            </span>
          </div>
          <div className="run-history-toolbar-actions">
            <button
              type="button"
              className="secondary btn-sm filter-toggle-btn"
              onClick={() => setShowFilters((prev) => !prev)}
              title={showFilters ? "Hide report filter controls" : "Show report filter controls"}
            >
              {showFilters ? "👁 Hide Filters" : "🔍 Show Filters"}
              {activeFilterCount > 0 && !showFilters && (
                <span className="filter-badge-counter">{activeFilterCount}</span>
              )}
            </button>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={exportReportCsv}
              title="Download quality metrics summary as CSV"
            >
              📥 Export CSV Summary
            </button>
            {onRefresh && (
              <button
                type="button"
                className="secondary btn-sm"
                onClick={onRefresh}
                disabled={loading}
              >
                {loading ? "Refreshing..." : "↻ Refresh Report Data"}
              </button>
            )}
          </div>
        </div>

        {/* Quick Presets for Timeframe */}
        <div className="filter-presets-bar">
          <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Time Window:</span>
          <button
            type="button"
            className={`filter-preset-chip ${timeframe === "7" ? "active" : ""}`}
            onClick={() => setTimeframe("7")}
          >
            Last 7 Days
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${timeframe === "14" ? "active" : ""}`}
            onClick={() => setTimeframe("14")}
          >
            Last 14 Days
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${timeframe === "30" ? "active" : ""}`}
            onClick={() => setTimeframe("30")}
          >
            Last 30 Days
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${timeframe === "all" ? "active" : ""}`}
            onClick={() => setTimeframe("all")}
          >
            All Time History
          </button>
        </div>

        {showFilters && (
          <div className="run-history-filter-grid" style={{ marginTop: "12px" }}>
            <label className="capture-label">
              Application Scope
              <select
                value={selectedAppScope}
                onChange={(e) => setSelectedAppScope(e.target.value)}
              >
                <option value="all">🌐 All Applications ({applications.length})</option>
                {applications.map((appItem) => (
                  <option key={`report-app-scope-${appItem.id}`} value={String(appItem.id)}>
                    {appItem.name} ({appItem.platform})
                  </option>
                ))}
              </select>
            </label>

            <label className="capture-label">
              Timeframe Window
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value as TimeframeOption)}
              >
                <option value="7">Last 7 Days</option>
                <option value="14">Last 14 Days</option>
                <option value="30">Last 30 Days</option>
                <option value="all">All Time History</option>
              </select>
            </label>

            <label className="capture-label">
              Filter Application Matrix
              <input
                type="search"
                value={appSearch}
                onChange={(e) => setAppSearch(e.target.value)}
                placeholder="Search application, platform, URL..."
              />
            </label>
          </div>
        )}

        {/* Active Filter Tags */}
        {activeFilterCount > 0 && (
          <div className="active-filter-tags">
            <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeFilterCount}):</span>
            {selectedAppScope !== "all" && (
              <span className="active-filter-tag">
                App: {appMap.get(Number(selectedAppScope))?.name ?? selectedAppScope}
                <button type="button" onClick={() => setSelectedAppScope("all")} aria-label="Clear app filter">✕</button>
              </span>
            )}
            {timeframe !== "7" && (
              <span className="active-filter-tag">
                Window: {timeframe === "all" ? "All Time" : `${timeframe} Days`}
                <button type="button" onClick={() => setTimeframe("7")} aria-label="Reset window">✕</button>
              </span>
            )}
            {appSearch && (
              <span className="active-filter-tag">
                "{appSearch}"
                <button type="button" onClick={() => setAppSearch("")} aria-label="Clear search">✕</button>
              </span>
            )}
            <button
              type="button"
              className="table-action"
              onClick={() => {
                setSelectedAppScope("all");
                setTimeframe("7");
                setAppSearch("");
              }}
              style={{ fontSize: "11px" }}
            >
              Reset filters
            </button>
          </div>
        )}
      </div>

      {/* 4 Executive KPI Metric Cards */}
      <div className="build-kpi-summary-cards">
        <div className="build-kpi-card">
          <small>Pass Rate Health</small>
          <strong style={{ color: passRate >= 80 ? "var(--success, #10b981)" : passRate >= 60 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
            {passRate}%
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {passedRunsCount} / {completedRuns.length} completed executions
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Failure &amp; Error Rate</small>
          <strong style={{ color: failureRate <= 20 ? "var(--success, #10b981)" : failureRate <= 40 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
            {failureRate}%
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {failedRunsCount} failed/error executions
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Defect Pressure</small>
          <strong style={{ color: criticalDefectsCount > 0 ? "var(--danger, #ef4444)" : "var(--brand-primary, #b5121b)" }}>
            {openDefectsCount} Open
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {criticalDefectsCount} critical · {resolvedDefectsCount} resolved
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Automation Coverage</small>
          <strong style={{ color: coverageRate >= 75 ? "var(--success, #10b981)" : "#f59e0b" }}>
            {coverageRate}%
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {readyCasesCount} / {scopedData.testCases.length} ready test cases
          </span>
        </div>
      </div>

      {/* Visual Analytics Grid */}
      <div className="reports-summary-grid">
        <AppCard className="designer-card v3-visual-card reports-summary-card">
          <SectionHeader kicker="Results analytics" title="Workspace Execution Health &amp; Rate Rings" />
          <div className="reports-rings-grid">
            <ProgressRing
              label="Pass rate"
              value={passRate}
              tone={passRate >= 80 ? "success" : passRate >= 60 ? "warning" : "danger"}
              detail={`${passedRunsCount}/${completedRuns.length} completed passed`}
            />
            <ProgressRing
              label="Failure rate"
              value={failureRate}
              tone={failureRate <= 20 ? "success" : failureRate <= 40 ? "warning" : "danger"}
              detail={`${failedRunsCount} failed/error executions`}
            />
          </div>
          <div className="reports-summary-strip">
            <article>
              <span>Total Executions</span>
              <strong>{scopedData.runs.length}</strong>
            </article>
            <article>
              <span>In-Flight / Queued</span>
              <strong>{inFlightRunsCount}</strong>
            </article>
            <article>
              <span>Active Builds</span>
              <strong>{builds.length}</strong>
            </article>
            <article>
              <span>Tracked Defects</span>
              <strong>{scopedData.defects.length}</strong>
            </article>
          </div>
        </AppCard>

        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Run posture" title="Execution status distribution" />
          <DistributionBars items={runStatusDistribution} />
        </AppCard>

        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Defect triage" title="Defect severity distribution" />
          <DistributionBars items={defectDistribution} />
        </AppCard>
      </div>

      {/* Multi-Day Trend Charts */}
      <div className="v3-chart-grid">
        <TrendBlock kicker="Execution velocity" title={`Daily Total vs Passed Runs (${daysCount} days)`}>
          {executionTrend.some((entry) => entry.executed > 0) ? (
            <div className="designer-line-chart cc-line-chart">
              <svg viewBox="0 0 360 140" preserveAspectRatio="none" aria-label="Execution trend chart">
                <TrendLine values={executionTrend.map((entry) => entry.executed)} className="line executed" />
                <TrendLine values={executionTrend.map((entry) => entry.passed)} className="line passed" />
              </svg>
              <div className="cc-line-labels">
                {executionTrend.map((entry, idx) =>
                  idx % Math.ceil(executionTrend.length / 7) === 0 || idx === executionTrend.length - 1 ? (
                    <span key={`rep-exec-${entry.label}`}>{entry.label}</span>
                  ) : null
                )}
              </div>
            </div>
          ) : (
            <EmptyState message="Execution trend timeline appears as runs are recorded." />
          )}
        </TrendBlock>

        <TrendBlock kicker="Quality movement" title={`Defect Activity Trend (${daysCount} days)`}>
          {defectTrend.some((entry) => entry.opened > 0 || entry.closed > 0) ? (
            <div className="designer-line-chart cc-line-chart">
              <svg viewBox="0 0 360 140" preserveAspectRatio="none" aria-label="Defect trend chart">
                <TrendLine values={defectTrend.map((entry) => entry.opened)} className="line opened" />
                <TrendLine values={defectTrend.map((entry) => entry.closed)} className="line closed" />
              </svg>
              <div className="cc-line-labels">
                {defectTrend.map((entry, idx) =>
                  idx % Math.ceil(defectTrend.length / 7) === 0 || idx === defectTrend.length - 1 ? (
                    <span key={`rep-def-${entry.label}`}>{entry.label}</span>
                  ) : null
                )}
              </div>
            </div>
          ) : (
            <EmptyState message="Defect velocity trend appears as defects are created and resolved." />
          )}
        </TrendBlock>
      </div>

      {/* Application Quality Matrix Table */}
      <div className="panel table-panel workspace-table-surface">
        <div className="table-title">
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Application Quality &amp; Coverage Matrix</h3>
          </div>
          <span className="muted">
            {applicationMatrixRows.length} application{applicationMatrixRows.length === 1 ? "" : "s"} tracked
          </span>
        </div>

        <div className="table-scroll table-scroll-contained">
          <table className="run-history-table" style={{ minWidth: "1150px", tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th style={{ width: "220px" }}>Application</th>
                <th style={{ width: "100px", whiteSpace: "nowrap" }}>Platform</th>
                <th style={{ minWidth: "220px" }}>Target URL</th>
                <th style={{ width: "110px", whiteSpace: "nowrap" }}>Executions</th>
                <th style={{ width: "160px" }}>Pass Rate</th>
                <th style={{ width: "130px", whiteSpace: "nowrap" }}>Passed / Failed</th>
                <th style={{ width: "110px", whiteSpace: "nowrap" }}>Open Defects</th>
                <th style={{ width: "130px", whiteSpace: "nowrap" }}>Coverage</th>
                <th style={{ width: "120px", whiteSpace: "nowrap" }}>Health</th>
                <th style={{ width: "140px", whiteSpace: "nowrap" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applicationMatrixRows.length ? (
                applicationMatrixRows.map((row) => {
                  const healthColor =
                    row.healthStatus === "Healthy"
                      ? "var(--success, #10b981)"
                      : row.healthStatus === "At Risk"
                      ? "#f59e0b"
                      : "var(--danger, #ef4444)";

                  return (
                    <tr key={`app-matrix-${row.app.id || row.app.name}`}>
                      {/* Application Name */}
                      <td>
                        <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>{row.app.name}</strong>
                      </td>

                      {/* Platform */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className="badge badge-secondary" style={{ textTransform: "uppercase", fontSize: "11px", fontWeight: 700 }}>
                          {row.app.platform}
                        </span>
                      </td>

                      {/* Target URL */}
                      <td>
                        <span className="muted" style={{ fontSize: "12px", fontFamily: "var(--font-code)", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                          {row.app.url || "—"}
                        </span>
                      </td>

                      {/* Total Executions */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <strong>{row.totalRuns}</strong>
                      </td>

                      {/* Pass Rate Progress Bar */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", fontWeight: 700 }}>
                            <span style={{ color: row.passRate >= 80 ? "var(--success, #10b981)" : "#f59e0b" }}>{row.passRate}%</span>
                            <small className="muted">{row.passedRuns}/{row.completedRuns}</small>
                          </div>
                          <div style={{ width: "100%", height: "6px", background: "var(--bg-layer-2, #e2e8f0)", borderRadius: "3px", overflow: "hidden" }}>
                            <div style={{ width: `${row.passRate}%`, height: "100%", background: row.passRate >= 80 ? "var(--success, #10b981)" : "#f59e0b" }} />
                          </div>
                        </div>
                      </td>

                      {/* Passed / Failed */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span style={{ color: "var(--success, #10b981)", fontWeight: 700 }}>{row.passedRuns}✓</span>
                        {" / "}
                        <span style={{ color: row.failedRuns > 0 ? "var(--danger, #ef4444)" : "var(--text-secondary)", fontWeight: 700 }}>
                          {row.failedRuns}✗
                        </span>
                      </td>

                      {/* Open Defects */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className={row.openDefects > 0 ? "badge badge-danger" : "muted"} style={{ fontWeight: 700 }}>
                          {row.openDefects > 0 ? `${row.openDefects} open` : "0"}
                        </span>
                      </td>

                      {/* Coverage */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span style={{ fontWeight: 600 }}>{row.coverage}%</span>
                        <small className="muted" style={{ marginLeft: "4px" }}>({row.readyCases}/{row.totalCases})</small>
                      </td>

                      {/* Health Status */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            padding: "2px 8px",
                            borderRadius: "999px",
                            fontSize: "11px",
                            fontWeight: 700,
                            background: row.healthStatus === "Healthy" ? "rgba(22, 163, 74, 0.12)" : row.healthStatus === "At Risk" ? "rgba(245, 158, 11, 0.14)" : "rgba(220, 38, 38, 0.12)",
                            color: healthColor,
                            border: `1px solid ${healthColor}40`,
                          }}
                        >
                          ● {row.healthStatus}
                        </span>
                      </td>

                      {/* Actions */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <div className="row-actions-group">
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => onNavigateToSection?.("cases")}
                          >
                            Cases
                          </button>
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => onNavigateToSection?.("execution")}
                          >
                            Execute
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", padding: "28px" }} className="muted">
                    No applications matched the current search filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Failures Needing Attention Table */}
      <div className="panel table-panel workspace-table-surface">
        <div className="table-title">
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Recent Failures &amp; Attention Triage</h3>
          </div>
          <span className="muted">
            {recentFailures.length ? `${recentFailures.length} latest failure/error run${recentFailures.length === 1 ? "" : "s"}` : "No failed executions"}
          </span>
        </div>

        <div className="table-scroll table-scroll-contained">
          <table className="run-history-table" style={{ minWidth: "960px", tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th className="col-id" style={{ width: "120px", whiteSpace: "nowrap" }}>Run ID</th>
                <th style={{ width: "180px" }}>Application</th>
                <th style={{ width: "120px", whiteSpace: "nowrap" }}>Status</th>
                <th style={{ width: "180px", whiteSpace: "nowrap" }}>Started</th>
                <th style={{ width: "140px", whiteSpace: "nowrap" }}>Trigger</th>
                <th style={{ width: "200px", whiteSpace: "nowrap" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {recentFailures.length ? (
                recentFailures.map((runItem) => {
                  const linkedApp = appMap.get(runItem.application_id);
                  return (
                    <tr key={`rep-fail-${runItem.run_id}`}>
                      {/* Run ID */}
                      <td className="col-id" style={{ whiteSpace: "nowrap" }}>
                        <button
                          type="button"
                          className="table-link defect-id-link"
                          onClick={() => onInspectRun?.(runItem.run_id)}
                          title={`Inspect run ${runItem.run_id}`}
                        >
                          <code>{runItem.run_id.slice(0, 8)}</code>
                        </button>
                      </td>

                      {/* Application */}
                      <td>
                        <strong>{linkedApp?.name ?? `Application #${runItem.application_id}`}</strong>
                      </td>

                      {/* Status */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        {renderStatusChip(runItem.status)}
                      </td>

                      {/* Started */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className="muted" style={{ fontSize: "12px" }}>
                          {formatTimestamp(runItem.created_at)}
                        </span>
                      </td>

                      {/* Trigger */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span style={{ textTransform: "capitalize", fontSize: "12px" }}>
                          {runItem.trigger_source || "manual"}
                        </span>
                      </td>

                      {/* Actions */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <div className="row-actions-group">
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => onInspectRun?.(runItem.run_id)}
                            title="Open detailed run diagnostics and logs"
                          >
                            Inspect Run
                          </button>
                          {onReportDefect && (
                            <button
                              type="button"
                              className="row-action-btn danger"
                              onClick={onReportDefect}
                              title="Report a defect linked to this failure"
                            >
                              + Defect
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "28px" }} className="muted">
                    No execution failures recorded in the selected timeframe. All runs passed successfully.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
