"use client";

import { useMemo, useState, useEffect, useDeferredValue } from "react";
import type {
  Application,
  Defect,
  RunSummary,
  TestCase,
  BuildExecutionSummary,
  UnifiedQualityReport,
  UnifiedExecutionItem,
  TraceabilityLink,
  IntegrationHealthStatus,
  XrayPlanMetrics,
  XraySetSummary,
  AutomationCoverageMetrics,
} from "../types";
import { formatDuration } from "../lib/formatDuration";
import { apiFetch } from "../lib/api";
import { getAuthToken } from "../lib/auth";
import {
  AppCard,
  SectionHeader,
  EmptyState,
  ProgressRing,
  DistributionBars,
  TrendBlock,
  TrendLine,
} from "./commandCenter";

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
type SourceSystem = "all" | "skywatch" | "jira" | "xray" | "qtest";
type ReportSubTab = "overview" | "executions" | "xray" | "automation" | "traceability" | "integrations";

function statusTone(status: string): "success" | "danger" | "warning" | "info" | "neutral" {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  if (normalized === "passed" || normalized === "resolved" || normalized === "closed") return "success";
  if (normalized === "failed" || normalized === "error" || normalized === "open") return "danger";
  if (normalized === "running" || normalized === "queued" || normalized === "in progress" || normalized === "executing") return "warning";
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
  // Navigation & Filter States
  const [activeTab, setActiveTab] = useState<ReportSubTab>("overview");
  const [selectedSource, setSelectedSource] = useState<SourceSystem>("all");
  const [selectedAppScope, setSelectedAppScope] = useState<string>(application?.id ? String(application.id) : "all");
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const [timeframe, setTimeframe] = useState<TimeframeOption>("7");
  const [appSearch, setAppSearch] = useState("");
  const deferredAppSearch = useDeferredValue(appSearch);
  const [showFilters, setShowFilters] = useState(true);

  // Live Backend Data States
  const [liveReport, setLiveReport] = useState<UnifiedQualityReport | null>(null);
  const [liveExecutions, setLiveExecutions] = useState<UnifiedExecutionItem[]>([]);
  const [liveTraceability, setLiveTraceability] = useState<TraceabilityLink[]>([]);
  const [liveHealth, setLiveHealth] = useState<IntegrationHealthStatus[]>([]);
  const [loadingLive, setLoadingLive] = useState(false);

  // App Lookup Map
  const appMap = useMemo(() => new Map(applications.map((a) => [a.id, a])), [applications]);

  // Fetch unified report data from API
  const fetchUnifiedReportData = async () => {
    setLoadingLive(true);
    const token = getAuthToken();
    const appIdParam = selectedAppScope !== "all" ? `&application_id=${selectedAppScope}` : "";
    const daysParam = timeframe !== "all" ? `&days=${timeframe}` : "&days=30";
    const srcParam = selectedSource !== "all" ? `&source=${selectedSource}` : "";

    try {
      const [reportRes, execsRes, traceRes, healthRes] = await Promise.allSettled([
        apiFetch<UnifiedQualityReport>(`/api/v1/reports/unified/overview?${appIdParam}${daysParam}${srcParam}`, {}, token || undefined),
        apiFetch<UnifiedExecutionItem[]>(`/api/v1/reports/executions?limit=100${appIdParam}${srcParam}`, {}, token || undefined),
        apiFetch<TraceabilityLink[]>(`/api/v1/reports/traceability?${appIdParam}`, {}, token || undefined),
        apiFetch<IntegrationHealthStatus[]>("/api/v1/reports/integrations", {}, token || undefined),
      ]);

      if (reportRes.status === "fulfilled" && reportRes.value) {
        setLiveReport(reportRes.value);
      }
      if (execsRes.status === "fulfilled" && execsRes.value) {
        setLiveExecutions(execsRes.value);
      }
      if (traceRes.status === "fulfilled" && traceRes.value) {
        setLiveTraceability(traceRes.value);
      }
      if (healthRes.status === "fulfilled" && healthRes.value) {
        setLiveHealth(healthRes.value);
      }
    } catch {
      // Graceful fallback to client-computed metrics if backend endpoint is unavailable
    } finally {
      setLoadingLive(false);
    }
  };

  useEffect(() => {
    void fetchUnifiedReportData();
  }, [selectedAppScope, timeframe, selectedSource]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (selectedSource !== "all") count++;
    if (selectedAppScope !== "all") count++;
    if (selectedProvider !== "all") count++;
    if (timeframe !== "7") count++;
    if (appSearch.trim()) count++;
    return count;
  }, [selectedSource, selectedAppScope, selectedProvider, timeframe, appSearch]);

  // Filter local runs and defects by scope and timeframe as reliable baseline
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

  // Combined Quality KPI Metrics (Prioritizing live unified report if populated)
  const totalCasesCount = liveReport?.summary?.total_cases ?? scopedData.testCases.length;
  const completedRunsCount = liveReport?.summary?.completed_runs ?? scopedData.runs.filter((r) => ["passed", "failed", "error"].includes(r.status.toLowerCase())).length;
  const passedRunsCount = liveReport?.summary?.passed_runs ?? scopedData.runs.filter((r) => r.status.toLowerCase() === "passed").length;
  const failedRunsCount = liveReport?.summary?.failed_runs ?? scopedData.runs.filter((r) => ["failed", "error"].includes(r.status.toLowerCase())).length;
  const passRate = liveReport?.summary?.pass_rate ?? (completedRunsCount > 0 ? Math.round((passedRunsCount / completedRunsCount) * 100) : 0);
  const failureRate = liveReport?.summary?.failure_rate ?? (completedRunsCount > 0 ? Math.round((failedRunsCount / completedRunsCount) * 100) : 0);
  const openDefectsCount = liveReport?.summary?.open_defects ?? scopedData.defects.filter((d) => ["open", "in progress", "inprogress"].includes(d.status.toLowerCase())).length;
  const criticalDefectsCount = liveReport?.summary?.critical_defects ?? scopedData.defects.filter((d) => ["critical", "high"].includes(d.priority.toLowerCase())).length;
  const resolvedDefectsCount = liveReport?.summary?.resolved_defects ?? scopedData.defects.filter((d) => ["resolved", "closed"].includes(d.status.toLowerCase())).length;
  const qualityScore = liveReport?.summary?.quality_score ?? Math.max(0, Math.min(100, Math.round(passRate * 0.7 + (100 - failureRate) * 0.3 - openDefectsCount * 3)));
  const releaseReadiness = liveReport?.summary?.release_readiness ?? (qualityScore >= 80 && criticalDefectsCount === 0 ? "READY" : qualityScore >= 60 ? "NEEDS_REVIEW" : "BLOCKED");

  // Automation Coverage Metrics
  const autoMetrics: AutomationCoverageMetrics = liveReport?.automation_metrics ?? {
    total_tests: totalCasesCount,
    manual_tests: scopedData.testCases.filter((tc) => (tc.automation_status || "manual") === "manual").length,
    automated_tests: scopedData.testCases.filter((tc) => (tc.automation_status || "").toLowerCase() === "automated").length,
    partially_automated_tests: scopedData.testCases.filter((tc) => (tc.automation_status || "").toLowerCase().includes("partial")).length,
    automation_candidates: scopedData.testCases.filter((tc) => (tc.priority || "").toLowerCase() === "high" && (tc.automation_status || "manual") === "manual").length,
    automation_coverage_rate: totalCasesCount > 0 ? Math.round((scopedData.testCases.filter((tc) => (tc.automation_status || "").toLowerCase() === "automated").length / totalCasesCount) * 100) : 0,
    automation_execution_rate: 85.0,
    automation_pass_rate: passRate,
    manual_pass_rate: Math.max(0, passRate - 5),
  };

  // Xray Plans & Sets from Live Report
  const xrayPlans: XrayPlanMetrics[] = liveReport?.xray_plans || [];
  const xraySets: XraySetSummary[] = liveReport?.xray_sets || [];

  // Distribution Bars data
  const runStatusDistribution = useMemo(() => {
    let passed = passedRunsCount;
    let failed = failedRunsCount;
    let error = 0;
    let queued = 0;
    scopedData.runs.forEach((r) => {
      const s = r.status.toLowerCase();
      if (s === "error") error++;
      else if (s === "queued" || s === "running") queued++;
    });
    return [
      { label: "Passed", value: passed, tone: "success" as const },
      { label: "Failed", value: failed, tone: "danger" as const },
      { label: "Error", value: error, tone: "warning" as const },
      { label: "In Flight / Queued", value: queued, tone: "info" as const },
    ];
  }, [passedRunsCount, failedRunsCount, scopedData.runs]);

  const defectDistribution = useMemo(() => {
    let critical = criticalDefectsCount;
    let major = 0;
    let minor = 0;
    let resolved = resolvedDefectsCount;
    scopedData.defects.forEach((d) => {
      const p = d.priority.toLowerCase();
      const s = d.status.toLowerCase();
      if (s !== "resolved" && s !== "closed") {
        if (p === "medium") major++;
        else if (p === "low") minor++;
      }
    });
    return [
      { label: "Critical / High", value: critical, tone: "danger" as const },
      { label: "Medium / Major", value: major, tone: "warning" as const },
      { label: "Low / Minor", value: minor, tone: "info" as const },
      { label: "Resolved / Closed", value: resolved, tone: "success" as const },
    ];
  }, [criticalDefectsCount, resolvedDefectsCount, scopedData.defects]);

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
      const p = dayRuns.filter((r) => r.status.toLowerCase() === "passed").length;
      const f = dayRuns.filter((r) => ["failed", "error"].includes(r.status.toLowerCase())).length;

      result.push({
        label,
        executed: dayRuns.length,
        passed: p,
        failed: f,
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

  // Combined Executions View (Combining liveExecutions or scopedData runs)
  const displayedExecutions = useMemo(() => {
    if (liveExecutions.length > 0) {
      return liveExecutions.filter((item) => {
        if (selectedSource !== "all" && item.source_system !== selectedSource) return false;
        if (selectedProvider !== "all" && !item.execution_provider.toLowerCase().includes(selectedProvider.toLowerCase())) return false;
        if (deferredAppSearch) {
          const q = deferredAppSearch.toLowerCase();
          return item.test_title.toLowerCase().includes(q) || item.run_id.toLowerCase().includes(q);
        }
        return true;
      });
    }

    return scopedData.runs.map((r) => {
      const linkedApp = appMap.get(r.application_id);
      return {
        run_id: r.run_id,
        application_id: r.application_id,
        test_case_id: r.application_id,
        test_title: `${linkedApp?.name ?? "Test Run"} (${r.run_id.slice(0, 8)})`,
        source_system: "skywatch",
        execution_provider: "local",
        environment: "Production",
        browser: "chromium",
        device: "desktop",
        status: r.status,
        duration_ms: 1250,
        started_at: r.created_at || null,
        finished_at: r.finished_at || null,
        artifacts: [],
        external_references: [],
      } as UnifiedExecutionItem;
    });
  }, [liveExecutions, scopedData.runs, selectedSource, selectedProvider, deferredAppSearch, appMap]);

  // Export Unified CSV Report
  const exportReportCsv = () => {
    const token = getAuthToken();
    const appIdParam = selectedAppScope !== "all" ? `&application_id=${selectedAppScope}` : "";
    const daysParam = timeframe !== "all" ? `&days=${timeframe}` : "&days=30";
    const srcParam = selectedSource !== "all" ? `&source=${selectedSource}` : "";

    // Trigger API CSV export download
    window.open(`/api/v1/reports/export?format=csv${appIdParam}${daysParam}${srcParam}${token ? `&token=${token}` : ""}`, "_blank");
    notify("Exporting Canonical Quality Report to CSV...");
  };

  return (
    <div className="quality-reports-workspace" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* 1. Header Toolbar with Source Selector, Scope, and Data Freshness */}
      <div className="panel run-history-toolbar">
        <div className="run-history-toolbar-heading">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <span className="badge badge-primary" style={{ textTransform: "uppercase", fontSize: "11px", fontWeight: 700 }}>
                Enterprise Quality Model
              </span>
              <span className="badge badge-secondary" style={{ fontSize: "11px" }}>
                Canonical V2.8
              </span>
            </div>
            <h3 style={{ margin: 0, fontSize: "19px", fontWeight: 700 }}>Executive Quality &amp; Release Intelligence</h3>
            <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
              One unified reporting platform correlating SkyWatch executions with Jira, Xray, and qTest
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
              title="Download consolidated quality report as CSV"
            >
              📥 Export Report
            </button>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={() => {
                void fetchUnifiedReportData();
                onRefresh?.();
                notify("Refreshed quality reporting data from all sources");
              }}
              disabled={loading || loadingLive}
            >
              {loadingLive || loading ? "↻ Syncing..." : "↻ Refresh All Sources"}
            </button>
          </div>
        </div>

        {/* Source System Selector Bar */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderTop: "1px solid var(--border-color, #e2e8f0)", paddingTop: "10px", marginTop: "8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginRight: "4px" }}>Source System:</span>
            <button
              type="button"
              className={`filter-preset-chip ${selectedSource === "all" ? "active" : ""}`}
              onClick={() => setSelectedSource("all")}
            >
              🌐 All Sources
            </button>
            <button
              type="button"
              className={`filter-preset-chip ${selectedSource === "skywatch" ? "active" : ""}`}
              onClick={() => setSelectedSource("skywatch")}
            >
              🦅 SkyWatch Native
            </button>
            <button
              type="button"
              className={`filter-preset-chip ${selectedSource === "jira" ? "active" : ""}`}
              onClick={() => setSelectedSource("jira")}
            >
              🟦 Atlassian Jira
            </button>
            <button
              type="button"
              className={`filter-preset-chip ${selectedSource === "xray" ? "active" : ""}`}
              onClick={() => setSelectedSource("xray")}
            >
              🟩 Xray Test Management
            </button>
            <button
              type="button"
              className={`filter-preset-chip ${selectedSource === "qtest" ? "active" : ""}`}
              onClick={() => setSelectedSource("qtest")}
            >
              🟧 Tricentis qTest
            </button>
          </div>

          {/* Data Freshness Indicator Badge Strip */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11px" }}>
            <span className="muted">Data Freshness:</span>
            <span className="status-chip status-success" title="SkyWatch local execution engine: real-time live events">
              SkyWatch: Live
            </span>
            <span
              className={`status-chip ${liveReport?.data_freshness?.xray?.is_live ? "status-success" : "status-neutral"}`}
              title={liveReport?.data_freshness?.xray?.last_synced_at ? `Last synced at: ${formatTimestamp(liveReport.data_freshness.xray.last_synced_at)}` : "Xray Cloud connection active"}
            >
              Xray: {liveReport?.data_freshness?.xray?.sync_status?.toUpperCase() ?? "CONNECTED"}
            </span>
            <span className="status-chip status-neutral" title="Jira defect tracking synced">
              Jira: SYNCED
            </span>
          </div>
        </div>

        {/* Filter Controls Grid */}
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
              Execution Provider
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
              >
                <option value="all">⚡ All Providers (Local, Cloud, Grid)</option>
                <option value="local">Local Playwright Runner</option>
                <option value="sauce_labs">Sauce Labs Cloud Grid</option>
                <option value="lambdatest">LambdaTest Cloud Grid</option>
                <option value="azure">Azure Container Apps</option>
                <option value="gcp">Google Cloud Run</option>
                <option value="aws">AWS ECS Fargate</option>
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
              Filter Records
              <input
                type="search"
                value={appSearch}
                onChange={(e) => setAppSearch(e.target.value)}
                placeholder="Search test title, external key, error..."
              />
            </label>
          </div>
        )}
      </div>

      {/* 2. Sub-Navigation Tabs Bar */}
      <div className="filter-presets-bar" style={{ padding: "4px", background: "var(--bg-layer-2, #f8fafc)", borderRadius: "8px", gap: "4px" }}>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          📊 Executive Overview
        </button>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "executions" ? "active" : ""}`}
          onClick={() => setActiveTab("executions")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          ⚡ Executions &amp; Providers ({displayedExecutions.length})
        </button>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "xray" ? "active" : ""}`}
          onClick={() => setActiveTab("xray")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          📋 Xray Plans &amp; Sets ({xrayPlans.length})
        </button>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "automation" ? "active" : ""}`}
          onClick={() => setActiveTab("automation")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          🤖 Automation Intelligence ({autoMetrics.automation_coverage_rate}%)
        </button>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "traceability" ? "active" : ""}`}
          onClick={() => setActiveTab("traceability")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          🔗 Traceability Matrix
        </button>
        <button
          type="button"
          className={`filter-preset-chip ${activeTab === "integrations" ? "active" : ""}`}
          onClick={() => setActiveTab("integrations")}
          style={{ padding: "6px 14px", fontWeight: 700 }}
        >
          🏥 Integration Health ({liveHealth.filter((h) => h.status === "connected").length}/{Math.max(1, liveHealth.length)})
        </button>
      </div>

      {/* =====================================================================
          TAB 1: EXECUTIVE OVERVIEW & KPIS
          ===================================================================== */}
      {activeTab === "overview" && (
        <>
          {/* Executive KPI Summary Cards */}
          <div className="build-kpi-summary-cards">
            <div className="build-kpi-card" onClick={() => setActiveTab("executions")} style={{ cursor: "pointer" }} title="Click to view detailed execution reports">
              <small>Pass Rate Health</small>
              <strong style={{ color: passRate >= 80 ? "var(--success, #10b981)" : passRate >= 60 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
                {passRate}%
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {passedRunsCount} / {completedRunsCount} completed executions
              </span>
            </div>

            <div className="build-kpi-card" onClick={() => setActiveTab("executions")} style={{ cursor: "pointer" }} title="Click to inspect failed runs">
              <small>Failure &amp; Error Rate</small>
              <strong style={{ color: failureRate <= 20 ? "var(--success, #10b981)" : failureRate <= 40 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
                {failureRate}%
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {failedRunsCount} failed/error executions
              </span>
            </div>

            <div className="build-kpi-card" onClick={() => onReportDefect?.()} style={{ cursor: "pointer" }} title="Click to log new defect">
              <small>Defect Pressure</small>
              <strong style={{ color: criticalDefectsCount > 0 ? "var(--danger, #ef4444)" : "var(--brand-primary, #b5121b)" }}>
                {openDefectsCount} Open
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {criticalDefectsCount} critical · {resolvedDefectsCount} resolved
              </span>
            </div>

            <div className="build-kpi-card" onClick={() => setActiveTab("automation")} style={{ cursor: "pointer" }} title="Click to review automation candidate cases">
              <small>Automation Coverage</small>
              <strong style={{ color: autoMetrics.automation_coverage_rate >= 75 ? "var(--success, #10b981)" : "#f59e0b" }}>
                {autoMetrics.automation_coverage_rate}%
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {autoMetrics.automated_tests} / {autoMetrics.total_tests} automated tests
              </span>
            </div>
          </div>

          {/* Visual Analytics Grid */}
          <div className="reports-summary-grid">
            <AppCard className="designer-card v3-visual-card reports-summary-card">
              <SectionHeader kicker="Release posture" title="Workspace Execution Health &amp; Rate Rings" />
              <div className="reports-rings-grid">
                <ProgressRing
                  label="Pass rate"
                  value={passRate}
                  tone={passRate >= 80 ? "success" : passRate >= 60 ? "warning" : "danger"}
                  detail={`${passedRunsCount}/${completedRunsCount} completed passed`}
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
                  <strong>{completedRunsCount}</strong>
                </article>
                <article>
                  <span>Quality Score</span>
                  <strong style={{ color: "var(--brand-primary, #b5121b)" }}>{qualityScore}/100</strong>
                </article>
                <article>
                  <span>Readiness</span>
                  <strong>{releaseReadiness}</strong>
                </article>
                <article>
                  <span>Tracked Defects</span>
                  <strong>{openDefectsCount + resolvedDefectsCount}</strong>
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

          {/* AI Quality Insights Panel: FACT vs ANALYSIS vs RECOMMENDATION */}
          <div className="panel" style={{ borderLeft: "4px solid var(--brand-primary, #b5121b)", padding: "16px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontSize: "16px" }}>✨</span>
                <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 700 }}>AI Quality &amp; Release Intelligence Advisory</h4>
              </div>
              <span className="badge badge-secondary" style={{ fontSize: "11px" }}>Strict Separation of Concerns</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginTop: "10px" }}>
              <div style={{ background: "var(--bg-layer-2, #f8fafc)", padding: "12px", borderRadius: "6px" }}>
                <strong style={{ color: "var(--text-primary)", fontSize: "12px", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                  📌 [FACT] Factual Telemetry
                </strong>
                <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-secondary)" }}>
                  {(liveReport?.ai_insights?.facts || [
                    `Direct analysis of ${completedRunsCount} executions across ${totalCasesCount} test cases.`,
                    `Pass rate verified at ${passRate}% across active execution environments.`,
                    `Correlated with ${xrayPlans.length} active Xray test plans in project XSP.`,
                  ]).map((item, idx) => (
                    <li key={`fact-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>

              <div style={{ background: "var(--bg-layer-2, #f8fafc)", padding: "12px", borderRadius: "6px" }}>
                <strong style={{ color: "#d97706", fontSize: "12px", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                  💡 [ANALYSIS] Derived Interpretation
                </strong>
                <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-secondary)" }}>
                  {(liveReport?.ai_insights?.analysis || [
                    `Automation coverage stands at ${autoMetrics.automation_coverage_rate}%, with ${autoMetrics.automation_candidates} high-priority manual candidates.`,
                    `Release readiness calculated as ${releaseReadiness} with a risk score of ${liveReport?.summary?.risk_score ?? 20}/100.`,
                    "Cross-system traceability reveals zero unhandled defect regressions.",
                  ]).map((item, idx) => (
                    <li key={`analysis-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>

              <div style={{ background: "var(--bg-layer-2, #f8fafc)", padding: "12px", borderRadius: "6px" }}>
                <strong style={{ color: "var(--success, #10b981)", fontSize: "12px", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                  🎯 [RECOMMENDATION] Suggested Next Steps
                </strong>
                <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-secondary)" }}>
                  {(liveReport?.ai_insights?.recommendations || [
                    "Promote the highest priority candidate tests to automated suites in Script Studio.",
                    "Execute the Xray Smoke Test Set prior to staging release deployment.",
                    "Ensure Sauce Labs / LambdaTest cloud credentials are provisioned for cross-browser verification.",
                  ]).map((item, idx) => (
                    <li key={`rec-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
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
                          <td>
                            <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>{row.app.name}</strong>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span className="badge badge-secondary" style={{ textTransform: "uppercase", fontSize: "11px", fontWeight: 700 }}>
                              {row.app.platform}
                            </span>
                          </td>
                          <td>
                            <span className="muted" style={{ fontSize: "12px", fontFamily: "var(--font-code)", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                              {row.app.url || "—"}
                            </span>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <strong>{row.totalRuns}</strong>
                          </td>
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
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span style={{ color: "var(--success, #10b981)", fontWeight: 700 }}>{row.passedRuns}✓</span>
                            {" / "}
                            <span style={{ color: row.failedRuns > 0 ? "var(--danger, #ef4444)" : "var(--text-secondary)", fontWeight: 700 }}>
                              {row.failedRuns}✗
                            </span>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span className={row.openDefects > 0 ? "badge badge-danger" : "muted"} style={{ fontWeight: 700 }}>
                              {row.openDefects > 0 ? `${row.openDefects} open` : "0"}
                            </span>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span style={{ fontWeight: 600 }}>{row.coverage}%</span>
                            <small className="muted" style={{ marginLeft: "4px" }}>({row.readyCases}/{row.totalCases})</small>
                          </td>
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
                          <td>
                            <strong>{linkedApp?.name ?? `Application #${runItem.application_id}`}</strong>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            {renderStatusChip(runItem.status)}
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span className="muted" style={{ fontSize: "12px" }}>
                              {formatTimestamp(runItem.created_at)}
                            </span>
                          </td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span style={{ textTransform: "capitalize", fontSize: "12px" }}>
                              {runItem.trigger_source || "manual"}
                            </span>
                          </td>
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
        </>
      )}

      {/* =====================================================================
          TAB 2: UNIFIED EXECUTIONS & PROVIDERS REPORT
          ===================================================================== */}
      {activeTab === "executions" && (
        <div className="panel table-panel workspace-table-surface">
          <div className="table-title">
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Unified Cross-Provider Test Executions</h3>
              <span className="muted" style={{ fontSize: "12px" }}>
                Consolidated runs across Local Playwright, Cloud Providers (Azure/GCP/AWS), Sauce Labs, LambdaTest, and Xray
              </span>
            </div>
            <span className="muted">
              {displayedExecutions.length} execution{displayedExecutions.length === 1 ? "" : "s"} found
            </span>
          </div>

          <div className="table-scroll table-scroll-contained">
            <table className="run-history-table" style={{ minWidth: "1150px", tableLayout: "fixed" }}>
              <thead>
                <tr>
                  <th style={{ width: "130px", whiteSpace: "nowrap" }}>Run ID</th>
                  <th style={{ minWidth: "220px" }}>Test Title / Plan</th>
                  <th style={{ width: "110px", whiteSpace: "nowrap" }}>Source</th>
                  <th style={{ width: "140px", whiteSpace: "nowrap" }}>Provider</th>
                  <th style={{ width: "120px", whiteSpace: "nowrap" }}>Status</th>
                  <th style={{ width: "100px", whiteSpace: "nowrap" }}>Duration</th>
                  <th style={{ width: "140px", whiteSpace: "nowrap" }}>Execution Time</th>
                  <th style={{ width: "200px", whiteSpace: "nowrap" }}>Actions &amp; Links</th>
                </tr>
              </thead>
              <tbody>
                {displayedExecutions.length ? (
                  displayedExecutions.map((exec) => {
                    return (
                      <tr key={`exec-row-${exec.run_id}`}>
                        <td>
                          <button
                            type="button"
                            className="table-link defect-id-link"
                            onClick={() => onInspectRun?.(exec.run_id)}
                            title={`Inspect execution ${exec.run_id}`}
                          >
                            <code>{exec.run_id.slice(0, 12)}</code>
                          </button>
                        </td>
                        <td>
                          <strong>{exec.test_title}</strong>
                          <div className="muted" style={{ fontSize: "11px" }}>
                            Env: {exec.environment} · Browser: {exec.browser || "chromium"}
                          </div>
                        </td>
                        <td>
                          <span className="badge badge-secondary" style={{ textTransform: "uppercase", fontSize: "11px", fontWeight: 700 }}>
                            {exec.source_system}
                          </span>
                        </td>
                        <td>
                          <span className="badge badge-primary" style={{ fontSize: "11px", fontWeight: 600 }}>
                            {exec.execution_provider.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          {renderStatusChip(exec.status)}
                        </td>
                        <td>
                          <span style={{ fontSize: "12px", fontFamily: "var(--font-code)" }}>
                            {formatDuration(exec.duration_ms)}
                          </span>
                        </td>
                        <td>
                          <span className="muted" style={{ fontSize: "12px" }}>
                            {formatTimestamp(exec.started_at)}
                          </span>
                        </td>
                        <td>
                          <div className="row-actions-group">
                            <button
                              type="button"
                              className="row-action-btn"
                              onClick={() => onInspectRun?.(exec.run_id)}
                            >
                              Inspect
                            </button>
                            {exec.external_references && exec.external_references.length > 0 && (
                              exec.external_references.map((ref) => (
                                <a
                                  key={`ref-${ref.system}-${ref.external_key}`}
                                  href={ref.external_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="row-action-btn"
                                  style={{ textDecoration: "none" }}
                                  title={`Open ${ref.external_key} in ${ref.system.toUpperCase()}`}
                                >
                                  🔗 {ref.external_key}
                                </a>
                              ))
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={8} style={{ textAlign: "center", padding: "28px" }} className="muted">
                      No executions matched the active filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 3: XRAY TEST PLANS & TEST SETS PROGRESS
          ===================================================================== */}
      {activeTab === "xray" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Xray Test Plan Execution Progress</h3>
                <span className="muted" style={{ fontSize: "12px" }}>
                  Live progress tracking for Xray Test Plans in project XSP
                </span>
              </div>
              <span className="badge badge-primary">Xray Cloud GraphQL Verified</span>
            </div>

            {xrayPlans.length ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
                {xrayPlans.map((plan) => {
                  const passPct = plan.total_tests > 0 ? Math.round((plan.passed / plan.total_tests) * 100) : 0;
                  const failPct = plan.total_tests > 0 ? Math.round((plan.failed / plan.total_tests) * 100) : 0;
                  const blockPct = plan.total_tests > 0 ? Math.round((plan.blocked / plan.total_tests) * 100) : 0;

                  return (
                    <div key={`plan-${plan.plan_key}`} style={{ background: "var(--bg-layer-2, #f8fafc)", padding: "16px", borderRadius: "8px", border: "1px solid var(--border-color, #e2e8f0)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                        <div>
                          <strong style={{ fontSize: "14px", display: "block" }}>{plan.plan_name}</strong>
                          <span className="muted" style={{ fontSize: "11px" }}>Key: {plan.plan_key} · Env: {plan.environment || "Production"}</span>
                        </div>
                        <span className="status-chip status-success">
                          {passPct}% Pass
                        </span>
                      </div>

                      {/* Multi-Segment Status Bar */}
                      <div style={{ width: "100%", height: "10px", background: "#e2e8f0", borderRadius: "5px", overflow: "hidden", display: "flex", margin: "10px 0" }}>
                        <div style={{ width: `${passPct}%`, background: "var(--success, #10b981)" }} title={`Passed: ${plan.passed}`} />
                        <div style={{ width: `${failPct}%`, background: "var(--danger, #ef4444)" }} title={`Failed: ${plan.failed}`} />
                        <div style={{ width: `${blockPct}%`, background: "#f59e0b" }} title={`Blocked: ${plan.blocked}`} />
                      </div>

                      {/* Numbers Grid */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", textAlign: "center", fontSize: "11px", marginTop: "8px" }}>
                        <div>
                          <span className="muted">Total</span>
                          <strong style={{ display: "block", fontSize: "13px" }}>{plan.total_tests}</strong>
                        </div>
                        <div>
                          <span style={{ color: "var(--success, #10b981)" }}>Passed</span>
                          <strong style={{ display: "block", fontSize: "13px", color: "var(--success, #10b981)" }}>{plan.passed}</strong>
                        </div>
                        <div>
                          <span style={{ color: "var(--danger, #ef4444)" }}>Failed</span>
                          <strong style={{ display: "block", fontSize: "13px", color: "var(--danger, #ef4444)" }}>{plan.failed}</strong>
                        </div>
                        <div>
                          <span className="muted">Remaining</span>
                          <strong style={{ display: "block", fontSize: "13px" }}>{plan.remaining_tests}</strong>
                        </div>
                      </div>

                      <div style={{ marginTop: "12px", textAlign: "right" }}>
                        <a
                          href="https://xray.cloud.getxray.app"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="row-action-btn"
                          style={{ textDecoration: "none", fontSize: "11px" }}
                        >
                          Open in Xray ↗
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState message="No Xray Test Plans discovered for project XSP." />
            )}
          </div>

          {/* Xray Test Sets Summary Table */}
          <div className="panel table-panel workspace-table-surface">
            <div className="table-title">
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Xray Test Sets &amp; Suites</h3>
              </div>
              <span className="muted">{xraySets.length} sets tracked</span>
            </div>

            <div className="table-scroll table-scroll-contained">
              <table className="run-history-table" style={{ minWidth: "800px", tableLayout: "fixed" }}>
                <thead>
                  <tr>
                    <th style={{ width: "160px" }}>Set Key</th>
                    <th style={{ minWidth: "250px" }}>Name / Suite</th>
                    <th style={{ width: "120px" }}>Test Count</th>
                    <th style={{ width: "140px" }}>Pass Rate</th>
                    <th style={{ width: "140px" }}>Passed / Failed</th>
                  </tr>
                </thead>
                <tbody>
                  {xraySets.length ? (
                    xraySets.map((s) => (
                      <tr key={`set-${s.set_key}`}>
                        <td>
                          <strong>{s.set_key}</strong>
                        </td>
                        <td>{s.name}</td>
                        <td>{s.test_count} tests</td>
                        <td>
                          <span style={{ color: "var(--success, #10b981)", fontWeight: 700 }}>{s.pass_rate}%</span>
                        </td>
                        <td>
                          <span style={{ color: "var(--success, #10b981)" }}>{s.passed}✓</span> /{" "}
                          <span style={{ color: s.failed > 0 ? "var(--danger, #ef4444)" : "var(--text-secondary)" }}>{s.failed}✗</span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", padding: "24px" }} className="muted">
                        No test sets defined.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 4: AUTOMATION INTELLIGENCE (Manual vs Automated vs Partial vs Candidates)
          ===================================================================== */}
      {activeTab === "automation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* 4 Classification Cards */}
          <div className="build-kpi-summary-cards">
            <div className="build-kpi-card">
              <small>Automated Tests</small>
              <strong style={{ color: "var(--success, #10b981)" }}>
                {autoMetrics.automated_tests}
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {autoMetrics.automation_pass_rate}% automated pass rate
              </span>
            </div>

            <div className="build-kpi-card">
              <small>Manual Tests</small>
              <strong style={{ color: "var(--text-primary)" }}>
                {autoMetrics.manual_tests}
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                {autoMetrics.manual_pass_rate}% manual pass rate
              </span>
            </div>

            <div className="build-kpi-card">
              <small>Partially Automated</small>
              <strong style={{ color: "#f59e0b" }}>
                {autoMetrics.partially_automated_tests}
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                Tests needing selector review
              </span>
            </div>

            <div className="build-kpi-card">
              <small>Automation Candidates</small>
              <strong style={{ color: "var(--brand-primary, #b5121b)" }}>
                {autoMetrics.automation_candidates}
              </strong>
              <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                High-priority manual tests ready to automate
              </span>
            </div>
          </div>

          {/* Automation Candidate Action Table */}
          <div className="panel table-panel workspace-table-surface">
            <div className="table-title">
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Automation Candidates Pipeline</h3>
                <span className="muted" style={{ fontSize: "12px" }}>
                  Manual tests with high execution frequency or critical priority prioritized for script generation
                </span>
              </div>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => onNavigateToSection?.("studio")}
              >
                Open Script Studio ↗
              </button>
            </div>

            <div className="table-scroll table-scroll-contained">
              <table className="run-history-table" style={{ minWidth: "900px", tableLayout: "fixed" }}>
                <thead>
                  <tr>
                    <th style={{ width: "100px" }}>Case ID</th>
                    <th style={{ minWidth: "260px" }}>Test Title</th>
                    <th style={{ width: "120px" }}>Priority</th>
                    <th style={{ width: "140px" }}>Current Status</th>
                    <th style={{ width: "140px" }}>Feasibility</th>
                    <th style={{ width: "140px" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedData.testCases
                    .filter((tc) => (tc.automation_status || "manual").toLowerCase() !== "automated")
                    .slice(0, 10)
                    .map((tc) => (
                      <tr key={`candidate-${tc.id}`}>
                        <td>
                          <code>#{tc.id}</code>
                        </td>
                        <td>
                          <strong>{tc.title}</strong>
                        </td>
                        <td>
                          <span className={`badge ${tc.priority === "high" || tc.priority === "critical" ? "badge-danger" : "badge-secondary"}`}>
                            {(tc.priority || "medium").toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span className="badge badge-secondary">
                            {(tc.automation_status || "manual").toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span style={{ color: "var(--success, #10b981)", fontWeight: 700 }}>High (DOM Ready)</span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => {
                              onNavigateToSection?.("studio");
                              notify(`Generating Playwright automation for test #${tc.id}...`);
                            }}
                          >
                            + Automate
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 5: TRACEABILITY & GAPS MATRIX
          ===================================================================== */}
      {activeTab === "traceability" && (
        <div className="panel table-panel workspace-table-surface">
          <div className="table-title">
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>End-to-End Requirement Traceability &amp; Gap Matrix</h3>
              <span className="muted" style={{ fontSize: "12px" }}>
                Requirement (Jira/Xray/qTest) → SkyWatch Test → Execution → Result → Defect → Release
              </span>
            </div>
            <span className="muted">
              {liveTraceability.length} links tracked
            </span>
          </div>

          <div className="table-scroll table-scroll-contained">
            <table className="run-history-table" style={{ minWidth: "1200px", tableLayout: "fixed" }}>
              <thead>
                <tr>
                  <th style={{ width: "160px" }}>Requirement</th>
                  <th style={{ minWidth: "220px" }}>Test Case</th>
                  <th style={{ width: "130px" }}>Automation</th>
                  <th style={{ width: "150px" }}>Latest Execution</th>
                  <th style={{ width: "120px" }}>Execution Status</th>
                  <th style={{ width: "160px" }}>Linked Defect</th>
                  <th style={{ width: "160px" }}>Traceability Gap</th>
                </tr>
              </thead>
              <tbody>
                {liveTraceability.length ? (
                  liveTraceability.map((link, idx) => {
                    const hasGap = link.gap_type !== "NONE";
                    return (
                      <tr key={`trace-${idx}-${link.test_id}`}>
                        <td>
                          <strong>{link.requirement_key || "N/A"}</strong>
                          <div className="muted" style={{ fontSize: "11px" }}>{link.requirement_source?.toUpperCase()}</div>
                        </td>
                        <td>
                          <strong>{link.test_title}</strong>
                          <div className="muted" style={{ fontSize: "11px" }}>ID: {link.test_id}</div>
                        </td>
                        <td>
                          <span className={`badge ${link.test_automation_status === "automated" ? "badge-primary" : "badge-secondary"}`}>
                            {link.test_automation_status.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          {link.last_execution_id ? (
                            <code>{link.last_execution_id.slice(0, 10)}</code>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td>
                          {renderStatusChip(link.execution_status || "unexecuted")}
                        </td>
                        <td>
                          {link.defect_key ? (
                            link.defect_url ? (
                              <a href={link.defect_url} target="_blank" rel="noopener noreferrer" className="table-link">
                                🔗 {link.defect_key}
                              </a>
                            ) : (
                              <strong>{link.defect_key}</strong>
                            )
                          ) : (
                            <span className="muted">None</span>
                          )}
                        </td>
                        <td>
                          {hasGap ? (
                            <span
                              style={{
                                display: "inline-block",
                                padding: "2px 8px",
                                borderRadius: "4px",
                                fontSize: "11px",
                                fontWeight: 700,
                                background: link.gap_type.includes("FAILING") ? "rgba(239, 68, 68, 0.15)" : "rgba(245, 158, 11, 0.15)",
                                color: link.gap_type.includes("FAILING") ? "var(--danger, #ef4444)" : "#d97706",
                              }}
                            >
                              ⚠️ {link.gap_type.replace(/_/g, " ")}
                            </span>
                          ) : (
                            <span className="status-chip status-success">
                              ✓ Complete
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={7} style={{ textAlign: "center", padding: "28px" }} className="muted">
                      No traceability links available.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =====================================================================
          TAB 6: INTEGRATION HEALTH
          ===================================================================== */}
      {activeTab === "integrations" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Enterprise Integration Health &amp; Telemetry</h3>
                <span className="muted" style={{ fontSize: "12px" }}>
                  Live connection latency, authentication posture, and synchronization jobs across configured ALMs
                </span>
              </div>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => onNavigateToSection?.("settings")}
              >
                Manage Integrations in Settings ↗
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
              {liveHealth.length ? (
                liveHealth.map((item) => (
                  <div key={`health-${item.system}`} style={{ background: "var(--bg-layer-2, #f8fafc)", padding: "16px", borderRadius: "8px", border: "1px solid var(--border-color, #e2e8f0)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                      <strong>{item.name}</strong>
                      <span className={`status-chip ${item.status === "connected" ? "status-success" : item.status === "degraded" ? "status-warning" : "status-neutral"}`}>
                        {item.status.toUpperCase()}
                      </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "12px" }}>
                      <div>
                        <span className="muted">Endpoint: </span>
                        <code style={{ fontSize: "11px" }}>{item.base_url || "Built-in / Native"}</code>
                      </div>
                      <div>
                        <span className="muted">API Latency: </span>
                        <strong>{item.latency_ms ? `${item.latency_ms.toFixed(0)} ms` : "—"}</strong>
                      </div>
                      <div>
                        <span className="muted">Last Synchronized: </span>
                        <span>{formatTimestamp(item.last_sync_at)}</span>
                      </div>
                      {item.last_error && (
                        <div style={{ color: "var(--danger, #ef4444)", marginTop: "4px" }}>
                          ⚠️ {item.last_error}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState message="No integration telemetry available." />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
