"use client";

import { useEffect, useMemo, useState, useDeferredValue } from "react";
import { useRouter } from "next/navigation";
import type { Application, BuildCaseItem, BuildExecutionDetail, BuildExecutionSummary, CaseExecutionSummary, RunSummary } from "../types";
import { formatDuration } from "../lib/formatDuration";

type RunHistoryColumnId =
  | "runId"
  | "testCase"
  | "browser"
  | "application"
  | "device"
  | "status"
  | "failureType"
  | "checks"
  | "duration"
  | "finished"
  | "label"
  | "tags"
  | "fields"
  | "actions";

type SortColumn = Exclude<RunHistoryColumnId, "actions" | "label" | "tags"> | "label" | "tags";
type SortDirection = "asc" | "desc";

type RunHistoryAnnotation = {
  label: string;
  tags: string[];
  fields: Record<string, string>;
};

type RunHistoryRow = {
  run: RunSummary;
  caseExecution?: CaseExecutionSummary;
  annotation: RunHistoryAnnotation;
};

type RunHistoryWorkspaceProps = {
  appName: string;
  application?: Application | null;
  runs: RunSummary[];
  caseExecutions: CaseExecutionSummary[];
  builds?: BuildExecutionSummary[];
  loading: boolean;
  onRefresh?: () => void;
  onViewRunReport?: (runId: string) => void;
  onViewBuildReport?: (buildId?: string) => void;
  hasBuildReport?: boolean;
  onCancelBuild?: (buildId: string) => Promise<void> | void;
  onCancelRun?: (runId: string) => Promise<void> | void;
  onRebuild?: (buildId: string, caseIds?: number[]) => Promise<void> | void;
  onRunCase?: (caseId: number) => Promise<void> | void;
};

const DEFAULT_COLUMNS: RunHistoryColumnId[] = [
  "runId",
  "testCase",
  "browser",
  "application",
  "device",
  "status",
  "failureType",
  "checks",
  "duration",
  "finished",
  "label",
  "tags",
  "fields",
  "actions",
];

const ALL_COLUMNS: RunHistoryColumnId[] = [
  "runId",
  "testCase",
  "browser",
  "application",
  "device",
  "status",
  "failureType",
  "checks",
  "duration",
  "finished",
  "label",
  "tags",
  "fields",
  "actions",
];

const COLUMN_LABELS: Record<RunHistoryColumnId, string> = {
  runId: "Run ID",
  testCase: "Test case",
  browser: "Browser",
  application: "Application",
  device: "Device",
  status: "Status",
  failureType: "Failure type",
  checks: "Checks",
  duration: "Duration",
  finished: "Finished",
  label: "Label",
  tags: "Tags",
  fields: "Key/value fields",
  actions: "Actions",
};

const EMPTY_ANNOTATION: RunHistoryAnnotation = { label: "", tags: [], fields: {} };
const PAGE_SIZE_OPTIONS = [10, 25, 50];

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const start = Math.min(Math.max(currentPage - 2, 1), totalPages - 4);
  return Array.from({ length: 5 }, (_, index) => start + index);
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function formatDateFilterValue(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString().slice(0, 10);
}

function formatFailureType(value?: string | null) {
  if (!value) return "—";
  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/(^|\s)\w/g, (character) => character.toUpperCase());
}

function statusTone(status: string) {
  const normalized = (status || "").trim().toLowerCase();
  if (normalized === "passed") return "success";
  if (normalized === "running" || normalized === "queued") return "info";
  return "danger";
}

function renderStatusChip(status: string) {
  const label = status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown";
  const tone = statusTone(status);
  return (
    <span className={`status-chip status-${tone}`}>
      <span>{label}</span>
    </span>
  );
}

function annotationStorageKey(appName: string) {
  return `ai-qa-engine:run-history-annotations:${appName}`;
}

function getBrowserDetails(application?: Application | null) {
  if (application?.platform === "web") return { name: "Chromium", detail: "Playwright runner" };
  if (application?.platform === "android" || application?.platform === "ios") return { name: "Appium", detail: "Native runner" };
  return { name: "—", detail: "No application selected" };
}

function getDeviceDetails(application?: Application | null) {
  if (application?.platform === "web") return { name: "Desktop", detail: "Browser runner context" };
  if (application?.platform === "android") return { name: "Android", detail: "Configured device" };
  if (application?.platform === "ios") return { name: "iOS", detail: "Configured device" };
  return { name: "—", detail: "No device context" };
}

function renderDetailCell(name: string, detail: string) {
  return (
    <div className="run-history-detail-cell">
      <strong>{name}</strong>
      <small>{detail}</small>
    </div>
  );
}

export default function RunHistoryWorkspace({
  appName,
  application,
  runs,
  caseExecutions,
  builds = [],
  loading,
  onViewRunReport,
  onViewBuildReport,
  hasBuildReport,
  onCancelBuild,
  onCancelRun,
  onRebuild,
  onRunCase,
}: RunHistoryWorkspaceProps) {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"builds" | "cases">("builds");
  const [expandedBuildIds, setExpandedBuildIds] = useState<Set<string>>(new Set());

  // Builds filters
  const [buildSearch, setBuildSearch] = useState("");
  const deferredBuildSearch = useDeferredValue(buildSearch);
  const [buildStatusFilter, setBuildStatusFilter] = useState("all");
  const [buildTriggerFilter, setBuildTriggerFilter] = useState("all");
  const [buildDateFrom, setBuildDateFrom] = useState("");
  const [buildDateTo, setBuildDateTo] = useState("");
  const [showBuildFilters, setShowBuildFilters] = useState(true);

  // Individual cases filters & state
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [statusFilter, setStatusFilter] = useState("all");
  const [failureFilter, setFailureFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortColumn, setSortColumn] = useState<SortColumn>("finished");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const [visibleColumns, setVisibleColumns] = useState<RunHistoryColumnId[]>(DEFAULT_COLUMNS);
  const [customizeColumns, setCustomizeColumns] = useState(false);
  const [showCaseFilters, setShowCaseFilters] = useState(true);
  const [annotations, setAnnotations] = useState<Record<string, RunHistoryAnnotation>>({});
  const [annotationRunId, setAnnotationRunId] = useState<string | null>(null);
  const [annotationLabel, setAnnotationLabel] = useState("");
  const [annotationTags, setAnnotationTags] = useState("");
  const [annotationFieldKey, setAnnotationFieldKey] = useState("");
  const [annotationFieldValue, setAnnotationFieldValue] = useState("");

  const [cancellingRunIds, setCancellingRunIds] = useState<Set<string>>(new Set());
  const [cancellingBuildIds, setCancellingBuildIds] = useState<Set<string>>(new Set());
  const [rebuildingBuildIds, setRebuildingBuildIds] = useState<Set<string>>(new Set());
  const [stoppingAll, setStoppingAll] = useState(false);

  const activeBuildFilterCount = useMemo(() => {
    let count = 0;
    if (buildSearch.trim()) count++;
    if (buildStatusFilter !== "all") count++;
    if (buildTriggerFilter !== "all") count++;
    if (buildDateFrom || buildDateTo) count++;
    return count;
  }, [buildSearch, buildStatusFilter, buildTriggerFilter, buildDateFrom, buildDateTo]);

  const activeCaseFilterCount = useMemo(() => {
    let count = 0;
    if (search.trim()) count++;
    if (statusFilter !== "all") count++;
    if (failureFilter !== "all") count++;
    if (dateFrom || dateTo) count++;
    return count;
  }, [search, statusFilter, failureFilter, dateFrom, dateTo]);

  const caseExecutionByRunId = useMemo(
    () => new Map(caseExecutions.map((execution) => [execution.run_id, execution])),
    [caseExecutions],
  );

  const failureOptions = useMemo(
    () => Array.from(new Set(runs.map((run) => formatFailureType(caseExecutionByRunId.get(run.run_id)?.failure_type)).filter((value) => value !== "—"))).sort(),
    [caseExecutionByRunId, runs],
  );

  const storageKey = annotationStorageKey(appName || "workspace");
  const browserDetails = getBrowserDetails(application);
  const deviceDetails = getDeviceDetails(application);
  const applicationDetails = {
    name: application?.name ?? appName,
    detail: [application?.type, application?.url || application?.target].filter(Boolean).join(" · ") || "Application details unavailable",
  };

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "{}") as Record<string, RunHistoryAnnotation>;
      setAnnotations(stored && typeof stored === "object" ? stored : {});
    } catch {
      setAnnotations({});
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(annotations));
    } catch {
    }
  }, [annotations, storageKey]);

  useEffect(() => {
    setPage(1);
  }, [dateFrom, dateTo, failureFilter, pageSize, search, sortColumn, sortDirection, statusFilter]);

  // Helper to extract timestamp for newest-first sorting
  const getBuildTimestamp = (b: BuildExecutionSummary) => {
    const d = b.created_at || b.finished_at;
    if (d) {
      const time = new Date(d).getTime();
      if (!Number.isNaN(time) && time > 0) return time;
    }
    const match = b.build_id.match(/build-(\d{4})(\d{2})(\d{2})-?(\d{2})?(\d{2})?(\d{2})?/i);
    if (match) {
      return new Date(Date.UTC(+match[1], +match[2] - 1, +match[3], +(match[4] || 0), +(match[5] || 0), +(match[6] || 0))).getTime();
    }
    return 0;
  };

  // Derive synthesized builds if builds list is empty but runs exist
  const derivedBuilds = useMemo<BuildExecutionSummary[]>(() => {
    if (builds.length > 0) {
      return [...builds].sort((a, b) => getBuildTimestamp(b) - getBuildTimestamp(a));
    }
    if (!runs.length) return [];

    const grouped = new Map<string, { runs: RunSummary[]; executions: CaseExecutionSummary[] }>();
    for (const run of runs) {
      const key = run.batch_id || (run.created_at ? run.created_at.slice(0, 10) : "default-batch");
      const current = grouped.get(key) || { runs: [], executions: [] };
      current.runs.push(run);
      const cExec = caseExecutionByRunId.get(run.run_id);
      if (cExec) current.executions.push(cExec);
      grouped.set(key, current);
    }

    const result: BuildExecutionSummary[] = [];
    for (const [key, group] of grouped.entries()) {
      const total = group.runs.length;
      const passed = group.runs.filter((r) => r.status === "passed").length;
      const failed = group.runs.filter((r) => r.status === "failed").length;
      const error = group.runs.filter((r) => r.status === "error" || r.status === "cancelled").length;
      const passRate = total > 0 ? Math.round((passed / total) * 1000) / 10 : 0;
      const totalDuration = group.executions.reduce((acc, c) => acc + (c.duration_ms || 0), 0);
      const firstRun = group.runs[0];
      const name = firstRun?.build_name || (key.startsWith("build-") ? `Build #${key.slice(-6).toUpperCase()}` : `Execution Batch (${key})`);
      const status = failed > 0 ? "failed" : error > 0 ? "error" : passed === total ? "passed" : "running";

      result.push({
        build_id: key,
        application_id: application?.id || 0,
        name,
        status,
        trigger_source: firstRun?.trigger_source || "manual",
        total_cases: total,
        passed_count: passed,
        failed_count: failed,
        error_count: error,
        pass_rate: passRate,
        duration_ms: totalDuration,
        created_at: firstRun?.created_at,
        finished_at: group.runs[group.runs.length - 1]?.finished_at || firstRun?.finished_at,
      });
    }

    return result.sort((a, b) => getBuildTimestamp(b) - getBuildTimestamp(a));
  }, [application?.id, builds, caseExecutionByRunId, runs]);

  // Filtered Builds
  const filteredBuilds = useMemo(() => {
    const q = deferredBuildSearch.trim().toLowerCase();
    return derivedBuilds.filter((build) => {
      const buildDate = formatDateFilterValue(build.finished_at || build.created_at);
      const matchesSearch = !q || build.name.toLowerCase().includes(q) || build.build_id.toLowerCase().includes(q) || build.trigger_source.toLowerCase().includes(q);
      const matchesStatus = buildStatusFilter === "all" || build.status === buildStatusFilter;
      const matchesTrigger = buildTriggerFilter === "all" || build.trigger_source === buildTriggerFilter;
      const matchesDateFrom = !buildDateFrom || (buildDate && buildDate >= buildDateFrom);
      const matchesDateTo = !buildDateTo || (buildDate && buildDate <= buildDateTo);
      return matchesSearch && matchesStatus && matchesTrigger && matchesDateFrom && matchesDateTo;
    });
  }, [buildDateFrom, buildDateTo, deferredBuildSearch, buildStatusFilter, buildTriggerFilter, derivedBuilds]);

  // Toggle build accordion expansion
  const toggleBuildAccordion = (buildId: string) => {
    setExpandedBuildIds((current) => {
      const next = new Set(current);
      if (next.has(buildId)) {
        next.delete(buildId);
      } else {
        next.add(buildId);
      }
      return next;
    });
  };

  // Get cases for a specific build with sequential TC-aware sorting
  const getCasesForBuild = (build: BuildExecutionSummary): BuildCaseItem[] => {
    const matchingRuns = runs.filter((r) => r.batch_id === build.build_id || (build.build_id.length === 10 && r.created_at?.startsWith(build.build_id)));
    if (!matchingRuns.length) return [];

    const tcNumber = (title: string) => {
      const match = title.match(/^TC\s*0*(\d+)/i);
      return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
    };

    const mappedCases: BuildCaseItem[] = matchingRuns.map((r) => {
      const cExec = caseExecutionByRunId.get(r.run_id);
      return {
        run_id: r.run_id,
        test_case_id: cExec?.test_case_id,
        title: cExec?.title || `Run ${r.run_id.slice(0, 8)}`,
        status: cExec?.status || r.status,
        duration_ms: cExec?.duration_ms,
        check_summary: cExec?.check_summary,
        failure_type: cExec?.failure_type,
        failure_summary: cExec?.failure_summary,
        error: cExec?.failure_summary,
        created_at: r.created_at,
        finished_at: r.finished_at,
      };
    });

    return mappedCases.sort((a, b) => {
      const numA = tcNumber(a.title);
      const numB = tcNumber(b.title);
      if (numA !== numB) return numA - numB;
      if (a.test_case_id && b.test_case_id && a.test_case_id !== b.test_case_id) {
        return a.test_case_id - b.test_case_id;
      }
      return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
    });
  };

  // Build KPI Stats
  const totalBuildsCount = derivedBuilds.length;
  const passedBuildsCount = derivedBuilds.filter((b) => b.status === "passed").length;
  const failedBuildsCount = derivedBuilds.filter((b) => b.status === "failed" || b.status === "error").length;
  const runningBuildsCount = derivedBuilds.filter((b) => b.status === "running" || b.status === "queued").length;
  const runningRunsCount = runs.filter((r) => r.status === "running" || r.status === "queued").length;
  const overallAvgPassRate = totalBuildsCount > 0
    ? Math.round(derivedBuilds.reduce((acc, b) => acc + b.pass_rate, 0) / totalBuildsCount)
    : 0;
  const totalCasesRunAcrossBuilds = derivedBuilds.reduce((acc, b) => acc + b.total_cases, 0);

  const handleStopRun = async (runId: string) => {
    if (!onCancelRun || cancellingRunIds.has(runId)) return;
    setCancellingRunIds((prev) => new Set(prev).add(runId));
    try {
      await onCancelRun(runId);
    } finally {
      setCancellingRunIds((prev) => {
        const next = new Set(prev);
        next.delete(runId);
        return next;
      });
    }
  };

  const handleStopBuild = async (buildId: string) => {
    if (!onCancelBuild || cancellingBuildIds.has(buildId)) return;
    setCancellingBuildIds((prev) => new Set(prev).add(buildId));
    try {
      await onCancelBuild(buildId);
    } finally {
      setCancellingBuildIds((prev) => {
        const next = new Set(prev);
        next.delete(buildId);
        return next;
      });
    }
  };

  const handleRebuild = async (build: BuildExecutionSummary) => {
    if (!onRebuild || rebuildingBuildIds.has(build.build_id)) return;
    const cases = getCasesForBuild(build);
    const caseIds = cases.map((c) => c.test_case_id).filter((id): id is number => typeof id === "number" && id > 0);
    setRebuildingBuildIds((prev) => new Set(prev).add(build.build_id));
    try {
      await onRebuild(build.build_id, caseIds.length > 0 ? caseIds : undefined);
    } finally {
      setRebuildingBuildIds((prev) => {
        const next = new Set(prev);
        next.delete(build.build_id);
        return next;
      });
    }
  };

  const handleStopAllRunning = async () => {
    if (stoppingAll) return;
    setStoppingAll(true);
    try {
      const runningBuilds = derivedBuilds.filter((b) => b.status === "running" || b.status === "queued");
      const runningRuns = runs.filter((r) => r.status === "running" || r.status === "queued");
      if (onCancelBuild && runningBuilds.length > 0) {
        await Promise.all(runningBuilds.map((b) => onCancelBuild(b.build_id)));
      }
      if (onCancelRun && runningRuns.length > 0) {
        await Promise.all(runningRuns.map((r) => onCancelRun(r.run_id)));
      }
    } finally {
      setStoppingAll(false);
    }
  };

  // Individual Cases Rows
  const rows = useMemo<RunHistoryRow[]>(
    () => runs.map((run) => ({
      run,
      caseExecution: caseExecutionByRunId.get(run.run_id),
      annotation: annotations[run.run_id] ?? EMPTY_ANNOTATION,
    })),
    [annotations, caseExecutionByRunId, runs],
  );

  const filteredRows = useMemo(() => {
    const normalizedSearch = deferredSearch.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      const failureType = formatFailureType(row.caseExecution?.failure_type);
      const searchableText = [
        row.run.run_id,
        row.run.build_name,
        row.run.batch_id,
        row.caseExecution?.title,
        row.run.status,
        browserDetails.name,
        browserDetails.detail,
        applicationDetails.name,
        applicationDetails.detail,
        deviceDetails.name,
        deviceDetails.detail,
        failureType,
        row.caseExecution?.check_summary,
        row.annotation.label,
        row.annotation.tags.join(" "),
        Object.entries(row.annotation.fields).map(([key, value]) => `${key} ${value}`).join(" "),
      ].filter(Boolean).join(" ").toLowerCase();
      const runDate = formatDateFilterValue(row.run.finished_at ?? row.run.created_at);
      return (
        (!normalizedSearch || searchableText.includes(normalizedSearch))
        && (statusFilter === "all" || row.run.status === statusFilter)
        && (failureFilter === "all" || failureType === failureFilter)
        && (!dateFrom || (runDate && runDate >= dateFrom))
        && (!dateTo || (runDate && runDate <= dateTo))
      );
    });

    return filtered.sort((left, right) => {
      const getValue = (row: RunHistoryRow): string | number => {
        if (sortColumn === "runId") return row.run.run_id;
        if (sortColumn === "testCase") return row.caseExecution?.title ?? "Ad-hoc execution";
        if (sortColumn === "browser") return browserDetails.name;
        if (sortColumn === "application") return applicationDetails.name;
        if (sortColumn === "device") return deviceDetails.name;
        if (sortColumn === "status") return row.run.status;
        if (sortColumn === "failureType") return formatFailureType(row.caseExecution?.failure_type);
        if (sortColumn === "checks") return row.caseExecution?.check_summary ?? "";
        if (sortColumn === "duration") return row.caseExecution?.duration_ms ?? 0;
        if (sortColumn === "label") return row.annotation.label;
        if (sortColumn === "tags") return row.annotation.tags.join(", ");
        if (sortColumn === "fields") return Object.entries(row.annotation.fields).map(([key, value]) => `${key}:${value}`).join(", ");
        return new Date(row.run.finished_at ?? row.run.created_at ?? 0).getTime() || 0;
      };
      const leftValue = getValue(left);
      const rightValue = getValue(right);
      const comparison = typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue));
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [applicationDetails.name, applicationDetails.detail, browserDetails.detail, browserDetails.name, dateFrom, dateTo, deviceDetails.detail, deviceDetails.name, failureFilter, rows, deferredSearch, sortColumn, sortDirection, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const firstVisibleRow = filteredRows.length ? (currentPage - 1) * pageSize + 1 : 0;
  const lastVisibleRow = Math.min(currentPage * pageSize, filteredRows.length);

  const toggleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortColumn(column);
    setSortDirection(column === "finished" || column === "duration" ? "desc" : "asc");
  };

  const startAnnotation = (row: RunHistoryRow) => {
    setAnnotationRunId(row.run.run_id);
    setAnnotationLabel(row.annotation.label);
    setAnnotationTags(row.annotation.tags.join(", "));
    const firstField = Object.entries(row.annotation.fields)[0];
    setAnnotationFieldKey(firstField?.[0] ?? "");
    setAnnotationFieldValue(firstField?.[1] ?? "");
  };

  const cancelAnnotation = () => {
    setAnnotationRunId(null);
    setAnnotationLabel("");
    setAnnotationTags("");
    setAnnotationFieldKey("");
    setAnnotationFieldValue("");
  };

  const saveAnnotation = () => {
    if (!annotationRunId) return;
    const tags = Array.from(new Set(annotationTags.split(",").map((tag) => tag.trim()).filter(Boolean))).slice(0, 12);
    const currentFields = annotations[annotationRunId]?.fields ?? {};
    const fields = { ...currentFields };
    if (annotationFieldKey.trim()) fields[annotationFieldKey.trim().slice(0, 64)] = annotationFieldValue.trim().slice(0, 240);
    setAnnotations((current) => ({
      ...current,
      [annotationRunId]: {
        label: annotationLabel.trim().slice(0, 120),
        tags,
        fields,
      },
    }));
    cancelAnnotation();
  };

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setFailureFilter("all");
    setDateFrom("");
    setDateTo("");
  };

  const clearBuildFilters = () => {
    setBuildSearch("");
    setBuildStatusFilter("all");
    setBuildTriggerFilter("all");
    setBuildDateFrom("");
    setBuildDateTo("");
  };

  const moveColumn = (column: RunHistoryColumnId, offset: number) => {
    setVisibleColumns((current) => {
      const index = current.indexOf(column);
      const nextIndex = index + offset;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const renderHeader = (column: RunHistoryColumnId) => {
    if (column === "actions") return <th key={column}>Actions</th>;
    return (
      <th key={column} aria-sort={sortColumn === column ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
        <button type="button" className="run-history-sort-button" onClick={() => toggleSort(column)}>
          {COLUMN_LABELS[column]}
          <span aria-hidden="true">{sortColumn === column ? (sortDirection === "asc" ? " ^" : " v") : ""}</span>
        </button>
      </th>
    );
  };

  const renderCell = (column: RunHistoryColumnId, row: RunHistoryRow) => {
    const { run, caseExecution, annotation } = row;
    if (column === "runId") {
      return (
        <td key={column} className="col-id" style={{ whiteSpace: "nowrap" }}>
          <a
            className="run-history-table-link"
            href={`/test-execution/${run.run_id}`}
            title={`Open run ${run.run_id}`}
            onClick={(e) => {
              e.preventDefault();
              router.push(`/test-execution/${run.run_id}`);
            }}
          >
            <code style={{ whiteSpace: "nowrap" }}>{run.run_id.slice(0, 8)}</code>
          </a>
        </td>
      );
    }
    if (column === "testCase") {
      return (
        <td key={column}>
          <a
            className="run-history-table-link"
            href={`/test-execution/${run.run_id}`}
            onClick={(e) => {
              e.preventDefault();
              router.push(`/test-execution/${run.run_id}`);
            }}
          >
            {caseExecution?.title ?? "Ad-hoc execution"}
          </a>
        </td>
      );
    }
    if (column === "browser") return <td key={column} style={{ whiteSpace: "nowrap" }}>{renderDetailCell(browserDetails.name, browserDetails.detail)}</td>;
    if (column === "application") return <td key={column}>{renderDetailCell(applicationDetails.name, applicationDetails.detail)}</td>;
    if (column === "device") return <td key={column} style={{ whiteSpace: "nowrap" }}>{renderDetailCell(deviceDetails.name, deviceDetails.detail)}</td>;
    if (column === "status") {
      return (
        <td key={column} style={{ whiteSpace: "nowrap" }}>
          <a
            className="run-history-status-link"
            href={`/test-execution/${run.run_id}`}
            aria-label={`Open ${run.status} run ${run.run_id}`}
            onClick={(e) => {
              e.preventDefault();
              router.push(`/test-execution/${run.run_id}`);
            }}
          >
            {renderStatusChip(run.status)}
          </a>
        </td>
      );
    }
    if (column === "failureType") return <td key={column} style={{ whiteSpace: "nowrap" }}>{formatFailureType(caseExecution?.failure_type)}</td>;
    if (column === "checks") return <td key={column}>{caseExecution?.check_summary ?? "See details"}</td>;
    if (column === "duration") return <td key={column} style={{ whiteSpace: "nowrap" }}>{caseExecution?.duration_ms ? formatDuration(caseExecution.duration_ms) : "See details"}</td>;
    if (column === "finished") return <td key={column} style={{ whiteSpace: "nowrap" }}>{formatTimestamp(run.finished_at)}</td>;
    if (column === "label") return <td key={column}>{annotation.label || "—"}</td>;
    if (column === "tags") {
      return (
        <td key={column}>
          {annotation.tags.length ? (
            <div className="run-history-tag-list">
              {annotation.tags.map((tag, tagIdx) => (
                <span key={`tag-${tag}-${tagIdx}`}>{tag}</span>
              ))}
            </div>
          ) : (
            "—"
          )}
        </td>
      );
    }
    if (column === "fields") {
      return (
        <td key={column}>
          {Object.keys(annotation.fields).length ? (
            <div className="run-history-custom-fields">
              {Object.entries(annotation.fields).map(([key, value], fldIdx) => (
                <span key={`field-${key}-${fldIdx}`}>
                  <b>{key}</b>: {value}
                </span>
              ))}
            </div>
          ) : (
            "—"
          )}
        </td>
      );
    }
    return (
      <td key={column}>
        <div className="run-history-row-actions">
          {(run.status === "running" || run.status === "queued") && onCancelRun ? (
            <button
              type="button"
              className="secondary btn-danger btn-sm"
              onClick={() => handleStopRun(run.run_id)}
              disabled={cancellingRunIds.has(run.run_id)}
              title={`Stop/cancel running test ${run.run_id.slice(0, 8)}`}
              style={{ fontWeight: 700 }}
            >
              {cancellingRunIds.has(run.run_id) ? "Stopping..." : "⏹ Stop Run"}
            </button>
          ) : null}
          <button
            type="button"
            className="primary btn-sm"
            onClick={() => (onViewRunReport ? onViewRunReport(run.run_id) : router.push(`/test-execution/${run.run_id}`))}
            title={`View execution report for run ${run.run_id.slice(0, 8)}`}
          >
            View Report
          </button>
          <button type="button" className="secondary btn-sm" onClick={() => startAnnotation(row)}>
            Label / tags
          </button>
        </div>
      </td>
    );
  };

  return (
    <section className="run-history-workspace" aria-label="Run history workspace">
      {/* Active In-Flight Executions Banner */}
      {(runningRunsCount > 0 || runningBuildsCount > 0) && (
        <div
          className="panel run-history-active-banner"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "#fef2f2",
            border: "1px solid #f87171",
            borderRadius: "var(--radius-md, 8px)",
            padding: "12px 18px",
            marginBottom: "16px",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontSize: "1.4rem" }}>🛑</span>
            <div>
              <strong style={{ color: "#b91c1c", fontSize: "14px" }}>
                Active Test Executions In-Flight
              </strong>
              <p className="muted" style={{ margin: "2px 0 0", fontSize: "12px", color: "#7f1d1d" }}>
                {runningRunsCount} test run{runningRunsCount === 1 ? "" : "s"} and {runningBuildsCount} build batch{runningBuildsCount === 1 ? "" : "es"} currently executing or queued.
              </p>
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button
              type="button"
              className="primary btn-sm"
              onClick={handleStopAllRunning}
              disabled={stoppingAll}
              style={{
                background: "#dc2626",
                borderColor: "#b91c1c",
                color: "#ffffff",
                fontWeight: 700,
                padding: "6px 14px",
                fontSize: "12px",
              }}
              title="Immediately stop and cancel all active test executions"
            >
              🛑 {stoppingAll ? "Stopping All..." : `Stop All Running (${runningRunsCount})`}
            </button>
          </div>
        </div>
      )}

      {/* Top View Selector Segmented Control */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div className="run-history-view-switcher" role="tablist" aria-label="Run History View Mode">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === "builds"}
            className={`run-history-view-button ${viewMode === "builds" ? "active" : ""}`}
            onClick={() => setViewMode("builds")}
          >
            📑 Build & Batch Executions ({derivedBuilds.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === "cases"}
            className={`run-history-view-button ${viewMode === "cases" ? "active" : ""}`}
            onClick={() => setViewMode("cases")}
          >
            📋 Individual Case Runs ({runs.length})
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {hasBuildReport && onViewBuildReport ? (
            <button
              type="button"
              className="primary btn-sm"
              onClick={() => onViewBuildReport()}
              title="Open latest build execution report"
            >
              📊 Latest Build Report
            </button>
          ) : null}
        </div>
      </div>

      {/* ======================= VIEW MODE: BUILDS ======================= */}
      {viewMode === "builds" && (
        <>
          {/* Build KPI Summary Cards */}
          <div className="build-kpi-summary-cards">
            <div className="build-kpi-card">
              <small>Total Build Runs</small>
              <strong>{totalBuildsCount}</strong>
            </div>
            <div className="build-kpi-card">
              <small>Avg Pass Rate</small>
              <strong style={{ color: overallAvgPassRate >= 80 ? "var(--success, #10b981)" : overallAvgPassRate >= 50 ? "#f59e0b" : "var(--danger, #ef4444)" }}>
                {overallAvgPassRate}%
              </strong>
            </div>
            <div className="build-kpi-card">
              <small>Total Case Runs</small>
              <strong>{totalCasesRunAcrossBuilds}</strong>
            </div>
            <div className="build-kpi-card">
              <small>Passed / Failed Builds</small>
              <strong style={{ fontSize: "1.1rem" }}>
                <span style={{ color: "var(--success, #10b981)" }}>{passedBuildsCount} passed</span>
                {" · "}
                <span style={{ color: failedBuildsCount > 0 ? "var(--danger, #ef4444)" : "var(--text-secondary)" }}>{failedBuildsCount} failed</span>
              </strong>
            </div>
          </div>

          {/* Builds Filter Toolbar */}
          <div className="panel run-history-toolbar">
            <div className="run-history-toolbar-heading">
              <div>
                <h3>Filter Build Runs</h3>
              </div>
              <div className="run-history-toolbar-actions">
                <button
                  type="button"
                  className="secondary btn-sm filter-toggle-btn"
                  onClick={() => setShowBuildFilters((prev) => !prev)}
                  title={showBuildFilters ? "Hide build filter controls" : "Show build filter controls"}
                >
                  {showBuildFilters ? "👁 Hide Filters" : "🔍 Show Filters"}
                  {activeBuildFilterCount > 0 && !showBuildFilters && (
                    <span className="filter-badge-counter">{activeBuildFilterCount}</span>
                  )}
                </button>
              </div>
            </div>

            {/* Quick Presets for Builds */}
            <div className="filter-presets-bar">
              <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Quick Presets:</span>
              <button
                type="button"
                className={`filter-preset-chip ${buildStatusFilter === "all" ? "active" : ""}`}
                onClick={() => setBuildStatusFilter("all")}
              >
                All Builds ({derivedBuilds.length})
              </button>
              {runningBuildsCount > 0 && (
                <button
                  type="button"
                  className={`filter-preset-chip ${buildStatusFilter === "running" ? "active" : ""}`}
                  onClick={() => setBuildStatusFilter("running")}
                  style={{ color: "#b91c1c", fontWeight: 700 }}
                >
                  ⚡ Running Only ({runningBuildsCount})
                </button>
              )}
              <button
                type="button"
                className={`filter-preset-chip ${buildStatusFilter === "passed" ? "active" : ""}`}
                onClick={() => setBuildStatusFilter("passed")}
              >
                Passed Only ({passedBuildsCount})
              </button>
              <button
                type="button"
                className={`filter-preset-chip ${buildStatusFilter === "failed" ? "active" : ""}`}
                onClick={() => setBuildStatusFilter("failed")}
              >
                Failed Only ({failedBuildsCount})
              </button>
            </div>

            {showBuildFilters && (
              <div className="run-history-filter-grid" style={{ marginTop: "12px" }}>
                <label className="capture-label">
                  Search builds
                  <input
                    type="search"
                    value={buildSearch}
                    onChange={(e) => setBuildSearch(e.target.value)}
                    placeholder="Build ID, name, trigger"
                  />
                </label>
                <label className="capture-label">
                  Status
                  <select value={buildStatusFilter} onChange={(e) => setBuildStatusFilter(e.target.value)}>
                    <option value="all">All statuses</option>
                    <option value="passed">Passed</option>
                    <option value="failed">Failed</option>
                    <option value="error">Error</option>
                    <option value="running">Running</option>
                    <option value="queued">Queued</option>
                  </select>
                </label>
                <label className="capture-label">
                  Trigger
                  <select value={buildTriggerFilter} onChange={(e) => setBuildTriggerFilter(e.target.value)}>
                    <option value="all">All triggers</option>
                    <option value="manual">Manual</option>
                    <option value="suite">Suite</option>
                    <option value="plan">Plan</option>
                    <option value="ci">CI / Pipeline</option>
                    <option value="ingest">Ingest & Run</option>
                  </select>
                </label>
                <label className="capture-label">
                  Executed from
                  <input type="date" value={buildDateFrom} onChange={(e) => setBuildDateFrom(e.target.value)} />
                </label>
                <label className="capture-label">
                  Executed to
                  <input type="date" value={buildDateTo} onChange={(e) => setBuildDateTo(e.target.value)} />
                </label>
              </div>
            )}

            {/* Active Build Filter Tags */}
            {activeBuildFilterCount > 0 && (
              <div className="active-filter-tags">
                <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeBuildFilterCount}):</span>
                {buildSearch && (
                  <span className="active-filter-tag">
                    "{buildSearch}"
                    <button type="button" onClick={() => setBuildSearch("")} aria-label="Clear build search">✕</button>
                  </span>
                )}
                {buildStatusFilter !== "all" && (
                  <span className="active-filter-tag">
                    Status: {buildStatusFilter}
                    <button type="button" onClick={() => setBuildStatusFilter("all")} aria-label="Clear build status">✕</button>
                  </span>
                )}
                {buildTriggerFilter !== "all" && (
                  <span className="active-filter-tag">
                    Trigger: {buildTriggerFilter}
                    <button type="button" onClick={() => setBuildTriggerFilter("all")} aria-label="Clear trigger">✕</button>
                  </span>
                )}
                <button type="button" className="table-action" onClick={clearBuildFilters} style={{ fontSize: "11px" }}>
                  Clear all
                </button>
              </div>
            )}

            <div className="run-history-filter-summary">
              <span>{filteredBuilds.length} matching build run{filteredBuilds.length === 1 ? "" : "s"}</span>
              {activeBuildFilterCount > 0 ? (
                <button type="button" className="table-action" onClick={clearBuildFilters}>
                  Clear filters
                </button>
              ) : null}
            </div>
          </div>

          {/* Builds Table with Expandable Accordions */}
          <div className="panel table-panel run-history-table-panel workspace-table-surface">
            <div className="table-title">
              <div>
                <h3>Build & Batch Execution Records</h3>
              </div>
              <span className="muted">
                {filteredBuilds.length} build execution{filteredBuilds.length === 1 ? "" : "s"} for {appName}
              </span>
            </div>
            <div className="table-scroll table-scroll-contained">
              <table className="run-history-table" style={{ minWidth: "1100px" }}>
                <thead>
                  <tr>
                    <th style={{ width: "44px" }}></th>
                    <th>Build ID / Name</th>
                    <th>Status</th>
                    <th>Pass Rate</th>
                    <th>Cases Breakdown</th>
                    <th>Total Duration</th>
                    <th>Trigger</th>
                    <th>Execution Time</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBuilds.length ? (
                    filteredBuilds.flatMap((build) => {
                      const isExpanded = expandedBuildIds.has(build.build_id);
                      const buildCases = getCasesForBuild(build);
                      const passedPercent = build.total_cases > 0 ? (build.passed_count / build.total_cases) * 100 : 0;
                      const failedPercent = build.total_cases > 0 ? (build.failed_count / build.total_cases) * 100 : 0;
                      const errorPercent = build.total_cases > 0 ? (build.error_count / build.total_cases) * 100 : 0;

                      const mainRow = (
                        <tr key={build.build_id} style={{ borderBottom: isExpanded ? "none" : undefined }}>
                          {/* Chevron / Toggle */}
                          <td>
                            <button
                              type="button"
                              className={`build-accordion-btn ${isExpanded ? "expanded" : ""}`}
                              onClick={() => toggleBuildAccordion(build.build_id)}
                              aria-label={isExpanded ? "Collapse build details" : "Expand build details"}
                              title={isExpanded ? "Collapse cases" : "Expand case-by-case breakdown"}
                            >
                              ▶
                            </button>
                          </td>

                          {/* Build Name & ID */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                              <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>{build.name}</strong>
                              <small className="muted" style={{ fontFamily: "monospace", whiteSpace: "nowrap" }}>
                                {build.build_id.slice(0, 16)}
                              </small>
                            </div>
                          </td>

                          {/* Status */}
                          <td style={{ whiteSpace: "nowrap" }}>{renderStatusChip(build.status)}</td>

                          {/* Pass Rate Progress Bar */}
                          <td style={{ minWidth: "150px" }}>
                            <div className="build-pass-rate-wrapper">
                              <div className="build-pass-rate-header">
                                <span style={{ fontWeight: 700 }}>{build.pass_rate}%</span>
                                <small className="muted" style={{ whiteSpace: "nowrap" }}>{build.passed_count}/{build.total_cases}</small>
                              </div>
                              <div className="build-pass-rate-bar">
                                <div className="build-pass-rate-fill-passed" style={{ width: `${passedPercent}%` }} />
                                <div className="build-pass-rate-fill-failed" style={{ width: `${failedPercent}%` }} />
                                <div className="build-pass-rate-fill-error" style={{ width: `${errorPercent}%` }} />
                              </div>
                            </div>
                          </td>

                          {/* Cases Breakdown */}
                          <td>
                            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", alignItems: "center", whiteSpace: "nowrap" }}>
                              <span className="build-badge build-badge-passed" style={{ whiteSpace: "nowrap" }}>✓ {build.passed_count} pass</span>
                              {build.failed_count > 0 ? (
                                <span className="build-badge build-badge-failed" style={{ whiteSpace: "nowrap" }}>✗ {build.failed_count} fail</span>
                              ) : null}
                              {build.error_count > 0 ? (
                                <span className="build-badge build-badge-error" style={{ whiteSpace: "nowrap" }}>⚠ {build.error_count} error</span>
                              ) : null}
                              <small className="muted" style={{ whiteSpace: "nowrap" }}>({build.total_cases} total)</small>
                            </div>
                          </td>

                          {/* Total Duration */}
                          <td style={{ whiteSpace: "nowrap" }}>{build.duration_ms > 0 ? formatDuration(build.duration_ms) : "—"}</td>

                          {/* Trigger */}
                          <td style={{ whiteSpace: "nowrap" }}>
                            <span style={{ textTransform: "capitalize", fontSize: "var(--font-caption)", whiteSpace: "nowrap" }}>
                              {build.trigger_source || "manual"}
                            </span>
                          </td>

                          {/* Execution Time */}
                          <td style={{ whiteSpace: "nowrap" }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                              <span style={{ whiteSpace: "nowrap" }}>{formatTimestamp(build.finished_at || build.created_at)}</span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td>
                            <div className="run-history-row-actions">
                              {(build.status === "running" || build.status === "queued") && onCancelBuild ? (
                                <button
                                  type="button"
                                  className="secondary btn-danger btn-sm"
                                  onClick={() => handleStopBuild(build.build_id)}
                                  disabled={cancellingBuildIds.has(build.build_id)}
                                  title="Stop and cancel this running build"
                                  style={{ fontWeight: 700 }}
                                >
                                  {cancellingBuildIds.has(build.build_id) ? "Stopping..." : "🛑 Stop Build"}
                                </button>
                              ) : onRebuild ? (
                                <button
                                  type="button"
                                  className="secondary btn-sm"
                                  onClick={() => handleRebuild(build)}
                                  disabled={rebuildingBuildIds.has(build.build_id)}
                                  title="Rebuild / re-run all test cases in this build"
                                  style={{ fontWeight: 700, color: "var(--brand-primary, #b5121b)" }}
                                >
                                  {rebuildingBuildIds.has(build.build_id) ? "Rebuilding..." : "🔄 Rebuild"}
                                </button>
                              ) : null}
                              <button
                                type="button"
                                className="primary btn-sm"
                                onClick={() => (onViewBuildReport ? onViewBuildReport(build.build_id) : toggleBuildAccordion(build.build_id))}
                                title="Open full build execution report"
                              >
                                📊 Inspect Report
                              </button>
                              <button
                                type="button"
                                className="secondary btn-sm"
                                onClick={() => toggleBuildAccordion(build.build_id)}
                              >
                                {isExpanded ? "Hide Cases" : `View Cases (${build.total_cases})`}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );

                      if (!isExpanded) return [mainRow];

                      const failedCaseIds = buildCases
                        .filter((c) => c.status === "failed" || c.status === "error")
                        .map((c) => c.test_case_id)
                        .filter((id): id is number => typeof id === "number" && id > 0);

                      const expandedRow = (
                        <tr key={`${build.build_id}-accordion`} className="build-accordion-row">
                          <td colSpan={9} style={{ padding: "0 12px 16px 12px", background: "transparent" }}>
                            <div className="build-subtable-container">
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", flexWrap: "wrap", gap: "8px" }}>
                                <strong style={{ fontSize: "var(--font-small)", color: "var(--text-primary)" }}>
                                  Test Cases Executed in {build.name} ({buildCases.length})
                                </strong>
                                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                                  <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
                                    Pass Rate: {build.pass_rate}% · Total Duration: {formatDuration(build.duration_ms)}
                                  </span>
                                  {(build.status === "running" || build.status === "queued") && onCancelBuild ? (
                                    <button
                                      type="button"
                                      className="secondary btn-danger btn-sm"
                                      onClick={() => handleStopBuild(build.build_id)}
                                      disabled={cancellingBuildIds.has(build.build_id)}
                                      style={{ padding: "3px 10px", fontSize: "11px", fontWeight: 700 }}
                                    >
                                      {cancellingBuildIds.has(build.build_id) ? "Stopping..." : "🛑 Stop Build"}
                                    </button>
                                  ) : onRebuild ? (
                                    <>
                                      {failedCaseIds.length > 0 && (
                                        <button
                                          type="button"
                                          className="secondary btn-sm"
                                          onClick={() => onRebuild(build.build_id, failedCaseIds)}
                                          disabled={rebuildingBuildIds.has(build.build_id)}
                                          style={{ padding: "3px 10px", fontSize: "11px", fontWeight: 700, color: "var(--brand-primary, #b5121b)" }}
                                          title="Re-run failed test cases in this build"
                                        >
                                          ↻ Re-run {failedCaseIds.length} Failed
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        className="primary btn-sm"
                                        onClick={() => handleRebuild(build)}
                                        disabled={rebuildingBuildIds.has(build.build_id)}
                                        style={{ padding: "3px 12px", fontSize: "11px", fontWeight: 700 }}
                                        title="Rebuild and execute all test cases in this build"
                                      >
                                        {rebuildingBuildIds.has(build.build_id) ? "Rebuilding..." : "🔄 Rebuild All Cases"}
                                      </button>
                                    </>
                                  ) : null}
                                </div>
                              </div>

                              {buildCases.length ? (
                                <table className="build-subtable">
                                  <thead>
                                    <tr>
                                      <th>Test Case Title</th>
                                      <th>Status</th>
                                      <th>Checks</th>
                                      <th>Duration</th>
                                      <th>Failure / Diagnostic</th>
                                      <th>Actions</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {buildCases.map((c, cIdx) => (
                                      <tr key={c.run_id || cIdx}>
                                        <td>
                                          <strong>{c.title}</strong>
                                          <br />
                                          <small className="muted" style={{ fontFamily: "monospace" }}>
                                            {c.run_id?.slice(0, 8)}
                                          </small>
                                        </td>
                                        <td>{renderStatusChip(c.status)}</td>
                                        <td>{c.check_summary || "—"}</td>
                                        <td>{c.duration_ms ? formatDuration(c.duration_ms) : "—"}</td>
                                        <td>
                                          {c.failure_summary || c.error || c.failure_type ? (
                                            <span style={{ color: "var(--danger, #ef4444)", fontSize: "var(--font-caption)" }}>
                                              {c.failure_type ? `[${formatFailureType(c.failure_type)}] ` : ""}
                                              {c.failure_summary || c.error}
                                            </span>
                                          ) : (
                                            <span className="muted">—</span>
                                          )}
                                        </td>
                                        <td>
                                          <div className="run-history-row-actions">
                                            {(c.status === "running" || c.status === "queued") && c.run_id && onCancelRun ? (
                                              <button
                                                type="button"
                                                className="secondary btn-danger btn-sm"
                                                onClick={() => handleStopRun(c.run_id!)}
                                                disabled={cancellingRunIds.has(c.run_id!)}
                                                title={`Stop/cancel running case ${c.run_id.slice(0, 8)}`}
                                                style={{ fontWeight: 700 }}
                                              >
                                                {cancellingRunIds.has(c.run_id!) ? "Stopping..." : "⏹ Stop"}
                                              </button>
                                            ) : null}
                                            {c.test_case_id && onRunCase && (
                                              <button
                                                type="button"
                                                className="secondary btn-sm"
                                                onClick={() => onRunCase(c.test_case_id!)}
                                                title={`Re-run test case #${c.test_case_id}`}
                                                style={{ fontWeight: 600 }}
                                              >
                                                ▶ Re-run
                                              </button>
                                            )}
                                            {c.run_id ? (
                                              <button
                                                type="button"
                                                className="secondary btn-sm"
                                                onClick={() =>
                                                  onViewRunReport
                                                    ? onViewRunReport(c.run_id)
                                                    : router.push(`/test-execution/${c.run_id}`)
                                                }
                                                title={`View report for case run ${c.run_id.slice(0, 8)}`}
                                              >
                                                View Run Report
                                              </button>
                                            ) : null}
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <p className="muted" style={{ margin: "8px 0" }}>
                                  No individual test case results recorded for this build.
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      );

                      return [mainRow, expandedRow];
                    })
                  ) : (
                    <tr>
                      <td colSpan={9} className="muted">
                        No build runs match the current filters. Execute test cases or batches to record builds.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ======================= VIEW MODE: INDIVIDUAL CASES ======================= */}
      {viewMode === "cases" && (
        <>
          <div className="panel run-history-toolbar">
            <div className="run-history-toolbar-heading">
              <div>
                <h3>Filter &amp; Search Individual Case Runs</h3>
              </div>
              <div className="run-history-toolbar-actions">
                <button
                  type="button"
                  className="secondary btn-sm filter-toggle-btn"
                  onClick={() => setShowCaseFilters((prev) => !prev)}
                  title={showCaseFilters ? "Hide filter controls" : "Show filter controls"}
                >
                  {showCaseFilters ? "👁 Hide Filters" : "🔍 Show Filters"}
                  {activeCaseFilterCount > 0 && !showCaseFilters && (
                    <span className="filter-badge-counter">{activeCaseFilterCount}</span>
                  )}
                </button>
                <button
                  type="button"
                  className="secondary btn-sm"
                  onClick={() => setCustomizeColumns((current) => !current)}
                >
                  {customizeColumns ? "Close columns" : "Customize columns"}
                </button>
              </div>
            </div>

            {/* Quick Presets for Cases */}
            <div className="filter-presets-bar">
              <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Quick Presets:</span>
              <button
                type="button"
                className={`filter-preset-chip ${statusFilter === "all" ? "active" : ""}`}
                onClick={() => { setStatusFilter("all"); setFailureFilter("all"); }}
              >
                All Runs ({runs.length})
              </button>
              {runningRunsCount > 0 && (
                <button
                  type="button"
                  className={`filter-preset-chip ${statusFilter === "running" ? "active" : ""}`}
                  onClick={() => setStatusFilter("running")}
                  style={{ color: "#b91c1c", fontWeight: 700 }}
                >
                  ⚡ Running ({runningRunsCount})
                </button>
              )}
              <button
                type="button"
                className={`filter-preset-chip ${statusFilter === "passed" ? "active" : ""}`}
                onClick={() => setStatusFilter("passed")}
              >
                Passed
              </button>
              <button
                type="button"
                className={`filter-preset-chip ${statusFilter === "failed" ? "active" : ""}`}
                onClick={() => setStatusFilter("failed")}
              >
                Failed / Errors
              </button>
              {runningRunsCount === 0 && (
                <button
                  type="button"
                  className={`filter-preset-chip ${statusFilter === "running" ? "active" : ""}`}
                  onClick={() => setStatusFilter("running")}
                >
                  Running / In-Flight
                </button>
              )}
            </div>

            {showCaseFilters && (
              <div className="run-history-filter-grid" style={{ marginTop: "12px" }}>
                <label className="capture-label">
                  Search runs
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Run ID, case, status, label, tag"
                  />
                </label>
                <label className="capture-label">
                  Status
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                    <option value="all">All statuses</option>
                    <option value="queued">Queued</option>
                    <option value="running">Running</option>
                    <option value="passed">Passed</option>
                    <option value="failed">Failed</option>
                    <option value="error">Error</option>
                  </select>
                </label>
                <label className="capture-label">
                  Failure type
                  <select value={failureFilter} onChange={(event) => setFailureFilter(event.target.value)}>
                    <option value="all">All failure types</option>
                    {failureOptions.map((failure) => (
                      <option key={failure} value={failure}>
                        {failure}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="capture-label">
                  Finished from
                  <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
                </label>
                <label className="capture-label">
                  Finished to
                  <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
                </label>
                <label className="capture-label">
                  Rows per page
                  <select value={String(pageSize)} onChange={(event) => setPageSize(Number(event.target.value))}>
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {/* Active Case Filter Tags */}
            {activeCaseFilterCount > 0 && (
              <div className="active-filter-tags">
                <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeCaseFilterCount}):</span>
                {search && (
                  <span className="active-filter-tag">
                    "{search}"
                    <button type="button" onClick={() => setSearch("")} aria-label="Clear search">✕</button>
                  </span>
                )}
                {statusFilter !== "all" && (
                  <span className="active-filter-tag">
                    Status: {statusFilter}
                    <button type="button" onClick={() => setStatusFilter("all")} aria-label="Clear status">✕</button>
                  </span>
                )}
                {failureFilter !== "all" && (
                  <span className="active-filter-tag">
                    Failure: {failureFilter}
                    <button type="button" onClick={() => setFailureFilter("all")} aria-label="Clear failure filter">✕</button>
                  </span>
                )}
                <button type="button" className="table-action" onClick={clearFilters} style={{ fontSize: "11px" }}>
                  Clear all
                </button>
              </div>
            )}

            <div className="run-history-filter-summary">
              <span>{filteredRows.length} matching run{filteredRows.length === 1 ? "" : "s"}</span>
              {activeCaseFilterCount > 0 ? (
                <button type="button" className="table-action" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : null}
            </div>
          </div>

          {customizeColumns && (
            <div className="panel run-history-column-editor">
              <div>
                <h3>Choose headers and arrange their order</h3>
              </div>
              <div className="run-history-column-list">
                {ALL_COLUMNS.map((column) => {
                  const visibleIndex = visibleColumns.indexOf(column);
                  return (
                    <div className="run-history-column-item" key={column}>
                      <label>
                        <input
                          type="checkbox"
                          checked={visibleIndex >= 0}
                          disabled={column === "actions"}
                          onChange={(event) =>
                            setVisibleColumns((current) =>
                              event.target.checked
                                ? [...current.filter((item) => item !== column), column]
                                : current.filter((item) => item !== column),
                            )
                          }
                        />
                        {COLUMN_LABELS[column]}
                      </label>
                      <div>
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => moveColumn(column, -1)}
                          disabled={visibleIndex <= 0}
                        >
                          Up
                        </button>
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => moveColumn(column, 1)}
                          disabled={visibleIndex < 0 || visibleIndex === visibleColumns.length - 1}
                        >
                          Down
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => setVisibleColumns(DEFAULT_COLUMNS)}
              >
                Reset columns
              </button>
            </div>
          )}

          {annotationRunId && (
            <div className="panel run-history-annotation-editor" role="dialog" aria-label="Add run metadata">
              <div>
                <h3>Add labels, tags, or a key/value field</h3>
              </div>
              <div className="run-history-annotation-grid">
                <label className="capture-label">
                  Label
                  <input
                    value={annotationLabel}
                    onChange={(event) => setAnnotationLabel(event.target.value)}
                    placeholder="Regression / Release candidate"
                  />
                </label>
                <label className="capture-label">
                  Tags
                  <input
                    value={annotationTags}
                    onChange={(event) => setAnnotationTags(event.target.value)}
                    placeholder="smoke, nightly, checkout"
                  />
                </label>
                <label className="capture-label">
                  Key
                  <input
                    value={annotationFieldKey}
                    onChange={(event) => setAnnotationFieldKey(event.target.value)}
                    placeholder="environment"
                  />
                </label>
                <label className="capture-label">
                  Value
                  <input
                    value={annotationFieldValue}
                    onChange={(event) => setAnnotationFieldValue(event.target.value)}
                    placeholder="staging"
                  />
                </label>
              </div>
              <p className="muted">Metadata is kept in this browser for the selected application and is included in search.</p>
              <div className="run-history-annotation-actions">
                <button type="button" className="secondary btn-sm" onClick={cancelAnnotation}>
                  Cancel
                </button>
                <button type="button" className="primary btn-sm" onClick={saveAnnotation}>
                  Save metadata
                </button>
              </div>
            </div>
          )}

          <div className="panel table-panel run-history-table-panel workspace-table-surface">
            <div className="table-title">
              <div>
                <h3>Individual Execution Records</h3>
              </div>
              <span className="muted">
                {firstVisibleRow}-{lastVisibleRow} of {filteredRows.length} shown for {appName}
              </span>
            </div>
            <div className="table-scroll table-scroll-contained">
              <table className="run-history-table">
                <thead>
                  <tr>{visibleColumns.map(renderHeader)}</tr>
                </thead>
                <tbody>
                  {pagedRows.length ? (
                    pagedRows.map((row) => (
                      <tr key={row.run.run_id}>{visibleColumns.map((column) => renderCell(column, row))}</tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={visibleColumns.length} className="muted">
                        No runs match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="run-history-pagination">
              <span>
                Page {currentPage} of {totalPages}
              </span>
              <div>
                <button
                  type="button"
                  className="secondary btn-sm"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </button>
                {getPageNumbers(currentPage, totalPages).map((pageNumber) => {
                  return (
                    <button
                      type="button"
                      className={`run-history-page-button ${pageNumber === currentPage ? "active" : ""}`}
                      key={pageNumber}
                      onClick={() => setPage(pageNumber)}
                    >
                      {pageNumber}
                    </button>
                  );
                })}
                <button
                  type="button"
                  className="secondary btn-sm"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
