import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "danger" | "neutral";

export function AppCard({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`panel cc-card ${className}`.trim()}>{children}</div>;
}

export function SectionHeader({
  title,
  meta,
  actions,
}: {
  kicker: string;
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="section-heading cc-section-heading">
      <div>
        <h2>{title}</h2>
      </div>
      <div className="cc-section-meta">
        {meta && <span className="muted">{meta}</span>}
        {actions}
      </div>
    </div>
  );
}

export function StatTile({
  icon,
  label,
  value,
  delta,
  tone = "info",
}: {
  icon: string;
  label: string;
  value: string;
  delta?: string;
  tone?: Tone;
}) {
  return (
    <article className={`designer-stat-card cc-stat-tile ${tone}`}>
      <span className="designer-stat-icon">{icon}</span>
      <div>
        <span className="designer-stat-label">{label}</span>
        <strong>{value}</strong>
        {delta ? <small>{delta}</small> : null}
      </div>
    </article>
  );
}

export function ActionBar({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`cc-action-bar ${className}`.trim()}>{children}</div>;
}

export function TrendBlock({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <AppCard className="designer-card cc-trend-block">
      <SectionHeader kicker={kicker} title={title} />
      {children}
    </AppCard>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="cc-empty-state">
      <p className="muted">{message}</p>
    </div>
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
  const color =
    tone === "success"
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
        style={{
          background: `conic-gradient(${color} 0 ${normalizedValue}%, var(--bg-layer-2) ${normalizedValue}% 100%)`,
        }}
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

export type DistributionItem = {
  label: string;
  value: number;
  tone: "info" | "success" | "warning" | "danger" | "neutral";
};

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
            <strong>
              {item.value}
              {percent ? "%" : ""}
            </strong>
          </div>
          <div className="v3-distribution-track">
            <div
              className={`v3-distribution-fill tone-${item.tone}`}
              style={{ width: `${Math.max(Math.round((item.value / maxValue) * 100), item.value ? 6 : 0)}%` }}
            />
          </div>
        </div>
      ))}
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
  const points = values
    .map((value, index) => {
      const x = padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
      const y = height - padding - (value / max) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return <polyline className={className} points={points} />;
}
