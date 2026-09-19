"use client";

import { useEffect, useState } from "react";
import { formatDuration } from "../lib/formatDuration";
import IntegrationConnectionsPanel, { type IntegrationConnectionsPanelProps } from "./IntegrationConnectionsPanel";

export type AIConfigState = {
  provider: string;
  model: string;
  endpoint: string;
  api_key_status: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  status: any;
  supported_providers: Array<{ id: string; name: string; description: string }>;
};

export type ModelOption = {
  id: string;
  name: string;
  family?: string;
  description?: string;
};

interface SettingsStudioProps {
  config: AIConfigState | null;
  onRefresh: () => Promise<void>;
  onTest: (provider: string, model: string, apiKey?: string, endpoint?: string) => Promise<any>;
  onSave?: (newConfig: {
    provider: string;
    model: string;
    api_key?: string;
    endpoint?: string;
    temperature?: number;
    max_tokens?: number;
    timeout_seconds?: number;
  }) => Promise<any>;
  onDiscoverModels?: (provider: string, endpoint?: string, apiKey?: string) => Promise<any>;
  integrations?: IntegrationConnectionsPanelProps;
}

type SettingsTab = "ai" | "integrations" | "execution" | "security";

export default function SettingsStudio({
  config,
  onRefresh,
  onTest,
  onSave,
  onDiscoverModels,
  integrations,
}: SettingsStudioProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>("ai");

  const [selectedProvider, setSelectedProvider] = useState<string>(config?.provider || "github_copilot");
  const [modelName, setModelName] = useState<string>(config?.model || "gpt-4o");
  const [endpointUrl, setEndpointUrl] = useState<string>(config?.endpoint || "https://api.githubcopilot.com");
  const [apiKeyInput, setApiKeyInput] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(config?.temperature ?? 0.2);
  const [maxTokens, setMaxTokens] = useState<number>(config?.max_tokens ?? 4096);
  const [timeoutSeconds, setTimeoutSeconds] = useState<number>(config?.timeout_seconds ?? 45);

  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [loadingModels, setLoadingModels] = useState<boolean>(false);
  const [modelSource, setModelSource] = useState<string>("catalog");

  const [saving, setSaving] = useState<boolean>(false);
  const [saveResult, setSaveResult] = useState<{ status: string; message: string } | null>(null);

  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string; latency_ms?: number } | null>(null);

  const providers = config?.supported_providers || [
    { id: "github_copilot", name: "GitHub Copilot / GitHub Models", description: "Direct GitHub Copilot API (GPT-4o, GPT-4.1, Claude Haiku 4.5, etc.)" },
    { id: "openai", name: "OpenAI API", description: "Direct OpenAI GPT-4o / GPT-4.1 endpoints" },
    { id: "azure_openai", name: "Azure OpenAI", description: "Enterprise Azure-hosted GPT models" },
    { id: "anthropic", name: "Anthropic Claude", description: "Claude 3.5 Sonnet / Haiku" },
    { id: "gemini", name: "Google Gemini", description: "Gemini 1.5 Pro / Flash" },
    { id: "local", name: "Local LLM / vLLM", description: "Custom OpenAI-compatible inference servers" },
  ];
  const selectedProviderMeta = providers.find((provider) => provider.id === selectedProvider);

  useEffect(() => {
    if (!config) return;
    setSelectedProvider(config.provider || "github_copilot");
    setModelName(config.model || "gpt-4o");
    setEndpointUrl(config.endpoint || "https://api.githubcopilot.com");
    setTemperature(config.temperature ?? 0.2);
    setMaxTokens(config.max_tokens ?? 4096);
    setTimeoutSeconds(config.timeout_seconds ?? 45);
  }, [config?.provider, config?.model, config?.endpoint, config?.temperature, config?.max_tokens, config?.timeout_seconds]);

  // Fetch / Discover available models for the selected provider
  const fetchModelsForProvider = async (provider: string, endpoint?: string, apiKey?: string) => {
    setLoadingModels(true);
    try {
      if (onDiscoverModels) {
        const res = await onDiscoverModels(provider, endpoint, apiKey);
        if (res && res.models && res.models.length > 0) {
          setAvailableModels(res.models);
          setModelSource(res.source || "live_api");
          return;
        }
      }
    } catch (e) {
      console.warn("Could not discover models from API:", e);
    } finally {
      setLoadingModels(false);
    }

    if (provider === "github_copilot") {
      setAvailableModels([
        { id: "gpt-4o", name: "GPT-4o (Recommended)", family: "OpenAI", description: "Flagship multimodal model" },
        { id: "gpt-4.1", name: "GPT-4.1", family: "OpenAI", description: "Next-gen code & reasoning engine" },
        { id: "claude-haiku-4.5", name: "Claude Haiku 4.5", family: "Anthropic", description: "High-speed lightweight reasoning" },
        { id: "gpt-4o-mini", name: "GPT-4o mini", family: "OpenAI", description: "Fast compact model" },
        { id: "gemini-3.7-flash", name: "Gemini 3.7 Flash", family: "Google", description: "High-speed multimodal flash reasoning" },
        { id: "kimi-k2.7-code", name: "Kimi K2.7 Code", family: "Moonshot AI", description: "Code and test case reasoning" },
        { id: "gpt-4", name: "GPT-4", family: "OpenAI", description: "Standard robust GPT-4 model" },
        { id: "gpt-3.5-turbo", name: "GPT-3.5 Turbo", family: "OpenAI", description: "Standard fast conversational model" },
      ]);
    } else if (provider === "openai") {
      setAvailableModels([
        { id: "gpt-4o", name: "GPT-4o", family: "OpenAI", description: "Flagship OpenAI model" },
        { id: "gpt-4o-mini", name: "GPT-4o mini", family: "OpenAI", description: "Fast and lightweight" },
        { id: "gpt-4.1", name: "GPT-4.1", family: "OpenAI", description: "High-reasoning GPT-4.1" },
        { id: "o3-mini", name: "o3-mini", family: "OpenAI", description: "Deep reasoning & planning" },
        { id: "o1", name: "o1", family: "OpenAI", description: "Deep reasoning for complex architectures" },
        { id: "gpt-4-turbo", name: "GPT-4 Turbo", family: "OpenAI", description: "High-throughput turbo model" },
      ]);
    } else if (provider === "anthropic") {
      setAvailableModels([
        { id: "claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet", family: "Anthropic", description: "Premier coding & test reasoning" },
        { id: "claude-3-5-haiku-20241022", name: "Claude 3.5 Haiku", family: "Anthropic", description: "Fast responsive test architect" },
      ]);
    } else if (provider === "gemini") {
      setAvailableModels([
        { id: "gemini-1.5-pro", name: "Gemini 1.5 Pro", family: "Google", description: "2M context reasoning" },
        { id: "gemini-1.5-flash", name: "Gemini 1.5 Flash", family: "Google", description: "High-speed multimodal" },
      ]);
    } else {
      setAvailableModels([{ id: "gpt-4o", name: "GPT-4o", family: "Default", description: "Standard LLM model" }]);
    }
  };

  useEffect(() => {
    void fetchModelsForProvider(selectedProvider, endpointUrl, apiKeyInput);
  }, [selectedProvider]);

  const handleProviderChange = (newProvider: string) => {
    setSelectedProvider(newProvider);
    const defaults: Record<string, { model: string; endpoint: string }> = {
      github_copilot: { model: "gpt-4o", endpoint: "https://api.githubcopilot.com" },
      openai: { model: "gpt-4o", endpoint: "https://api.openai.com/v1" },
      azure_openai: { model: "gpt-4o", endpoint: "" },
      anthropic: { model: "claude-3-5-sonnet-20241022", endpoint: "https://api.anthropic.com/v1" },
      gemini: { model: "gemini-1.5-pro", endpoint: "https://generativelanguage.googleapis.com/v1beta/openai" },
      local: { model: "local-model", endpoint: "http://127.0.0.1:8080/v1" },
    };
    const nextDefaults = defaults[newProvider] ?? defaults.github_copilot;
    setModelName(nextDefaults.model);
    setEndpointUrl(nextDefaults.endpoint);
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await onTest(selectedProvider, modelName, apiKeyInput || undefined, endpointUrl || undefined);
      setTestResult(res);
    } catch (e) {
      setTestResult({
        status: "error",
        message: e instanceof Error ? e.message : "Connection test failed",
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveConfiguration = async () => {
    if (!onSave) return;
    setSaving(true);
    setSaveResult(null);
    try {
      await onSave({
        provider: selectedProvider,
        model: modelName,
        endpoint: endpointUrl,
        api_key: apiKeyInput || undefined,
        temperature,
        max_tokens: maxTokens,
        timeout_seconds: timeoutSeconds,
      });
      setSaveResult({
        status: "success",
        message: `Saved configuration successfully! Provider: ${selectedProvider}, Model: ${modelName}`,
      });
      if (onRefresh) {
        await onRefresh();
      }
    } catch (e) {
      setSaveResult({
        status: "error",
        message: e instanceof Error ? e.message : "Failed to save AI configuration",
      });
    } finally {
      setSaving(false);
    }
  };

  const modelOptions = availableModels.some((model) => model.id === modelName)
    ? availableModels
    : [
      ...availableModels,
      {
        id: modelName,
        name: modelName,
        family: "Configured",
        description: "Currently configured model; verify it with a connection test.",
      },
    ];
  const selectedModelMeta = modelOptions.find((model) => model.id === modelName);
  const credentialStatus = config?.api_key_status?.toLowerCase().startsWith("not") ? "Not configured" : "Configured (Active)";
  const isConfigured = Boolean(config?.status?.configured);

  const integrationCount = integrations?.connections?.length ?? 0;
  const activeIntegrationCount = integrations?.connections?.filter((c) => c.status === "active").length ?? 0;

  return (
    <div className="settings-studio-container" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* KPI Overview Strip */}
      <div className="build-kpi-summary-cards">
        <div className="build-kpi-card">
          <small>Active AI Engine</small>
          <strong style={{ color: isConfigured ? "var(--success, #10b981)" : "#f59e0b" }}>
            {selectedProviderMeta?.name.split(" ")[0] ?? selectedProvider}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Model: <b>{modelName}</b>
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Credential Status</small>
          <strong style={{ color: credentialStatus.includes("Configured") ? "var(--success, #10b981)" : "#f59e0b" }}>
            {credentialStatus}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Endpoint: {endpointUrl ? new URL(endpointUrl).hostname : "Local"}
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Inference Parameters</small>
          <strong>T: {temperature}</strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Max: {maxTokens} tokens · Timeout: {timeoutSeconds}s
          </span>
        </div>

        <div className="build-kpi-card">
          <small>Enterprise Integrations</small>
          <strong style={{ color: "var(--brand-primary, #b5121b)" }}>
            {integrationCount} Configured
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            {activeIntegrationCount} active sync pipelines
          </span>
        </div>
      </div>

      {/* Tab Navigation Toolbar */}
      <div className="panel run-history-toolbar" style={{ padding: "8px 16px" }}>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          <button
            type="button"
            className={`btn-sm ${activeTab === "ai" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("ai")}
          >
            🧠 AI Provider &amp; Model
          </button>
          <button
            type="button"
            className={`btn-sm ${activeTab === "integrations" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("integrations")}
          >
            🔌 Enterprise Integrations ({integrationCount})
          </button>
          <button
            type="button"
            className={`btn-sm ${activeTab === "execution" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("execution")}
          >
            ⚡ Execution Defaults
          </button>
          <button
            type="button"
            className={`btn-sm ${activeTab === "security" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("security")}
          >
            🛡️ Privacy &amp; Security
          </button>
        </div>
      </div>

      {/* Tab 1: AI Provider & Model Configuration */}
      {activeTab === "ai" && (
        <div className="settings-studio-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                AI Generation &amp; Reasoning Settings
              </h2>
              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-secondary)" }}>
                Configure primary LLM providers, model selection, reasoning temperature, and runtime tokens.
              </p>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "4px 10px",
                  borderRadius: "12px",
                  fontSize: "12px",
                  fontWeight: 600,
                  background: isConfigured ? "rgba(22, 163, 74, 0.1)" : "rgba(234, 179, 8, 0.1)",
                  color: isConfigured ? "#15803d" : "#b45309",
                  border: `1px solid ${isConfigured ? "rgba(22, 163, 74, 0.2)" : "rgba(234, 179, 8, 0.2)"}`,
                }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: isConfigured ? "#16a34a" : "#eab308",
                  }}
                />
                {isConfigured ? "AI Provider Ready" : "Configuration Needed"}
              </span>
            </div>
          </div>

          <div className="settings-studio-grid">
            {/* Left Column: Provider, Endpoint, Model Selection */}
            <div className="settings-field-group">
              <div>
                <label className="settings-label">Primary AI Provider Engine</label>
                <select
                  value={selectedProvider}
                  onChange={(e) => handleProviderChange(e.target.value)}
                  className="settings-select"
                >
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                {selectedProviderMeta?.description ? <span className="settings-field-help">{selectedProviderMeta.description}</span> : null}
              </div>

              {/* Dynamic Model Selection & Discovery Section */}
              <div
                style={{
                  background: "var(--bg-layer-2, #f8fafc)",
                  border: "1px solid var(--border-medium, #cbd5e1)",
                  borderRadius: "var(--radius-md, 8px)",
                  padding: "14px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <label className="settings-label" style={{ margin: 0 }}>
                    AI Model Selection ({availableModels.length} available)
                  </label>
                  <button
                    type="button"
                    onClick={() => void fetchModelsForProvider(selectedProvider, endpointUrl, apiKeyInput)}
                    disabled={loadingModels}
                    className="btn btn-secondary"
                    style={{ fontSize: "11px", padding: "4px 8px" }}
                    title="Query live model endpoint to refresh list"
                  >
                    {loadingModels ? "Discovering..." : "↻ Discover Models"}
                  </button>
                </div>

                {/* Model Select Dropdown */}
                <select
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  className="settings-select"
                  style={{ fontWeight: 600 }}
                >
                  {modelOptions.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} {m.family ? `[${m.family}]` : ""}
                    </option>
                  ))}
                </select>

                {selectedModelMeta && (
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)", display: "flex", gap: "8px", alignItems: "center" }}>
                    {selectedModelMeta.family && (
                      <span style={{ background: "rgba(30, 41, 59, 0.08)", padding: "2px 6px", borderRadius: "4px", fontWeight: 600 }}>
                        {selectedModelMeta.family}
                      </span>
                    )}
                    <span>{selectedModelMeta.name}</span>
                  </div>
                )}
              </div>

              <div>
                <label className="settings-label">API Base Endpoint / URL</label>
                <input
                  type="text"
                  value={endpointUrl}
                  onChange={(e) => setEndpointUrl(e.target.value)}
                  placeholder="https://api.githubcopilot.com or https://api.openai.com/v1"
                  className="settings-input"
                  style={{ fontFamily: "var(--font-code)" }}
                />
              </div>

              <div>
                <label className="settings-label">
                  API Key Override (Optional)
                </label>
                <input
                  type="password"
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder={config?.api_key_status === "configured" || config?.api_key_status?.startsWith("gh") ? "•••••••••••••••• (Active in env)" : "Enter API key or gho_ token"}
                  className="settings-input"
                  style={{ fontFamily: "var(--font-code)" }}
                />
                <span style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "4px", display: "block" }}>
                  Credential status: <strong>{credentialStatus}</strong>
                </span>
                {selectedProvider === "gemini" && !apiKeyInput && credentialStatus.includes("Not configured") && (
                  <div style={{ fontSize: "12px", color: "#1e40af", marginTop: "8px", background: "rgba(59, 130, 246, 0.08)", padding: "8px 12px", borderRadius: "6px", border: "1px solid rgba(59, 130, 246, 0.2)", lineHeight: "1.4" }}>
                    💡 <strong>Google Gemini API Key:</strong> Obtain a free key at{" "}
                    <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" style={{ color: "#2563eb", textDecoration: "underline", fontWeight: 600 }}>
                      Google AI Studio ↗
                    </a>
                    , paste it above, and click <strong>Save AI Configuration</strong>.
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Temperature, Token Limit, Save & Test Controls */}
            <div className="settings-field-group">
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <label className="settings-label" style={{ margin: 0 }}>
                    Temperature: <strong>{temperature}</strong>
                  </label>
                  <span style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
                    {temperature <= 0.3 ? "Deterministic & Precise" : "Creative & Exploratory"}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  style={{ width: "100%", cursor: "pointer" }}
                />
              </div>

              <div>
                <label className="settings-label">Max Output Tokens</label>
                <input
                  type="number"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 4096)}
                  className="settings-input"
                  style={{ fontFamily: "var(--font-code)" }}
                />
              </div>

              <div>
                <label className="settings-label">Request Timeout (Seconds)</label>
                <input
                  type="number"
                  value={timeoutSeconds}
                  onChange={(e) => setTimeoutSeconds(parseInt(e.target.value, 10) || 45)}
                  className="settings-input"
                  style={{ fontFamily: "var(--font-code)" }}
                />
              </div>

              {/* Action Buttons: Save & Test */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", paddingTop: "8px" }}>
                <button
                  type="button"
                  onClick={() => void handleSaveConfiguration()}
                  disabled={saving}
                  className="primary"
                  style={{
                    width: "100%",
                    padding: "10px 18px",
                    fontSize: "14px",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "8px",
                  }}
                >
                  {saving ? "Saving Configuration..." : "💾 Save AI Configuration"}
                </button>

                <button
                  type="button"
                  onClick={() => void handleTestConnection()}
                  disabled={testing}
                  className="secondary"
                  style={{
                    width: "100%",
                    padding: "10px 18px",
                    fontSize: "13px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                  }}
                >
                  {testing ? "Testing Connection..." : "⚡ Test AI Provider Connection"}
                </button>
              </div>

              {/* Save Feedback Banner */}
              {saveResult && (
                <div className={`settings-alert ${saveResult.status === "success" ? "success" : "error"}`}>
                  <div style={{ fontWeight: 700 }}>
                    {saveResult.status === "success" ? "✓ Configuration Saved" : "✗ Save Error"}
                  </div>
                  <div>{saveResult.message}</div>
                </div>
              )}

              {/* Connection Test Feedback Banner */}
              {testResult && (
                <div className={`settings-alert ${testResult.status === "success" ? "success" : "error"}`}>
                  <div style={{ fontWeight: 700 }}>
                    {testResult.status === "success" ? "✓ Connection Verified" : "✗ Connection Error"}
                  </div>
                  <div>{testResult.message}</div>
                  {typeof testResult.latency_ms === "number" && testResult.latency_ms > 0 ? (
                    <div style={{ fontSize: "11px", marginTop: "2px" }}>Response Latency: {formatDuration(testResult.latency_ms)}</div>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Enterprise Integrations */}
      {activeTab === "integrations" && (
        <div>
          {integrations ? (
            <IntegrationConnectionsPanel {...integrations} />
          ) : (
            <div className="panel" style={{ padding: "32px", textAlign: "center" }}>
              <p className="muted">No enterprise integration connections configured yet.</p>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Execution Defaults */}
      {activeTab === "execution" && (
        <div className="settings-studio-card">
          <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Execution Engine Defaults</h2>
          <p className="muted" style={{ margin: "4px 0 16px" }}>
            Default Playwright execution parameters, worker concurrency, evidence capture, and self-healing policies.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
            <div className="panel" style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
              <strong>Execution Mode</strong>
              <span className="muted" style={{ fontSize: "13px" }}>Default mode for test runs (Watch Live interactive stream vs Background batch queue).</span>
              <span className="badge badge-secondary" style={{ width: "fit-content" }}>Watch Live / Parallel Workers</span>
            </div>

            <div className="panel" style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
              <strong>Evidence Retention</strong>
              <span className="muted" style={{ fontSize: "13px" }}>Screenshots captured on every failed step; full video and Playwright trace on demand.</span>
              <span className="badge badge-secondary" style={{ width: "fit-content" }}>Screenshots + Traces on Failure</span>
            </div>

            <div className="panel" style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
              <strong>Autonomous Self-Healing</strong>
              <span className="muted" style={{ fontSize: "13px" }}>AI healer agent identifies broken locators in real time, applies repairs, and persists candidates.</span>
              <span className="badge badge-secondary" style={{ width: "fit-content" }}>Active (Bounded Strict Mode)</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Privacy & Security */}
      {activeTab === "security" && (
        <div className="settings-studio-card">
          <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Privacy, Security &amp; Data Governance</h2>
          <p className="muted" style={{ margin: "4px 0 16px" }}>
            Security boundaries, credential isolation, and local storage retention policies.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div className="panel" style={{ padding: "16px" }}>
              <strong style={{ color: "var(--brand-primary, #b5121b)" }}>🔒 Credential Isolation &amp; Zero-Leak Policy</strong>
              <p className="muted" style={{ margin: "6px 0 0", fontSize: "13px", lineHeight: 1.5 }}>
                Passwords, API tokens, and secret parameters are never committed to version control, never echoed in plain text logs, and are masked automatically during browser test execution.
              </p>
            </div>

            <div className="panel" style={{ padding: "16px" }}>
              <strong>🌐 Local Storage Persistence</strong>
              <p className="muted" style={{ margin: "6px 0 0", fontSize: "13px", lineHeight: 1.5 }}>
                Runtime test data profiles and filter configurations are stored scoped per application ID in the local browser session.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
