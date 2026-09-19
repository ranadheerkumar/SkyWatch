"use client";

import React, { Component, type ErrorInfo, type ReactNode } from "react";
import { logger } from "../lib/logger";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  correlationId: string;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: "",
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    const correlationId = `err-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return {
      hasError: true,
      error,
      correlationId,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const correlationId = this.state.correlationId || `err-${Date.now()}`;
    logger.error("Unhandled React component error caught by ErrorBoundary", {
      correlationId,
      error: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
    this.setState({ errorInfo });
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: "",
    });
    this.props.onReset?.();
  };

  handleReload = (): void => {
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  };

  render(): ReactNode {
    if (this.state.hasError) {
      const { error, errorInfo, correlationId } = this.state;
      const title = this.props.fallbackTitle ?? "Application Encountered an Unexpected Issue";

      return (
        <div
          style={{
            minHeight: "400px",
            padding: "32px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-page, #f8fafc)",
          }}
        >
          <div
            className="panel"
            style={{
              maxWidth: "680px",
              width: "100%",
              padding: "28px",
              border: "1px solid var(--border-medium, #cbd5e1)",
              borderRadius: "var(--radius-lg, 12px)",
              background: "var(--bg-surface, #ffffff)",
              boxShadow: "var(--shadow-md, 0 4px 14px rgba(0,0,0,0.08))",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
            }}
            role="alert"
            aria-live="assertive"
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div
                style={{
                  width: "42px",
                  height: "42px",
                  borderRadius: "50%",
                  background: "rgba(220, 38, 38, 0.12)",
                  color: "#dc2626",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "20px",
                  fontWeight: 800,
                }}
              >
                ⚠
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                  {title}
                </h2>
                <small className="muted" style={{ fontSize: "12px" }}>
                  Diagnostic Correlation ID: <code style={{ color: "var(--brand-primary, #b5121b)" }}>{correlationId}</code>
                </small>
              </div>
            </div>

            <p style={{ margin: 0, fontSize: "14px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              The workspace caught an unhandled component error. Your data and session context remain intact. You can recover the session or refresh the view safely.
            </p>

            {error?.message && (
              <div
                style={{
                  padding: "12px 14px",
                  background: "var(--bg-layer-2, #f1f5f9)",
                  borderRadius: "var(--radius-md, 8px)",
                  border: "1px solid var(--border-light, #e2e8f0)",
                  fontFamily: "var(--font-code, monospace)",
                  fontSize: "12px",
                  color: "#b91c1c",
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                }}
              >
                {error.name}: {error.message}
              </div>
            )}

            {process.env.NODE_ENV !== "production" && errorInfo?.componentStack && (
              <details style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>Component Stack Details</summary>
                <pre style={{ margin: "8px 0 0", padding: "8px", background: "#0f172a", color: "#f8fafc", borderRadius: "6px", overflowX: "auto" }}>
                  {errorInfo.componentStack}
                </pre>
              </details>
            )}

            <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "8px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="secondary"
                onClick={this.handleReload}
              >
                ↻ Reload Page
              </button>
              <button
                type="button"
                className="primary"
                onClick={this.handleReset}
              >
                ⚡ Recover Session
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
