"use client";

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { RuntimeParameter } from "../types";

type ParameterizedDataProfileProps = {
  parameters: RuntimeParameter[];
  setParameters: Dispatch<SetStateAction<RuntimeParameter[]>>;
  applicationName?: string;
  onLoginAdded?: () => void;
  onSaveProfile?: () => void;
  onSmartGenerate?: () => void;
  onAutoLearnEntities?: () => void;
  generatingSmartData?: boolean;
  learningEntities?: boolean;
};

function createParameter(key = ""): RuntimeParameter {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    key,
    value: "",
    sensitive: false,
  };
}

function isSensitiveKey(key: string): boolean {
  return /login[_-]?(email|username)|username|password|passcode|secret|token|api[_-]?key|credential/i.test(key);
}

function getParameterInputType(parameter: { key: string; sensitive: boolean }): "email" | "password" | "text" {
  const normalizedKey = parameter.key.trim().toLowerCase();
  if (normalizedKey.includes("email")) return "email";
  if (normalizedKey.includes("password") || normalizedKey.includes("passcode") || normalizedKey === "pwd") return "password";
  return parameter.sensitive ? "password" : "text";
}

function ParameterizedRow({
  parameter,
  onUpdate,
  onRemove,
}: {
  parameter: RuntimeParameter;
  onUpdate: (id: string, update: Partial<RuntimeParameter>) => void;
  onRemove: (id: string) => void;
}) {
  const [localKey, setLocalKey] = useState(parameter.key);
  const [localValue, setLocalValue] = useState(parameter.value);
  const keyTimerRef = useRef<NodeJS.Timeout | null>(null);
  const valTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setLocalKey(parameter.key);
  }, [parameter.key]);

  useEffect(() => {
    setLocalValue(parameter.value);
  }, [parameter.value]);

  const handleKeyChange = (val: string) => {
    setLocalKey(val);
    if (keyTimerRef.current) clearTimeout(keyTimerRef.current);
    keyTimerRef.current = setTimeout(() => {
      onUpdate(parameter.id, { key: val });
    }, 150);
  };

  const handleValueChange = (val: string) => {
    setLocalValue(val);
    if (valTimerRef.current) clearTimeout(valTimerRef.current);
    valTimerRef.current = setTimeout(() => {
      onUpdate(parameter.id, { value: val });
    }, 150);
  };

  const handleBlur = () => {
    if (keyTimerRef.current) clearTimeout(keyTimerRef.current);
    if (valTimerRef.current) clearTimeout(valTimerRef.current);
    onUpdate(parameter.id, { key: localKey, value: localValue });
  };

  return (
    <div className="parameterized-value-row">
      <label className="capture-label">
        Parameter key
        <input
          value={localKey}
          onChange={(event) => handleKeyChange(event.target.value)}
          onBlur={handleBlur}
          placeholder="order_id"
          autoComplete="off"
          aria-label="Parameterized value key"
        />
      </label>
      <label className="capture-label">
        Parameter value
        <input
          type={getParameterInputType({ key: localKey, sensitive: parameter.sensitive })}
          value={localValue}
          onChange={(event) => handleValueChange(event.target.value)}
          onBlur={handleBlur}
          placeholder={localKey.toLowerCase().includes("email") ? "user@example.com" : "Value used by generation and execution"}
          autoComplete="off"
          aria-label="Parameterized value"
        />
      </label>
      <label className="capture-label flow-toggle parameterized-value-sensitive">
        <input
          type="checkbox"
          checked={parameter.sensitive}
          onChange={(event) => onUpdate(parameter.id, { sensitive: event.target.checked })}
          aria-label="Sensitive parameter"
        />
        Sensitive
      </label>
      <button
        type="button"
        className="table-action"
        onClick={() => onRemove(parameter.id)}
        aria-label={`Remove parameter ${parameter.key || "value"}`}
      >
        Remove
      </button>
    </div>
  );
}

export default function ParameterizedDataProfile({
  parameters,
  setParameters,
  applicationName,
  onSaveProfile,
  onSmartGenerate,
  onAutoLearnEntities,
  generatingSmartData = false,
  learningEntities = false,
}: ParameterizedDataProfileProps) {
  const addParameterizedValue = () => {
    setParameters((current) => [...current, createParameter()]);
  };

  const updateParameter = (id: string, update: Partial<RuntimeParameter>) => {
    setParameters((current) => current.map((parameter) => {
      if (parameter.id !== id) return parameter;
      const next = { ...parameter, ...update };
      if (!Object.prototype.hasOwnProperty.call(update, "sensitive") && isSensitiveKey(next.key)) {
        next.sensitive = true;
      }
      return next;
    }));
  };

  const removeParameter = (id: string) => {
    setParameters((current) => current.filter((parameter) => parameter.id !== id));
  };

  return (
    <div className="parameterized-values-editor">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button type="button" className="secondary btn-sm" onClick={addParameterizedValue}>
            + Add parameter
          </button>
          {onSmartGenerate && (
            <button
              type="button"
              className="secondary btn-sm"
              onClick={onSmartGenerate}
              disabled={generatingSmartData}
              title="Generate synthetic valid & boundary dataset values with AI"
            >
              {generatingSmartData ? "Synthesizing..." : "⚡ Synthesize data"}
            </button>
          )}
          {onAutoLearnEntities && (
            <button
              type="button"
              className="secondary btn-sm"
              onClick={onAutoLearnEntities}
              disabled={learningEntities}
              title="Harvest live domain entities from the target application"
            >
              {learningEntities ? "Harvesting..." : "🔍 Harvest entities"}
            </button>
          )}
        </div>
        <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
          {parameters.length} parameter{parameters.length === 1 ? "" : "s"} configured
          {applicationName ? ` for ${applicationName}` : ""}
        </span>
      </div>

      {parameters.length ? (
        <div className="parameterized-values-list" aria-label="Parameterized values">
          {parameters.map((parameter) => (
            <ParameterizedRow
              key={parameter.id}
              parameter={parameter}
              onUpdate={updateParameter}
              onRemove={removeParameter}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
