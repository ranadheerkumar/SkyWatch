"use client";

import { useEffect, useMemo, useState, useDeferredValue } from "react";
import { apiFetch } from "../lib/api";

export type AgentRecommendation = {
  id: number;
  application_id: number;
  test_case_id?: number | null;
  recommendation_type: string;
  title: string;
  description?: string | null;
  proposed_steps?: any[] | null;
  proposed_checks?: any[] | null;
  status: string;
  created_at: string;
  reviewed_at?: string | null;
};

export type PreExecutionAnalysis = {
  application_id: number;
  total_analyzed: number;
  ready_count: number;
  at_risk_count: number;
  outdated_count: number;
  insights: string[];
  recommendations: AgentRecommendation[];
};

export type AgentManifestItem = {
  key: string;
  title: string;
  file_name: string;
  version: string;
  checksum_sha256?: string;
};

interface AgentRecommendationsBoardProps {
  appName: string;
  appId?: number;
  token?: string;
  recommendations: AgentRecommendation[];
  analysis: PreExecutionAnalysis | null;
  analyzing: boolean;
  onAnalyze: () => Promise<void>;
  onReview: (recommendationId: number, action: "approve" | "reject", reviewNotes?: string) => Promise<void>;
  onOpenTestCases?: () => void;
}

const REGISTERED_AGENTS_FALLBACK: Array<{
  key: string;
  name: string;
  category: "Intake & Discovery" | "Planning & Design" | "Execution & Quality" | "Intelligence & Analytics";
  responsibility: string;
  modelType: "Autonomous" | "LLM-Powered" | "Deterministic Guard";
}> = [
  { key: "discovery", name: "Application Discovery Agent", category: "Intake & Discovery", responsibility: "Autonomous DOM crawling, page structure mapping, form detection, and route inventory.", modelType: "Autonomous" },
  { key: "context_builder", name: "Context Builder Agent", category: "Intake & Discovery", responsibility: "Aggregates requirements, live discovery, reference cases, and project parameters.", modelType: "Deterministic Guard" },
  { key: "document_analysis", name: "Document Analysis Agent", category: "Intake & Discovery", responsibility: "Extracts requirements, features, business rules, and risks from uploaded files.", modelType: "Deterministic Guard" },
  { key: "planner", name: "Test Planning Agent", category: "Planning & Design", responsibility: "Computes coverage matrix, entry points, risk areas, and recommended case quotas.", modelType: "LLM-Powered" },
  { key: "scenario", name: "Scenario Generation Agent", category: "Planning & Design", responsibility: "Balances positive, negative, boundary, edge, security, and accessibility scenarios.", modelType: "Deterministic Guard" },
  { key: "selection", name: "Test Selection Agent", category: "Planning & Design", responsibility: "Sub-selects optimal regression suites based on code/requirement changes and historical risk.", modelType: "Autonomous" },
  { key: "deduplication", name: "Test Deduplication Agent", category: "Planning & Design", responsibility: "Detects semantic and locator overlap across test suites to reduce maintenance.", modelType: "Autonomous" },
  { key: "generator", name: "Test Case Generator Agent", category: "Planning & Design", responsibility: "Generates detailed, numbered, step-by-step test cases with expected results.", modelType: "LLM-Powered" },
  { key: "test_data", name: "Test Data Generator Agent", category: "Planning & Design", responsibility: "Synthesizes realistic, valid, invalid, and boundary test datasets with masking.", modelType: "Autonomous" },
  { key: "validator", name: "Validation Agent", category: "Execution & Quality", responsibility: "Validates completeness, steps bounds, coverage signals, and review needs.", modelType: "Deterministic Guard" },
  { key: "authoring", name: "Low-Code Authoring Agent", category: "Execution & Quality", responsibility: "Translates approved test cases into structured Playwright step automations.", modelType: "Autonomous" },
  { key: "repository", name: "Repository Agent", category: "Execution & Quality", responsibility: "Persists approved test cases and compiles executable automation assets.", modelType: "Deterministic Guard" },
  { key: "healer", name: "Playwright Test Healer", category: "Execution & Quality", responsibility: "Detects locator drift and performs real-time validated element repairs.", modelType: "LLM-Powered" },
  { key: "failure_analysis", name: "Failure Analysis Agent", category: "Intelligence & Analytics", responsibility: "Multimodal root-cause diagnosis using Playwright traces, console logs, and screenshots.", modelType: "Autonomous" },
  { key: "maintenance", name: "Test Maintenance Agent", category: "Intelligence & Analytics", responsibility: "Monitors application evolution and proactively updates locators and assertions.", modelType: "Autonomous" },
  { key: "reporting", name: "Reporting Agent", category: "Intelligence & Analytics", responsibility: "Synthesizes executive quality summaries, pass-rate trends, and coverage matrices.", modelType: "Autonomous" },
];

function formatRecommendationType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "Not reviewed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function getStepValue(step: Record<string, unknown>) {
  const selector = String(step.selector ?? "");
  if (step.secret_name || /password|secret|token|credential/i.test(selector)) return "Protected value";
  return step.value ? String(step.value) : "No input value";
}

function hasStepValue(step: Record<string, unknown>) {
  return Boolean(step.value || step.secret_name);
}

function getStepTarget(step: Record<string, unknown>) {
  return String(step.selector ?? step.value ?? "Page-level action");
}

function getStatusClass(status: string) {
  const normalized = status.toLowerCase();
  return normalized === "approved" || normalized === "auto_applied" ? "approved" : normalized === "rejected" ? "rejected" : "pending";
}

export default function AgentRecommendationsBoard({
  appName,
  appId,
  token,
  recommendations,
  analysis,
  analyzing,
  onAnalyze,
  onReview,
  onOpenTestCases,
}: AgentRecommendationsBoardProps) {
  const [activeTab, setActiveTab] = useState<"recommendations" | "registry">("recommendations");
  const [manifestItems, setManifestItems] = useState<AgentManifestItem[]>([]);
  const [filterType, setFilterType] = useState<string>("all");
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearch = useDeferredValue(searchQuery);
  const [selectedId, setSelectedId] = useState<number | null>(recommendations[0]?.id ?? null);
  const [reviewNotes, setReviewNotes] = useState("");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const fetchManifest = async () => {
      try {
        const items = await apiFetch<AgentManifestItem[]>("/api/v1/agents/manifest", {}, token);
        if (!cancelled && Array.isArray(items)) setManifestItems(items);
      } catch {
        // Keep fallback items
      }
    };
    void fetchManifest();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const pendingRecs = useMemo(() => recommendations.filter((r) => r.status === "pending"), [recommendations]);

  const filteredRecs = useMemo(() => {
    const normalizedQuery = deferredSearch.trim().toLowerCase();
    return recommendations.filter((recommendation) => {
      const matchesFilter = filterType === "all"
        || recommendation.recommendation_type === filterType
        || recommendation.status === filterType;
      const searchableText = `${recommendation.title} ${recommendation.description ?? ""} ${recommendation.recommendation_type}`.toLowerCase();
      return matchesFilter && (!normalizedQuery || searchableText.includes(normalizedQuery));
    });
  }, [recommendations, filterType, deferredSearch]);

  const selectedRecommendation = filteredRecs.find((recommendation) => recommendation.id === selectedId) ?? filteredRecs[0] ?? null;
  const selectedIndex = selectedRecommendation
    ? filteredRecs.findIndex((recommendation) => recommendation.id === selectedRecommendation.id)
    : -1;

  const selectRecommendationAt = (index: number) => {
    const recommendation = filteredRecs[index];
    if (!recommendation) return;
    setSelectedId(recommendation.id);
    setReviewNotes("");
  };

  useEffect(() => {
    if (selectedRecommendation?.id !== selectedId) {
      setSelectedId(selectedRecommendation?.id ?? null);
      setReviewNotes("");
    }
  }, [selectedId, selectedRecommendation]);

  const handleReviewClick = async (id: number, action: "approve" | "reject") => {
    setReviewingId(id);
    try {
      await onReview(id, action, reviewNotes.trim() || undefined);
      setReviewNotes("");
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <div className="agent-recommendations-board">
      <div className="agent-hero-banner">
        <div className="agent-hero-head">
          <div>
            <div className="agent-hero-badge">
              <span className="agent-hero-pulse"></span>
              Autonomous Agent Framework · 12+ Specialized Agents
            </div>
            <h2 className="agent-hero-title">Autonomous QA Agents · {appName}</h2>
          </div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
            <button
              type="button"
              className={`btn ${activeTab === "recommendations" ? "btn-indigo" : "btn-secondary"}`}
              onClick={() => setActiveTab("recommendations")}
            >
              Recommendations & Actions ({recommendations.length})
            </button>
            <button
              type="button"
              className={`btn ${activeTab === "registry" ? "btn-indigo" : "btn-secondary"}`}
              onClick={() => setActiveTab("registry")}
            >
              Agent Registry & Capabilities (16)
            </button>
            {activeTab === "recommendations" ? (
              <button
                type="button"
                onClick={() => void onAnalyze()}
                disabled={analyzing || !appId}
                className="btn btn-emerald"
                style={{ padding: "10px 20px", fontSize: "14px" }}
              >
                {analyzing ? "Analyzing Application..." : "Run Pre-Execution Analysis"}
              </button>
            ) : null}
          </div>
        </div>

        {analysis && activeTab === "recommendations" && (
          <div className="agent-metrics-row">
            <div className="agent-metric-tile">
              <div className="agent-metric-label">Total Analyzed</div>
              <div className="agent-metric-value">{analysis.total_analyzed}</div>
            </div>
            <div className="agent-metric-tile ready">
              <div className="agent-metric-label" style={{ color: "#86efac" }}>Ready Cases</div>
              <div className="agent-metric-value" style={{ color: "#4ade80" }}>{analysis.ready_count}</div>
            </div>
            <div className="agent-metric-tile risk">
              <div className="agent-metric-label" style={{ color: "#fde68a" }}>At-Risk Locators</div>
              <div className="agent-metric-value" style={{ color: "#facc15" }}>{analysis.at_risk_count}</div>
            </div>
            <div className="agent-metric-tile outdated">
              <div className="agent-metric-label" style={{ color: "#fecdd3" }}>Outdated / Missing</div>
              <div className="agent-metric-value" style={{ color: "#f87171" }}>{analysis.outdated_count}</div>
            </div>
          </div>
        )}
      </div>

      {activeTab === "registry" ? (
        <div className="panel agent-registry-panel" style={{ marginTop: "16px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Autonomous QA Agent Registry</h3>
              <p className="muted" style={{ margin: "4px 0 0" }}>
                16 specialized autonomous, LLM-powered, and deterministic quality engineering agents.
              </p>
            </div>
            <span className="badge badge-indigo" style={{ padding: "6px 12px", borderRadius: "999px" }}>
              Framework v1.3 · All Agents Active
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "14px" }}>
            {REGISTERED_AGENTS_FALLBACK.map((agent) => {
              const liveManifest = manifestItems.find((item) => item.key === agent.key);
              return (
                <div
                  key={`agent-card-${agent.key}`}
                  style={{
                    border: "1px solid var(--border-light)",
                    borderRadius: "var(--radius-md)",
                    padding: "16px",
                    background: "var(--bg-layer-2)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "8px" }}>
                    <div>
                      <span className="detail-label" style={{ fontSize: "11px", textTransform: "uppercase" }}>{agent.category}</span>
                      <strong style={{ display: "block", fontSize: "15px", marginTop: "2px" }}>{agent.name}</strong>
                    </div>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "3px 8px",
                        borderRadius: "999px",
                        background: agent.modelType === "Autonomous" ? "rgba(34, 197, 94, 0.15)" : agent.modelType === "LLM-Powered" ? "rgba(99, 102, 241, 0.15)" : "rgba(148, 163, 184, 0.15)",
                        color: agent.modelType === "Autonomous" ? "var(--success-dark)" : agent.modelType === "LLM-Powered" ? "var(--info-dark)" : "var(--text-secondary)",
                        border: "1px solid currentColor",
                      }}
                    >
                      {agent.modelType}
                    </span>
                  </div>
                  <p className="muted" style={{ fontSize: "13px", margin: 0, lineHeight: 1.45, flex: 1 }}>
                    {agent.responsibility}
                  </p>
                  <div style={{ borderTop: "1px solid var(--border-light)", paddingTop: "8px", fontSize: "11px", color: "var(--text-secondary)", display: "flex", justifyContent: "space-between" }}>
                    <span>Key: <code>{agent.key}</code></span>
                    <span>Version: {liveManifest?.version ? `v${liveManifest.version}` : "v1.3"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {activeTab === "recommendations" && analysis?.insights && analysis.insights.length > 0 && (
        <div className="agent-insights-box">
          <div className="agent-insights-title">Agent Insights & Recommendations</div>
          <ul className="agent-insights-list">
            {analysis.insights.map((insight, idx) => (
              <li key={`insight-${idx}`}>{insight}</li>
            ))}
          </ul>
        </div>
      )}

      {activeTab === "recommendations" && (
        <>
          <div className="agent-board-toolbar">
            <div className="agent-filter-controls">
              <label htmlFor="agent-recommendation-search">Find recommendations</label>
              <input
                id="agent-recommendation-search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search title, reason, or type"
              />
              <select
                id="agent-recommendation-filter"
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="settings-select"
              >
                <option value="all">All ({recommendations.length})</option>
                <option value="pending">Pending Approval ({pendingRecs.length})</option>
                <option value="missing_validation">Missing Validations</option>
                <option value="outdated_test">Outdated Selectors</option>
                <option value="healing">Self-Healing Suggestions</option>
                <option value="auto_applied">Automatically Learned</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <div className="agent-board-toolbar-meta">
              <strong>{filteredRecs.length}</strong> showing
              <span>Review is required before repository updates.</span>
            </div>
          </div>

          {filteredRecs.length === 0 ? (
            <div className="panel agent-empty-state">
              No agent recommendations in this view. Run pre-execution analysis or execute tests to generate recommendations.
            </div>
          ) : (
            <div className="agent-recommendation-layout">
              <div className="agent-recommendation-list" role="list" aria-label="Agent recommendations">
                <div className="agent-recommendation-list-header">
                  <strong>Recommendations</strong>
                  <span>{recommendations.length} total</span>
                </div>
                {filteredRecs.map((rec) => (
                  <button
                    type="button"
                    key={`rec-${rec.id}`}
                    className={`agent-recommendation-list-item ${selectedRecommendation?.id === rec.id ? "active" : ""}`}
                    onClick={() => { setSelectedId(rec.id); setReviewNotes(""); }}
                    aria-pressed={selectedRecommendation?.id === rec.id}
                  >
                    <span className="agent-recommendation-list-meta">
                      <span className={`agent-badge-pill ${rec.recommendation_type}`}>{formatRecommendationType(rec.recommendation_type)}</span>
                      <span className={`agent-status-pill ${getStatusClass(rec.status)}`}>{rec.status.toUpperCase()}</span>
                    </span>
                    <strong>{rec.title}</strong>
                    <span className="agent-recommendation-list-description">{rec.description || "No explanation provided."}</span>
                    <span className="agent-recommendation-list-counts">
                      {rec.proposed_steps?.length ?? 0} steps
                      <span aria-hidden="true">·</span>
                      {rec.proposed_checks?.length ?? 0} checks
                    </span>
                  </button>
                ))}
              </div>

              {selectedRecommendation ? (
                <article className="agent-recommendation-detail" aria-label="Selected agent recommendation">
                  <header className="agent-detail-header">
                    <div>
                      <div className="agent-detail-header-meta">
                        <span className={`agent-badge-pill ${selectedRecommendation.recommendation_type}`}>
                          {formatRecommendationType(selectedRecommendation.recommendation_type)}
                        </span>
                        <span className={`agent-status-pill ${getStatusClass(selectedRecommendation.status)}`}>
                          {selectedRecommendation.status.toUpperCase()}
                        </span>
                      </div>
                      <h2>{selectedRecommendation.title}</h2>
                      <p>Created {formatDate(selectedRecommendation.created_at)} · {selectedRecommendation.test_case_id ? `Test case #${selectedRecommendation.test_case_id}` : "Application-level recommendation"}</p>
                    </div>
                    <div className="agent-detail-header-actions">
                      {selectedRecommendation.test_case_id && onOpenTestCases ? (
                        <button type="button" className="secondary btn-sm" onClick={onOpenTestCases}>Open Test Cases</button>
                      ) : null}
                      <div className="agent-detail-navigation" aria-label="Recommendation navigation">
                        <button type="button" className="secondary btn-sm" onClick={() => selectRecommendationAt(selectedIndex - 1)} disabled={selectedIndex <= 0}>Previous</button>
                        <span>{selectedIndex + 1} of {filteredRecs.length}</span>
                        <button type="button" className="secondary btn-sm" onClick={() => selectRecommendationAt(selectedIndex + 1)} disabled={selectedIndex < 0 || selectedIndex >= filteredRecs.length - 1}>Next</button>
                      </div>
                    </div>
                  </header>

                  <div className="agent-detail-summary-grid">
                    <div><span>Recommendation</span><strong>{formatRecommendationType(selectedRecommendation.recommendation_type)}</strong></div>
                    <div><span>Proposed steps</span><strong>{selectedRecommendation.proposed_steps?.length ?? 0}</strong></div>
                    <div><span>Proposed checks</span><strong>{selectedRecommendation.proposed_checks?.length ?? 0}</strong></div>
                    <div><span>Reviewed</span><strong>{formatDate(selectedRecommendation.reviewed_at)}</strong></div>
                  </div>

                  <section className="agent-detail-section">
                    <div className="agent-detail-section-heading"><h3>Why the agent suggested this</h3><span>Analysis rationale</span></div>
                    <p>{selectedRecommendation.description || "The agent did not provide additional rationale for this recommendation."}</p>
                  </section>

                  <section className="agent-detail-section">
                    <div className="agent-detail-section-heading"><h3>Analysis context</h3><span>Current application snapshot</span></div>
                    {analysis ? (
                      <>
                        <div className="agent-analysis-context-grid">
                          <div><span>Analyzed</span><strong>{analysis.total_analyzed}</strong></div>
                          <div><span>Ready</span><strong>{analysis.ready_count}</strong></div>
                          <div><span>At risk</span><strong>{analysis.at_risk_count}</strong></div>
                          <div><span>Outdated</span><strong>{analysis.outdated_count}</strong></div>
                        </div>
                        {analysis.insights.length > 0 ? (
                          <ul className="agent-analysis-context-list">
                            {analysis.insights.map((insight, index) => <li key={`detail-insight-${index}`}>{insight}</li>)}
                          </ul>
                        ) : null}
                      </>
                    ) : <p className="muted">Run pre-execution analysis to add application-level context.</p>}
                  </section>

                  <div className="agent-detail-columns">
                    <section className="agent-detail-section">
                      <div className="agent-detail-section-heading"><h3>Proposed execution steps</h3><span>{selectedRecommendation.proposed_steps?.length ?? 0} steps</span></div>
                      {selectedRecommendation.proposed_steps?.length ? (
                        <ol className="agent-detail-step-list">
                          {selectedRecommendation.proposed_steps.map((rawStep, index) => {
                            const step = (rawStep ?? {}) as Record<string, unknown>;
                            return (
                              <li key={`detail-step-${selectedRecommendation.id}-${index}`}>
                                <span className="agent-detail-step-number">{index + 1}</span>
                                <div>
                                  <strong>{formatRecommendationType(String(step.action ?? "action"))}</strong>
                                  <code>{getStepTarget(step)}</code>
                                  {hasStepValue(step) ? <span className="agent-detail-step-value">Value: {getStepValue(step)}</span> : null}
                                </div>
                              </li>
                            );
                          })}
                        </ol>
                      ) : <p className="muted">No step changes were proposed.</p>}
                    </section>

                    <section className="agent-detail-section">
                      <div className="agent-detail-section-heading"><h3>Proposed validations</h3><span>{selectedRecommendation.proposed_checks?.length ?? 0} checks</span></div>
                      {selectedRecommendation.proposed_checks?.length ? (
                        <ul className="agent-detail-check-list">
                          {selectedRecommendation.proposed_checks.map((rawCheck, index) => {
                            const check = (rawCheck ?? {}) as Record<string, unknown>;
                            return (
                              <li key={`detail-check-${selectedRecommendation.id}-${index}`}>
                                <span className="agent-detail-check-icon">✓</span>
                                <div><strong>{formatRecommendationType(String(check.type ?? "validation"))}</strong><code>{String(check.value ?? "No target specified")}</code></div>
                              </li>
                            );
                          })}
                        </ul>
                      ) : <p className="muted">No validation changes were proposed.</p>}
                    </section>
                  </div>

                  {selectedRecommendation.status === "pending" ? (
                    <div className="agent-review-panel">
                      <label htmlFor={`agent-review-notes-${selectedRecommendation.id}`}>Review notes <span>(optional)</span></label>
                      <textarea
                        id={`agent-review-notes-${selectedRecommendation.id}`}
                        value={reviewNotes}
                        onChange={(event) => setReviewNotes(event.target.value)}
                        placeholder="Add context for the next reviewer or explain the decision."
                        rows={3}
                      />
                      <div className="agent-review-actions">
                        <button type="button" className="btn btn-emerald" onClick={() => void handleReviewClick(selectedRecommendation.id, "approve")} disabled={reviewingId === selectedRecommendation.id}>
                          {reviewingId === selectedRecommendation.id ? "Saving..." : "Approve & Apply"}
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={() => void handleReviewClick(selectedRecommendation.id, "reject")} disabled={reviewingId === selectedRecommendation.id}>Reject recommendation</button>
                      </div>
                    </div>
                  ) : (
                    <div className="agent-reviewed-panel">This recommendation was {selectedRecommendation.status} on {formatDate(selectedRecommendation.reviewed_at)}.</div>
                  )}
                </article>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}
