import type {
  Application,
  Defect,
  FailureType,
  Platform,
  ProjectHealthBucket,
  ProjectLifecycle,
  RunSummary,
  TestCase,
} from "../types";

export type DistributionItem = {
  label: string;
  value: number;
  tone: "info" | "success" | "warning" | "danger" | "neutral";
};

export function buildCategoryCoverage(cases: TestCase[]) {
  const counts = new Map<string, number>();
  for (const caseItem of cases) {
    const category = caseItem.category?.trim() || "Uncategorized";
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  const categoryCounts = Array.from(counts, ([categoryName, caseCount]) => ({ categoryName, caseCount }))
    .sort((left, right) => right.caseCount - left.caseCount || left.categoryName.localeCompare(right.categoryName));
  const maxCount = Math.max(...categoryCounts.map((entry) => entry.caseCount), 1);
  return categoryCounts.map((entry) => ({
    ...entry,
    barPercent: entry.caseCount ? Math.round((entry.caseCount / maxCount) * 100) : 0,
  }));
}

export function buildExecutionTrend(runs: RunSummary[], days = 7) {
  const timeline: Array<{ label: string; executed: number; passed: number }> = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const day = new Date(today);
    day.setDate(today.getDate() - offset);
    const dayKey = day.toISOString().slice(0, 10);
    const dayLabel = day.toLocaleDateString(undefined, { weekday: "short" });
    const runsForDay = runs.filter((run) => (run.created_at ?? "").slice(0, 10) === dayKey);
    timeline.push({
      label: dayLabel,
      executed: runsForDay.length,
      passed: runsForDay.filter((run) => run.status === "passed").length,
    });
  }
  return timeline;
}

export function buildDefectTrend(defects: Defect[], points = 7) {
  const sorted = [...defects].sort((left, right) => left.id - right.id).slice(-points);
  let opened = 0;
  let closed = 0;
  return sorted.map((defect, index) => {
    const status = defect.status.trim().toLowerCase();
    if (status.includes("resolved") || status.includes("closed")) closed += 1;
    else opened += 1;
    return {
      label: `D${index + 1}`,
      opened,
      closed,
    };
  });
}

export function buildApplicationCaseDistribution(applications: Application[], cases: TestCase[]) {
  return applications.map((application) => ({
    label: application.name,
    value: cases.filter((caseItem) => caseItem.application_id === application.id).length,
  }));
}

export function buildApplicationPassRateDistribution(applications: Application[], runs: RunSummary[]) {
  return applications.map((application) => {
    const appRuns = runs.filter((run) => run.application_id === application.id);
    const completed = appRuns.filter((run) => ["passed", "failed", "error"].includes(run.status));
    const passed = completed.filter((run) => run.status === "passed").length;
    const rate = completed.length ? Math.round((passed / completed.length) * 100) : 0;
    return { label: application.name, value: rate };
  });
}

export function buildDefectPriorityDistribution(defects: Defect[]): DistributionItem[] {
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
}

export function buildDefectStatusDistribution(defects: Defect[]): DistributionItem[] {
  let open = 0;
  let inProgress = 0;
  let resolved = 0;
  defects.forEach((defect) => {
    const status = defect.status.trim().toLowerCase();
    if (status.includes("open")) open += 1;
    else if (status.includes("progress")) inProgress += 1;
    else if (status.includes("resolved") || status.includes("closed")) resolved += 1;
  });
  return [
    { label: "Open", value: open, tone: "danger" },
    { label: "In progress", value: inProgress, tone: "warning" },
    { label: "Resolved", value: resolved, tone: "success" },
  ];
}

export function buildRunStatusDistribution(runs: RunSummary[]): DistributionItem[] {
  const passed = runs.filter((run) => run.status === "passed").length;
  const failed = runs.filter((run) => run.status === "failed" || run.status === "error").length;
  const queued = runs.filter((run) => run.status === "queued" || run.status === "running").length;
  return [
    { label: "Passed", value: passed, tone: "success" },
    { label: "Failed/Error", value: failed, tone: "danger" },
    { label: "Queued/Running", value: queued, tone: "info" },
  ];
}

export function formatTimestamp(value?: string) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function toTimestampValue(value?: string) {
  if (!value) return 0;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
}

export function formatProjectLifecycle(lifecycle: ProjectLifecycle) {
  if (lifecycle === "active") return "Active";
  if (lifecycle === "paused") return "Paused";
  return "Archived";
}

export function formatPlatformLabel(platform: Platform) {
  if (platform === "web") return "Web";
  if (platform === "android") return "Android";
  return "iOS";
}

export function inferEnvironmentLabel(target?: string) {
  const value = (target ?? "").toLowerCase();
  if (!value) return "Not set";
  if (value.includes("localhost") || value.includes("127.0.0.1")) return "Local";
  if (value.includes("staging") || value.includes("stage")) return "Staging";
  if (value.includes("prod") || value.includes("live")) return "Production";
  return "Shared";
}

export function inferProjectHealth(passRate: number, openDefectCount: number, completedRuns: number): { bucket: ProjectHealthBucket; label: string } {
  if (completedRuns === 0) {
    return { bucket: "noData", label: "No data" };
  }
  if (passRate >= 85 && openDefectCount <= 1) {
    return { bucket: "healthy", label: "Healthy" };
  }
  if (passRate >= 60 && openDefectCount <= 4) {
    return { bucket: "watch", label: "Watch" };
  }
  return { bucket: "critical", label: "Critical" };
}

export function isDraftStatus(status?: string) {
  return status?.trim().toLowerCase() === "draft";
}

export function normaliseStatusValue(status?: string) {
  return (status ?? "").trim().toLowerCase().replace(/_/g, " ");
}

export function formatFailureTypeLabel(failureType?: FailureType | string | null) {
  if (!failureType) return "—";
  return failureType
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
