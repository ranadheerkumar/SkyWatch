"use client";

import { useEffect, useMemo, useState, useDeferredValue } from "react";
import type { AIAgentStage } from "../types";

export type ConsoleLogLevel = "info" | "ai" | "step" | "success" | "warn" | "error";

export type ConsoleLogEntry = {
  id: string;
  timestamp: string;
  level: ConsoleLogLevel;
  message: string;
};

type AIGenerationConsoleProps = {
  logs: ConsoleLogEntry[];
  phase: string;
  active: boolean;
  agentStages?: AIAgentStage[];
  onClear: () => void;
};

const levelLabels: Record<ConsoleLogLevel, string> = {
  info: "Info",
  ai: "AI engine",
  step: "Step",
  success: "Success",
  warn: "Warning",
  error: "Error",
};

function logText(logs: ConsoleLogEntry[]) {
  return logs.map((log) => `[${log.timestamp}] [${levelLabels[log.level].toUpperCase()}] ${log.message}`).join("\n");
}

export default function AIGenerationConsole({ logs, phase, active, agentStages = [], onClear }: AIGenerationConsoleProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [levelFilter, setLevelFilter] = useState<ConsoleLogLevel | "all">("all");
  const [followStream, setFollowStream] = useState(true);
  const [copied, setCopied] = useState(false);
  const [consoleElement, setConsoleElement] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!followStream || !consoleElement) return;
    consoleElement.scrollTop = consoleElement.scrollHeight;
  }, [consoleElement, followStream, logs.length]);

  const filteredLogs = useMemo(() => {
    const normalizedQuery = deferredQuery.trim().toLowerCase();
    return logs.filter((log) => {
      const matchesLevel = levelFilter === "all" || log.level === levelFilter;
      const matchesQuery = !normalizedQuery || `${log.message} ${log.timestamp}`.toLowerCase().includes(normalizedQuery);
      return matchesLevel && matchesQuery;
    });
  }, [logs, levelFilter, deferredQuery]);
  const visiblePhase = phase === "idle" ? "Ready" : phase === "error" ? "Error" : phase === "done" ? "Complete" : phase;
  const statusClass = active ? "active" : phase === "error" ? "error" : "idle";
  const activeStage = agentStages.find((stage) => stage.status === "running");
  const failedStage = agentStages.find((stage) => stage.status === "failed");
  const completedStageCount = agentStages.filter((stage) => stage.status === "completed").length;
  const workflowComplete = agentStages.length > 0 && completedStageCount === agentStages.length;
  const liveStageTitle = activeStage?.name
    ?? failedStage?.name
    ?? (workflowComplete ? "AI agent workflow complete" : active ? "AI agent workflow starting" : "AI agent workflow queued");
  const liveStageDetail = activeStage?.detail
    ?? failedStage?.detail
    ?? (workflowComplete ? "All planned stages completed and repository output is available." : "Waiting for the server-owned agent workflow to start.");
  const liveStageProgress = activeStage?.progress ?? (workflowComplete ? 100 : 0);
  const levelCounts = logs.reduce<Record<string, number>>((counts, log) => {
    counts[log.level] = (counts[log.level] ?? 0) + 1;
    return counts;
  }, {});

  const copyLogs = async () => {
    if (!logs.length) return;
    try {
      await navigator.clipboard.writeText(logText(logs));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const downloadLogs = () => {
    if (!logs.length) return;
    const file = new Blob([logText(logs)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ai-qa-engine-ai-generation-console.log";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="ai-console-card" aria-label="AI generation console">
      <div className="ai-console-header">
        <div className="ai-console-header-left">
          <span className={`ai-console-dot ${statusClass}`} />
          <div className="ai-console-title-group">
            <strong>AI Test Generation Console</strong>
            <span>Live execution trace</span>
          </div>
          <span className={`ai-console-phase ai-console-phase-${statusClass}`}>{visiblePhase}</span>
        </div>
        <div className="ai-console-header-actions">
          <span className="ai-console-event-count">{logs.length} event{logs.length === 1 ? "" : "s"}</span>
          <button type="button" className="ai-console-tool" onClick={() => setFollowStream((current) => !current)} disabled={!logs.length}>
            {followStream ? "Pause follow" : "Resume follow"}
          </button>
          <button type="button" className="ai-console-tool" onClick={() => void copyLogs()} disabled={!logs.length}>
            {copied ? "Copied" : "Copy log"}
          </button>
          <button type="button" className="ai-console-tool" onClick={downloadLogs} disabled={!logs.length}>
            Export
          </button>
          <button type="button" className="ai-console-tool ai-console-tool-danger" onClick={onClear} disabled={!logs.length}>
            Clear
          </button>
        </div>
      </div>

      {agentStages.length > 0 && (
        <div className="ai-console-live-status" aria-live="polite">
          <div className="ai-console-live-status-head">
            <span className={`ai-console-live-indicator ${activeStage ? "running" : failedStage ? "failed" : workflowComplete ? "completed" : "queued"}`} />
            <div className="ai-console-live-copy">
              <strong>{liveStageTitle}</strong>
              <span>{liveStageDetail}</span>
            </div>
            <strong className="ai-console-live-progress-label">{liveStageProgress}%</strong>
          </div>
          <div className="ai-console-live-progress" role="progressbar" aria-label={`${liveStageTitle} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={liveStageProgress}>
            <i style={{ width: `${liveStageProgress}%` }} />
          </div>
          <div className="ai-console-stage-strip" aria-label="AI agent stage progress">
            {agentStages.map((stage) => (
              <span key={stage.key} className={`ai-console-stage-pill ai-console-stage-pill-${stage.status}`} title={`${stage.name}: ${stage.status}`}>
                <i />
                {stage.name.replace(" Agent", "")}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="ai-console-toolbar">
        <label className="ai-console-filter-field">
          <span className="sr-only">Filter console events</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter events or search text" />
        </label>
        <label className="ai-console-filter-field ai-console-level-filter">
          <span className="sr-only">Filter event level</span>
          <select value={levelFilter} onChange={(event) => setLevelFilter(event.target.value as ConsoleLogLevel | "all")}>
            <option value="all">All levels</option>
            {(Object.keys(levelLabels) as ConsoleLogLevel[]).map((level) => <option key={level} value={level}>{levelLabels[level]}</option>)}
          </select>
        </label>
        <span className="ai-console-filter-summary">Showing {filteredLogs.length} of {logs.length}</span>
        {logs.length > 0 && (
          <div className="ai-console-level-counts" aria-label="Event counts by level">
            {(Object.keys(levelLabels) as ConsoleLogLevel[]).filter((level) => levelCounts[level]).map((level) => (
              <span key={level} className={`ai-console-count ai-console-count-${level}`}>{levelLabels[level]} {levelCounts[level]}</span>
            ))}
          </div>
        )}
      </div>

      <div className="ai-console-body" ref={setConsoleElement} aria-live={active ? "polite" : "off"}>
        {!logs.length ? (
          <div className="ai-console-empty">
            <strong>{active ? "Waiting for generation events..." : "AI Generation Console is ready."}</strong>
            <span>{active ? "Prompt analysis and provider activity will appear here." : "Run generation to inspect prompt analysis, LLM inference, validation, and repository events."}</span>
          </div>
        ) : !filteredLogs.length ? (
          <div className="ai-console-empty">
            <strong>No matching events</strong>
            <span>Adjust the filter to inspect the complete event stream.</span>
          </div>
        ) : (
          filteredLogs.map((log) => (
            <div key={log.id} className={`ai-console-line ai-console-line-${log.level}`}>
              <span className="ai-console-time">{log.timestamp}</span>
              <span className={`ai-console-tag tag-${log.level}`}>{levelLabels[log.level]}</span>
              <span className="ai-console-msg">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
