"use client";

import { useEffect, useMemo, useState } from "react";

type TestStepEditorProps = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
};

function normalizeStep(value: string) {
  return value.replace(/^\s*\d+[\).:\-\s]+/, "");
}

export function parseTestSteps(value: string) {
  if (!value) return [];
  return value
    .split(/\r?\n/)
    .map(normalizeStep)
    .filter((s) => s.trim().length > 0);
}

export function serializeTestSteps(steps: string[]) {
  return steps
    .filter((step) => step.trim().length > 0)
    .map((step, index) => `${index + 1}. ${step.trim()}`)
    .join("\n");
}

function inferStepActionTag(stepText: string): { label: string; color: string; bg: string } {
  const lower = stepText.toLowerCase();
  if (lower.startsWith("navigate") || lower.startsWith("open") || lower.startsWith("goto") || lower.includes("http")) {
    return { label: "Navigate", color: "#2563eb", bg: "#eff6ff" };
  }
  if (lower.startsWith("click") || lower.startsWith("tap") || lower.startsWith("press") || lower.startsWith("submit")) {
    return { label: "Click", color: "#16a34a", bg: "#f0fdf4" };
  }
  if (lower.startsWith("enter") || lower.startsWith("type") || lower.startsWith("fill") || lower.startsWith("input")) {
    return { label: "Type", color: "#9333ea", bg: "#faf5ff" };
  }
  if (lower.startsWith("select") || lower.startsWith("choose")) {
    return { label: "Select", color: "#d97706", bg: "#fffbeb" };
  }
  if (lower.startsWith("check") || lower.startsWith("uncheck")) {
    return { label: "Toggle", color: "#0891b2", bg: "#ecfeff" };
  }
  if (lower.startsWith("verify") || lower.startsWith("assert") || lower.startsWith("validate") || lower.startsWith("confirm")) {
    return { label: "Assert", color: "#dc2626", bg: "#fef2f2" };
  }
  return { label: "Action", color: "#475569", bg: "#f1f5f9" };
}

function renderFormattedStepText(text: string) {
  if (!text) return <span className="muted">Empty step</span>;
  const parts = text.split(/(\{\{[^}]+\}\})/g);
  return (
    <span style={{ color: "#1e293b", fontSize: "13px", lineHeight: "1.5" }}>
      {parts.map((part, i) => {
        if (part.startsWith("{{") && part.endsWith("}}")) {
          return (
            <code
              key={i}
              style={{
                background: "rgba(37, 99, 235, 0.12)",
                color: "#1d4ed8",
                border: "1px solid rgba(37, 99, 235, 0.25)",
                padding: "1px 5px",
                borderRadius: "4px",
                fontWeight: 700,
                fontSize: "12px",
                margin: "0 2px",
                fontFamily: "var(--font-code, monospace)",
              }}
            >
              {part}
            </code>
          );
        }
        return part;
      })}
    </span>
  );
}

export default function TestStepEditor({ value, onChange, disabled = false }: TestStepEditorProps) {
  const parsedSteps = useMemo(() => {
    const parsed = parseTestSteps(value);
    return parsed.length ? parsed : [""];
  }, [value]);

  const [localSteps, setLocalSteps] = useState<string[]>(parsedSteps);

  useEffect(() => {
    const serializedLocal = serializeTestSteps(localSteps);
    const serializedIncoming = serializeTestSteps(parseTestSteps(value));
    if (serializedLocal !== serializedIncoming) {
      setLocalSteps(parseTestSteps(value).length ? parseTestSteps(value) : [""]);
    }
  }, [value]);

  const updateStep = (index: number, nextValue: string) => {
    const nextSteps = [...localSteps];
    nextSteps[index] = nextValue.replace(/\r?\n/g, " ");
    setLocalSteps(nextSteps);
    onChange(serializeTestSteps(nextSteps));
  };

  const addStep = (prefix = "") => {
    const nextSteps = [...localSteps, prefix];
    setLocalSteps(nextSteps);
    onChange(serializeTestSteps(nextSteps));
  };

  const insertStepAfter = (index: number) => {
    const nextSteps = [...localSteps.slice(0, index + 1), "", ...localSteps.slice(index + 1)];
    setLocalSteps(nextSteps);
    onChange(serializeTestSteps(nextSteps));
  };

  const moveStep = (index: number, direction: -1 | 1) => {
    const targetIdx = index + direction;
    if (targetIdx < 0 || targetIdx >= localSteps.length) return;
    const nextSteps = [...localSteps];
    const temp = nextSteps[index];
    nextSteps[index] = nextSteps[targetIdx];
    nextSteps[targetIdx] = temp;
    setLocalSteps(nextSteps);
    onChange(serializeTestSteps(nextSteps));
  };

  const removeStep = (index: number) => {
    const nextSteps = localSteps.filter((_, stepIndex) => stepIndex !== index);
    const finalSteps = nextSteps.length ? nextSteps : [""];
    setLocalSteps(finalSteps);
    onChange(serializeTestSteps(finalSteps));
  };

  return (
    <div className="test-step-editor" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div className="test-step-editor-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", flexWrap: "wrap" }}>
        <div>
          <label htmlFor="test-step-editor-first" style={{ fontWeight: 700, fontSize: "14px" }}>
            Step Actions ({localSteps.filter((s) => s.trim().length > 0).length}) <span style={{ color: "var(--danger, #ef4444)" }}>*</span>
          </label>
          <p className="muted" style={{ fontSize: "12px", margin: "2px 0 0" }}>
            Sequential browser actions. Use placeholders like <code style={{ fontSize: "11px" }}>{"{{email}}"}</code> or <code style={{ fontSize: "11px" }}>{"{{login_password}}"}</code> for dynamic test data.
          </p>
        </div>

        {/* Action Insertion Shortcuts */}
        {!disabled && (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
            <button type="button" className="filter-preset-chip" style={{ fontSize: "11px", padding: "3px 8px" }} onClick={() => addStep("Navigate to ")}>
              🌐 + Navigate
            </button>
            <button type="button" className="filter-preset-chip" style={{ fontSize: "11px", padding: "3px 8px" }} onClick={() => addStep("Click button ")}>
              🖱️ + Click
            </button>
            <button type="button" className="filter-preset-chip" style={{ fontSize: "11px", padding: "3px 8px" }} onClick={() => addStep("Enter \"value\" into ")}>
              ⌨️ + Type
            </button>
            <button type="button" className="filter-preset-chip" style={{ fontSize: "11px", padding: "3px 8px" }} onClick={() => addStep("Verify that ")}>
              🔍 + Assert
            </button>
            <button type="button" className="primary btn-sm" onClick={() => addStep("")}>
              + Add Step
            </button>
          </div>
        )}
      </div>

      {localSteps.length ? (
        <div className="test-step-list" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {localSteps.map((step, index) => {
            const actionTag = inferStepActionTag(step);
            if (disabled) {
              return (
                <div
                  className="test-step-view-row"
                  key={`test-step-view-${index}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto 1fr",
                    gap: "12px",
                    alignItems: "center",
                    background: "#ffffff",
                    padding: "10px 14px",
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.03)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: "120px" }}>
                    <span
                      style={{
                        fontFamily: "var(--font-code, monospace)",
                        fontWeight: 800,
                        fontSize: "12px",
                        color: "#334155",
                        background: "#e2e8f0",
                        borderRadius: "999px",
                        padding: "2px 8px",
                      }}
                    >
                      #{index + 1}
                    </span>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        color: actionTag.color,
                        background: actionTag.bg,
                        border: `1px solid ${actionTag.color}33`,
                        padding: "2px 8px",
                        borderRadius: "6px",
                        letterSpacing: "0.03em",
                      }}
                    >
                      {actionTag.label}
                    </span>
                  </div>
                  <div>
                    {renderFormattedStepText(step)}
                  </div>
                </div>
              );
            }

            return (
              <div
                className="test-step-row"
                key={`test-step-${index}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  gap: "10px",
                  alignItems: "center",
                  background: "var(--bg-layer-2, #f8fafc)",
                  padding: "10px 14px",
                  border: "1px solid var(--border-light, #e2e8f0)",
                  borderRadius: "var(--radius-md, 8px)",
                }}
              >
                {/* Step Number & Action Badge */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", minWidth: "60px" }}>
                  <span
                    style={{
                      fontFamily: "var(--font-code, monospace)",
                      fontWeight: 800,
                      fontSize: "12px",
                      color: "#334155",
                      background: "#e2e8f0",
                      borderRadius: "999px",
                      padding: "2px 8px",
                    }}
                  >
                    #{index + 1}
                  </span>
                  <span
                    style={{
                      fontSize: "10px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: actionTag.color,
                      background: actionTag.bg,
                      padding: "1px 4px",
                      borderRadius: "4px",
                    }}
                  >
                    {actionTag.label}
                  </span>
                </div>

                {/* Step Description Input */}
                <input
                  id={index === 0 ? "test-step-editor-first" : `test-step-editor-${index + 1}`}
                  type="text"
                  value={step}
                  onChange={(event) => updateStep(index, event.target.value)}
                  disabled={disabled}
                  aria-label={`Step ${index + 1}`}
                  placeholder="e.g. Click button 'Submit', Navigate to /dashboard, Enter '{{login_email}}' into username"
                  style={{
                    width: "100%",
                    fontSize: "13px",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm, 6px)",
                    border: "1px solid var(--border-light, #cbd5e1)",
                    background: "#ffffff",
                  }}
                />

                {/* Step Actions: Move Up / Move Down / Insert / Delete */}
                <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                  <button
                    type="button"
                    className="row-action-btn"
                    onClick={() => moveStep(index, -1)}
                    disabled={index === 0}
                    title="Move step up"
                    style={{ padding: "4px 6px" }}
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    className="row-action-btn"
                    onClick={() => moveStep(index, 1)}
                    disabled={index === localSteps.length - 1}
                    title="Move step down"
                    style={{ padding: "4px 6px" }}
                  >
                    ▼
                  </button>
                  <button
                    type="button"
                    className="row-action-btn"
                    onClick={() => insertStepAfter(index)}
                    title="Insert new step below this step"
                    style={{ padding: "4px 6px" }}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className="row-action-btn danger"
                    onClick={() => removeStep(index)}
                    disabled={localSteps.length === 1}
                    aria-label={`Delete step ${index + 1}`}
                    title="Delete step"
                    style={{ padding: "4px 8px" }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="muted test-step-empty">No steps yet. Add the first step to make this test case executable.</p>
      )}
    </div>
  );
}
