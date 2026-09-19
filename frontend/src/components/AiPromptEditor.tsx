"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";

export interface AiPromptEditorProps {
  value: string;
  onChange: (value: string) => void;
  onApplySmoke?: () => void;
  onApplyRegression?: () => void;
  disabled?: boolean;
  rows?: number;
  placeholder?: string;
}

export default function AiPromptEditor({
  value,
  onChange,
  onApplySmoke,
  onApplyRegression,
  disabled = false,
  rows = 9,
  placeholder = "Describe the workflow, pages, and validations you want covered.",
}: AiPromptEditorProps) {
  const [localValue, setLocalValue] = useState(value);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const latestLocalRef = useRef(localValue);
  latestLocalRef.current = localValue;

  // Synchronize when the external value changes from outside (e.g. preset clicked, Jira applied)
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const nextValue = event.target.value;
    setLocalValue(nextValue);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      onChange(nextValue);
    }, 150);
  };

  const handleBlur = () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    onChange(latestLocalRef.current);
  };

  const handleSmokePreset = () => {
    const smokeText = "Generate smoke test cases for authentication, primary navigation, and key page visibility checks.";
    setLocalValue(smokeText);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    onChange(smokeText);
    onApplySmoke?.();
  };

  const handleRegressionPreset = () => {
    const regressionText = "Generate full regression coverage for authentication, search and filter behavior, data validation, error handling, and reset behavior.";
    setLocalValue(regressionText);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    onChange(regressionText);
    onApplyRegression?.();
  };

  return (
    <div>
      <label className="capture-label">
        Prompt
        <textarea
          value={localValue}
          onChange={handleChange}
          onBlur={handleBlur}
          rows={rows}
          disabled={disabled}
          placeholder={placeholder}
        />
      </label>
      <div className="ai-simple-preset-row">
        <button
          type="button"
          className="secondary"
          onClick={handleSmokePreset}
          disabled={disabled}
        >
          Use smoke preset
        </button>
        <button
          type="button"
          className="secondary"
          onClick={handleRegressionPreset}
          disabled={disabled}
        >
          Use regression preset
        </button>
      </div>
    </div>
  );
}
