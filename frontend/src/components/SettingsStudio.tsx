"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { formatDuration } from "../lib/formatDuration";
import IntegrationConnectionsPanel, { type IntegrationConnectionsPanelProps } from "./IntegrationConnectionsPanel";
import AuditLogViewer, { type AuditEntry } from "./AuditLogViewer";
import SystemLogViewer from "./SystemLogViewer";

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

export type SettingsTab = "ai" | "integrations" | "capabilities" | "execution" | "security" | "audit" | "systemLogs";

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
  auditLogs?: AuditEntry[];
  refreshingAuditLogs?: boolean;
  onRefreshAuditLogs?: () => Promise<void>;
  initialTab?: SettingsTab;
  token?: string | null;
  apiUrl?: string;
}

export default function SettingsStudio({
  config,
  onRefresh,
  onTest,
  onSave,
  onDiscoverModels,
  integrations,
  auditLogs,
  refreshingAuditLogs,
  onRefreshAuditLogs,
  initialTab,
  token,
  apiUrl = "",
}: SettingsStudioProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab || "ai");

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

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

  // Git Repository Integration State
  const [gitRepoInput, setGitRepoInput] = useState<string>("");
  const [gitTesting, setGitTesting] = useState<boolean>(false);
  const [gitTestResult, setGitTestResult] = useState<{
    success: boolean;
    message: string;
    provider?: string;
    repo?: string;
    default_branch?: string;
    permissions?: Record<string, boolean>;
  } | null>(null);
  const [gitReposLoading, setGitReposLoading] = useState<boolean>(false);
  const [gitReposList, setGitReposList] = useState<
    Array<{
      full_name: string;
      default_branch: string;
      private: boolean;
      html_url: string;
      description?: string;
    }>
  >([]);
  const [gitReposFetched, setGitReposFetched] = useState<boolean>(false);

  const handleTestGitConnection = async () => {
    if (!token) return;
    setGitTesting(true);
    setGitTestResult(null);
    try {
      const res = await apiFetch<{
        success: boolean;
        message: string;
        provider?: string;
        repo?: string;
        default_branch?: string;
        permissions?: Record<string, boolean>;
      }>(
        "/api/v1/integrations/git/test-connection",
        {
          method: "POST",
          body: JSON.stringify({ repo: gitRepoInput.trim() || undefined }),
        },
        token
      );
      setGitTestResult(res);
    } catch (err) {
      setGitTestResult({
        success: false,
        message: err instanceof Error ? err.message : "Git connection test failed",
      });
    } finally {
      setGitTesting(false);
    }
  };

  const [capabilitiesData, setCapabilitiesData] = useState<Array<{
    capability: string;
    name: string;
    category: string;
    description: string;
    supported_environments: string[];
    is_available: boolean;
  }>>([]);
  const [toolsData, setToolsData] = useState<Array<{
    tool_id: string;
    name: string;
    description: string;
    capability: string;
    version: string;
    permissions: string[];
    supported_environments: string[];
    is_available: boolean;
  }>>([]);
  const [loadingCaps, setLoadingCaps] = useState(false);
  const [testObjective, setTestObjective] = useState("Test checkout flow on web and mobile, validate REST API endpoints, and commit test suite to GitHub");
  const [planResult, setPlanResult] = useState<any>(null);
  const [planLoading, setPlanLoading] = useState(false);

  const handleLoadCapabilities = async () => {
    setLoadingCaps(true);
    try {
      const [capsRes, toolsRes] = await Promise.all([
        apiFetch<{ capabilities: any[] }>("/api/v1/capabilities", {}, token || undefined),
        apiFetch<{ tools: any[] }>("/api/v1/tools", {}, token || undefined),
      ]);
      setCapabilitiesData(capsRes.capabilities || []);
      setToolsData(toolsRes.tools || []);
    } catch {
      // Graceful fallback
    } finally {
      setLoadingCaps(false);
    }
  };

  const handleGeneratePlan = async () => {
    if (!testObjective.trim()) return;
    setPlanLoading(true);
    try {
      const res = await apiFetch<any>(
        "/api/v1/orchestrator/agentic-plan",
        {
          method: "POST",
          body: JSON.stringify({ objective: testObjective.trim() }),
        },
        token || undefined
      );
      setPlanResult(res);
    } catch (err) {
      setPlanResult({ error: err instanceof Error ? err.message : "Planning failed" });
    } finally {
      setPlanLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "capabilities") {
      handleLoadCapabilities();
    }
  }, [activeTab]);

  const handleFetchGitRepos = async () => {
    if (!token) return;
    setGitReposLoading(true);
    try {
      const res = await apiFetch<{
        total: number;
        repos: Array<{
          full_name: string;
          default_branch: string;
          private: boolean;
          html_url: string;
          description?: string;
        }>;
      }>("/api/v1/integrations/git/repos", {}, token);
      setGitReposList(res.repos || []);
      setGitReposFetched(true);
    } catch (err) {
      setGitTestResult({
        success: false,
        message: err instanceof Error ? err.message : "Failed to load repositories",
      });
    } finally {
      setGitReposLoading(false);
    }
  };

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
        { id: "gemini-flash-latest", name: "Gemini Flash Latest (Recommended)", family: "Google", description: "High-throughput multimodal flash model" },
        { id: "gemini-pro-latest", name: "Gemini Pro Latest", family: "Google", description: "Flagship multi-modal reasoning engine" },
        { id: "gemini-3.7-flash", name: "Gemini 3.7 Flash", family: "Google", description: "High-speed multimodal flash reasoning" },
        { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", family: "Google", description: "Mid-size multimodal model with 1M context" },
        { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", family: "Google", description: "High-capacity reasoning engine with thinking capability" },
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
      gemini: { model: "gemini-flash-latest", endpoint: "https://generativelanguage.googleapis.com/v1beta/openai" },
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
    <div className="settings-studio-container" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Tab Navigation Toolbar */}
      <div className="panel run-history-toolbar" style={{ padding: "6px 12px", marginBottom: 0 }}>
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
            className={`btn-sm ${activeTab === "capabilities" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("capabilities")}
          >
            ⚡ Capabilities &amp; Tools ({capabilitiesData.length || "18+"})
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
          <button
            type="button"
            className={`btn-sm ${activeTab === "audit" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("audit")}
          >
            📜 Audit Logs {auditLogs?.length ? `(${auditLogs.length})` : ""}
          </button>
          <button
            type="button"
            className={`btn-sm ${activeTab === "systemLogs" ? "primary" : "secondary"}`}
            onClick={() => setActiveTab("systemLogs")}
          >
            🖥️ System Logs
          </button>
        </div>
      </div>

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

        <div className="build-kpi-card">
          <small>Audit Trail &amp; Governance</small>
          <strong style={{ color: "var(--brand-primary, #b5121b)" }}>
            {auditLogs ? `${auditLogs.length} Events` : "Active"}
          </strong>
          <span className="muted" style={{ fontSize: "var(--font-caption)" }}>
            Tamper-evident audit logs
          </span>
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
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Git Repository Integration Card */}
          <div className="settings-studio-card" style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div
                  style={{
                    width: "40px",
                    height: "40px",
                    borderRadius: "8px",
                    background: "#24292e",
                    color: "#ffffff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "20px",
                  }}
                >
                  🐙
                </div>
                <div>
                  <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                    Git Repository Integration · GitHub REST API
                  </h2>
                  <p className="muted" style={{ margin: "2px 0 0", fontSize: "12px" }}>
                    Commit compiled test scripts (Playwright, Cypress, Selenium, Robot Framework, Java TestNG, Jest + Puppeteer) directly to remote Git repositories with smart branch detection and atomic multi-file commits.
                  </p>
                </div>
              </div>

              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  type="button"
                  className="secondary btn-sm"
                  onClick={() => void handleFetchGitRepos()}
                  disabled={gitReposLoading}
                  title="List repositories accessible with the configured token"
                >
                  {gitReposLoading ? "Loading Repos..." : "📋 Browse Repos"}
                </button>
                <button
                  type="button"
                  className="primary btn-sm"
                  onClick={() => void handleTestGitConnection()}
                  disabled={gitTesting}
                >
                  {gitTesting ? "Testing Connection..." : "🔌 Test Git Connection"}
                </button>
              </div>
            </div>

            {/* Test Status Banner */}
            {gitTestResult && (
              <div
                style={{
                  marginTop: "14px",
                  padding: "10px 14px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  background: gitTestResult.success ? "rgba(22, 163, 74, 0.12)" : "rgba(220, 38, 38, 0.12)",
                  border: `1px solid ${gitTestResult.success ? "rgba(22, 163, 74, 0.3)" : "rgba(220, 38, 38, 0.3)"}`,
                  color: gitTestResult.success ? "var(--success-dark, #15803d)" : "var(--error-dark, #b91c1c)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600 }}>
                  <span>{gitTestResult.success ? "✅" : "❌"}</span>
                  <span>{gitTestResult.message}</span>
                </div>
                {gitTestResult.success && gitTestResult.repo && (
                  <div style={{ marginTop: "6px", fontSize: "11px", display: "flex", gap: "16px", flexWrap: "wrap", color: "var(--text-secondary)" }}>
                    <span>Repository: <strong>{gitTestResult.repo}</strong></span>
                    <span>Default Branch: <strong>{gitTestResult.default_branch || "main"}</strong></span>
                    {gitTestResult.permissions && (
                      <span>
                        Permissions: Push: {gitTestResult.permissions.push ? "✅" : "❌"} | Pull: {gitTestResult.permissions.pull ? "✅" : "❌"} | Admin: {gitTestResult.permissions.admin ? "✅" : "❌"}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Config & Repos Grid */}
            <div style={{ marginTop: "14px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
              <div className="panel" style={{ padding: "12px" }}>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>
                  Target Repository (owner/repo)
                </label>
                <input
                  type="text"
                  placeholder="e.g. your-org/test-automation"
                  value={gitRepoInput}
                  onChange={(e) => setGitRepoInput(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 10px",
                    borderRadius: "6px",
                    border: "1px solid var(--border-light)",
                    fontSize: "12px",
                  }}
                />
                <span className="muted" style={{ fontSize: "11px", marginTop: "4px", display: "block" }}>
                  Leave empty to test token against user profile, or specify a repository to verify write access.
                </span>
              </div>

              <div className="panel" style={{ padding: "12px" }}>
                <strong style={{ fontSize: "12px", display: "block", marginBottom: "4px" }}>
                  Supported Export Frameworks
                </strong>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "4px" }}>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>🎭 Playwright (TypeScript)</span>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>🌲 Cypress (JavaScript)</span>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>🐍 Selenium (Python)</span>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>🤖 Robot Framework</span>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>☕ Java TestNG</span>
                  <span className="badge badge-secondary" style={{ fontSize: "11px" }}>🎪 Jest + Puppeteer</span>
                </div>
              </div>
            </div>

            {/* Accessible Repos List (if loaded) */}
            {gitReposFetched && (
              <div style={{ marginTop: "14px" }}>
                <strong style={{ fontSize: "12px", display: "block", marginBottom: "6px" }}>
                  Accessible GitHub Repositories ({gitReposList.length})
                </strong>
                <div
                  style={{
                    maxHeight: "180px",
                    overflowY: "auto",
                    border: "1px solid var(--border-light)",
                    borderRadius: "6px",
                    background: "var(--bg-layer-2)",
                  }}
                >
                  {gitReposList.length === 0 ? (
                    <div style={{ padding: "12px", textAlign: "center", fontSize: "12px", color: "var(--text-secondary)" }}>
                      No accessible repositories found for the configured token.
                    </div>
                  ) : (
                    gitReposList.map((r) => (
                      <div
                        key={r.full_name}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderBottom: "1px solid var(--border-light)",
                          fontSize: "12px",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <button
                            type="button"
                            className="btn-xs secondary"
                            onClick={() => setGitRepoInput(r.full_name)}
                            title="Select this repository"
                          >
                            Select
                          </button>
                          <strong>{r.full_name}</strong>
                          {r.private && (
                            <span className="badge badge-secondary" style={{ fontSize: "10px", padding: "1px 4px" }}>
                              private
                            </span>
                          )}
                        </div>
                        <span className="muted" style={{ fontSize: "11px" }}>
                          default: {r.default_branch}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {integrations ? (
            <IntegrationConnectionsPanel {...integrations} />
          ) : (
            <div className="panel" style={{ padding: "32px", textAlign: "center" }}>
              <p className="muted">No enterprise integration connections configured yet.</p>
            </div>
          )}
        </div>
      )}

      {/* Tab: Platform Capabilities & Tool Registry */}
      {activeTab === "capabilities" && (
        <div className="settings-studio-card" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
              <div>
                <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>
                  ⚡ Enterprise Platform Capabilities &amp; Tool Registry
                </h2>
                <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>
                  Platform-neutral, capability-based quality architecture (Sections 4, 6 &amp; 7 of Master Architecture). Decoupled from specific libraries, clouds, or vendors.
                </p>
              </div>
              <button
                type="button"
                className="btn-sm secondary"
                onClick={handleLoadCapabilities}
                disabled={loadingCaps}
              >
                {loadingCaps ? "Refreshing..." : "🔄 Refresh Registry"}
              </button>
            </div>
          </div>

          {/* Interactive Agentic Orchestrator Box */}
          <div className="panel" style={{ padding: "20px", background: "rgba(181, 18, 27, 0.03)", border: "1px solid rgba(181, 18, 27, 0.2)", borderRadius: "8px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "15px", fontWeight: 700, color: "var(--brand-primary, #b5121b)" }}>
              🎯 Dynamic Agentic Orchestration Studio
            </h3>
            <p className="muted" style={{ margin: "0 0 12px", fontSize: "12.5px" }}>
              Enter a high-level quality objective. The agent will discover active capabilities, query the tool registry, and formulate a multi-stage execution plan dynamically without hardcoded workflows.
            </p>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <input
                type="text"
                className="input-sm"
                style={{ flex: 1, minWidth: "320px" }}
                value={testObjective}
                onChange={(e) => setTestObjective(e.target.value)}
                placeholder="e.g. Test checkout flow on web and mobile, validate REST API endpoints, and commit test suite to GitHub"
              />
              <button
                type="button"
                className="btn-sm primary"
                onClick={handleGeneratePlan}
                disabled={planLoading || !testObjective.trim()}
              >
                {planLoading ? "Orchestrating..." : "⚡ Formulate Agentic Plan"}
              </button>
            </div>

            {planResult && (
              <div style={{ marginTop: "16px", padding: "14px", background: "var(--bg-card, #0f172a)", borderRadius: "6px", border: "1px solid var(--border, #334155)", fontSize: "13px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", flexWrap: "wrap" }}>
                  <strong>Plan ID: <code>{planResult.plan_id}</code></strong>
                  <span className="badge badge-success" style={{ textTransform: "uppercase" }}>{planResult.status}</span>
                </div>
                <div style={{ marginBottom: "8px" }}>
                  <span className="muted">Discovered Capabilities: </span>
                  {planResult.capabilities_discovered?.map((cap: string) => (
                    <span key={cap} className="badge badge-secondary" style={{ marginRight: "6px", fontSize: "11px" }}>{cap}</span>
                  ))}
                </div>
                <div style={{ marginBottom: "12px" }}>
                  <span className="muted">Tools Selected: </span>
                  {planResult.tools_selected?.map((tool: string) => (
                    <span key={tool} className="badge badge-secondary" style={{ marginRight: "6px", fontSize: "11px", background: "rgba(59, 130, 246, 0.15)", color: "#60a5fa" }}>{tool}</span>
                  ))}
                </div>
                <div>
                  <strong>Planned Execution Steps:</strong>
                  <ol style={{ margin: "6px 0 0", paddingLeft: "20px" }}>
                    {planResult.steps?.map((step: any) => (
                      <li key={step.step_id} style={{ margin: "4px 0" }}>
                        <b>{step.goal}</b> <span className="muted">({step.capability} &rarr; <code>{step.tool_id}</code>)</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}
          </div>

          {/* Cloud Neutrality & Provider Abstraction */}
          <div className="panel" style={{ padding: "16px", borderRadius: "8px" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: "14px", fontWeight: 700 }}>
              ☁️ Cloud Portability &amp; Provider Abstraction (Sections 13–17 &amp; 43)
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" }}>
              <div style={{ padding: "12px", background: "var(--bg-card, #0f172a)", borderRadius: "6px", border: "1px solid var(--border, #334155)" }}>
                <small className="muted">Storage Provider Interface</small>
                <div style={{ fontWeight: 600, marginTop: "4px" }}>Local Disk / Docker (Active)</div>
                <span className="badge badge-success" style={{ marginTop: "6px", display: "inline-block", fontSize: "10px" }}>✓ Pluggable Azure/GCP/AWS</span>
              </div>
              <div style={{ padding: "12px", background: "var(--bg-card, #0f172a)", borderRadius: "6px", border: "1px solid var(--border, #334155)" }}>
                <small className="muted">Secret Provider Interface</small>
                <div style={{ fontWeight: 600, marginTop: "4px" }}>Local Environment / OS (Active)</div>
                <span className="badge badge-success" style={{ marginTop: "6px", display: "inline-block", fontSize: "10px" }}>✓ Pluggable KeyVault/SecretManager</span>
              </div>
              <div style={{ padding: "12px", background: "var(--bg-card, #0f172a)", borderRadius: "6px", border: "1px solid var(--border, #334155)" }}>
                <small className="muted">Container Portability</small>
                <div style={{ fontWeight: 600, marginTop: "4px" }}>Docker &amp; Kubernetes Ready</div>
                <span className="badge badge-success" style={{ marginTop: "6px", display: "inline-block", fontSize: "10px" }}>✓ Zero-Cloud-Lockin</span>
              </div>
            </div>
          </div>

          {/* Capabilities Grid */}
          <div>
            <h3 style={{ margin: "0 0 12px", fontSize: "14px", fontWeight: 700 }}>
              Registered Platform Capabilities ({capabilitiesData.length || "18"})
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "12px" }}>
              {(capabilitiesData.length > 0 ? capabilitiesData : [
                { capability: "UI_BROWSER_AUTOMATION", name: "UI Browser Automation", category: "execution", description: "Cross-browser test execution via Playwright, Selenium, and Cypress engines.", supported_environments: ["web", "cloud"], is_available: true },
                { capability: "API_AUTOMATION", name: "API & Microservices Automation", category: "execution", description: "Automated contract verification, schema conformance, and negative payload testing.", supported_environments: ["api", "cloud"], is_available: true },
                { capability: "MOBILE_AUTOMATION", name: "Mobile App Automation", category: "execution", description: "Native and hybrid mobile execution across iOS, Android, and iPad devices.", supported_environments: ["mobile", "cloud"], is_available: true },
                { capability: "DATABASE_VALIDATION", name: "Database & State Validation", category: "execution", description: "Automated SQL query assertions, transactional consistency, and data state verification.", supported_environments: ["database", "cloud"], is_available: true },
                { capability: "VISUAL_TESTING", name: "Visual Regression & Pixel Diffing", category: "execution", description: "Multi-viewport snapshot baseline comparison and pixel diff classification.", supported_environments: ["web", "mobile"], is_available: true },
                { capability: "TEST_DATA_GENERATION", name: "Smart Test Data Generation", category: "design", description: "Synthesis of type-safe valid, invalid, boundary, and edge test datasets.", supported_environments: ["all"], is_available: true },
                { capability: "REQUIREMENT_ANALYSIS", name: "Requirement Document Analysis", category: "design", description: "Ingestion of user stories, PRDs, Word/PDF documents, and OpenAPI specs.", supported_environments: ["all"], is_available: true },
                { capability: "TEST_GENERATION", name: "AI Test Case Synthesis", category: "design", description: "Context-anchored generation of positive, negative, security, and edge scenarios.", supported_environments: ["all"], is_available: true },
                { capability: "SOURCE_CONTROL", name: "Source Control & Git Provider", category: "infrastructure", description: "Remote branch auto-resolution, change traceability, and atomic suite commits.", supported_environments: ["all"], is_available: true },
                { capability: "DEFECT_CREATION", name: "ALM Defect Synchronization", category: "governance", description: "Bi-directional synchronization with Jira Cloud and Tricentis qTest.", supported_environments: ["all"], is_available: true },
                { capability: "REPORTING", name: "Quality Intelligence & Reporting", category: "governance", description: "Allure 2 execution reports, release scorecards, and flakiness analytics.", supported_environments: ["all"], is_available: true },
                { capability: "CLOUD_STORAGE", name: "Cloud & Object Storage", category: "infrastructure", description: "Multi-cloud artifact storage across Azure Blob, GCS, AWS S3, and Local Disk.", supported_environments: ["all"], is_available: true },
              ]).map((cap) => (
                <div key={cap.capability} className="panel" style={{ padding: "14px", display: "flex", flexDirection: "column", gap: "6px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong style={{ fontSize: "13.5px" }}>{cap.name}</strong>
                    <span className="badge badge-success" style={{ fontSize: "10px" }}>✓ Ready</span>
                  </div>
                  <span className="muted" style={{ fontSize: "11px", fontFamily: "monospace" }}>{cap.capability}</span>
                  <p className="muted" style={{ margin: "2px 0", fontSize: "12px", lineHeight: 1.4 }}>{cap.description}</p>
                  <div style={{ display: "flex", gap: "4px", marginTop: "auto", flexWrap: "wrap" }}>
                    <span className="badge badge-secondary" style={{ fontSize: "10px", textTransform: "capitalize" }}>{cap.category}</span>
                    {cap.supported_environments?.map((env: string) => (
                      <span key={env} className="badge badge-secondary" style={{ fontSize: "10px" }}>{env}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Standardized Tools Table */}
          <div>
            <h3 style={{ margin: "0 0 12px", fontSize: "14px", fontWeight: 700 }}>
              Standardized Enterprise Tool Catalog ({toolsData.length || "8"})
            </h3>
            <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
              <table className="table" style={{ width: "100%", fontSize: "12.5px" }}>
                <thead>
                  <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border, #334155)" }}>
                    <th style={{ padding: "10px 14px" }}>Tool ID</th>
                    <th style={{ padding: "10px 14px" }}>Name</th>
                    <th style={{ padding: "10px 14px" }}>Capability</th>
                    <th style={{ padding: "10px 14px" }}>Version</th>
                    <th style={{ padding: "10px 14px" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(toolsData.length > 0 ? toolsData : [
                    { tool_id: "tool.generator.script", name: "Multi-Framework Script Generator", capability: "UI_BROWSER_AUTOMATION", version: "2.4.0", is_available: true },
                    { tool_id: "tool.vcs.github", name: "GitHub Git Provider Tool", capability: "SOURCE_CONTROL", version: "2.4.0", is_available: true },
                    { tool_id: "tool.api.rest", name: "REST API Testing Tool", capability: "API_AUTOMATION", version: "1.0.0", is_available: true },
                    { tool_id: "tool.data.synthesizer", name: "Smart Test Data Synthesizer", capability: "TEST_DATA_GENERATION", version: "1.0.0", is_available: true },
                    { tool_id: "tool.doc.analyzer", name: "Requirement Document Analyzer", capability: "REQUIREMENT_ANALYSIS", version: "1.0.0", is_available: true },
                    { tool_id: "tool.report.allure", name: "Allure 2 Report Generator", capability: "REPORTING", version: "1.0.0", is_available: true },
                    { tool_id: "tool.alm.jira", name: "Jira ALM Adapter", capability: "DEFECT_CREATION", version: "1.0.0", is_available: true },
                    { tool_id: "tool.alm.qtest", name: "qTest ALM Adapter", capability: "DEFECT_CREATION", version: "1.0.0", is_available: true },
                  ]).map((t) => (
                    <tr key={t.tool_id} style={{ borderBottom: "1px solid var(--border, rgba(255,255,255,0.05))" }}>
                      <td style={{ padding: "8px 14px", fontFamily: "monospace", color: "#60a5fa" }}>{t.tool_id}</td>
                      <td style={{ padding: "8px 14px", fontWeight: 600 }}>{t.name}</td>
                      <td style={{ padding: "8px 14px" }}><span className="badge badge-secondary" style={{ fontSize: "11px" }}>{t.capability}</span></td>
                      <td style={{ padding: "8px 14px", fontFamily: "monospace" }}>v{t.version}</td>
                      <td style={{ padding: "8px 14px" }}><span className="badge badge-success" style={{ fontSize: "11px" }}>Active</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
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

      {/* Tab 5: System Audit Trail & Governance */}
      {activeTab === "audit" && (
        <div className="settings-studio-card">
          <AuditLogViewer
            logs={auditLogs || []}
            onRefresh={onRefreshAuditLogs || (async () => {})}
            refreshing={Boolean(refreshingAuditLogs)}
          />
        </div>
      )}

      {/* Tab 6: System & Runtime Logs */}
      {activeTab === "systemLogs" && (
        <div className="settings-studio-card">
          <SystemLogViewer token={token} apiUrl={apiUrl} />
        </div>
      )}
    </div>
  );
}
