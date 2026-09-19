"use client";

import { useEffect, useMemo, useState, useDeferredValue } from "react";
import type { Application, Defect } from "../types";
import { AppCard, SectionHeader, EmptyState } from "./commandCenter";
import AppIcon from "./navigation/AppIcon";
import { apiFetch } from "../lib/api";

interface DefectManagementWorkspaceProps {
  appName: string;
  application?: Application | null;
  applications: Application[];
  defects: Defect[];
  loading?: boolean;
  token?: string | null;
  onReportDefect: () => void;
  onEditDefect: (defect: Defect) => void;
  onDeleteDefect: (defect: Defect) => Promise<void>;
  onQuickStatusChange?: (defect: Defect, nextStatus: string) => Promise<void>;
  deletingDefectId?: number | null;
  onRefresh?: () => void;
  notify: (msg: string) => void;
}

type SortColumn = "updated" | "id" | "title" | "priority" | "severity" | "status" | "application";
type SortDirection = "asc" | "desc";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function statusTone(status: string) {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  if (normalized === "resolved" || normalized === "closed") return "success";
  if (normalized === "in progress" || normalized === "running") return "info";
  if (normalized === "open") return "danger";
  return "neutral";
}

function renderStatusChip(status: string) {
  const normalized = (status || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  const label = normalized
    ? normalized
        .split(" ")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
    : "Open";
  const tone = statusTone(status);
  return (
    <span className={`status-chip status-${tone}`}>
      <span>{label}</span>
    </span>
  );
}

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const start = Math.min(Math.max(currentPage - 2, 1), totalPages - 4);
  return Array.from({ length: 5 }, (_, index) => start + index);
}

type DistributionItem = {
  label: string;
  value: number;
  tone: "info" | "success" | "warning" | "danger" | "neutral";
};

function DistributionBars({ items, percent = false }: { items: DistributionItem[]; percent?: boolean }) {
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  const hasData = items.some((item) => item.value > 0);
  if (!hasData) return <EmptyState message="No records to visualize yet." />;
  return (
    <div className="v3-distribution-bars">
      {items.map((item) => (
        <div className="v3-distribution-row" key={`${item.label}-${item.tone}`}>
          <div className="v3-distribution-meta">
            <span>{item.label}</span>
            <strong>{item.value}{percent ? "%" : ""}</strong>
          </div>
          <div className="v3-distribution-track">
            <div
              className={`v3-distribution-fill tone-${item.tone}`}
              style={{ width: `${Math.max(Math.round((item.value / maxValue) * 100), item.value ? 6 : 0)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DefectManagementWorkspace({
  appName,
  application,
  applications,
  defects,
  loading = false,
  token,
  onReportDefect,
  onEditDefect,
  onDeleteDefect,
  onQuickStatusChange,
  deletingDefectId,
  onRefresh,
  notify,
}: DefectManagementWorkspaceProps) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [statusFilter, setStatusFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [appFilter, setAppFilter] = useState<string>("all");
  const [sortColumn, setSortColumn] = useState<SortColumn>("updated");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const [selectedDefectId, setSelectedDefectId] = useState<number | null>(null);
  const [quickUpdatingId, setQuickUpdatingId] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(true);

  // Export to external system state
  const [exportModalDefect, setExportModalDefect] = useState<Defect | null>(null);
  const [exportSystem, setExportSystem] = useState<"jira" | "qtest">("jira");
  const [exportProjectKey, setExportProjectKey] = useState("");
  const [exportIssueType, setExportIssueType] = useState("Bug");
  const [exporting, setExporting] = useState(false);

  const handleExportDefect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!exportModalDefect || !token) {
      notify("Authentication required to push defect to external system.");
      return;
    }
    setExporting(true);
    try {
      const endpoint = exportSystem === "jira"
        ? `/api/v1/defects/${exportModalDefect.id}/export-jira`
        : `/api/v1/defects/${exportModalDefect.id}/export-qtest`;
      const res = await apiFetch<{ external_key: string; external_url: string }>(
        endpoint,
        {
          method: "POST",
          body: JSON.stringify({
            project_key: exportProjectKey.trim() || undefined,
            issue_type: exportIssueType,
          }),
        },
        token,
      );
      notify(`Successfully logged to ${exportSystem.toUpperCase()} as ${res.external_key}!`);
      setExportModalDefect(null);
      if (onRefresh) onRefresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : `Failed to export defect to ${exportSystem.toUpperCase()}`);
    } finally {
      setExporting(false);
    }
  };

  // Active filter count for badge
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (search.trim()) count++;
    if (statusFilter !== "all") count++;
    if (priorityFilter !== "all") count++;
    if (severityFilter !== "all") count++;
    if (appFilter !== "all") count++;
    return count;
  }, [search, statusFilter, priorityFilter, severityFilter, appFilter]);

  // App map for quick lookup
  const appMap = useMemo(() => {
    return new Map(applications.map((a) => [a.id, a]));
  }, [applications]);

  // Reset pagination on filter changes
  useEffect(() => {
    setPage(1);
  }, [deferredSearch, statusFilter, priorityFilter, severityFilter, appFilter, sortColumn, sortDirection, pageSize]);

  // Filtered and Sorted Defects
  const filteredDefects = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase();
    return defects
      .filter((defect) => {
        const appNameMatch = (defect.application_id && appMap.get(defect.application_id)?.name) || "";
        const matchesSearch =
          !q ||
          `DEF-${defect.id}`.toLowerCase().includes(q) ||
          String(defect.id).includes(q) ||
          defect.title.toLowerCase().includes(q) ||
          (defect.description && defect.description.toLowerCase().includes(q)) ||
          defect.priority.toLowerCase().includes(q) ||
          defect.severity.toLowerCase().includes(q) ||
          defect.status.toLowerCase().includes(q) ||
          appNameMatch.toLowerCase().includes(q);

        const normalizedStatus = defect.status.trim().toLowerCase().replace(/[_-]+/g, " ");
        const matchesStatus =
          statusFilter === "all" ||
          (statusFilter === "open" && normalizedStatus === "open") ||
          (statusFilter === "in_progress" && (normalizedStatus === "in progress" || normalizedStatus === "inprogress")) ||
          (statusFilter === "resolved" && normalizedStatus === "resolved") ||
          (statusFilter === "closed" && normalizedStatus === "closed");

        const normalizedPriority = defect.priority.trim().toLowerCase();
        const matchesPriority = priorityFilter === "all" || normalizedPriority === priorityFilter;

        const normalizedSeverity = defect.severity.trim().toLowerCase();
        const matchesSeverity = severityFilter === "all" || normalizedSeverity === severityFilter;

        const matchesApp = appFilter === "all" || String(defect.application_id ?? "") === appFilter;

        return matchesSearch && matchesStatus && matchesPriority && matchesSeverity && matchesApp;
      })
      .sort((a, b) => {
        let cmp = 0;
        if (sortColumn === "id") {
          cmp = a.id - b.id;
        } else if (sortColumn === "title") {
          cmp = a.title.localeCompare(b.title);
        } else if (sortColumn === "priority") {
          const priorityWeight: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
          cmp = (priorityWeight[a.priority.toLowerCase()] || 0) - (priorityWeight[b.priority.toLowerCase()] || 0);
        } else if (sortColumn === "severity") {
          const severityWeight: Record<string, number> = { critical: 3, major: 2, minor: 1 };
          cmp = (severityWeight[a.severity.toLowerCase()] || 0) - (severityWeight[b.severity.toLowerCase()] || 0);
        } else if (sortColumn === "status") {
          cmp = a.status.localeCompare(b.status);
        } else if (sortColumn === "application") {
          const appA = (a.application_id && appMap.get(a.application_id)?.name) || "";
          const appB = (b.application_id && appMap.get(b.application_id)?.name) || "";
          cmp = appA.localeCompare(appB);
        } else {
          // Default: updated
          const timeA = a.updated_at ? new Date(a.updated_at).getTime() : a.id;
          const timeB = b.updated_at ? new Date(b.updated_at).getTime() : b.id;
          cmp = timeA - timeB;
        }
        return sortDirection === "asc" ? cmp : -cmp;
      });
  }, [defects, deferredSearch, statusFilter, priorityFilter, severityFilter, appFilter, sortColumn, sortDirection, appMap]);

  // Selected Defect object
  const selectedDefect = useMemo(() => {
    if (selectedDefectId !== null) {
      const found = defects.find((d) => d.id === selectedDefectId);
      if (found) return found;
    }
    return filteredDefects[0] ?? null;
  }, [defects, filteredDefects, selectedDefectId]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredDefects.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedDefects = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredDefects.slice(start, start + pageSize);
  }, [currentPage, filteredDefects, pageSize]);

  const firstVisibleIndex = filteredDefects.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const lastVisibleIndex = Math.min(currentPage * pageSize, filteredDefects.length);

  // KPI Metrics
  const totalDefectsCount = defects.length;
  const openDefectsCount = defects.filter((d) => d.status.toLowerCase() === "open").length;
  const inProgressDefectsCount = defects.filter((d) => d.status.toLowerCase().includes("progress")).length;
  const resolvedDefectsCount = defects.filter((d) => ["resolved", "closed"].includes(d.status.toLowerCase())).length;
  const criticalOrHighCount = defects.filter((d) => ["critical", "high"].includes(d.priority.toLowerCase())).length;
  const resolutionRate = totalDefectsCount > 0 ? Math.round((resolvedDefectsCount / totalDefectsCount) * 100) : 100;

  // Distribution data
  const priorityDistribution = useMemo<DistributionItem[]>(() => {
    const count = { critical: 0, high: 0, medium: 0, low: 0 };
    defects.forEach((defect) => {
      const priority = defect.priority.trim().toLowerCase();
      if (priority.includes("critical")) count.critical += 1;
      else if (priority.includes("high")) count.high += 1;
      else if (priority.includes("medium")) count.medium += 1;
      else count.low += 1;
    });
    return [
      { label: "Critical", value: count.critical, tone: "danger" },
      { label: "High", value: count.high, tone: "danger" },
      { label: "Medium", value: count.medium, tone: "warning" },
      { label: "Low", value: count.low, tone: "info" },
    ];
  }, [defects]);

  const statusDistribution = useMemo<DistributionItem[]>(() => {
    let open = 0;
    let inProgress = 0;
    let resolved = 0;
    let closed = 0;
    defects.forEach((defect) => {
      const status = defect.status.trim().toLowerCase();
      if (status === "open") open += 1;
      else if (status.includes("progress")) inProgress += 1;
      else if (status === "resolved") resolved += 1;
      else if (status === "closed") closed += 1;
      else open += 1;
    });
    return [
      { label: "Open", value: open, tone: "danger" },
      { label: "In Progress", value: inProgress, tone: "warning" },
      { label: "Resolved", value: resolved, tone: "success" },
      { label: "Closed", value: closed, tone: "neutral" },
    ];
  }, [defects]);

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setPriorityFilter("all");
    setSeverityFilter("all");
    setAppFilter("all");
    setSortColumn("updated");
    setSortDirection("desc");
  };

  const handleSort = (col: SortColumn) => {
    if (sortColumn === col) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(col);
      setSortDirection("desc");
    }
  };

  const exportCsv = () => {
    if (!filteredDefects.length) {
      notify("No defects match current filters to export.");
      return;
    }
    const headers = ["Defect ID", "Title", "Description", "Priority", "Severity", "Status", "Application", "Updated At"];
    const rows = filteredDefects.map((d) => [
      `DEF-${d.id}`,
      d.title,
      d.description || "",
      d.priority,
      d.severity,
      d.status,
      (d.application_id && appMap.get(d.application_id)?.name) || "Unlinked",
      d.updated_at ? new Date(d.updated_at).toLocaleString() : "Today",
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.map((h) => `"${h.replace(/"/g, '""')}"`).join(","), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))].join(
        "\n"
      );
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `defects-export-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    notify(`Exported ${filteredDefects.length} defect(s) to CSV`);
  };

  const handleQuickStatus = async (defect: Defect) => {
    if (!onQuickStatusChange) return;
    const current = defect.status.toLowerCase();
    const next = current === "open" ? "in progress" : current.includes("progress") ? "resolved" : current === "resolved" ? "closed" : "open";
    setQuickUpdatingId(defect.id);
    try {
      await onQuickStatusChange(defect, next);
    } finally {
      setQuickUpdatingId(null);
    }
  };

  return (
    <div className="defect-workspace" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* KPI Summary Cards */}
      <div className="build-kpi-summary-cards">
        <div className="build-kpi-card">
          <small>Total Defects</small>
          <strong>{totalDefectsCount}</strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {openDefectsCount} open · {inProgressDefectsCount} in progress
          </span>
        </div>
        <div className="build-kpi-card">
          <small>Resolution Rate</small>
          <strong style={{ color: resolutionRate >= 75 ? "var(--success, #10b981)" : resolutionRate >= 40 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
            {resolutionRate}%
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {resolvedDefectsCount} resolved or closed
          </span>
        </div>
        <div className="build-kpi-card">
          <small>Critical & High Priority</small>
          <strong style={{ color: criticalOrHighCount > 0 ? "var(--danger, #ef4444)" : "var(--success, #10b981)" }}>
            {criticalOrHighCount}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {criticalOrHighCount > 0 ? "Requires active triage" : "No urgent blockers"}
          </span>
        </div>
        <div className="build-kpi-card">
          <small>Filtered Defects</small>
          <strong style={{ color: "var(--brand-primary, #b5121b)" }}>
            {filteredDefects.length}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Matching active filters
          </span>
        </div>
      </div>

      {/* Analytics Pressure Cards */}
      <div className="v3-chart-grid" style={{ marginBottom: "4px" }}>
        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Severity pressure" title="Defect priority distribution" />
          <DistributionBars items={priorityDistribution} />
        </AppCard>
        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Resolution pressure" title="Defect status distribution" />
          <DistributionBars items={statusDistribution} />
        </AppCard>
      </div>

      {/* Filter & Search Toolbar */}
      <div className="panel run-history-toolbar">
        <div className="run-history-toolbar-heading">
          <div>
            <h3>Filter &amp; Search Defects</h3>
          </div>
          <div className="run-history-toolbar-actions">
            <button
              type="button"
              className="secondary btn-sm filter-toggle-btn"
              onClick={() => setShowFilters((prev) => !prev)}
              title={showFilters ? "Hide filter controls" : "Show filter controls"}
            >
              {showFilters ? "👁 Hide Filters" : "🔍 Show Filters"}
              {activeFilterCount > 0 && !showFilters && (
                <span className="filter-badge-counter">{activeFilterCount}</span>
              )}
            </button>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={exportCsv}
              disabled={!filteredDefects.length}
              title="Export filtered defects to CSV"
            >
              📥 Export CSV
            </button>
            {onRefresh && (
              <button
                type="button"
                className="secondary btn-sm"
                onClick={onRefresh}
                disabled={loading}
              >
                {loading ? "Refreshing..." : "↻ Refresh"}
              </button>
            )}
          </div>
        </div>

        {/* Quick Filter Presets */}
        <div className="filter-presets-bar">
          <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Quick Presets:</span>
          <button
            type="button"
            className={`filter-preset-chip ${statusFilter === "all" && priorityFilter === "all" ? "active" : ""}`}
            onClick={() => { setStatusFilter("all"); setPriorityFilter("all"); setSeverityFilter("all"); }}
          >
            All Defects ({totalDefectsCount})
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${priorityFilter === "critical" ? "active" : ""}`}
            onClick={() => { setPriorityFilter("critical"); }}
          >
            Critical / Blockers
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${statusFilter === "open" ? "active" : ""}`}
            onClick={() => { setStatusFilter("open"); }}
          >
            Open Only ({openDefectsCount})
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${statusFilter === "in_progress" ? "active" : ""}`}
            onClick={() => { setStatusFilter("in_progress"); }}
          >
            In Progress ({inProgressDefectsCount})
          </button>
          <button
            type="button"
            className={`filter-preset-chip ${statusFilter === "resolved" ? "active" : ""}`}
            onClick={() => { setStatusFilter("resolved"); }}
          >
            Resolved ({resolvedDefectsCount})
          </button>
        </div>

        {showFilters && (
          <div className="run-history-filter-grid" style={{ marginTop: "6px" }}>
            <label className="capture-label">
              Search defects
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="DEF-ID, title, description, app..."
              />
            </label>
            <label className="capture-label">
              Status
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">All statuses ({defects.length})</option>
                <option value="open">Open ({openDefectsCount})</option>
                <option value="in_progress">In Progress ({inProgressDefectsCount})</option>
                <option value="resolved">Resolved ({defects.filter((d) => d.status.toLowerCase() === "resolved").length})</option>
                <option value="closed">Closed ({defects.filter((d) => d.status.toLowerCase() === "closed").length})</option>
              </select>
            </label>
            <label className="capture-label">
              Priority
              <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
                <option value="all">All priorities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
            <label className="capture-label">
              Severity
              <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                <option value="all">All severities</option>
                <option value="critical">Critical</option>
                <option value="major">Major</option>
                <option value="minor">Minor</option>
              </select>
            </label>
            <label className="capture-label">
              Application
              <select value={appFilter} onChange={(e) => setAppFilter(e.target.value)}>
                <option value="all">All applications</option>
                {applications.map((appItem) => (
                  <option key={`defect-app-filter-${appItem.id}`} value={String(appItem.id)}>
                    {appItem.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="capture-label">
              Rows per page
              <select value={String(pageSize)} onChange={(e) => setPageSize(Number(e.target.value))}>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size} rows
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {/* Active Filter Tags with Single-Click Dismissal */}
        {activeFilterCount > 0 && (
          <div className="active-filter-tags">
            <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeFilterCount}):</span>
            {search && (
              <span className="active-filter-tag">
                "{search}"
                <button type="button" onClick={() => setSearch("")} aria-label="Clear search">✕</button>
              </span>
            )}
            {statusFilter !== "all" && (
              <span className="active-filter-tag">
                Status: {statusFilter.replace("_", " ")}
                <button type="button" onClick={() => setStatusFilter("all")} aria-label="Clear status">✕</button>
              </span>
            )}
            {priorityFilter !== "all" && (
              <span className="active-filter-tag">
                Priority: {priorityFilter}
                <button type="button" onClick={() => setPriorityFilter("all")} aria-label="Clear priority">✕</button>
              </span>
            )}
            {severityFilter !== "all" && (
              <span className="active-filter-tag">
                Severity: {severityFilter}
                <button type="button" onClick={() => setSeverityFilter("all")} aria-label="Clear severity">✕</button>
              </span>
            )}
            {appFilter !== "all" && (
              <span className="active-filter-tag">
                App: {appMap.get(Number(appFilter))?.name ?? appFilter}
                <button type="button" onClick={() => setAppFilter("all")} aria-label="Clear app filter">✕</button>
              </span>
            )}
            <button type="button" className="table-action" onClick={clearFilters} style={{ fontSize: "11px" }}>
              Clear all
            </button>
          </div>
        )}

        <div className="run-history-filter-summary">
          <span>
            {filteredDefects.length} matching defect{filteredDefects.length === 1 ? "" : "s"}
            {appName ? ` in ${appName}` : ""}
          </span>
          {activeFilterCount > 0 ? (
            <button type="button" className="table-action" onClick={clearFilters}>
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

      {/* Main Defects Table Surface */}
      <div className="panel table-panel workspace-table-surface">
        <div className="table-title">
          <div>
            <h3>Defect Log &amp; Triage Records</h3>
          </div>
          <span className="muted">
            {firstVisibleIndex}-{lastVisibleIndex} of {filteredDefects.length} shown
          </span>
        </div>

        <div className="table-scroll table-scroll-contained">
          <table className="run-history-table defect-table" style={{ minWidth: "1240px", tableLayout: "fixed", width: "100%" }}>
            <thead>
              <tr>
                <th className="col-id" style={{ width: "115px", minWidth: "115px", whiteSpace: "nowrap" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("id")}>
                    ID {sortColumn === "id" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-title" style={{ minWidth: "320px" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("title")}>
                    Defect Title &amp; Summary {sortColumn === "title" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-app" style={{ width: "150px", minWidth: "150px" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("application")}>
                    Application {sortColumn === "application" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-priority" style={{ width: "120px", minWidth: "120px", whiteSpace: "nowrap" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("priority")}>
                    Priority {sortColumn === "priority" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-severity" style={{ width: "120px", minWidth: "120px", whiteSpace: "nowrap" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("severity")}>
                    Severity {sortColumn === "severity" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-status" style={{ width: "130px", minWidth: "130px", whiteSpace: "nowrap" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("status")}>
                    Status {sortColumn === "status" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-updated" style={{ width: "160px", minWidth: "160px", whiteSpace: "nowrap" }}>
                  <button type="button" className="run-history-sort-button" onClick={() => handleSort("updated")}>
                    Updated {sortColumn === "updated" ? (sortDirection === "asc" ? "▲" : "▼") : ""}
                  </button>
                </th>
                <th className="col-actions" style={{ width: "230px", minWidth: "230px", whiteSpace: "nowrap" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pagedDefects.length ? (
                pagedDefects.map((defect) => {
                  const isSelected = selectedDefect?.id === defect.id;
                  const targetApp = defect.application_id ? appMap.get(defect.application_id) : null;
                  const normalizedPriority = defect.priority.toLowerCase();
                  const normalizedSeverity = defect.severity.toLowerCase();

                  return (
                    <tr
                      key={`defect-row-${defect.id}`}
                      className={isSelected ? "row-selected" : ""}
                      onClick={() => setSelectedDefectId(defect.id)}
                      style={{ cursor: "pointer" }}
                    >
                      {/* ID Badge */}
                      <td className="col-id" style={{ whiteSpace: "nowrap" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <button
                            type="button"
                            className="table-link defect-id-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedDefectId(defect.id);
                            }}
                          >
                            DEF-{defect.id}
                          </button>
                          {defect.external_links && defect.external_links.length > 0 && (
                            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                              {defect.external_links.map((link) => (
                                <a
                                  key={`link-${link.id}`}
                                  href={link.external_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="defect-id-badge"
                                  style={{ fontSize: "10px", padding: "1px 4px", textDecoration: "none" }}
                                  title={`Open in ${link.system.toUpperCase()}: ${link.external_key}`}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  🔗 {link.external_key}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Defect Title and Description Snippet */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                          <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>
                            {defect.title}
                          </strong>
                          {defect.description ? (
                            <small
                              className="muted"
                              style={{
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                                overflowWrap: "anywhere",
                                wordBreak: "break-word",
                                lineHeight: 1.35,
                              }}
                            >
                              {defect.description}
                            </small>
                          ) : (
                            <small className="muted" style={{ fontStyle: "italic" }}>No description provided</small>
                          )}
                        </div>
                      </td>

                      {/* Application */}
                      <td>
                        {targetApp ? (
                          <span className="badge badge-secondary" style={{ fontSize: "11px", fontWeight: 600, whiteSpace: "nowrap" }}>
                            {targetApp.name}
                          </span>
                        ) : (
                          <span className="muted" style={{ fontSize: "11px", whiteSpace: "nowrap" }}>Unlinked</span>
                        )}
                      </td>

                      {/* Priority */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className={`priority ${normalizedPriority}`} style={{ whiteSpace: "nowrap" }}>
                          {defect.priority}
                        </span>
                      </td>

                      {/* Severity */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span
                          className={`severity severity-${normalizedSeverity}`}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            padding: "2px 8px",
                            borderRadius: "999px",
                            fontSize: "var(--font-caption)",
                            fontWeight: 700,
                            textTransform: "capitalize",
                            whiteSpace: "nowrap",
                            background:
                              normalizedSeverity === "critical"
                                ? "rgba(220, 38, 38, 0.12)"
                                : normalizedSeverity === "major"
                                ? "rgba(245, 158, 11, 0.14)"
                                : "rgba(107, 114, 128, 0.12)",
                            color:
                              normalizedSeverity === "critical"
                                ? "#b91c1c"
                                : normalizedSeverity === "major"
                                ? "#b45309"
                                : "#475569",
                            border: `1px solid ${
                              normalizedSeverity === "critical"
                                ? "rgba(220, 38, 38, 0.25)"
                                : normalizedSeverity === "major"
                                ? "rgba(245, 158, 11, 0.25)"
                                : "rgba(107, 114, 128, 0.2)"
                            }`,
                          }}
                        >
                          {defect.severity}
                        </span>
                      </td>

                      {/* Status */}
                      <td style={{ whiteSpace: "nowrap" }}>{renderStatusChip(defect.status)}</td>

                      {/* Timestamp */}
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className="muted" style={{ fontSize: "12px", whiteSpace: "nowrap" }}>
                          {formatTimestamp(defect.updated_at || defect.created_by ? defect.updated_at : null)}
                        </span>
                      </td>

                      {/* Row Actions */}
                      <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap" }}>
                        <div className="row-actions-group" style={{ display: "flex", gap: "4px", flexWrap: "wrap", whiteSpace: "nowrap" }}>
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => setSelectedDefectId(defect.id)}
                            title="View defect inspector"
                          >
                            View
                          </button>
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => {
                              setExportModalDefect(defect);
                              setExportSystem("jira");
                            }}
                            title="Push defect to Jira or qTest"
                            style={{ color: "var(--brand-primary, #b5121b)", fontWeight: 600 }}
                          >
                            📤 Jira
                          </button>
                          <button
                            type="button"
                            className="row-action-btn"
                            onClick={() => onEditDefect(defect)}
                            title="Edit defect details"
                          >
                            Edit
                          </button>
                          {onQuickStatusChange && (
                            <button
                              type="button"
                              className="row-action-btn"
                              onClick={() => void handleQuickStatus(defect)}
                              disabled={quickUpdatingId === defect.id}
                              title={`Advance status from ${defect.status}`}
                              style={{ color: "var(--info-dark, #1e40af)", fontWeight: 600 }}
                            >
                              {quickUpdatingId === defect.id
                                ? "..."
                                : defect.status.toLowerCase() === "open"
                                ? "Start"
                                : defect.status.toLowerCase().includes("progress")
                                ? "Resolve"
                                : defect.status.toLowerCase() === "resolved"
                                ? "Close"
                                : "Reopen"}
                            </button>
                          )}
                          <button
                            type="button"
                            className="row-action-btn danger"
                            onClick={() => void onDeleteDefect(defect)}
                            disabled={deletingDefectId === defect.id}
                            title="Delete this defect"
                          >
                            {deletingDefectId === defect.id ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8}>
                    <div className="project-detail-empty" style={{ padding: "36px 16px", textAlign: "center" }}>
                      <strong>No defects match the current filters</strong>
                      <p className="muted">Try adjusting search parameters or report a new quality defect.</p>
                      <button type="button" className="primary btn-sm" onClick={onReportDefect} style={{ marginTop: "8px" }}>
                        + Report Defect
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="run-history-pagination" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px" }}>
            <span>
              Page {currentPage} of {totalPages} ({filteredDefects.length} total)
            </span>
            <div style={{ display: "flex", gap: "4px" }}>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => setPage((c) => Math.max(1, c - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </button>
              {getPageNumbers(currentPage, totalPages).map((pNum) => (
                <button
                  key={`defect-page-${pNum}`}
                  type="button"
                  className={`run-history-page-button ${pNum === currentPage ? "active" : ""}`}
                  onClick={() => setPage(pNum)}
                >
                  {pNum}
                </button>
              ))}
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => setPage((c) => Math.min(totalPages, c + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Selected Defect Detail Inspector */}
      {selectedDefect && (
        <div className="panel defect-detail" style={{ marginTop: "8px" }}>
          <div className="detail-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "4px" }}>
                <span style={{ fontFamily: "var(--font-code, monospace)", fontWeight: 800, color: "var(--brand-primary, #b5121b)", fontSize: "14px" }}>
                  DEF-{selectedDefect.id}
                </span>
                {renderStatusChip(selectedDefect.status)}
                <span className={`priority ${selectedDefect.priority.toLowerCase()}`}>
                  {selectedDefect.priority} Priority
                </span>
              </div>
              <h2 style={{ fontSize: "18px", fontWeight: 700, margin: 0, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                {selectedDefect.title}
              </h2>
            </div>

            <div className="projects-modal-actions" style={{ margin: 0 }}>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => {
                  setExportModalDefect(selectedDefect);
                  setExportSystem("jira");
                }}
                style={{ color: "var(--brand-primary, #b5121b)", fontWeight: 700 }}
              >
                📤 Push to Jira / qTest
              </button>
              <button type="button" className="secondary btn-sm" onClick={() => onEditDefect(selectedDefect)}>
                Edit Defect
              </button>
              {onQuickStatusChange && (
                <button
                  type="button"
                  className="secondary btn-sm"
                  onClick={() => void handleQuickStatus(selectedDefect)}
                  disabled={quickUpdatingId === selectedDefect.id}
                >
                  {quickUpdatingId === selectedDefect.id
                    ? "Updating..."
                    : selectedDefect.status.toLowerCase() === "open"
                    ? "Mark In Progress"
                    : selectedDefect.status.toLowerCase().includes("progress")
                    ? "Mark Resolved"
                    : selectedDefect.status.toLowerCase() === "resolved"
                    ? "Close Defect"
                    : "Reopen Defect"}
                </button>
              )}
              <button
                type="button"
                className="secondary btn-sm btn-danger"
                onClick={() => void onDeleteDefect(selectedDefect)}
                disabled={deletingDefectId === selectedDefect.id}
              >
                {deletingDefectId === selectedDefect.id ? "Deleting..." : "Delete Defect"}
              </button>
            </div>
          </div>

          <div className="detail-grid" style={{ marginTop: "12px" }}>
            <div>
              <span className="detail-label">Issue Type</span>
              <strong>Quality Bug / Defect</strong>
            </div>
            <div>
              <span className="detail-label">Target Application</span>
              <strong>
                {(selectedDefect.application_id && appMap.get(selectedDefect.application_id)?.name) || "Unlinked / Global"}
              </strong>
            </div>
            <div>
              <span className="detail-label">Severity Level</span>
              <strong style={{ textTransform: "capitalize" }}>{selectedDefect.severity}</strong>
            </div>
            <div>
              <span className="detail-label">Last Updated</span>
              <strong>{formatTimestamp(selectedDefect.updated_at)}</strong>
            </div>
            {selectedDefect.external_links && selectedDefect.external_links.length > 0 && (
              <div style={{ gridColumn: "1 / -1" }}>
                <span className="detail-label">External Tracking Links</span>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
                  {selectedDefect.external_links.map((link) => (
                    <a
                      key={`inspect-link-${link.id}`}
                      href={link.external_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="defect-id-badge"
                      style={{ fontSize: "12px", padding: "4px 8px", textDecoration: "none" }}
                    >
                      🔗 {link.system.toUpperCase()}: <strong>{link.external_key}</strong> (Open in {link.system.toUpperCase()})
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="description" style={{ marginTop: "12px" }}>
            <span className="detail-label">Description &amp; Steps to Reproduce</span>
            <div
              style={{
                marginTop: "4px",
                padding: "14px",
                background: "var(--bg-layer-2, #f8fafc)",
                border: "1px solid var(--border-light, #e2e8f0)",
                borderRadius: "var(--radius-md, 8px)",
                fontSize: "var(--font-body, 14px)",
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
                overflowWrap: "anywhere",
                wordBreak: "break-word",
              }}
            >
              {selectedDefect.description || (
                <span className="muted" style={{ fontStyle: "italic" }}>
                  No detailed description has been provided for this defect.
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Export to External System Modal */}
      {exportModalDefect && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && !exporting) setExportModalDefect(null);
          }}
        >
          <div
            className="panel projects-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-defect-modal-title"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: "520px", width: "95%" }}
          >
            <div className="projects-modal-head">
              <div>
                <h3 id="export-defect-modal-title">Push Defect to External Tracker</h3>
                <span className="muted">DEF-{exportModalDefect.id}: {exportModalDefect.title}</span>
              </div>
              <button
                type="button"
                className="table-action"
                onClick={() => setExportModalDefect(null)}
                disabled={exporting}
                aria-label="Close export modal"
              >
                ✕
              </button>
            </div>

            <form onSubmit={(e) => void handleExportDefect(e)} className="projects-modal-body">
              <label className="capture-label">
                Target System
                <select
                  value={exportSystem}
                  onChange={(e) => setExportSystem(e.target.value as "jira" | "qtest")}
                  disabled={exporting}
                >
                  <option value="jira">Jira Software (Issue / Bug)</option>
                  <option value="qtest">Tricentis qTest (Defect)</option>
                </select>
              </label>

              {exportSystem === "jira" && (
                <>
                  <label className="capture-label">
                    Jira Project Key (Optional, defaults to configured project)
                    <input
                      type="text"
                      value={exportProjectKey}
                      onChange={(e) => setExportProjectKey(e.target.value)}
                      placeholder="e.g. ECOM, QA, PROJ"
                      disabled={exporting}
                    />
                  </label>
                  <label className="capture-label">
                    Issue Type
                    <select
                      value={exportIssueType}
                      onChange={(e) => setExportIssueType(e.target.value)}
                      disabled={exporting}
                    >
                      <option value="Bug">Bug</option>
                      <option value="Defect">Defect</option>
                      <option value="Task">Task</option>
                      <option value="Story">Story</option>
                    </select>
                  </label>
                </>
              )}

              <p className="muted" style={{ fontSize: "12px", marginTop: "4px" }}>
                This will create a new defect in {exportSystem.toUpperCase()} containing the failure summary, description, severity, and link it to this defect record.
              </p>

              <div className="projects-modal-actions" style={{ marginTop: "16px" }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setExportModalDefect(null)}
                  disabled={exporting}
                >
                  Cancel
                </button>
                <button type="submit" className="primary" disabled={exporting}>
                  {exporting ? "Logging to " + exportSystem.toUpperCase() + "..." : "Confirm & Push to " + exportSystem.toUpperCase()}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
