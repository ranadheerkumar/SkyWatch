"use client";

import React, { useState, useEffect, useRef } from "react";

export interface GenerationLogItem {
  job_id?: string;
  stage?: string;
  level?: string;
  message: string;
  metadata?: Record<string, any>;
  timestamp?: number;
  iso_time?: string;
}

interface GenerationLogViewerProps {
  jobId?: string | null;
  logs?: GenerationLogItem[];
  status?: string;
  phase?: string;
  isLoading?: boolean;
  onRefresh?: () => void;
  className?: string;
}

export default function GenerationLogViewer({
  jobId,
  logs = [],
  status = "idle",
  phase = "idle",
  isLoading = false,
  onRefresh,
  className = "",
}: GenerationLogViewerProps) {
  const [filterLevel, setFilterLevel] = useState<string>("ALL");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom as new logs arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Filter logs
  const filteredLogs = logs.filter((log) => {
    const matchesLevel =
      filterLevel === "ALL" ||
      (log.level || "").toUpperCase() === filterLevel.toUpperCase();
    const query = searchTerm.toLowerCase();
    const matchesSearch =
      !query ||
      (log.message || "").toLowerCase().includes(query) ||
      (log.stage || "").toLowerCase().includes(query) ||
      JSON.stringify(log.metadata || {}).toLowerCase().includes(query);
    return matchesLevel && matchesSearch;
  });

  const getLevelColor = (level?: string) => {
    switch ((level || "").toUpperCase()) {
      case "ERROR":
        return "text-rose-400 bg-rose-950/40 border-rose-800/50";
      case "WARN":
      case "WARNING":
        return "text-amber-400 bg-amber-950/40 border-amber-800/50";
      case "LLM":
        return "text-purple-400 bg-purple-950/40 border-purple-800/50";
      case "STEP":
        return "text-indigo-400 bg-indigo-950/40 border-indigo-800/50";
      case "SUCCESS":
        return "text-emerald-400 bg-emerald-950/40 border-emerald-800/50";
      case "INFO":
      default:
        return "text-sky-400 bg-sky-950/40 border-sky-800/50";
    }
  };

  const handleCopy = () => {
    const text = filteredLogs
      .map((log) => {
        const time = log.iso_time || (log.timestamp ? new Date(log.timestamp * 1000).toISOString() : "");
        const meta = log.metadata ? ` | ${JSON.stringify(log.metadata)}` : "";
        return `[${time}] [${log.level || "INFO"}] [${log.stage || "general"}] ${log.message}${meta}`;
      })
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const text = logs
      .map((log) => {
        const time = log.iso_time || (log.timestamp ? new Date(log.timestamp * 1000).toISOString() : "");
        const meta = log.metadata ? ` | ${JSON.stringify(log.metadata)}` : "";
        return `[${time}] [${log.level || "INFO"}] [${log.stage || "general"}] ${log.message}${meta}`;
      })
      .join("\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ai-generation-${jobId || "logs"}-${Date.now()}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`border border-slate-800 rounded-xl bg-slate-900/90 shadow-xl overflow-hidden ${className}`}>
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-3 bg-slate-950/80 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-slate-400 hover:text-white transition-colors"
            title={isExpanded ? "Collapse logs" : "Expand logs"}
          >
            <span className="text-sm font-semibold">{isExpanded ? "▼" : "▶"}</span>
          </button>
          <div className="flex items-center gap-2">
            <span className="text-base">📜</span>
            <span className="font-semibold text-sm text-slate-200">
              AI Generation Logs & Trace
            </span>
          </div>
          {jobId && (
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
              #{jobId.slice(0, 8)}
            </span>
          )}
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              status === "running"
                ? "bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse"
                : status === "completed"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                : status === "failed"
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                : "bg-slate-800 text-slate-400 border border-slate-700"
            }`}
          >
            {status.toUpperCase()}
          </span>
          <span className="text-xs text-slate-400">
            ({filteredLogs.length} {filteredLogs.length === 1 ? "entry" : "entries"})
          </span>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={handleCopy}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center gap-1"
            title="Copy logs to clipboard"
          >
            {copied ? "✓ Copied" : "📋 Copy"}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={logs.length === 0}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-40 transition flex items-center gap-1"
            title="Download .log file"
          >
            💾 Download .log
          </button>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading}
              className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-40 transition"
              title="Refresh logs"
            >
              🔄
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <>
          {/* Filter Toolbar */}
          <div className="flex flex-wrap items-center justify-between px-4 py-2 bg-slate-950/40 border-b border-slate-800/80 gap-2">
            <div className="flex items-center gap-1.5 flex-wrap">
              {["ALL", "INFO", "STEP", "LLM", "WARN", "ERROR"].map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => setFilterLevel(lvl)}
                  className={`text-xs px-2.5 py-0.5 rounded font-mono font-medium transition ${
                    filterLevel === lvl
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-750"
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search logs..."
                className="text-xs bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-36 sm:w-48"
              />
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                  className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-0"
                />
                Auto-scroll
              </label>
            </div>
          </div>

          {/* Log Output Body */}
          <div
            ref={scrollRef}
            className="p-3 bg-slate-950 font-mono text-xs leading-relaxed max-h-72 overflow-y-auto space-y-1.5 divide-y divide-slate-900"
          >
            {filteredLogs.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                {logs.length === 0
                  ? "No generation logs recorded yet. As the AI Agent proceeds, step-by-step logs will appear here."
                  : "No log entries match the current filter."}
              </div>
            ) : (
              filteredLogs.map((log, idx) => {
                const timeStr = log.iso_time
                  ? log.iso_time.split("T")[1]?.slice(0, 8) || ""
                  : log.timestamp
                  ? new Date(log.timestamp * 1000).toLocaleTimeString()
                  : "";
                return (
                  <div key={idx} className="pt-1.5 first:pt-0 flex items-start gap-2 group hover:bg-slate-900/50 px-1 rounded transition">
                    <span className="text-slate-500 shrink-0 select-none text-[11px]">
                      {timeStr || `${idx + 1}`}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded font-semibold uppercase shrink-0 border ${getLevelColor(
                        log.level
                      )}`}
                    >
                      {log.level || "INFO"}
                    </span>
                    {log.stage && (
                      <span className="text-slate-400 text-[11px] shrink-0 font-medium">
                        [{log.stage}]
                      </span>
                    )}
                    <span className="text-slate-200 flex-1 break-words">
                      {log.message}
                    </span>
                    {log.metadata && Object.keys(log.metadata).length > 0 && (
                      <div className="shrink-0 flex items-center gap-1 flex-wrap">
                        {Object.entries(log.metadata).map(([k, v]) => (
                          <span
                            key={k}
                            className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800/80 text-slate-300 border border-slate-700 font-sans"
                          >
                            {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}
