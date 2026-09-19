import { AUTH_EXPIRED_EVENT, clearAuthToken } from "./auth";
import { formatDuration } from "./formatDuration";
import { logger } from "./logger";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
const DEFAULT_READ_RETRIES = 2;
const RETRYABLE_STATUS_CODES = new Set([408, 425, 429, 500, 502, 503, 504]);

export type ApiRequestOptions = RequestInit & {
  retries?: number;
  timeoutMs?: number;
};

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly code?: string;
  readonly details?: unknown;

  constructor(message: string, status: number, url: string, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
    this.code = code;
    this.details = details;
  }
}

type ApiResponseWithMeta<T> = {
  data: T;
  headers: Headers;
  status: number;
};

const responseCache = new Map<string, { expiresAt: number; data: unknown }>();

export function clearApiCache(pathPrefix?: string): void {
  for (const key of responseCache.keys()) {
    const separatorIndex = key.indexOf(":");
    const cachedPath = separatorIndex >= 0 ? key.slice(separatorIndex + 1) : key;
    if (!pathPrefix || cachedPath.startsWith(pathPrefix)) responseCache.delete(key);
  }
}

export async function apiFetchCached<T>(path: string, ttlMs = 5000, token?: string): Promise<T> {
  const cacheKey = `${token ? "authenticated" : "anonymous"}:${path}`;
  const cached = responseCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) return cached.data as T;
  const data = await apiFetch<T>(path, {}, token);
  responseCache.set(cacheKey, { expiresAt: Date.now() + ttlMs, data });
  return data;
}

function isReadMethod(method: string): boolean {
  return method === "GET" || method === "HEAD" || method === "OPTIONS";
}

function retryDelayMs(response: Response, attempt: number): number {
  const retryAfter = response.headers.get("retry-after");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds)) return Math.min(Math.max(seconds * 1000, 100), 10_000);
    const retryAt = Date.parse(retryAfter);
    if (!Number.isNaN(retryAt)) return Math.min(Math.max(retryAt - Date.now(), 100), 10_000);
  }
  return Math.min(500 * 2 ** attempt, 5_000);
}

function waitForRetry(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException("Request aborted", "AbortError"));
  return new Promise((resolve, reject) => {
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, delayMs);
    const abort = () => {
      globalThis.clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(signal?.reason ?? new DOMException("Request aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
}

async function fetchWithPolicy(url: string, options: ApiRequestOptions, headers: Headers): Promise<Response> {
  const {
    retries: requestedRetries,
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    signal: callerSignal,
    ...fetchOptions
  } = options;
  const method = String(fetchOptions.method ?? "GET").toUpperCase();
  const retries = isReadMethod(method) ? Math.max(0, requestedRetries ?? DEFAULT_READ_RETRIES) : 0;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    let timedOut = false;
    const timeout = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const abortFromCaller = () => controller.abort(callerSignal?.reason);
    if (callerSignal?.aborted) abortFromCaller();
    else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });
      if (response.ok || !RETRYABLE_STATUS_CODES.has(response.status) || attempt >= retries) return response;
      await response.body?.cancel();
      await waitForRetry(retryDelayMs(response, attempt), callerSignal ?? undefined);
    } catch (error) {
      if (timedOut) throw new Error(`Request timed out after ${formatDuration(timeoutMs)} for ${url}`);
      if (callerSignal?.aborted) throw error;
      if (attempt >= retries) {
        const detail = error instanceof Error ? error.message : "Unknown network error";
        throw new Error(`Network request failed for ${url}. Verify the backend is running and reachable. Technical detail: ${detail}`);
      }
      await waitForRetry(500 * 2 ** attempt, callerSignal ?? undefined);
    } finally {
      globalThis.clearTimeout(timeout);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    }
  }

  throw new Error(`Request failed for ${url}`);
}

function parseResponseBody(rawBody: string, contentType: string): unknown {
  if (!contentType.includes("application/json")) return rawBody;
  if (!rawBody) return null;
  try {
    return JSON.parse(rawBody) as unknown;
  } catch {
    return rawBody;
  }
}

function responseError(data: unknown, response: Response, url: string): ApiError {
  const payload = typeof data === "object" && data !== null ? data as { code?: unknown; detail?: unknown; message?: unknown } : undefined;
  const detail = payload?.detail ?? payload?.message;
  const message = typeof detail === "string" ? detail : `Request failed with status ${response.status}`;
  const code = typeof payload?.code === "string" ? payload.code : undefined;
  return new ApiError(message, response.status, url, code, data);
}

export async function apiFetchWithMeta<T>(path: string, options: ApiRequestOptions = {}, token?: string): Promise<ApiResponseWithMeta<T>> {
  const headers = new Headers(options.headers ?? {});
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const url = `${API_BASE_URL}${path}`;
  const response = await fetchWithPolicy(url, options, headers);

  const contentType = response.headers.get("content-type") ?? "";
  const rawBody = response.status === 204 || response.status === 205 ? "" : await response.text();
  const data = parseResponseBody(rawBody, contentType);

  if (!response.ok) {
    if (response.status === 401 && token && typeof window !== "undefined") {
      logger.warn("Received 401 Unauthorized, session token expired", { url });
      clearAuthToken();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    } else {
      logger.error(`API ${options.method ?? "GET"} request failed (${response.status})`, { url, status: response.status });
    }
    throw responseError(data, response, url);
  }

  if (!isReadMethod(String(options.method ?? "GET").toUpperCase())) clearApiCache();

  return {
    data: data as T,
    headers: response.headers,
    status: response.status,
  };
}

export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}, token?: string): Promise<T> {
  const { data } = await apiFetchWithMeta<T>(path, options, token);
  return data;
}

export async function apiFetchBlob(path: string, token?: string, options: ApiRequestOptions = {}): Promise<Blob> {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const url = `${API_BASE_URL}${path}`;
  const response = await fetchWithPolicy(url, { ...options, method: "GET" }, headers);
  if (!response.ok) throw new ApiError(`Unable to load artifact (${response.status})`, response.status, url);
  return response.blob();
}

export const API_URL = API_BASE_URL;
