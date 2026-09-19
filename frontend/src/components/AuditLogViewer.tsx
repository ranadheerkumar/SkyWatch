"use client";

import { useMemo, useState, useDeferredValue } from "react";

export type AuditEntry = {
  id: number;
  user_id: number;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  old_value?: any;
  new_value?: any;
  approval_status?: string | null;
  created_at: string;
  metadata_json?: any;
};

interface AuditLogViewerProps {
  logs: AuditEntry[];
  onRefresh: () => Promise<void>;
  refreshing: boolean;
}

export default function AuditLogViewer({
  logs,
  onRefresh,
  refreshing,
}: AuditLogViewerProps) {
  const [searchTerm, setSearchTerm] = useState<string>("");
  const deferredSearch = useDeferredValue(searchTerm);
  const [selectedAction, setSelectedAction] = useState<string>("all");
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState<boolean>(true);

  const uniqueActions = useMemo(() => Array.from(new Set(logs.map((l) => l.action))), [logs]);

  const activeFilterCount = (searchTerm.trim() ? 1 : 0) + (selectedAction !== "all" ? 1 : 0);

  const filteredLogs = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase();
    return logs.filter((log) => {
      const matchesSearch =
        !q ||
        log.action.toLowerCase().includes(q) ||
        log.resource_type.toLowerCase().includes(q) ||
        String(log.resource_id || "").toLowerCase().includes(q) ||
        (log.metadata_json && JSON.stringify(log.metadata_json).toLowerCase().includes(q));
      const matchesAction = selectedAction === "all" || log.action === selectedAction;
      return matchesSearch && matchesAction;
    });
  }, [logs, deferredSearch, selectedAction]);

  return (
    <div className="audit-viewer-container" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div className="audit-toolbar panel run-history-toolbar">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
              System Audit Trail &amp; Governance
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-secondary)" }}>
              Immutable log of test case creation, edit, deletion, AI generation, agent recommendation, and execution events.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
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
              onClick={() => void onRefresh()}
              disabled={refreshing}
              className="btn btn-secondary btn-sm"
            >
              {refreshing ? "Refreshing..." : "↻ Refresh Logs"}
            </button>
          </div>
        </div>

        {/* Quick Presets for Audit Categories */}
        <div className="filter-presets-bar">
          <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Quick Presets:</span>
          <button
            type="button"
            className={`filter-preset-chip ${selectedAction === "all" ? "active" : ""}`}
            onClick={() => { setSelectedAction("all"); setSearchTerm(""); }}
          >
            All Logs ({logs.length})
          </button>
          {uniqueActions.slice(0, 5).map((act) => (
            <button
              key={`quick-audit-${act}`}
              type="button"
              className={`filter-preset-chip ${selectedAction === act ? "active" : ""}`}
              onClick={() => setSelectedAction(act)}
            >
              {act}
            </button>
          ))}
        </div>

        {showFilters && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", paddingTop: "8px" }}>
            <input
              type="search"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by action, resource type, ID, or metadata..."
              className="settings-input"
              style={{ flex: 1, minWidth: "220px" }}
            />
            <select
              value={selectedAction}
              onChange={(e) => setSelectedAction(e.target.value)}
              className="settings-select"
              style={{ width: "auto", minWidth: "160px" }}
            >
              <option value="all">All Actions ({logs.length})</option>
              {uniqueActions.map((act) => (
                <option key={act} value={act}>{act}</option>
              ))}
            </select>
          </div>
        )}

        {/* Active Filter Tags */}
        {activeFilterCount > 0 && (
          <div className="active-filter-tags">
            <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeFilterCount}):</span>
            {selectedAction !== "all" && (
              <span className="active-filter-tag">
                Action: {selectedAction}
                <button type="button" onClick={() => setSelectedAction("all")} aria-label="Clear action filter">✕</button>
              </span>
            )}
            {searchTerm && (
              <span className="active-filter-tag">
                "{searchTerm}"
                <button type="button" onClick={() => setSearchTerm("")} aria-label="Clear search">✕</button>
              </span>
            )}
            <button
              type="button"
              className="table-action"
              onClick={() => { setSelectedAction("all"); setSearchTerm(""); }}
              style={{ fontSize: "11px" }}
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      <div className="panel table-panel workspace-table-surface audit-table-card">
        <div className="table-scroll table-scroll-contained">
          <table className="audit-table workspace-table" style={{ minWidth: "960px", tableLayout: "fixed", width: "100%" }}>
            <thead>
              <tr>
                <th className="col-updated" style={{ width: "180px", minWidth: "180px", whiteSpace: "nowrap" }}>Timestamp</th>
                <th className="col-user" style={{ width: "110px", minWidth: "110px", whiteSpace: "nowrap" }}>User</th>
                <th className="col-action" style={{ width: "180px", minWidth: "180px" }}>Action</th>
                <th className="col-resource" style={{ width: "160px", minWidth: "160px" }}>Resource</th>
                <th className="col-id" style={{ width: "150px", minWidth: "150px", whiteSpace: "nowrap" }}>Resource ID</th>
                <th className="col-actions" style={{ textAlign: "right", width: "130px", minWidth: "130px", whiteSpace: "nowrap" }}>Metadata</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: "32px", textAlign: "center", color: "var(--text-secondary)" }}>
                    No audit records match the current filters.
                  </td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <tr key={`audit-${log.id}`}>
                    <td style={{ fontFamily: "var(--font-code)", fontSize: "12px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}><strong>User #{log.user_id}</strong></td>
                    <td>
                      <span className="audit-action-chip" style={{ whiteSpace: "nowrap" }}>
                        {log.action}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{log.resource_type}</td>
                    <td className="col-id" style={{ fontFamily: "var(--font-code)", fontSize: "12px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                      {log.resource_id || "—"}
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button
                        type="button"
                        onClick={() => setExpandedLogId(expandedLogId === log.id ? null : log.id)}
                        className="btn btn-secondary btn-xs"
                      >
                        {expandedLogId === log.id ? "Hide Details" : "View Details"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Expanded Metadata Inspector */}
      {expandedLogId && (
        <div className="audit-json-box">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "#94a3b8", borderBottom: "1px solid #334155", paddingBottom: "8px", marginBottom: "8px" }}>
            <span>Audit Metadata Inspector · Record #{expandedLogId}</span>
            <button
              type="button"
              onClick={() => setExpandedLogId(null)}
              className="btn-ghost btn-xs"
              style={{ color: "#ffffff", border: "none" }}
            >
              ✕ Close
            </button>
          </div>
          <pre style={{ margin: 0, padding: "8px", overflowX: "auto", fontSize: "12px", lineHeight: "1.5" }}>
            {JSON.stringify(logs.find((l) => l.id === expandedLogId) || {}, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
