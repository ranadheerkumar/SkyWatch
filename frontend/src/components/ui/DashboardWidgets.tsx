"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import ApplicationCapture from "../ApplicationCapture";
import { EmptyState } from "../commandCenter";
import SortControl from "../SortControl";
import type { SortOption } from "../SortControl";
import { apiFetchBlob } from "../../lib/api";
import { formatDuration } from "../../lib/formatDuration";
import type { DistributionItem } from "../../lib/distributions";
import { getStatusMeta } from "../../lib/testCaseHelpers";
import type { ExecutionResult } from "../../types";

export function renderStatusChip(status?: string) {
  const meta = getStatusMeta(status);
  return (
    <span className={`status-chip status-${meta.tone}`}>
      <span className="status-chip-icon">{meta.icon}</span>
      <span>{meta.label}</span>
    </span>
  );
}

export function renderWorkflowStatusChip(state: "completed" | "inProgress" | "queued" | "attention") {
  const meta = state === "completed"
    ? { label: "Completed", icon: "OK", tone: "success" }
    : state === "inProgress"
      ? { label: "In Progress", icon: "IP", tone: "info" }
      : state === "attention"
        ? { label: "Attention", icon: "ER", tone: "danger" }
        : { label: "Queued", icon: "DR", tone: "warning" };
  return (
    <span className={`status-chip status-${meta.tone}`}>
      <span className="status-chip-icon">{meta.icon}</span>
      <span>{meta.label}</span>
    </span>
  );
}

export function PageTitle({
  title,
  action,
  onAction,
  actionDisabled = false,
}: {
  title: string;
  kicker: string;
  action?: string;
  onAction?: (savedApplicationName?: string) => void;
  actionDisabled?: boolean;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{title}</h1>
        </div>
        {action && !action.includes("Add new application") ? (
          <button className="primary btn-primary" onClick={() => onAction?.()} disabled={actionDisabled}>
            {action}
          </button>
        ) : null}
      </div>
      {action?.includes("Add new application") && onAction ? (
        <ApplicationCapture onSaved={(savedApplicationName) => onAction(savedApplicationName)} />
      ) : null}
    </>
  );
}

export function InteractiveKpiCard({
  className,
  label,
  value,
  detail,
  onClick,
}: {
  className: string;
  label: string;
  value: string | number;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`panel interactive-kpi-card ${className}`}
      onClick={onClick}
      aria-label={`${label}: ${value}. ${detail}`}
      title={`Open ${label}`}
    >
      <span className="kpi-card-label">{label}</span>
      <strong>{value}</strong>
      <small className="kpi-card-detail">{detail}</small>
    </button>
  );
}

export function ProgressRing({
  label,
  value,
  tone = "info",
  detail,
}: {
  label: string;
  value: number;
  tone?: "success" | "warning" | "danger" | "info";
  detail?: string;
}) {
  const normalizedValue = Math.max(0, Math.min(100, Number.isFinite(value) ? Math.round(value) : 0));
  const color = tone === "success"
    ? "var(--success)"
    : tone === "warning"
      ? "var(--warning)"
      : tone === "danger"
        ? "var(--error)"
        : "var(--info)";

  return (
    <article className={`progress-ring-card tone-${tone}`}>
      <div
        className="progress-ring"
        role="img"
        aria-label={`${label}: ${normalizedValue}%`}
        style={{ background: `conic-gradient(${color} 0 ${normalizedValue}%, var(--bg-layer-2) ${normalizedValue}% 100%)` }}
      >
        <div className="progress-ring-hole">
          <strong>{normalizedValue}%</strong>
          <span>{label}</span>
        </div>
      </div>
      {detail ? <p className="muted">{detail}</p> : null}
    </article>
  );
}

export function TableScroll({ children, containedScroll }: { children: ReactNode; containedScroll: boolean }) {
  const topScrollRef = useRef<HTMLDivElement>(null);
  const bottomScrollRef = useRef<HTMLDivElement>(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [hasHorizontalOverflow, setHasHorizontalOverflow] = useState(false);

  useEffect(() => {
    const updateScrollMetrics = () => {
      const scrollElement = bottomScrollRef.current;
      if (!scrollElement) return;
      const nextScrollWidth = scrollElement.scrollWidth;
      setScrollWidth(nextScrollWidth);
      setHasHorizontalOverflow(nextScrollWidth > scrollElement.clientWidth + 1);
    };

    updateScrollMetrics();
    const resizeObserver = typeof ResizeObserver !== "undefined" ? new ResizeObserver(updateScrollMetrics) : null;
    if (bottomScrollRef.current) {
      resizeObserver?.observe(bottomScrollRef.current);
      if (bottomScrollRef.current.firstElementChild) resizeObserver?.observe(bottomScrollRef.current.firstElementChild);
    }
    window.addEventListener("resize", updateScrollMetrics);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateScrollMetrics);
    };
  }, []);

  const syncScrollPosition = (source: HTMLDivElement | null, target: HTMLDivElement | null) => {
    if (!source || !target || source.scrollLeft === target.scrollLeft) return;
    target.scrollLeft = source.scrollLeft;
  };

  return (
    <div className="table-scroll-stack">
      {hasHorizontalOverflow ? (
        <div
          ref={topScrollRef}
          className="table-scroll table-scroll-top"
          aria-hidden="true"
          onScroll={() => syncScrollPosition(topScrollRef.current, bottomScrollRef.current)}
        >
          <div style={{ width: `${scrollWidth}px` }} />
        </div>
      ) : null}
      <div
        ref={bottomScrollRef}
        className={`table-scroll ${containedScroll ? "table-scroll-contained" : ""}`.trim()}
        onScroll={() => syncScrollPosition(bottomScrollRef.current, topScrollRef.current)}
      >
        {children}
      </div>
    </div>
  );
}

export function Table({
  title,
  meta,
  children,
  containedScroll = true,
  sortValue,
  sortOptions,
  onSortChange,
}: {
  title: string;
  meta: string;
  children: ReactNode;
  containedScroll?: boolean;
  sortValue?: string;
  sortOptions?: SortOption[];
  onSortChange?: (value: string) => void;
}) {
  return (
    <div className="panel table-panel workspace-table-surface">
      <div className="table-title">
        <div>
          <h3>{title}</h3>
        </div>
        <div className="table-title-actions">
          {sortOptions && sortValue !== undefined && onSortChange ? (
            <SortControl value={sortValue} options={sortOptions} onChange={onSortChange} />
          ) : null}
          <span className="muted">{meta}</span>
        </div>
      </div>
      <TableScroll containedScroll={containedScroll}>{children}</TableScroll>
    </div>
  );
}

export function TrendLine({
  values,
  className,
}: {
  values: number[];
  className: string;
}) {
  const width = 360;
  const height = 140;
  const padding = 10;
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
    const y = height - padding - ((value / max) * (height - padding * 2));
    return `${x},${y}`;
  }).join(" ");

  return <polyline className={className} points={points} />;
}

export function DistributionBars({ items, percent = false }: { items: DistributionItem[]; percent?: boolean }) {
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  const hasData = items.some((item) => item.value > 0);
  if (!hasData) return <EmptyState message="No records to visualize yet." />;
  return (
    <div className="v3-distribution-bars">
      {items.map((item) => (
        <div className="v3-distribution-row" key={`${item.label}-${item.tone}`}>
          <div className="v3-distribution-meta">
            <span>{item.label}</span>
            <strong>{item.value}{percent ? "%" : ""}</strong>
          </div>
          <div className="v3-distribution-track">
            <div className={`v3-distribution-fill tone-${item.tone}`} style={{ width: `${Math.max(Math.round((item.value / maxValue) * 100), item.value ? 6 : 0)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ExecutionArtifactPreview({
  artifacts,
  token,
  runId,
  showHeading = true,
  headingTitle = "Execution evidence",
  headingDescription = "Loaded securely from the test run",
}: {
  artifacts: Array<{ type: "screenshot" | "video" | "trace"; path: string; label: string; step_index?: number | null }>;
  token: string;
  runId: string;
  showHeading?: boolean;
  headingTitle?: string;
  headingDescription?: string;
}) {
  const [artifactUrls, setArtifactUrls] = useState<Record<number, string>>({});
  const [artifactErrors, setArtifactErrors] = useState<Record<number, string>>({});
  const artifactSignature = artifacts.map((artifact) => `${artifact.type}:${artifact.path}`).join("|");

  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];
    setArtifactUrls({});
    setArtifactErrors({});
    if (!token || !artifacts.length) return () => undefined;

    const loadArtifacts = async () => {
      const loaded = await Promise.all(artifacts.map(async (artifact, index) => {
        const filename = artifact.path.split(/[\\/]/).pop() ?? "";
        if (!filename) return { index, url: "", error: "Artifact filename is unavailable." };
        try {
          const blob = await apiFetchBlob(`/api/v1/evidence/file/${encodeURIComponent(filename)}?run_id=${encodeURIComponent(runId)}`, token);
          const url = URL.createObjectURL(blob);
          objectUrls.push(url);
          return { index, url, error: "" };
        } catch (error) {
          return { index, url: "", error: error instanceof Error ? error.message : "Unable to load artifact." };
        }
      }));
      if (cancelled) return;
      setArtifactUrls(Object.fromEntries(loaded.filter((item) => item.url).map((item) => [item.index, item.url])));
      setArtifactErrors(Object.fromEntries(loaded.filter((item) => item.error).map((item) => [item.index, item.error])));
    };
    void loadArtifacts();

    return () => {
      cancelled = true;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [artifactSignature, runId, token]);

  if (!artifacts.length) return null;
  return (
    <section className="execution-artifacts" aria-label="Execution evidence">
      {showHeading ? (
        <div className="execution-artifacts-heading">
          <div>
            <span className="detail-label">{headingTitle}</span>
            <strong>{artifacts.length} captured artifact{artifacts.length === 1 ? "" : "s"}</strong>
          </div>
          <span className="muted">{headingDescription}</span>
        </div>
      ) : null}
      <div className="execution-artifact-grid">
        {artifacts.map((artifact, index) => {
          const artifactUrl = artifactUrls[index];
          const artifactError = artifactErrors[index];
          return (
            <article className="execution-artifact-card" key={`${runId}-artifact-preview-${index}`}>
              <div className="execution-artifact-card-head">
                <strong>{artifact.label}</strong>
                <span>{artifact.type}</span>
              </div>
              {artifactUrl && artifact.type === "screenshot" ? (
                <img src={artifactUrl} alt={artifact.label} className="execution-artifact-image" />
              ) : null}
              {artifactUrl && artifact.type === "video" ? (
                <video className="execution-artifact-video" controls preload="metadata" src={artifactUrl} />
              ) : null}
              {artifact.type === "trace" && artifactUrl ? <p className="muted">Playwright trace is ready to download.</p> : null}
              {!artifactUrl && !artifactError ? <p className="muted">Loading artifact...</p> : null}
              {artifactError ? <p className="fail">{artifactError}</p> : null}
              {artifactUrl ? (
                <a className="execution-artifact-download" href={artifactUrl} download={artifact.path.split(/[\\/]/).pop() ?? "execution-artifact"}>
                  Download {artifact.type}
                </a>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function ExecutionStepEvidence({
  steps,
  artifacts,
  token,
  runId,
}: {
  steps: Array<{ index: number; action: string; selector: string; passed: boolean; message: string; durationMs: number; state: string }>;
  artifacts: NonNullable<ExecutionResult["step_artifacts"]>;
  token: string;
  runId: string;
}) {
  const screenshotByStep = new Map(
    artifacts
      .filter((artifact) => artifact.type === "screenshot" && artifact.step_index)
      .map((artifact) => [artifact.step_index as number, artifact]),
  );

  return (
    <section className="execution-step-evidence" aria-label="Step level evidence">
      <div className="execution-step-evidence-heading">
        <div>
          <span className="detail-label">Step evidence</span>
          <strong>Screenshot after each action</strong>
        </div>
        <span className="muted">Collapsed by default. Expand a step to inspect its captured state.</span>
      </div>
      <div className="execution-step-evidence-list">
        {steps.length ? steps.map((step) => {
          const screenshot = screenshotByStep.get(step.index);
          const stepState = step.state === "passed" ? "Passed" : step.state === "failed" ? "Failed" : "Pending";
          return (
            <details className="execution-step-evidence-item" key={`${runId}-step-evidence-${step.index}`}>
              <summary>
                <span className="execution-step-evidence-number">Step {step.index}</span>
                <span className="execution-step-evidence-action">{step.action}</span>
                <span className={`execution-step-evidence-status ${step.state}`}>{stepState}</span>
                <span className="execution-step-evidence-capture">{screenshot ? "Screenshot ready" : "No screenshot"}</span>
              </summary>
              <div className="execution-step-evidence-body">
                <div className="execution-step-evidence-copy">
                  <span className="detail-label">Selector</span>
                  <strong>{step.selector || "No selector"}</strong>
                  <p>{step.message}</p>
                  {step.durationMs ? <span className="muted">Duration {formatDuration(step.durationMs)}</span> : null}
                </div>
                {screenshot ? (
                  <ExecutionArtifactPreview
                    artifacts={[screenshot]}
                    token={token}
                    runId={runId}
                    showHeading={false}
                  />
                ) : (
                  <p className="muted execution-step-evidence-empty">This run predates step-level capture or the screenshot could not be written.</p>
                )}
              </div>
            </details>
          );
        }) : <p className="muted">No execution steps were recorded.</p>}
      </div>
    </section>
  );
}
