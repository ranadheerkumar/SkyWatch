import type {
  AIGenerationJob,
  AIGenerationMode,
  AIGenerationSource,
  ExecutionMode,
  TestCase,
} from "../types";

export type CaseTableDisplayRow = {
  key: string;
  caseId: number;
  isFirst: boolean;
  rowSpan: number;
  testCase: string;
  precondition: string;
  description: string;
  stepNumber: string;
  step: string;
  expectedResult: string;
  status: string;
};

export function isVerificationOnlyLine(lowerLine: string) {
  return /^(verify|validate|confirm|check)\b/.test(lowerLine);
}

export function isInvalidCredentialInstruction(lowerLine: string) {
  if (isVerificationOnlyLine(lowerLine)) return false;
  return /\b(?:invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent|expired|locked|disabled|unverified|mismatched)\b/.test(lowerLine)
    && /\b(?:credential|credentials|email|username|user name|password|passcode)\b/.test(lowerLine);
}

export function isLoginInstructionLine(lowerLine: string) {
  if (isVerificationOnlyLine(lowerLine)) return false;
  const hasCredentialField = /\b(?:credential|credentials|email|username|user name|password|passcode)\b/.test(lowerLine);
  const hasEntryVerb = /\b(?:enter|type|use|provide|input|fill|submit|with|using)\b/.test(lowerLine);
  const loginWithCredentials = /\b(?:login|log in|sign in|authenticate)\b[^.]{0,50}\b(?:with|using)\b/.test(lowerLine);
  const loginSubmitControl = /\b(?:login|log in|sign in|authenticate)\b/.test(lowerLine)
    && /\b(?:click|tap|press|submit)\b/.test(lowerLine);
  return (hasCredentialField && hasEntryVerb) || loginWithCredentials || loginSubmitControl;
}

export function normalizeActionTargetText(value: string) {
  const normalized = value
    .replace(/\bagain\b/gi, " ")
    .replace(/\s+based on\s+.+$/i, "")
    .replace(/\s+(?:from|under|within|inside)\s+.+$/i, "")
    .replace(/\s+on\s+the\s+.+\bpage\b.*$/i, "")
    .replace(/\b(?:button|link|tab|section|dropdown|menu|field)\b/gi, " ")
    .replace(/^[Tt]he\s+/, "")
    .replace(/[.,:;]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return normalized;
}

export function extractVerificationText(line: string, quoted: string[]) {
  const quotedValue = quoted[0]?.trim();
  if (quotedValue) return normalizeActionTargetText(quotedValue);
  const displayedAsMatch = line.match(/displayed as\s+(.+)/i)?.[1];
  if (displayedAsMatch) return normalizeActionTargetText(displayedAsMatch);
  const titleMatch = line.match(/page title(?:\s+\w+)*\s+(.+?)\s+(?:is|was)\s+displayed/i)?.[1];
  if (titleMatch) return normalizeActionTargetText(titleMatch);
  const messageMatch = line.match(/(?:success|error|warning|info)\s+message(?:\s+\w+)*\s+(.+?)\s+(?:is|was)\s+displayed/i)?.[1];
  if (messageMatch) return normalizeActionTargetText(messageMatch);
  return "";
}

export function buildPollingPlan(stepCount: number, checkCount: number, mode: ExecutionMode) {
  const safeStepCount = Number.isFinite(stepCount) ? Math.max(1, Math.floor(stepCount)) : 1;
  const safeCheckCount = Number.isFinite(checkCount) ? Math.max(0, Math.floor(checkCount)) : 0;
  const pollIntervalMs = 1000;
  const baseMs = mode === "watch_live" ? 180_000 : 120_000;
  const perStepMs = mode === "watch_live" ? 8_500 : 5_500;
  const perCheckMs = 2_500;
  const maxWindowMs = mode === "watch_live" ? 12 * 60_000 : 8 * 60_000;
  const maxWaitMs = Math.min(
    maxWindowMs,
    Math.max(baseMs, baseMs + (safeStepCount * perStepMs) + (safeCheckCount * perCheckMs)),
  );
  return {
    pollIntervalMs,
    maxWaitMs,
    maxAttempts: Math.ceil(maxWaitMs / pollIntervalMs),
  };
}

export function getStatusMeta(status?: string): { label: string; icon: string; tone: "success" | "info" | "warning" | "danger" | "neutral" } {
  const normalized = (status ?? "").trim().toLowerCase().replace(/_/g, " ");
  if (["ready", "passed", "connected", "resolved"].includes(normalized)) {
    return { label: normalized === "resolved" ? "Resolved" : normalized === "connected" ? "Connected" : normalized === "passed" ? "Passed" : "Ready", icon: "OK", tone: "success" };
  }
  if (["running", "queued", "in progress", "in-progress"].includes(normalized)) {
    return { label: normalized === "in progress" || normalized === "in-progress" ? "In Progress" : normalized === "queued" ? "Queued" : "Running", icon: "IP", tone: "info" };
  }
  if (["draft", "pending"].includes(normalized)) {
    return { label: normalized === "pending" ? "Pending" : "Draft", icon: "DR", tone: "warning" };
  }
  if (["failed", "error", "open"].includes(normalized)) {
    return { label: normalized === "open" ? "Open" : normalized === "error" ? "Error" : "Failed", icon: "ER", tone: "danger" };
  }
  if (!normalized) {
    return { label: "Unknown", icon: "NA", tone: "neutral" };
  }
  return { label: normalized.charAt(0).toUpperCase() + normalized.slice(1), icon: "IN", tone: "neutral" };
}

export function formatConfidenceLabel(label: "high" | "medium" | "low") {
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function formatConfidenceChipLabel(score: number, label: "high" | "medium" | "low") {
  const icon = label === "high" ? "H" : label === "medium" ? "M" : "L";
  return `${icon} ${score}% ${formatConfidenceLabel(label)}`;
}

export function splitNonEmptyLines(value?: string) {
  return (value ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

export function normaliseCaseKey(value?: string) {
  return (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function inferRunScopeKey(status?: string) {
  const normalized = (status ?? "").trim().toLowerCase();
  if (normalized === "draft") return "draft";
  if (normalized === "ready") return "ready";
  return "all";
}

export function parseAiGenerationSourceFromJob(job: AIGenerationJob): AIGenerationSource {
  const rawMode = (job.result?.generation_mode ?? "").trim().toLowerCase();
  const mode: AIGenerationMode = rawMode === "provider" ? "provider" : "unknown";
  const provider = (job.result?.generation_provider || job.provider || "").trim() || "unknown";
  return {
    mode,
    provider,
    providerConfigured: mode === "provider" && provider !== "unknown",
    note: (job.result?.generation_note || job.result?.summary || "").trim(),
  };
}

export function normalizeGeneratedCases(generatedCases: TestCase[], applicationId: number) {
  const uniqueCases: TestCase[] = [];
  const seen = new Set<string>();
  let duplicateCount = 0;
  let invalidCount = 0;

  for (const caseItem of generatedCases) {
    const title = caseItem.title.trim();
    const steps = (caseItem.steps ?? "").trim();
    const expectedResult = (caseItem.expected_result ?? "").trim();
    if (!title || !steps) {
      invalidCount += 1;
      continue;
    }

    const key = `${normaliseCaseKey(title)}|${normaliseCaseKey(steps)}|${normaliseCaseKey(expectedResult)}`;
    if (seen.has(key)) {
      duplicateCount += 1;
      continue;
    }
    seen.add(key);

    const normalizedStatus = inferRunScopeKey(caseItem.status) === "ready" ? "ready" : "draft";
    uniqueCases.push({
      ...caseItem,
      application_id: applicationId,
      title,
      description: caseItem.description?.trim() || undefined,
      preconditions: caseItem.preconditions?.trim() || undefined,
      steps,
      expected_result: expectedResult || undefined,
      status: normalizedStatus,
    });
  }

  return {
    cases: uniqueCases,
    duplicateCount,
    invalidCount,
  };
}

export function parseStepEntries(steps?: string): Array<{ number: string; text: string }> {
  const lines = splitNonEmptyLines(steps).flatMap((line) => {
    const markers = Array.from(line.matchAll(/(?:^|\s)(\d+)[.)]\s+/g));
    if (markers.length < 2 || markers[0]?.index !== 0) return [line];

    return markers.map((marker, index) => {
      const start = (marker.index ?? 0) + marker[0].length;
      const end = markers[index + 1]?.index ?? line.length;
      const text = line.slice(start, end).trim();
      return `${marker[1]}. ${text}`;
    }).filter((entry) => entry.length > 3);
  });
  if (!lines.length) return [{ number: "—", text: "—" }];
  return lines.map((line, index) => {
    const match = line.match(/^(\d+)[).:\-\s]+(.*)$/);
    if (match) {
      return { number: match[1], text: match[2].trim() || line };
    }
    return { number: String(index + 1), text: line };
  });
}

export function buildCaseTableRows(cases: TestCase[]): CaseTableDisplayRow[] {
  return cases.flatMap((caseItem) => {
    const steps = parseStepEntries(caseItem.steps);
    const expectedResults = splitNonEmptyLines(caseItem.expected_result);
    const rowCount = Math.max(steps.length, expectedResults.length, 1);

    return Array.from({ length: rowCount }, (_, index) => {
      const step = steps[index];
      const expected = expectedResults[index];
      return {
        key: `${caseItem.id}-${index + 1}`,
        caseId: caseItem.id,
        isFirst: index === 0,
        rowSpan: rowCount,
        testCase: caseItem.title,
        precondition: caseItem.preconditions ?? "—",
        description: caseItem.description ?? "—",
        stepNumber: step?.number ?? "",
        step: step?.text ?? "",
        expectedResult: expected ?? (index === 0 ? "—" : ""),
        status: caseItem.status,
      };
    });
  });
}
