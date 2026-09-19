"use client";

import { useState, type FormEvent } from "react";

export type IntegrationSystem = "jira" | "qtest";
export type IntegrationStatus = "untested" | "active" | "inactive" | "error";
export type IntegrationAuthType = "api_token" | "basic_api_token" | "bearer_token";
export type IntegrationAssetType =
  | "requirements"
  | "modules"
  | "releases"
  | "cycles"
  | "test_suites"
  | "test_cases"
  | "test_runs"
  | "test_logs"
  | "metadata";

export type IntegrationConnection = {
  id: number;
  system: IntegrationSystem;
  name: string;
  base_url: string;
  project_key?: string | null;
  project_name?: string | null;
  project_id?: string | null;
  username?: string | null;
  auth_type: IntegrationAuthType;
  environment?: string | null;
  status: IntegrationStatus;
  credential_configured: boolean;
  environment_backed?: boolean;
  secret_ref?: string | null;
  last_test_status?: string | null;
  last_test_message?: string | null;
  last_test_latency_ms?: number | null;
  last_tested_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IntegrationConnectionDraft = {
  system: IntegrationSystem;
  name: string;
  base_url: string;
  project_key: string;
  project_name: string;
  project_id: string;
  username: string;
  auth_type: IntegrationAuthType;
  environment: string;
  credential?: string;
  secret_ref?: string;
};

export type IntegrationTestResult = {
  connection_id: number;
  system: IntegrationSystem;
  status: "success" | "error";
  message: string;
  latency_ms: number;
  read_only: boolean;
  metadata: Record<string, unknown>;
};

export type IntegrationAssetResponse = {
  connection_id: number;
  system: IntegrationSystem;
  asset_type: IntegrationAssetType;
  items: Array<Record<string, unknown>>;
  read_only: boolean;
  next_page?: number | null;
};

export type IntegrationEnvironmentProfile = {
  configured: boolean;
  profile_name?: string | null;
  base_url?: string | null;
  username?: string | null;
  project_key?: string | null;
  filter_id?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  credential_env_name?: string | null;
  credential_configured: boolean;
};

export type IntegrationEnvironmentConfig = {
  read_only: true;
  jira: IntegrationEnvironmentProfile;
  qtest: IntegrationEnvironmentProfile;
};

export type IntegrationEnvironmentUpdate = {
  jira?: {
    base_url?: string;
    email?: string;
    api_token?: string;
    project_key?: string;
    filter_id?: string;
    profile_name?: string;
  };
  qtest?: {
    base_url?: string;
    token?: string;
    project_id?: string;
    project_name?: string;
    profile_name?: string;
  };
};

export interface IntegrationConnectionsPanelProps {
  connections: IntegrationConnection[];
  environmentConfiguration?: IntegrationEnvironmentConfig | null;
  onRefresh: () => Promise<void>;
  onUpdateEnvironment: (update: IntegrationEnvironmentUpdate) => Promise<IntegrationEnvironmentConfig>;
  onCreate: (draft: IntegrationConnectionDraft) => Promise<IntegrationConnection>;
  onUpdate: (connectionId: number, draft: IntegrationConnectionDraft) => Promise<IntegrationConnection>;
  onDelete: (connectionId: number) => Promise<void>;
  onTest: (connectionId: number) => Promise<IntegrationTestResult>;
  onSetActive: (connectionId: number, active: boolean) => Promise<IntegrationConnection>;
  onLoadAssets: (connectionId: number, assetType: IntegrationAssetType) => Promise<IntegrationAssetResponse>;
}

function emptyDraft(system: IntegrationSystem = "jira", environment?: IntegrationEnvironmentProfile): IntegrationConnectionDraft {
  return {
    system,
    name: environment?.profile_name ?? "",
    base_url: environment?.base_url ?? "",
    project_key: environment?.project_key ?? "",
    project_name: environment?.project_name ?? "",
    project_id: environment?.project_id ?? "",
    username: environment?.username ?? "",
    auth_type: system === "jira" ? "basic_api_token" : "bearer_token",
    environment: "",
    credential: "",
    secret_ref: environment?.credential_env_name ?? "",
  };
}

function formatDate(value?: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString();
}

function statusLabel(status: IntegrationStatus): string {
  return status === "untested" ? "Not tested" : status.charAt(0).toUpperCase() + status.slice(1);
}

function assetTitle(item: Record<string, unknown>): string {
  const title = item.key ?? item.name ?? item.summary ?? item.id;
  return title === undefined ? "External record" : String(title);
}

function assetSecondaryText(item: Record<string, unknown>): string {
  const summary = item.summary ?? item.description ?? item.status ?? item.project_name;
  return summary === undefined ? "Read-only external metadata" : String(summary);
}

export default function IntegrationConnectionsPanel({
  connections,
  environmentConfiguration,
  onRefresh,
  onCreate,
  onUpdate,
  onDelete,
  onTest,
  onSetActive,
  onLoadAssets,
  onUpdateEnvironment,
}: IntegrationConnectionsPanelProps) {
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<IntegrationConnectionDraft>(() => emptyDraft());
  const [saving, setSaving] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [assetConnectionId, setAssetConnectionId] = useState<number | null>(null);
  const [assetType, setAssetType] = useState<IntegrationAssetType>("requirements");
  const [assetResult, setAssetResult] = useState<IntegrationAssetResponse | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [assetError, setAssetError] = useState("");
  const selectedAssetConnection = connections.find((connection) => connection.id === assetConnectionId);
  const [environmentFormOpen, setEnvironmentFormOpen] = useState(false);
  const [environmentSaving, setEnvironmentSaving] = useState(false);
  const [environmentDraft, setEnvironmentDraft] = useState<IntegrationEnvironmentUpdate>({});

  const updateDraft = <K extends keyof IntegrationConnectionDraft>(field: K, value: IntegrationConnectionDraft[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const openCreate = (system: IntegrationSystem) => {
    setEditingId(null);
    setDraft(emptyDraft(system, environmentConfiguration?.[system]));
    setFormOpen(true);
    setMessage(null);
  };

  const openEdit = (connection: IntegrationConnection) => {
    setEditingId(connection.id);
    setDraft({
      system: connection.system,
      name: connection.name,
      base_url: connection.base_url,
      project_key: connection.project_key ?? "",
      project_name: connection.project_name ?? "",
      project_id: connection.project_id ?? "",
      username: connection.username ?? "",
      auth_type: connection.auth_type,
      environment: connection.environment ?? "",
      credential: "",
      secret_ref: connection.secret_ref ?? "",
    });
    setFormOpen(true);
    setMessage(null);
  };

  const closeForm = () => {
    if (saving) return;
    setFormOpen(false);
    setEditingId(null);
    setDraft(emptyDraft());
  };

  const submitProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const payload: IntegrationConnectionDraft = {
        ...draft,
        name: draft.name.trim(),
        base_url: draft.base_url.trim(),
        project_key: draft.project_key.trim(),
        project_name: draft.project_name.trim(),
        project_id: draft.project_id.trim(),
        username: draft.username.trim(),
        environment: draft.environment.trim(),
        credential: draft.credential?.trim() || undefined,
        secret_ref: draft.credential?.trim() ? undefined : draft.secret_ref?.trim() || undefined,
      };
      if (editingId) await onUpdate(editingId, payload);
      else await onCreate(payload);
      setMessage({ tone: "success", text: editingId ? "Connection profile updated." : "Connection profile created." });
      closeForm();
      await onRefresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to save connection profile." });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (connection: IntegrationConnection) => {
    setWorkingId(connection.id);
    setMessage(null);
    try {
      const result = await onTest(connection.id);
      setMessage({
        tone: result.status === "success" ? "success" : "error",
        text: `${result.message} ${result.latency_ms} ms. Read-only validation: ${result.read_only ? "yes" : "no"}.`,
      });
      await onRefresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Connection test failed." });
    } finally {
      setWorkingId(null);
    }
  };

  const handleToggle = async (connection: IntegrationConnection) => {
    setWorkingId(connection.id);
    setMessage(null);
    try {
      await onSetActive(connection.id, connection.status !== "active");
      setMessage({ tone: "success", text: connection.status === "active" ? "Connection deactivated." : "Connection activated." });
      await onRefresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to change connection status." });
    } finally {
      setWorkingId(null);
    }
  };

  const handleDelete = async (connection: IntegrationConnection) => {
    if (!window.confirm(`Delete the local ${connection.system.toUpperCase()} profile "${connection.name}"? This does not change external records.`)) return;
    setWorkingId(connection.id);
    setMessage(null);
    try {
      await onDelete(connection.id);
      if (assetConnectionId === connection.id) {
        setAssetConnectionId(null);
        setAssetResult(null);
      }
      setMessage({ tone: "success", text: "Local connection profile deleted. External records were not changed." });
      await onRefresh();
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to delete connection profile." });
    } finally {
      setWorkingId(null);
    }
  };

  const handleLoadAssets = async () => {
    if (!assetConnectionId) return;
    setAssetLoading(true);
    setAssetError("");
    try {
      setAssetResult(await onLoadAssets(assetConnectionId, assetType));
    } catch (error) {
      setAssetResult(null);
      setAssetError(error instanceof Error ? error.message : "Unable to load external metadata.");
    } finally {
      setAssetLoading(false);
    }
  };

  const openEnvironmentEditor = () => {
    if (!environmentConfiguration) return;
    setEnvironmentDraft({
      jira: {
        base_url: environmentConfiguration.jira.base_url ?? "",
        email: environmentConfiguration.jira.username ?? "",
        project_key: environmentConfiguration.jira.project_key ?? "",
        filter_id: environmentConfiguration.jira.filter_id ?? "",
        profile_name: environmentConfiguration.jira.profile_name ?? "",
      },
      qtest: {
        base_url: environmentConfiguration.qtest.base_url ?? "",
        project_id: environmentConfiguration.qtest.project_id ?? "",
        project_name: environmentConfiguration.qtest.project_name ?? "",
        profile_name: environmentConfiguration.qtest.profile_name ?? "",
      },
    });
    setEnvironmentFormOpen(true);
    setMessage(null);
  };

  const closeEnvironmentEditor = () => {
    if (environmentSaving) return;
    setEnvironmentFormOpen(false);
    setEnvironmentDraft({});
  };

  const updateJiraEnvironmentDraft = (field: keyof NonNullable<IntegrationEnvironmentUpdate["jira"]>, value: string) => {
    setEnvironmentDraft((current) => ({ ...current, jira: { ...(current.jira ?? {}), [field]: value } }));
  };

  const updateQTestEnvironmentDraft = (field: keyof NonNullable<IntegrationEnvironmentUpdate["qtest"]>, value: string) => {
    setEnvironmentDraft((current) => ({ ...current, qtest: { ...(current.qtest ?? {}), [field]: value } }));
  };

  const saveEnvironmentConfiguration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setEnvironmentSaving(true);
    setMessage(null);
    const jira = environmentDraft.jira;
    const qtest = environmentDraft.qtest;
    const jiraUpdate = jira ? {
      base_url: jira.base_url?.trim(),
      email: jira.email?.trim(),
      project_key: jira.project_key?.trim(),
      filter_id: jira.filter_id?.trim(),
      profile_name: jira.profile_name?.trim(),
      ...(jira.api_token?.trim() ? { api_token: jira.api_token.trim() } : {}),
    } : undefined;
    const qtestUpdate = qtest ? {
      base_url: qtest.base_url?.trim(),
      project_id: qtest.project_id?.trim(),
      project_name: qtest.project_name?.trim(),
      profile_name: qtest.profile_name?.trim(),
      ...(qtest.token?.trim() ? { token: qtest.token.trim() } : {}),
    } : undefined;
    const update: IntegrationEnvironmentUpdate = {
      jira: jiraUpdate && Object.values(jiraUpdate).some((value) => Boolean(value)) ? jiraUpdate : undefined,
      qtest: qtestUpdate && Object.values(qtestUpdate).some((value) => Boolean(value)) ? qtestUpdate : undefined,
    };
    try {
      await onUpdateEnvironment(update);
      await onRefresh();
      setEnvironmentFormOpen(false);
      setEnvironmentDraft({});
      setMessage({ tone: "success", text: "Environment configuration saved locally. External Jira and qTest records were not changed." });
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Unable to save environment configuration." });
    } finally {
      setEnvironmentSaving(false);
    }
  };

  return (
    <section className="integration-studio" aria-labelledby="integrations-heading">
      <div className="integration-section-heading">
        <div>
          <p className="integration-eyebrow">Enterprise connectors</p>
          <h2 id="integrations-heading">Jira and qTest integrations</h2>
          <p className="settings-field-help">Manage local connection profiles and inspect bounded Jira/qTest metadata. External records are read-only.</p>
        </div>
        <div className="integration-heading-actions">
          <button type="button" className="btn btn-secondary" onClick={() => openCreate("jira")}>Add Jira profile</button>
          <button type="button" className="btn btn-secondary" onClick={() => openCreate("qtest")}>Add qTest profile</button>
          <button type="button" className="btn btn-secondary" onClick={() => void onRefresh()}>Refresh</button>
        </div>
      </div>

      {message ? <div className={`settings-alert ${message.tone === "success" ? "success" : "error"}`} role="status">{message.text}</div> : null}

      {environmentConfiguration ? (
        <div className="integration-environment-panel">
          <div className="integration-section-heading compact">
            <div>
              <p className="integration-eyebrow">Environment-backed configuration</p>
              <h3>Read-only external access</h3>
              <p className="settings-field-help">Connection URLs, project identifiers, and credentials are loaded from the backend environment. Tokens are never returned to the browser.</p>
            </div>
            <div className="integration-environment-heading-actions">
              <span className="integration-readonly-badge">GET only</span>
              <button type="button" className="btn btn-secondary" onClick={openEnvironmentEditor} disabled={environmentSaving}>Edit configuration</button>
            </div>
          </div>
          <div className="integration-environment-grid">
            {(["jira", "qtest"] as const).map((system) => {
              const profile = environmentConfiguration[system];
              const project = system === "jira"
                ? profile.project_key || (profile.filter_id ? `Filter ${profile.filter_id}` : "Project not configured")
                : profile.project_id || profile.project_name || "Project not configured";
              return (
                <article className="integration-environment-card" key={system}>
                  <div>
                    <strong>{system === "jira" ? "Jira" : "qTest"}</strong>
                    <span className={`integration-status ${profile.configured ? "active" : "untested"}`}>
                      <span className="integration-status-dot" />{profile.configured ? "Configured" : "Not configured"}
                    </span>
                  </div>
                  <span>{profile.base_url || `Set ${system === "jira" ? "JIRA_BASE_URL" : "QTEST_BASE_URL"}`}</span>
                  <span>{project}</span>
                  <span>{profile.credential_configured ? `Credential: ${profile.credential_env_name || "environment"}` : "Credential not configured"}</span>
                </article>
              );
            })}
          </div>
        </div>
      ) : null}

      {environmentFormOpen && environmentConfiguration ? (
        <form className="integration-environment-form" onSubmit={(event) => void saveEnvironmentConfiguration(event)}>
          <div className="integration-form-heading">
            <div>
              <h3>Edit environment configuration</h3>
              <p className="settings-field-help">Save updates the local backend environment file. Leave token fields blank to keep the current secret. No Jira or qTest record is changed.</p>
            </div>
            <button type="button" className="btn btn-secondary" onClick={closeEnvironmentEditor} disabled={environmentSaving}>Cancel</button>
          </div>
          <div className="integration-environment-edit-grid">
            <fieldset className="integration-environment-edit-card">
              <legend>Jira</legend>
              <label className="settings-label">Base URL
                <input className="settings-input" type="url" value={environmentDraft.jira?.base_url ?? ""} onChange={(event) => updateJiraEnvironmentDraft("base_url", event.target.value)} placeholder="https://your-jira.example.com" required />
              </label>
              <label className="settings-label">Email
                <input className="settings-input" type="email" value={environmentDraft.jira?.email ?? ""} onChange={(event) => updateJiraEnvironmentDraft("email", event.target.value)} placeholder="Jira account email" required />
              </label>
              <label className="settings-label">Project key
                <input className="settings-input" value={environmentDraft.jira?.project_key ?? ""} onChange={(event) => updateJiraEnvironmentDraft("project_key", event.target.value)} placeholder="Optional when filter ID is set" />
              </label>
              <label className="settings-label">Filter ID
                <input className="settings-input" inputMode="numeric" value={environmentDraft.jira?.filter_id ?? ""} onChange={(event) => updateJiraEnvironmentDraft("filter_id", event.target.value)} placeholder="Numeric Jira filter ID" />
              </label>
              <label className="settings-label">Profile name
                <input className="settings-input" value={environmentDraft.jira?.profile_name ?? ""} onChange={(event) => updateJiraEnvironmentDraft("profile_name", event.target.value)} placeholder="Jira environment" />
              </label>
              <label className="settings-label">Replace API token
                <input className="settings-input" type="password" value={environmentDraft.jira?.api_token ?? ""} onChange={(event) => updateJiraEnvironmentDraft("api_token", event.target.value)} placeholder="Leave blank to keep current token" autoComplete="new-password" />
              </label>
            </fieldset>
            <fieldset className="integration-environment-edit-card">
              <legend>qTest</legend>
              <label className="settings-label">Base URL
                <input className="settings-input" type="url" value={environmentDraft.qtest?.base_url ?? ""} onChange={(event) => updateQTestEnvironmentDraft("base_url", event.target.value)} placeholder="https://your-qtest.example.com" />
              </label>
              <label className="settings-label">Project ID
                <input className="settings-input" value={environmentDraft.qtest?.project_id ?? ""} onChange={(event) => updateQTestEnvironmentDraft("project_id", event.target.value)} placeholder="qTest project ID" />
              </label>
              <label className="settings-label">Project name
                <input className="settings-input" value={environmentDraft.qtest?.project_name ?? ""} onChange={(event) => updateQTestEnvironmentDraft("project_name", event.target.value)} placeholder="qTest project name" />
              </label>
              <label className="settings-label">Profile name
                <input className="settings-input" value={environmentDraft.qtest?.profile_name ?? ""} onChange={(event) => updateQTestEnvironmentDraft("profile_name", event.target.value)} placeholder="qTest environment" />
              </label>
              <label className="settings-label">Replace bearer token
                <input className="settings-input" type="password" value={environmentDraft.qtest?.token ?? ""} onChange={(event) => updateQTestEnvironmentDraft("token", event.target.value)} placeholder="Leave blank to keep current token" autoComplete="new-password" />
              </label>
            </fieldset>
          </div>
          <div className="integration-form-actions">
            <button type="submit" className="btn btn-primary" disabled={environmentSaving}>{environmentSaving ? "Saving configuration..." : "Save local configuration"}</button>
          </div>
        </form>
      ) : null}

      {formOpen ? (
        <form className="integration-profile-form" onSubmit={(event) => void submitProfile(event)}>
          <div className="integration-form-heading">
            <div>
              <h3>{editingId ? "Edit connection profile" : "New connection profile"}</h3>
              <p className="settings-field-help">Credentials are encrypted locally or resolved by the configured secret provider. They are never returned.</p>
            </div>
            <button type="button" className="btn btn-secondary" onClick={closeForm} disabled={saving}>Cancel</button>
          </div>
          <div className="integration-form-grid">
            <label className="settings-label">System
              <select className="settings-select" value={draft.system} onChange={(event) => {
                const system = event.target.value as IntegrationSystem;
                setDraft((current) => ({ ...current, system, auth_type: system === "jira" ? "basic_api_token" : "bearer_token" }));
              }} disabled={Boolean(editingId)}>
                <option value="jira">Jira</option>
                <option value="qtest">qTest</option>
              </select>
            </label>
            <label className="settings-label">Profile name
              <input className="settings-input" value={draft.name} onChange={(event) => updateDraft("name", event.target.value)} required maxLength={120} />
            </label>
            <label className="settings-label integration-field-wide">Base URL
              <input className="settings-input" type="url" value={draft.base_url} onChange={(event) => updateDraft("base_url", event.target.value)} placeholder="https://configured-host.example.com" required />
            </label>
            {draft.system === "jira" ? (
              <label className="settings-label">Jira project key
                <input className="settings-input" value={draft.project_key} onChange={(event) => updateDraft("project_key", event.target.value)} placeholder="From JIRA_PROJECT_KEY" required={!environmentConfiguration?.jira.filter_id} maxLength={120} />
                {environmentConfiguration?.jira.filter_id ? <span className="settings-field-help">Optional when JIRA_FILTER_ID is configured in the backend environment.</span> : null}
              </label>
            ) : (
              <>
                <label className="settings-label">qTest project ID
                  <input className="settings-input" value={draft.project_id} onChange={(event) => updateDraft("project_id", event.target.value)} placeholder="From QTEST_PROJECT_ID" maxLength={120} />
                </label>
                <label className="settings-label">qTest project name
                  <input className="settings-input" value={draft.project_name} onChange={(event) => updateDraft("project_name", event.target.value)} placeholder="From QTEST_PROJECT_NAME" maxLength={200} />
                </label>
              </>
            )}
            <label className="settings-label">Authentication
              <select className="settings-select" value={draft.auth_type} onChange={(event) => updateDraft("auth_type", event.target.value as IntegrationAuthType)}>
                <option value="basic_api_token">Username and API token</option>
                <option value="bearer_token">Bearer token</option>
                <option value="api_token">API token</option>
              </select>
            </label>
            {draft.auth_type === "basic_api_token" ? (
              <label className="settings-label">Username or email
                <input className="settings-input" type="email" value={draft.username} onChange={(event) => updateDraft("username", event.target.value)} required />
              </label>
            ) : null}
            <label className="settings-label">Environment
              <input className="settings-input" value={draft.environment} onChange={(event) => updateDraft("environment", event.target.value)} placeholder="From environment configuration" maxLength={120} />
            </label>
            <label className="settings-label">Secret reference
              <input className="settings-input" value={draft.secret_ref ?? ""} onChange={(event) => {
                const secretRef = event.target.value;
                setDraft((current) => ({ ...current, secret_ref: secretRef, ...(secretRef.trim() ? { credential: "" } : {}) }));
              }} placeholder="JIRA_API_TOKEN" pattern="[A-Z][A-Z0-9_]{1,159}" />
              <span className="settings-field-help">Use this instead of entering a token when env/Vault is configured. Entering a credential clears this field.</span>
            </label>
            <label className="settings-label">{editingId ? "Replace credential" : "Credential"}
              <input className="settings-input" type="password" value={draft.credential ?? ""} onChange={(event) => {
                const credential = event.target.value;
                setDraft((current) => ({ ...current, credential, ...(credential.trim() ? { secret_ref: "" } : {}) }));
              }} placeholder={editingId ? "Leave blank to keep current credential" : "Enter token"} required={!editingId && !draft.secret_ref} autoComplete="new-password" />
              <span className="settings-field-help">The value is write-only and will be masked after save. Entering a credential clears the secret reference.</span>
            </label>
          </div>
          <div className="integration-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : editingId ? "Save profile" : "Create profile"}</button>
          </div>
        </form>
      ) : null}

      <div className="integration-profile-table-wrap">
        <table className="integration-profile-table">
          <thead>
            <tr><th>System</th><th>Profile</th><th>Project</th><th>Status</th><th>Last tested</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {connections.length === 0 ? (
              <tr><td colSpan={6}><div className="integration-empty-state"><strong>No connector profiles yet</strong><span>Add a Jira or qTest profile to begin read-only validation.</span></div></td></tr>
            ) : connections.map((connection) => (
              <tr key={connection.id}>
                <td><span className={`integration-system-badge ${connection.system}`}>{connection.system === "jira" ? "Jira" : "qTest"}</span></td>
                <td><strong>{connection.name}</strong><span className="integration-muted">{connection.base_url}</span></td>
                <td>{connection.system === "jira" ? connection.project_key || (connection.environment_backed && environmentConfiguration?.jira.filter_id ? `Filter ${environmentConfiguration.jira.filter_id}` : "Not set") : connection.project_id || connection.project_name || "Not set"}</td>
                <td><span className={`integration-status ${connection.status}`}><span className="integration-status-dot" />{statusLabel(connection.status)}</span><span className="integration-muted">{connection.environment_backed ? "Environment-backed · GET only" : connection.credential_configured ? "Credential configured" : "Credential missing"}</span></td>
                <td><span>{formatDate(connection.last_tested_at)}</span><span className="integration-muted">{connection.last_test_latency_ms ? `${Math.round(connection.last_test_latency_ms)} ms` : ""}</span></td>
                <td>
                  <div className="integration-row-actions">
                    <button type="button" className="btn btn-secondary" onClick={() => void handleTest(connection)} disabled={workingId === connection.id}>Test</button>
                    {connection.environment_backed ? <span className="integration-readonly-badge">Environment controlled</span> : (
                      <>
                        <button type="button" className="btn btn-secondary" onClick={() => void handleToggle(connection)} disabled={workingId === connection.id}>{connection.status === "active" ? "Deactivate" : "Activate"}</button>
                        <button type="button" className="btn btn-secondary" onClick={() => openEdit(connection)} disabled={workingId === connection.id}>Edit</button>
                        <button type="button" className="btn btn-secondary" onClick={() => void handleDelete(connection)} disabled={workingId === connection.id}>Delete</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="integration-read-panel">
        <div className="integration-section-heading compact">
          <div>
            <p className="integration-eyebrow">No synchronization</p>
            <h3>Read-only external metadata</h3>
            <p className="settings-field-help">These views retrieve bounded records for review and AI context. They cannot change Jira or qTest.</p>
          </div>
        </div>
        <div className="integration-read-controls">
          <label className="settings-label">Connection
            <select className="settings-select" value={assetConnectionId ?? ""} onChange={(event) => { setAssetConnectionId(event.target.value ? Number(event.target.value) : null); setAssetResult(null); }}>
              <option value="">Choose a profile</option>
              {connections.map((connection) => <option key={connection.id} value={connection.id}>{connection.system.toUpperCase()} - {connection.name}</option>)}
            </select>
          </label>
          <label className="settings-label">Asset type
            <select className="settings-select" value={assetType} onChange={(event) => setAssetType(event.target.value as IntegrationAssetType)}>
              {(selectedAssetConnection?.system === "jira" ? ["requirements"] : ["metadata", "requirements", "modules", "releases", "cycles", "test_suites", "test_cases", "test_runs", "test_logs"]).map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
            </select>
          </label>
          <button type="button" className="btn btn-primary" onClick={() => void handleLoadAssets()} disabled={!assetConnectionId || assetLoading}>{assetLoading ? "Loading..." : "Load read-only data"}</button>
        </div>
        {assetError ? <div className="integration-inline-error">{assetError}</div> : null}
        {assetResult ? (
          <div className="integration-assets" aria-live="polite">
            <div className="integration-assets-heading"><strong>{assetResult.items.length} records</strong><span>Read-only response{assetResult.next_page ? `; next page ${assetResult.next_page}` : ""}</span></div>
            {assetResult.items.length === 0 ? <div className="integration-empty-state">No records returned for this profile.</div> : assetResult.items.map((item, index) => <article className="integration-asset-row" key={`${assetTitle(item)}-${index}`}><div><strong>{assetTitle(item)}</strong><span>{assetSecondaryText(item)}</span></div><pre>{JSON.stringify(item, null, 2)}</pre></article>)}
          </div>
        ) : null}
      </div>

    </section>
  );
}
