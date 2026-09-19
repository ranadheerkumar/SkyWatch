"use client";

import React, { useState, useEffect, useCallback } from "react";
import { apiFetch } from "../lib/api";

interface EndpointGroupMetric {
  requests: number;
  errors: number;
  rate_limited: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
}

interface ObservabilityMetricsResponse {
  status?: string;
  message?: string;
  total_requests: number;
  total_errors: number;
  rate_limited_requests: number;
  groups?: Record<string, EndpointGroupMetric>;
  rate_limiter_enabled?: boolean;
  active_buckets?: number;
}

interface SelfLearningMetricsResponse {
  application_id: number;
  total_learned_locators: number;
  total_locator_hits: number;
  healed_adaptations_retained: number;
  monitored_route_profiles: number;
  average_route_load_ms: number;
  learning_engine_status: string;
}

interface ObservabilityMetricsCardProps {
  token: string | null;
  appId?: number | null;
  appName?: string | null;
}

export default function ObservabilityMetricsCard({
  token,
  appId,
  appName,
}: ObservabilityMetricsCardProps) {
  const [loading, setLoading] = useState(false);
  const [metrics, setMetrics] = useState<ObservabilityMetricsResponse | null>(null);
  const [learningMetrics, setLearningMetrics] = useState<SelfLearningMetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<ObservabilityMetricsResponse>(
        "/api/v1/observability/metrics",
        {},
        token
      );
      setMetrics(res);

      if (appId) {
        try {
          const learnRes = await apiFetch<SelfLearningMetricsResponse>(
            `/api/v1/ai-generation/self-learning/${appId}`,
            {},
            token
          );
          setLearningMetrics(learnRes);
        } catch {
          // Self learning might be empty for new apps, handle gracefully
          setLearningMetrics(null);
        }
      }
      setLastRefreshed(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load observability metrics");
    } finally {
      setLoading(false);
    }
  }, [token, appId]);

  useEffect(() => {
    void fetchMetrics();
  }, [fetchMetrics]);

  const errorRate =
    metrics && metrics.total_requests > 0
      ? ((metrics.total_errors / metrics.total_requests) * 100).toFixed(1)
      : "0.0";

  return (
    <div
      className="panel"
      style={{
        background: "linear-gradient(135deg, rgba(24, 24, 27, 0.85) 0%, rgba(15, 15, 18, 0.95) 100%)",
        border: "1px solid rgba(63, 63, 70, 0.4)",
        borderRadius: "12px",
        padding: "20px",
        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.4)",
        marginBottom: "20px",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "16px",
          paddingBottom: "12px",
          borderBottom: "1px solid rgba(63, 63, 70, 0.3)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "20px" }}>📡</span>
          <div>
            <h3
              style={{
                margin: 0,
                fontSize: "16px",
                fontWeight: 700,
                letterSpacing: "-0.01em",
                color: "#f4f4f5",
              }}
            >
              System Observability & Autonomous Self-Learning Telemetry
            </h3>
            <span style={{ fontSize: "12px", color: "#a1a1aa" }}>
              Real-time API gateway throughput, token bucket rates, and adaptive locator memory
              {appName ? ` for ${appName}` : ""}
            </span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {lastRefreshed && (
            <span style={{ fontSize: "11px", color: "#71717a" }}>
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
          )}
          <button
            type="button"
            onClick={() => void fetchMetrics()}
            disabled={loading}
            className="secondary btn-sm"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              padding: "6px 12px",
            }}
          >
            <span style={{ display: "inline-block", animation: loading ? "spin 1s linear infinite" : "none" }}>
              🔄
            </span>
            {loading ? "Refreshing..." : "Refresh Telemetry"}
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: "10px 14px",
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "8px",
            color: "#fca5a5",
            fontSize: "13px",
            marginBottom: "14px",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* KPI Tiles */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "12px",
          marginBottom: "18px",
        }}
      >
        <div
          style={{
            background: "rgba(39, 39, 42, 0.5)",
            border: "1px solid rgba(63, 63, 70, 0.3)",
            borderRadius: "8px",
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#a1a1aa", textTransform: "uppercase", fontWeight: 600 }}>
            API Throughput
          </div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: "#fafafa", marginTop: "4px" }}>
            {metrics?.total_requests ?? 0}
            <span style={{ fontSize: "11px", fontWeight: 400, color: "#a1a1aa", marginLeft: "4px" }}>
              reqs
            </span>
          </div>
          <div style={{ fontSize: "11px", color: "#71717a", marginTop: "2px" }}>
            Live tracked HTTP calls
          </div>
        </div>

        <div
          style={{
            background: "rgba(39, 39, 42, 0.5)",
            border: "1px solid rgba(63, 63, 70, 0.3)",
            borderRadius: "8px",
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#a1a1aa", textTransform: "uppercase", fontWeight: 600 }}>
            Error Rate
          </div>
          <div
            style={{
              fontSize: "22px",
              fontWeight: 800,
              color: Number(errorRate) > 5 ? "#ef4444" : "#10b981",
              marginTop: "4px",
            }}
          >
            {errorRate}%
          </div>
          <div style={{ fontSize: "11px", color: "#71717a", marginTop: "2px" }}>
            {metrics?.total_errors ?? 0} total error responses
          </div>
        </div>

        <div
          style={{
            background: "rgba(39, 39, 42, 0.5)",
            border: "1px solid rgba(63, 63, 70, 0.3)",
            borderRadius: "8px",
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#a1a1aa", textTransform: "uppercase", fontWeight: 600 }}>
            Rate Limiter Status
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "6px" }}>
            <span
              style={{
                display: "inline-block",
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: metrics?.rate_limiter_enabled ? "#10b981" : "#eab308",
              }}
            />
            <span style={{ fontSize: "14px", fontWeight: 700, color: "#fafafa" }}>
              {metrics?.rate_limiter_enabled ? "Active Enforcement" : "Monitoring Mode"}
            </span>
          </div>
          <div style={{ fontSize: "11px", color: "#71717a", marginTop: "4px" }}>
            {metrics?.active_buckets ?? 0} active token buckets
          </div>
        </div>

        <div
          style={{
            background: "rgba(39, 39, 42, 0.5)",
            border: "1px solid rgba(63, 63, 70, 0.3)",
            borderRadius: "8px",
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#a1a1aa", textTransform: "uppercase", fontWeight: 600 }}>
            Rate Limited Calls
          </div>
          <div
            style={{
              fontSize: "22px",
              fontWeight: 800,
              color: (metrics?.rate_limited_requests ?? 0) > 0 ? "#f97316" : "#fafafa",
              marginTop: "4px",
            }}
          >
            {metrics?.rate_limited_requests ?? 0}
          </div>
          <div style={{ fontSize: "11px", color: "#71717a", marginTop: "2px" }}>
            Throttled 429 requests
          </div>
        </div>

        {learningMetrics && (
          <div
            style={{
              background: "rgba(39, 39, 42, 0.5)",
              border: "1px solid rgba(139, 92, 246, 0.3)",
              borderRadius: "8px",
              padding: "12px 14px",
            }}
          >
            <div style={{ fontSize: "11px", color: "#a78bfa", textTransform: "uppercase", fontWeight: 600 }}>
              AI Learned Locators
            </div>
            <div style={{ fontSize: "22px", fontWeight: 800, color: "#c4b5fd", marginTop: "4px" }}>
              {learningMetrics.total_learned_locators}
              <span style={{ fontSize: "11px", fontWeight: 400, color: "#a78bfa", marginLeft: "4px" }}>
                ({learningMetrics.total_locator_hits} hits)
              </span>
            </div>
            <div style={{ fontSize: "11px", color: "#71717a", marginTop: "2px" }}>
              {learningMetrics.healed_adaptations_retained} self-healed retained
            </div>
          </div>
        )}
      </div>

      {/* Endpoint Groups Breakdown (Collapsible) */}
      {metrics?.groups && Object.keys(metrics.groups).length > 0 && (
        <details style={{ marginTop: "14px" }}>
          <summary
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "#a1a1aa",
              cursor: "pointer",
              userSelect: "none",
              padding: "4px 0",
              outline: "none",
            }}
          >
            📊 View Service Route Latencies &amp; Traffic Distribution ({Object.keys(metrics.groups).length} routes)
          </summary>
          <div style={{ overflowX: "auto", marginTop: "10px" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "12px",
                textAlign: "left",
              }}
            >
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(63, 63, 70, 0.4)", color: "#71717a" }}>
                  <th style={{ padding: "6px 8px" }}>Endpoint Group</th>
                  <th style={{ padding: "6px 8px" }}>Requests</th>
                  <th style={{ padding: "6px 8px" }}>Avg Latency</th>
                  <th style={{ padding: "6px 8px" }}>P95 Latency</th>
                  <th style={{ padding: "6px 8px" }}>Errors</th>
                  <th style={{ padding: "6px 8px" }}>Throttled</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.groups).map(([groupKey, data]) => (
                  <tr
                    key={groupKey}
                    style={{
                      borderBottom: "1px solid rgba(63, 63, 70, 0.2)",
                      color: "#d4d4d8",
                    }}
                  >
                    <td style={{ padding: "6px 8px", fontWeight: 600 }}>
                      <span
                        style={{
                          background: "rgba(63, 63, 70, 0.4)",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontFamily: "monospace",
                        }}
                      >
                        {groupKey}
                      </span>
                    </td>
                    <td style={{ padding: "6px 8px" }}>{data.requests}</td>
                    <td style={{ padding: "6px 8px" }}>
                      {data.avg_latency_ms ? `${data.avg_latency_ms.toFixed(1)} ms` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      {data.p95_latency_ms ? `${data.p95_latency_ms.toFixed(1)} ms` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: data.errors > 0 ? "#ef4444" : "inherit" }}>
                      {data.errors}
                    </td>
                    <td style={{ padding: "6px 8px", color: data.rate_limited > 0 ? "#f97316" : "inherit" }}>
                      {data.rate_limited}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
