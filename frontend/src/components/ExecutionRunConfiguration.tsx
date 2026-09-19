"use client";

import type { ChangeEvent, Dispatch, SetStateAction } from "react";
import type { ExecutionMode, ExecutionSlowMode, ExecutionTraceMode, RuntimeParameter, VoiceGender } from "../types";

type ExecutionRunScope = "all" | "draft" | "ready" | "latest" | "selected";
type ExecutionScopeOption = { value: ExecutionRunScope; label: string };

type ExecutionRunConfigurationProps = {
  executionRunScope: ExecutionRunScope;
  setExecutionRunScope: (scope: ExecutionRunScope) => void;
  executionScopeOptions: ExecutionScopeOption[];
  executionMode: ExecutionMode;
  setExecutionMode: (mode: ExecutionMode) => void;
  parallelExecutionCount: number;
  setParallelExecutionCount: (count: number) => void;
  executionSlowMode: ExecutionSlowMode;
  setExecutionSlowMode: (mode: ExecutionSlowMode) => void;
  executionTraceMode: ExecutionTraceMode;
  setExecutionTraceMode: (mode: ExecutionTraceMode) => void;
  voiceGender: VoiceGender;
  onVoiceGenderChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  voiceOverEnabled: boolean;
  setVoiceOverEnabled: (enabled: boolean) => void;
  onTestVoice: () => void;
  captureScreenshotEvidence: boolean;
  setCaptureScreenshotEvidence: (enabled: boolean) => void;
  highlightActionTargets: boolean;
  setHighlightActionTargets: (enabled: boolean) => void;
  recordVideoEvidence: boolean;
  setRecordVideoEvidence: (enabled: boolean) => void;
  keepBrowserOpenOnFailure: boolean;
  setKeepBrowserOpenOnFailure: (enabled: boolean) => void;
  keepBrowserOpenSeconds: number;
  setKeepBrowserOpenSeconds: (seconds: number) => void;
  authenticatedFlow: boolean;
  setAuthenticatedFlow: (enabled: boolean) => void;
  emailSelector: string;
  setEmailSelector: (selector: string) => void;
  passwordSelector: string;
  setPasswordSelector: (selector: string) => void;
  submitSelector: string;
  setSubmitSelector: (selector: string) => void;
  runtimeParameters: RuntimeParameter[];
  setRuntimeParameters: Dispatch<SetStateAction<RuntimeParameter[]>>;
  onAutoPopulateParameters?: () => void;
  populatingParameters?: boolean;
  onSaveConfiguration: () => void;
  onDownloadHistory: () => void;
  downloadingExecutionHistory: boolean;
};

export default function ExecutionRunConfiguration({
  executionRunScope,
  setExecutionRunScope,
  executionScopeOptions,
  executionMode,
  setExecutionMode,
  parallelExecutionCount,
  setParallelExecutionCount,
  executionSlowMode,
  setExecutionSlowMode,
  executionTraceMode,
  setExecutionTraceMode,
  voiceGender,
  onVoiceGenderChange,
  voiceOverEnabled,
  setVoiceOverEnabled,
  onTestVoice,
  captureScreenshotEvidence,
  setCaptureScreenshotEvidence,
  highlightActionTargets,
  setHighlightActionTargets,
  recordVideoEvidence,
  setRecordVideoEvidence,
  keepBrowserOpenOnFailure,
  setKeepBrowserOpenOnFailure,
  keepBrowserOpenSeconds,
  setKeepBrowserOpenSeconds,
  authenticatedFlow,
  setAuthenticatedFlow,
  emailSelector,
  setEmailSelector,
  passwordSelector,
  setPasswordSelector,
  submitSelector,
  setSubmitSelector,
  runtimeParameters,
  setRuntimeParameters,
  onAutoPopulateParameters,
  populatingParameters,
  onSaveConfiguration,
  onDownloadHistory,
  downloadingExecutionHistory,
}: ExecutionRunConfigurationProps) {
  return (
    <div className="run-control">
      <div className="run-control-field-grid">
        <label htmlFor="execution-scope">Run scope</label>
        <select id="execution-scope" value={executionRunScope} onChange={(event) => setExecutionRunScope(event.target.value as ExecutionRunScope)}>
          {executionScopeOptions.map((option) => <option key={`run-scope-${option.value}`} value={option.value}>{option.label}</option>)}
        </select>
        <label htmlFor="execution-mode">Execution mode</label>
        <select id="execution-mode" value={executionMode} onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)}>
          <option value="watch_live">Watch live (visible browser)</option>
          <option value="background">Background (headless)</option>
        </select>
        <label htmlFor="execution-parallelism">Parallel workers</label>
        <select id="execution-parallelism" value={parallelExecutionCount} onChange={(event) => setParallelExecutionCount(Math.max(1, Math.min(5, Number(event.target.value) || 1)))}>
          {[1, 2, 3, 4, 5].map((count) => <option key={`parallel-workers-${count}`} value={count}>{count} {count === 1 ? "worker" : "workers"}</option>)}
        </select>
        <label htmlFor="execution-slow-mode">Speed profile</label>
        <select id="execution-slow-mode" value={executionSlowMode} onChange={(event) => setExecutionSlowMode(event.target.value as ExecutionSlowMode)}>
          <option value="normal">Normal</option>
          <option value="demo">Demo (0.8s paced)</option>
          <option value="showcase">Client Showcase (2.0s lockstep voice)</option>
        </select>
        <label htmlFor="execution-trace-mode">Trace capture</label>
        <select id="execution-trace-mode" value={executionTraceMode} onChange={(event) => setExecutionTraceMode(event.target.value as ExecutionTraceMode)}>
          <option value="off">Off</option>
          <option value="on_failure">On failure</option>
          <option value="always">Always</option>
        </select>
      </div>

      <div className="execution-artifact-options">
        <label className="capture-label voice-mode-select" htmlFor="execution-voice-mode">
          Voice mode
          <select id="execution-voice-mode" value={voiceGender} onChange={onVoiceGenderChange} disabled={typeof window !== "undefined" && !("speechSynthesis" in window)} title="Choose the browser voice profile used for execution narration">
            <option value="male">Male voice</option>
            <option value="female">Female voice</option>
          </select>
        </label>
        <label className="capture-label flow-toggle" title="Read meaningful execution actions aloud in this browser">
          <input type="checkbox" checked={voiceOverEnabled} onChange={(event) => setVoiceOverEnabled(event.target.checked)} disabled={typeof window !== "undefined" && !("speechSynthesis" in window)} />
          Voice-over actions
        </label>
        <button type="button" className="secondary btn-sm" onClick={onTestVoice} disabled={!voiceOverEnabled || (typeof window !== "undefined" && !("speechSynthesis" in window))} title="Play a short voice-over confirmation">Test voice</button>
        <label className="capture-label flow-toggle">
          <input type="checkbox" checked={captureScreenshotEvidence} onChange={(event) => setCaptureScreenshotEvidence(event.target.checked)} disabled={highlightActionTargets} title={highlightActionTargets ? "Screenshot capture is required while action highlighting is enabled" : "Capture screenshot evidence after each test step"} />
          Capture screenshot{highlightActionTargets ? " (required for highlights)" : ""}
        </label>
        <label className="capture-label flow-toggle">
          <input type="checkbox" checked={highlightActionTargets} onChange={(event) => { const enabled = event.target.checked; setHighlightActionTargets(enabled); if (enabled) setCaptureScreenshotEvidence(true); }} title="Draw a red outline around the active target before each action" />
          Highlight action targets
        </label>
        <label className="capture-label flow-toggle">
          <input type="checkbox" checked={recordVideoEvidence} onChange={(event) => setRecordVideoEvidence(event.target.checked)} />
          Record video
        </label>
        <label className="capture-label flow-toggle">
          <input type="checkbox" checked={keepBrowserOpenOnFailure} onChange={(event) => setKeepBrowserOpenOnFailure(event.target.checked)} disabled={executionMode === "background"} />
          Keep browser open on failure
        </label>
        <label className="capture-label">
          Browser hold (seconds)
          <input type="number" min={0} max={120} value={keepBrowserOpenSeconds} onChange={(event) => { const parsed = Number.parseInt(event.target.value, 10); setKeepBrowserOpenSeconds(Number.isNaN(parsed) ? 0 : Math.max(0, Math.min(120, parsed))); }} disabled={executionMode === "background"} />
        </label>
      </div>

      <p className="muted execution-mode-note">{executionMode === "watch_live" ? "Watch live opens a visible Playwright browser on the runner machine and streams real execution events." : "Background mode runs headless for CI/CD and unattended regression."}</p>

      <div className="run-control-parameters">
        <div className="run-control-parameters-heading">
          <h3>Login parameters</h3>
          <p className="muted">Use per-run runtime parameters for protected targets. Credentials are sent only with this run and are never saved in browser configuration.</p>
        </div>
        <label className="capture-label flow-toggle">
          <input type="checkbox" checked={authenticatedFlow} onChange={(event) => setAuthenticatedFlow(event.target.checked)} />
          Run login flow
        </label>
        {authenticatedFlow ? (
          <>
            <div className="execution-parameter-list">
              {(["login_email", "login_password"] as const).map((parameterKey) => {
                const parameter = runtimeParameters.find((item) => item.key.trim().toLowerCase() === parameterKey);
                return (
                  <label className="capture-label" key={parameterKey}>
                    {parameterKey === "login_email" ? "Login email" : "Login password"}
                    <input
                      type={parameterKey === "login_password" ? "password" : "email"}
                      value={parameter?.value ?? ""}
                      onChange={(event) => setRuntimeParameters((current) => {
                        const existing = current.find((item) => item.key.trim().toLowerCase() === parameterKey);
                        if (!existing) {
                          return [...current, { id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, key: parameterKey, value: event.target.value, sensitive: true }];
                        }
                        return current.map((item) => item.id === existing.id ? { ...item, key: parameterKey, value: event.target.value, sensitive: true } : item);
                      })}
                      placeholder={parameterKey === "login_email" ? "user@example.com" : "Enter password for this run"}
                      autoComplete="off"
                    />
                  </label>
                );
              })}
            </div>
            <div className="run-control-field-grid">
              <label htmlFor="login-email-selector">Email field selector</label>
              <input id="login-email-selector" value={emailSelector} onChange={(event) => setEmailSelector(event.target.value)} placeholder="#user_email" autoComplete="off" />
              <label htmlFor="login-password-selector">Password field selector</label>
              <input id="login-password-selector" value={passwordSelector} onChange={(event) => setPasswordSelector(event.target.value)} placeholder="#user_password" autoComplete="off" />
              <label htmlFor="login-submit-selector">Submit control selector</label>
              <input id="login-submit-selector" value={submitSelector} onChange={(event) => setSubmitSelector(event.target.value)} placeholder="input[type=submit]" autoComplete="off" />
            </div>
          </>
        ) : <p className="muted">Login is disabled for this run. Enable it when the selected cases require authentication.</p>}
      </div>

      <div className="run-control-parameters">
        <div className="run-control-parameters-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <h3>Parameterized values</h3>
            <p className="muted">Pass key/value data into steps, selectors, URLs, and checks with placeholders such as {"{{login_email}}"} or {"{{clinic_id}}"}. Values are automatically populated from live application entities and AI Test Data Generator.</p>
          </div>
          {onAutoPopulateParameters ? (
            <button
              type="button"
              className="secondary btn-sm"
              onClick={onAutoPopulateParameters}
              disabled={populatingParameters}
              title="Automatically detect all {{parameter}} tokens in test cases and populate with real/synthesized AI test data"
              style={{ whiteSpace: "nowrap" }}
            >
              {populatingParameters ? "Auto-populating..." : "⚡ Auto-populate from AI Test Data"}
            </button>
          ) : null}
        </div>
        <div className="execution-parameter-list">
          {runtimeParameters.length ? runtimeParameters.map((parameter) => (
            <div className="execution-parameter-row" key={parameter.id}>
              <label className="capture-label">Parameter key<input value={parameter.key} onChange={(event) => setRuntimeParameters((current) => current.map((item) => item.id === parameter.id ? { ...item, key: event.target.value } : item))} placeholder="login_email" autoComplete="off" /></label>
              <label className="capture-label">Parameter value<input type={parameter.sensitive ? "password" : "text"} value={parameter.value} onChange={(event) => setRuntimeParameters((current) => current.map((item) => item.id === parameter.id ? { ...item, value: event.target.value } : item))} placeholder={parameter.sensitive ? "Sensitive value" : "Value used by the test"} autoComplete="off" /></label>
              <label className="capture-label flow-toggle execution-parameter-sensitive"><input type="checkbox" checked={parameter.sensitive} onChange={(event) => setRuntimeParameters((current) => current.map((item) => item.id === parameter.id ? { ...item, sensitive: event.target.checked } : item))} />Sensitive</label>
              <button type="button" className="table-action" onClick={() => setRuntimeParameters((current) => current.filter((item) => item.id !== parameter.id))} aria-label={`Remove ${parameter.key || "runtime parameter"}`}>Remove</button>
            </div>
          )) : <p className="muted">No runtime parameters configured. Click 'Auto-populate from AI Test Data' or add custom key/value pairs.</p>}
        </div>
        <div className="execution-parameter-actions">
          <button type="button" className="secondary btn-sm" onClick={() => setRuntimeParameters((current) => [...current, { id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, key: "", value: "", sensitive: false }])}>Add parameter</button>
          <span className="muted">Parameters are auto-injected into matching {"{{token}}"} variables at execution runtime. You can edit any value above to test custom data scenarios.</span>
        </div>
      </div>

      <div className="execution-config-actions">
        <button type="button" className="primary" onClick={onSaveConfiguration}>Save configuration</button>
        <button type="button" className="secondary" onClick={onDownloadHistory} disabled={downloadingExecutionHistory}>{downloadingExecutionHistory ? "Downloading..." : "Download history"}</button>
      </div>
    </div>
  );
}
