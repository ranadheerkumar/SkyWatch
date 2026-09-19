"use client";

import React, { useState, useEffect, useRef } from "react";

export interface SystemLogRecord {
  timestamp: number;
  iso_time: string;
  level: string;
  logger: string;
  correlation_id: string;
  message: string;
}

interface SystemLogViewerProps {
  token?: string | null;
  apiUrl?: string;
  className?: string;
}

export default function SystemLogViewer({
  token,
  apiUrl = "",
  className = "",
}: SystemLogViewerProps) {
  const [logs, setLogs] = useState<SystemLogRecord[]>([]);
  const [filterLevel, setFilterLevel] = useState<string>("ALL");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [limit, setLimit] = useState<number>(100);
  const [isLive, setIsLive] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const fetchLogs = async () => {
    if (!token) return;
    try {
      setIsLoading(true);
      setError(null);
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (filterLevel !== "ALL") {
        params.set("level", filterLevel);
      }
      if (searchTerm.trim()) {
        params.set("search", searchTerm.trim());
      }

      const res = await fetch(`${apiUrl}/api/v1/observability/logs?${params.toString()}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!res.ok) {
        throw new Error(`Failed to load system logs: HTTP ${res.status}`);
      }

      const data = await res.json();
      setLogs(data.logs || []);
    } catch (err: any) {
      setError(err?.message || "Error fetching system logs");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [filterLevel, limit, token]);

  // Live polling effect
  useEffect(() => {
    if (!isLive || !token) return;
    const interval = setInterval(() => {
      fetchLogs();
    }, 3000);
    return () => clearInterval(interval);
  }, [isLive, filterLevel, limit, searchTerm, token]);

  const handleCopy = () => {
    const text = logs
      .map((l) => `[${l.iso_time}] [${l.level}] [${l.logger}] ${l.message}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const text = logs
      .map((l) => `[${l.iso_time}] [${l.level}] [${l.logger}] ${l.message}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `skywatch-system-logs-${Date.now()}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getLevelBadgeClass = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR":
      case "CRITICAL":
        return "text-rose-400 bg-rose-950/40 border-rose-800/60";
      case "WARNING":
      case "WARN":
        return "text-amber-400 bg-amber-950/40 border-amber-800/60";
      case "DEBUG":
        return "text-slate-400 bg-slate-900 border-slate-700";
      case "INFO":
      default:
        return "text-sky-400 bg-sky-950/40 border-sky-800/60";
    }
  };

  return (
    <div className={`border border-slate-800 rounded-xl bg-slate-900/90 shadow-xl overflow-hidden ${className}`}>
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between px-4 py-3 bg-slate-950/80 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base">🖥️</span>
          <span className="font-semibold text-sm text-slate-200">
            System & Runtime Logs
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
            In-Memory Ring Buffer (1,000 max)
          </span>
          <span className="text-xs text-slate-400">
            ({logs.length} loaded)
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setIsLive(!isLive)}
            className={`text-xs px-2.5 py-1 rounded font-medium border transition flex items-center gap-1.5 ${
              isLive
                ? "bg-emerald-950/40 text-emerald-300 border-emerald-800/60 hover:bg-emerald-900/40"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-750"
            }`}
          >
            <span className={`inline-block w-2 h-2 rounded-full ${isLive ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}`} />
            {isLive ? "Live Tailing" : "Paused"}
          </button>
          <button
            type="button"
            onClick={fetchLogs}
            disabled={isLoading}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-40 transition flex items-center gap-1"
          >
            🔄 Refresh
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center gap-1"
          >
            {copied ? "✓ Copied" : "📋 Copy"}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={logs.length === 0}
            className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-40 transition flex items-center gap-1"
          >
            💾 Download .log
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2 bg-slate-950/40 border-b border-slate-800/80 gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400">Level:</span>
          {["ALL", "INFO", "WARNING", "ERROR"].map((lvl) => (
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
            onKeyDown={(e) => e.key === "Enter" && fetchLogs()}
            placeholder="Search logs & press enter..."
            className="text-xs bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-44 sm:w-60"
          />
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">Limit:</span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="text-xs bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/30 border-b border-rose-800/50 text-xs text-rose-300">
          ⚠️ {error}
        </div>
      )}

      {/* Log Console Body */}
      <div
        ref={scrollRef}
        className="p-3 bg-slate-950 font-mono text-xs leading-relaxed max-h-96 overflow-y-auto space-y-1 divide-y divide-slate-900"
      >
        {logs.length === 0 ? (
          <div className="text-center py-10 text-slate-500">
            {isLoading ? "Fetching system logs..." : "No logs recorded matching current criteria."}
          </div>
        ) : (
          logs.map((log, idx) => {
            const timeStr = log.iso_time
              ? log.iso_time.split("T")[1]?.slice(0, 8) || ""
              : "";
            return (
              <div
                key={idx}
                className="pt-1.5 first:pt-0 flex items-start gap-2 hover:bg-slate-900/60 px-1.5 py-0.5 rounded transition"
              >
                <span className="text-slate-500 shrink-0 select-none text-[11px]">
                  {timeStr || `${idx + 1}`}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-semibold uppercase shrink-0 border ${getLevelBadgeClass(
                    log.level
                  )}`}
                >
                  {log.level}
                </span>
                <span className="text-slate-400 text-[11px] shrink-0">
                  [{log.logger}]
                </span>
                {log.correlation_id && (
                  <span className="text-slate-500 text-[10px] shrink-0 font-mono">
                    cid={log.correlation_id.slice(0, 8)}
                  </span>
                )}
                <span className="text-slate-200 flex-1 break-words font-mono">
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
