import type { Application, Platform, ProjectLifecycle, RuntimeParameter, WorkspaceProject } from "../types";

export const PREPARED_EXECUTION_CASES_STORAGE_KEY = "ai-qa-engine:prepared-execution-cases";
export const LATEST_GENERATED_CASES_STORAGE_KEY = "ai-qa-engine:latest-generated-cases";
export const EXECUTION_CONFIGURATION_STORAGE_KEY = "ai-qa-engine:execution-configuration";
export const TEST_DATA_PROFILE_STORAGE_KEY = "ai-qa-engine:test-data-profile";
export const RUNTIME_PARAMETER_KEY_PATTERN = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/;
export const DEFAULT_EXECUTION_PARALLELISM = 1;
export const DEFAULT_LOGIN_EMAIL_SELECTOR = "input[type=email], #email, #user_email, input[name=email], [data-testid=email], input[type=text]";
export const DEFAULT_LOGIN_PASSWORD_SELECTOR = "input[type=password], #password, #user_password, input[name=password], [data-testid=password]";
export const DEFAULT_LOGIN_SUBMIT_SELECTOR = "button[type=submit], input[type=submit], form button, [data-testid=submit]";

export function createRuntimeParameter(): RuntimeParameter {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    key: "",
    value: "",
    sensitive: false,
  };
}

export function normalizeLoginSelector(selector: string): string {
  return selector.trim().replace(/\s+/g, " ").toLowerCase();
}

export function validateLoginSelectors(emailSelector: string, passwordSelector: string, submitSelector: string): string | null {
  const email = emailSelector.trim();
  const password = passwordSelector.trim();
  const submit = submitSelector.trim();
  if (!email || !password || !submit) {
    return "Provide email, password, and submit selectors before running the login flow.";
  }
  if (normalizeLoginSelector(email) === normalizeLoginSelector(password)) {
    return "Email and password selectors must target different fields. Use #user_email and #user_password, or the matching selectors from the target login form.";
  }
  return null;
}

export function validateRuntimeParameters(parameters: RuntimeParameter[], requireLoginCredentials = false, loginSelectors: string[] = []): string | null {
  const seenKeys = new Set<string>();
  for (const parameter of parameters) {
    const key = parameter.key.trim();
    if (!key) continue;
    if (!RUNTIME_PARAMETER_KEY_PATTERN.test(key)) {
      return `Runtime parameter key "${key}" is invalid. Use letters, numbers, dots, hyphens, or underscores.`;
    }
    if (seenKeys.has(key)) return `Runtime parameter "${key}" is defined more than once.`;
    seenKeys.add(key);
  }
  if (requireLoginCredentials) {
    const parameterKeys = new Set(
      parameters
        .filter((parameter) => parameter.value.trim())
        .map((parameter) => parameter.key.trim().toLowerCase()),
    );
    if (!parameterKeys.has("login_email") || !parameterKeys.has("login_password")) {
      return "Add non-empty login_email and login_password runtime parameters before running the login flow.";
    }
    const selectorError = validateLoginSelectors(loginSelectors[0] ?? "", loginSelectors[1] ?? "", loginSelectors[2] ?? "");
    if (selectorError) {
      return selectorError;
    }
  }
  return null;
}

export function buildRuntimeParameterMap(parameters: RuntimeParameter[]): Record<string, string> {
  return Object.fromEntries(
    parameters
      .map((parameter) => [parameter.key.trim(), parameter.value] as const)
      .filter(([key]) => Boolean(key)),
  );
}

export function isSensitiveRuntimeParameter(parameter: RuntimeParameter): boolean {
  return parameter.sensitive || /login[_-]?(email|username)|username|password|passcode|secret|token|api[_-]?key|credential/i.test(parameter.key);
}

export function buildGenerationParameterContext(parameters: RuntimeParameter[]): string {
  const configuredParameters = parameters.filter((parameter) => parameter.key.trim());
  if (!configuredParameters.length) return "";
  const lines = configuredParameters.map((parameter) => {
    const key = parameter.key.trim();
    const value = isSensitiveRuntimeParameter(parameter)
      ? "provided at execution time"
      : parameter.value.trim() || "provided at execution time";
    return `- ${key}: ${value}; use {{${key}}} when the scenario needs this value.`;
  });
  return [
    "TEST DATA PARAMETERS",
    "Use these approved variables instead of inventing account, identifier, or business data. Sensitive values are intentionally unavailable during generation.",
    ...lines,
  ].join("\n");
}

export function readPreparedExecutionCaseIds(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(PREPARED_EXECUTION_CASES_STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(stored)
      ? stored.filter((value): value is number => Number.isInteger(value) && value > 0)
      : [];
  } catch {
    return [];
  }
}

export function readLatestGeneratedCaseIds(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(LATEST_GENERATED_CASES_STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(stored)
      ? stored.filter((value): value is number => Number.isInteger(value) && value > 0)
      : [];
  } catch {
    return [];
  }
}

export const sortApplicationsForDisplay = (items: Application[]) => [...items].sort((left, right) => {
  return left.name.localeCompare(right.name);
});

export const mapApiApplication = (item: { id: number; name: string; platform: string; target: string }, fallbackCases = 0): Application => ({
  id: item.id,
  name: item.name,
  type: item.platform === "web" ? "Web application" : item.platform === "android" ? "Android application" : "iOS application",
  platform: item.platform as Platform,
  url: item.target,
  target: item.target,
  cases: fallbackCases,
});

export const mapApiProject = (item: {
  id: string;
  name: string;
  description?: string | null;
  lifecycle: ProjectLifecycle;
  owner: string;
  created_at?: string | null;
  updated_at?: string | null;
}): WorkspaceProject => ({
  id: item.id,
  name: item.name,
  description: item.description ?? "",
  lifecycle: item.lifecycle,
  owner: item.owner,
  createdAt: item.created_at ?? new Date().toISOString(),
  updatedAt: item.updated_at ?? item.created_at ?? new Date().toISOString(),
});
