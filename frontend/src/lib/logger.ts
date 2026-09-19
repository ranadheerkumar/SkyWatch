"use client";

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  correlationId?: string;
  context?: Record<string, unknown>;
}

const MAX_LOG_BUFFER = 100;
const logBuffer: LogEntry[] = [];

let activeSessionId = "";
if (typeof window !== "undefined") {
  try {
    activeSessionId = window.sessionStorage.getItem("ai-qa-engine:session-id") ?? "";
    if (!activeSessionId) {
      activeSessionId = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      window.sessionStorage.setItem("ai-qa-engine:session-id", activeSessionId);
    }
  } catch {
    activeSessionId = `sess-${Date.now()}`;
  }
}

function writeLog(level: LogLevel, message: string, context?: Record<string, unknown>): void {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    message,
    correlationId: (context?.correlationId as string) || activeSessionId,
    context: {
      sessionId: activeSessionId,
      ...context,
    },
  };

  logBuffer.push(entry);
  if (logBuffer.length > MAX_LOG_BUFFER) {
    logBuffer.shift();
  }

  const formatted = `[AI-QA-Engine] [${level.toUpperCase()}] ${message}`;
  if (level === "error") {
    console.error(formatted, context ?? "");
  } else if (level === "warn") {
    console.warn(formatted, context ?? "");
  } else if (level === "info") {
    console.info(formatted, context ?? "");
  } else {
    console.debug(formatted, context ?? "");
  }
}

export const logger = {
  debug: (message: string, context?: Record<string, unknown>) => writeLog("debug", message, context),
  info: (message: string, context?: Record<string, unknown>) => writeLog("info", message, context),
  warn: (message: string, context?: Record<string, unknown>) => writeLog("warn", message, context),
  error: (message: string, context?: Record<string, unknown>) => writeLog("error", message, context),
  getRecentLogs: (): LogEntry[] => [...logBuffer],
  getSessionId: (): string => activeSessionId,
};
