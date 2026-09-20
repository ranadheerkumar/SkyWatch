"use client";

import { useState, type FormEvent } from "react";

export type IntegrationSystem = "jira" | "qtest" | "xray" | "github" | "gitlab";
export type IntegrationStatus = "untested" | "active" | "inactive" | "error";
export type IntegrationAuthType = "api_token" | "basic_api_token" | "bearer_token" | "oauth2_client_credentials";
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

export type FieldMappingRule = {
  source_field: string;
  target_canonical_field: string;
  transform?: string | null;
  default_value?: any;
};

export type StatusMappingRule = {
  source_status: string;
  target_canonical_status: string;
};

export type ConnectionMappings = {
  connection_id?: number;
  system?: IntegrationSystem;
  field_mappings: FieldMappingRule[];
  status_mappings: StatusMappingRule[];
};

export type SyncDirection = "bidirectional" | "import_to_skywatch" | "export_to_external";
export type SyncConflictPolicy = "external_wins" | "skywatch_wins" | "manual_review";

export type SyncExecutionRequest = {
  connection_id: number;
  direction?: SyncDirection;
  entity_types?: string[];
  conflict_policy?: SyncConflictPolicy;
  dry_run?: boolean;
};

export type SyncExecutionResponse = {
  job_id: string;
  connection_id: number;
  system: IntegrationSystem;
  direction: SyncDirection;
  status: "completed" | "failed" | "in_progress";
  entities_synced: number;
  entities_failed: number;
  conflicts_detected: number;
  error_details?: string[];
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
};

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
  onSync?: (connectionId: number, request: Partial<SyncExecutionRequest>) => Promise<SyncExecutionResponse>;
  onLoadMappings?: (connectionId: number) => Promise<ConnectionMappings>;
  onSaveMappings?: (connectionId: number, mappings: ConnectionMappings) => Promise<ConnectionMappings>;
}

function emptyDraft(system: IntegrationSystem = "jira", environment?: IntegrationEnvironmentProfile): IntegrationConnectionDraft {
  const defaultBaseUrl = system === "xray" ? "https://xray.cloud.getxray.app" : environment?.base_url ?? "";
  const defaultAuth: IntegrationAuthType =
    system === "xray" ? "oauth2_client_credentials" : system === "jira" ? "basic_api_token" : "bearer_token";
  return {
    system,
    name: environment?.profile_name ?? (system === "xray" ? "Xray Cloud Integration" : ""),
    base_url: defaultBaseUrl,
    project_key: environment?.project_key ?? "",
    project_name: environment?.project_name ?? "",
    project_id: environment?.project_id ?? "",
    username: environment?.username ?? "",
    auth_type: defaultAuth,
    environment: "",
    credential: "",
    secret_ref: environment?.credential_env_name ?? (system === "xray" ? "XRAY_CLIENT_SECRET" : ""),
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
  onSync,
  onLoadMappings,
  onSaveMappings,
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

  // Bidirectional Sync State
  const [syncModalConnection, setSyncModalConnection] = useState<IntegrationConnection | null>(null);
  const [syncDirection, setSyncDirection] = useState<SyncDirection>("bidirectional");
  const [syncConflictPolicy, setSyncConflictPolicy] = useState<SyncConflictPolicy>("external_wins");
  const [syncEntityTypes, setSyncEntityTypes] = useState<string[]>(["test_case", "test_execution"]);
  const [syncDryRun, setSyncDryRun] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncExecutionResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Field & Status Mappings State
  const [mappingsModalConnection, setMappingsModalConnection] = useState<IntegrationConnection | null>(null);
  const [mappingsActiveTab, setMappingsActiveTab] = useState<"fields" | "statuses">("fields");
  const [mappingsData, setMappingsData] = useState<ConnectionMappings | null>(null);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [mappingsSaving, setMappingsSaving] = useState(false);
  const [mappingsNotice, setMappingsNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  // New mapping rule row drafts
  const [newSourceField, setNewSourceField] = useState("");
  const [newTargetCanonicalField, setNewTargetCanonicalField] = useState("");
  const [newTransform, setNewTransform] = useState("identity");
  const [newDefaultValue, setNewDefaultValue] = useState("");
  const [newSourceStatus, setNewSourceStatus] = useState("");
  const [newTargetCanonicalStatus, setNewTargetCanonicalStatus] = useState("");

  const updateDraft = <K extends keyof IntegrationConnectionDraft>(field: K, value: IntegrationConnectionDraft[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const openCreate = (system: IntegrationSystem) => {
    setEditingId(null);
    setDraft(emptyDraft(system, system === "jira" || system === "qtest" ? environmentConfiguration?.[system] : undefined));
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

  // Sync Modal Handlers
  const openSyncModal = (connection: IntegrationConnection) => {
    setSyncModalConnection(connection);
    setSyncResult(null);
    setSyncError(null);
  };

  const closeSyncModal = () => {
    if (syncing) return;
    setSyncModalConnection(null);
  };

  const handleExecuteSync = async () => {
    if (!syncModalConnection || !onSync) return;
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const response = await onSync(syncModalConnection.id, {
        direction: syncDirection,
        conflict_policy: syncConflictPolicy,
        entity_types: syncEntityTypes,
        dry_run: syncDryRun,
      });
      setSyncResult(response);
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "Failed to execute sync job.");
    } finally {
      setSyncing(false);
    }
  };

  const toggleEntityType = (type: string) => {
    setSyncEntityTypes((current) =>
      current.includes(type) ? current.filter((t) => t !== type) : [...current, type],
    );
  };

  // Mappings Modal Handlers
  const openMappingsModal = async (connection: IntegrationConnection) => {
    setMappingsModalConnection(connection);
    setMappingsNotice(null);
    if (!onLoadMappings) return;
    setMappingsLoading(true);
    try {
      const mappings = await onLoadMappings(connection.id);
      setMappingsData(mappings);
    } catch (error) {
      setMappingsNotice({
        tone: "error",
        text: error instanceof Error ? error.message : "Failed to load mapping rules.",
      });
    } finally {
      setMappingsLoading(false);
    }
  };

  const closeMappingsModal = () => {
    if (mappingsSaving) return;
    setMappingsModalConnection(null);
    setMappingsData(null);
    setMappingsNotice(null);
  };

  const addFieldMappingRule = () => {
    if (!newSourceField.trim() || !newTargetCanonicalField.trim() || !mappingsData) return;
    const rule: FieldMappingRule = {
      source_field: newSourceField.trim(),
      target_canonical_field: newTargetCanonicalField.trim(),
      transform: newTransform.trim() || null,
      default_value: newDefaultValue.trim() || undefined,
    };
    setMappingsData({
      ...mappingsData,
      field_mappings: [...mappingsData.field_mappings, rule],
    });
    setNewSourceField("");
    setNewTargetCanonicalField("");
    setNewDefaultValue("");
  };

  const removeFieldMappingRule = (index: number) => {
    if (!mappingsData) return;
    setMappingsData({
      ...mappingsData,
      field_mappings: mappingsData.field_mappings.filter((_, idx) => idx !== index),
    });
  };

  const addStatusMappingRule = () => {
    if (!newSourceStatus.trim() || !newTargetCanonicalStatus.trim() || !mappingsData) return;
    const rule: StatusMappingRule = {
      source_status: newSourceStatus.trim(),
      target_canonical_status: newTargetCanonicalStatus.trim(),
    };
    setMappingsData({
      ...mappingsData,
      status_mappings: [...mappingsData.status_mappings, rule],
    });
    setNewSourceStatus("");
    setNewTargetCanonicalStatus("");
  };

  const removeStatusMappingRule = (index: number) => {
    if (!mappingsData) return;
    setMappingsData({
      ...mappingsData,
      status_mappings: mappingsData.status_mappings.filter((_, idx) => idx !== index),
    });
  };

  const handleSaveMappings = async () => {
    if (!mappingsModalConnection || !mappingsData || !onSaveMappings) return;
    setMappingsSaving(true);
    setMappingsNotice(null);
    try {
      const updated = await onSaveMappings(mappingsModalConnection.id, mappingsData);
      setMappingsData(updated);
      setMappingsNotice({ tone: "success", text: "Mapping rules saved successfully." });
    } catch (error) {
      setMappingsNotice({
        tone: "error",
        text: error instanceof Error ? error.message : "Unable to save mapping rules.",
      });
    } finally {
      setMappingsSaving(false);
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
    const jiraUpdate = jira
      ? {
          base_url: jira.base_url?.trim(),
          email: jira.email?.trim(),
          project_key: jira.project_key?.trim(),
          filter_id: jira.filter_id?.trim(),
          profile_name: jira.profile_name?.trim(),
          ...(jira.api_token?.trim() ? { api_token: jira.api_token.trim() } : {}),
        }
      : undefined;
    const qtestUpdate = qtest
      ? {
          base_url: qtest.base_url?.trim(),
          project_id: qtest.project_id?.trim(),
          project_name: qtest.project_name?.trim(),
          profile_name: qtest.profile_name?.trim(),
          ...(qtest.token?.trim() ? { token: qtest.token.trim() } : {}),
        }
      : undefined;
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
          <h2 id="integrations-heading">Jira, Xray, and qTest Integrations</h2>
          <p className="settings-field-help">
            Manage enterprise test management connections with bidirectional synchronization, universal schema mappings, and bounded read-only inspection.
          </p>
        </div>
        <div className="integration-heading-actions">
          <button type="button" className="btn btn-secondary" onClick={() => openCreate("jira")}>Add Jira profile</button>
          <button type="button" className="btn btn-secondary" onClick={() => openCreate("xray")}>Add Xray profile</button>
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
              <select
                className="settings-select"
                value={draft.system}
                onChange={(event) => {
                  const system = event.target.value as IntegrationSystem;
                  const defaultAuth: IntegrationAuthType =
                    system === "xray" ? "oauth2_client_credentials" : system === "jira" ? "basic_api_token" : "bearer_token";
                  const defaultBaseUrl = system === "xray" ? "https://xray.cloud.getxray.app" : draft.base_url;
                  setDraft((current) => ({
                    ...current,
                    system,
                    auth_type: defaultAuth,
                    base_url: defaultBaseUrl,
                  }));
                }}
                disabled={Boolean(editingId)}
              >
                <option value="jira">Jira</option>
                <option value="xray">Xray Test Management</option>
                <option value="qtest">Tricentis qTest</option>
                <option value="github">GitHub</option>
                <option value="gitlab">GitLab</option>
              </select>
            </label>
            <label className="settings-label">Profile name
              <input className="settings-input" value={draft.name} onChange={(event) => updateDraft("name", event.target.value)} required maxLength={120} />
            </label>
            <label className="settings-label integration-field-wide">Base URL
              <input
                className="settings-input"
                type="url"
                value={draft.base_url}
                onChange={(event) => updateDraft("base_url", event.target.value)}
                placeholder={draft.system === "xray" ? "https://xray.cloud.getxray.app" : "https://configured-host.example.com"}
                required
              />
            </label>
            {draft.system === "jira" ? (
              <label className="settings-label">Jira project key
                <input className="settings-input" value={draft.project_key} onChange={(event) => updateDraft("project_key", event.target.value)} placeholder="From JIRA_PROJECT_KEY" required={!environmentConfiguration?.jira.filter_id} maxLength={120} />
                {environmentConfiguration?.jira.filter_id ? <span className="settings-field-help">Optional when JIRA_FILTER_ID is configured in the backend environment.</span> : null}
              </label>
            ) : draft.system === "xray" ? (
              <label className="settings-label">Xray project key
                <input className="settings-input" value={draft.project_key} onChange={(event) => updateDraft("project_key", event.target.value)} placeholder="e.g. QA, PROJ" required maxLength={120} />
                <span className="settings-field-help">Target Jira project key where Xray tests and executions reside.</span>
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
                {draft.system === "xray" ? (
                  <>
                    <option value="oauth2_client_credentials">OAuth2 Client Credentials (Xray Cloud)</option>
                    <option value="bearer_token">Bearer Token / Personal Access Token (Server/DC)</option>
                    <option value="basic_api_token">Basic Auth - Username & API Token (Server/DC)</option>
                    <option value="api_token">API Token</option>
                  </>
                ) : (
                  <>
                    <option value="basic_api_token">Username and API token</option>
                    <option value="bearer_token">Bearer token</option>
                    <option value="api_token">API token</option>
                  </>
                )}
              </select>
            </label>
            {draft.auth_type === "oauth2_client_credentials" ? (
              <label className="settings-label">Client ID
                <input className="settings-input" value={draft.username} onChange={(event) => updateDraft("username", event.target.value)} placeholder="Xray Cloud Client ID" required />
              </label>
            ) : draft.auth_type === "basic_api_token" ? (
              <label className="settings-label">Username or email
                <input className="settings-input" type="email" value={draft.username} onChange={(event) => updateDraft("username", event.target.value)} required />
              </label>
            ) : null}
            <label className="settings-label">Environment
              <input className="settings-input" value={draft.environment} onChange={(event) => updateDraft("environment", event.target.value)} placeholder="From environment configuration" maxLength={120} />
            </label>
            <label className="settings-label">Secret reference
              <input
                className="settings-input"
                value={draft.secret_ref ?? ""}
                onChange={(event) => {
                  const secretRef = event.target.value;
                  setDraft((current) => ({ ...current, secret_ref: secretRef, ...(secretRef.trim() ? { credential: "" } : {}) }));
                }}
                placeholder={draft.system === "xray" ? "XRAY_CLIENT_SECRET" : "JIRA_API_TOKEN"}
                pattern="[A-Z][A-Z0-9_]{1,159}"
              />
              <span className="settings-field-help">Use this instead of entering a token when env/Vault is configured. Entering a credential clears this field.</span>
            </label>
            <label className="settings-label">
              {editingId
                ? "Replace credential"
                : draft.auth_type === "oauth2_client_credentials"
                ? "Client Secret"
                : draft.auth_type === "bearer_token"
                ? "Bearer Token"
                : "Credential"}
              <input
                className="settings-input"
                type="password"
                value={draft.credential ?? ""}
                onChange={(event) => {
                  const credential = event.target.value;
                  setDraft((current) => ({ ...current, credential, ...(credential.trim() ? { secret_ref: "" } : {}) }));
                }}
                placeholder={editingId ? "Leave blank to keep current credential" : "Enter secret/token"}
                required={!editingId && !draft.secret_ref}
                autoComplete="new-password"
              />
              <span className="settings-field-help">The value is write-only and will be masked after save. Entering a credential clears the secret reference.</span>
            </label>
          </div>
          <div className="integration-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : editingId ? "Save profile" : "Create profile"}</button>
          </div>
        </form>
      ) : null}

      {/* Connection Profiles Table */}
      <div className="integration-profile-table-wrap">
        <table className="integration-profile-table">
          <thead>
            <tr><th>System</th><th>Profile</th><th>Project</th><th>Status</th><th>Last tested</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {connections.length === 0 ? (
              <tr><td colSpan={6}><div className="integration-empty-state"><strong>No connector profiles yet</strong><span>Add a Jira, Xray, or qTest profile to begin test management synchronization.</span></div></td></tr>
            ) : connections.map((connection) => (
              <tr key={connection.id}>
                <td>
                  <span className={`integration-system-badge ${connection.system}`}>
                    {connection.system === "xray" ? "Xray" : connection.system === "jira" ? "Jira" : connection.system === "qtest" ? "qTest" : connection.system.toUpperCase()}
                  </span>
                </td>
                <td><strong>{connection.name}</strong><span className="integration-muted">{connection.base_url}</span></td>
                <td>
                  {connection.system === "jira"
                    ? connection.project_key || (connection.environment_backed && environmentConfiguration?.jira.filter_id ? `Filter ${environmentConfiguration.jira.filter_id}` : "Not set")
                    : connection.system === "xray"
                    ? connection.project_key || "Not set"
                    : connection.project_id || connection.project_name || "Not set"}
                </td>
                <td>
                  <span className={`integration-status ${connection.status}`}>
                    <span className="integration-status-dot" />{statusLabel(connection.status)}
                  </span>
                  <span className="integration-muted">{connection.environment_backed ? "Environment-backed · GET only" : connection.credential_configured ? "Credential configured" : "Credential missing"}</span>
                </td>
                <td><span>{formatDate(connection.last_tested_at)}</span><span className="integration-muted">{connection.last_test_latency_ms ? `${Math.round(connection.last_test_latency_ms)} ms` : ""}</span></td>
                <td>
                  <div className="integration-row-actions">
                    <button type="button" className="btn btn-secondary" onClick={() => void handleTest(connection)} disabled={workingId === connection.id}>Test</button>
                    {onSync ? (
                      <button type="button" className="btn btn-secondary" onClick={() => openSyncModal(connection)} disabled={workingId === connection.id}>Sync</button>
                    ) : null}
                    {onLoadMappings ? (
                      <button type="button" className="btn btn-secondary" onClick={() => void openMappingsModal(connection)} disabled={workingId === connection.id}>Mappings</button>
                    ) : null}
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

      {/* Bidirectional Sync Drawer / Modal */}
      {syncModalConnection ? (
        <div className="integration-sync-panel" role="region" aria-label="Bidirectional synchronization">
          <div className="integration-section-heading compact">
            <div>
              <p className="integration-eyebrow">Universal Sync Engine</p>
              <h3>Bidirectional Sync — {syncModalConnection.system.toUpperCase()}: {syncModalConnection.name}</h3>
              <p className="settings-field-help">Synchronize test artifacts between SkyWatch Universal Quality Model and external test management systems.</p>
            </div>
            <button type="button" className="btn btn-secondary" onClick={closeSyncModal} disabled={syncing}>Close</button>
          </div>

          <div className="integration-sync-grid">
            <label className="settings-label">Sync Direction
              <select className="settings-select" value={syncDirection} onChange={(e) => setSyncDirection(e.target.value as SyncDirection)}>
                <option value="bidirectional">Bidirectional (Two-way Synchronization)</option>
                <option value="import_to_skywatch">Import to SkyWatch (External → SkyWatch)</option>
                <option value="export_to_external">Export to External (SkyWatch → External)</option>
              </select>
            </label>

            <label className="settings-label">Conflict Resolution Policy
              <select className="settings-select" value={syncConflictPolicy} onChange={(e) => setSyncConflictPolicy(e.target.value as SyncConflictPolicy)}>
                <option value="external_wins">External Wins (External ALM is Source of Truth)</option>
                <option value="skywatch_wins">SkyWatch Wins (SkyWatch is Source of Truth)</option>
                <option value="manual_review">Manual Review (Flag for Inspection)</option>
              </select>
            </label>
          </div>

          <div>
            <span className="settings-field-help" style={{ fontWeight: 600, display: "block", marginBottom: "4px" }}>Entity Types to Sync</span>
            <div className="integration-checkbox-row">
              {[
                { id: "test_case", label: "Test Cases" },
                { id: "test_execution", label: "Test Executions / Results" },
                { id: "test_plan", label: "Test Plans" },
                { id: "test_run", label: "Test Runs / Sets" },
              ].map((entity) => (
                <label className="integration-checkbox-item" key={entity.id}>
                  <input
                    type="checkbox"
                    checked={syncEntityTypes.includes(entity.id)}
                    onChange={() => toggleEntityType(entity.id)}
                    disabled={syncing}
                  />
                  {entity.label}
                </label>
              ))}
              <label className="integration-checkbox-item" style={{ marginLeft: "16px" }}>
                <input
                  type="checkbox"
                  checked={syncDryRun}
                  onChange={(e) => setSyncDryRun(e.target.checked)}
                  disabled={syncing}
                />
                Dry Run (Simulate without committing mutations)
              </label>
            </div>
          </div>

          <div className="integration-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleExecuteSync()}
              disabled={syncing || syncEntityTypes.length === 0}
            >
              {syncing ? "Running Synchronization..." : "Execute Sync"}
            </button>
          </div>

          {syncError ? <div className="integration-inline-error">{syncError}</div> : null}

          {syncResult ? (
            <div className="integration-sync-results" aria-live="polite">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong>Sync Job {syncResult.job_id}</strong>
                  <span className="integration-muted" style={{ marginLeft: "8px" }}>Direction: {syncResult.direction}</span>
                </div>
                <span className={`integration-badge-pill ${syncResult.status}`}>
                  {syncResult.status}
                </span>
              </div>

              <div className="integration-stats-grid">
                <div className="integration-stat-card">
                  <span className="integration-stat-value success">{syncResult.entities_synced}</span>
                  <span className="integration-stat-label">Entities Synced</span>
                </div>
                <div className="integration-stat-card">
                  <span className={`integration-stat-value ${syncResult.entities_failed > 0 ? "error" : ""}`}>{syncResult.entities_failed}</span>
                  <span className="integration-stat-label">Entities Failed</span>
                </div>
                <div className="integration-stat-card">
                  <span className={`integration-stat-value ${syncResult.conflicts_detected > 0 ? "warning" : ""}`}>{syncResult.conflicts_detected}</span>
                  <span className="integration-stat-label">Conflicts</span>
                </div>
                <div className="integration-stat-card">
                  <span className="integration-stat-value">{syncResult.duration_ms ? `${Math.round(syncResult.duration_ms)} ms` : "N/A"}</span>
                  <span className="integration-stat-label">Duration</span>
                </div>
              </div>

              {syncResult.error_details && syncResult.error_details.length > 0 ? (
                <div style={{ marginTop: "12px" }}>
                  <span className="settings-field-help" style={{ color: "var(--error-dark)", fontWeight: 600 }}>Sync Failure Details:</span>
                  <ul style={{ margin: "4px 0", paddingLeft: "20px", fontSize: "var(--font-caption)", color: "var(--text-secondary)" }}>
                    {syncResult.error_details.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Field & Status Mappings Modal */}
      {mappingsModalConnection ? (
        <div className="integration-mapping-panel" role="region" aria-label="Field and Status Mappings">
          <div className="integration-section-heading compact">
            <div>
              <p className="integration-eyebrow">Universal Schema Mappings</p>
              <h3>Field & Status Mappings — {mappingsModalConnection.system.toUpperCase()}: {mappingsModalConnection.name}</h3>
              <p className="settings-field-help">Configure field transformation rules and status mappings between {mappingsModalConnection.system.toUpperCase()} and SkyWatch.</p>
            </div>
            <button type="button" className="btn btn-secondary" onClick={closeMappingsModal} disabled={mappingsSaving}>Close</button>
          </div>

          {mappingsNotice ? (
            <div className={`settings-alert ${mappingsNotice.tone === "success" ? "success" : "error"}`} role="status">
              {mappingsNotice.text}
            </div>
          ) : null}

          {mappingsLoading ? (
            <div className="integration-empty-state">Loading mappings...</div>
          ) : mappingsData ? (
            <div>
              <div className="integration-mapping-tabs">
                <button
                  type="button"
                  className={`integration-mapping-tab ${mappingsActiveTab === "fields" ? "active" : ""}`}
                  onClick={() => setMappingsActiveTab("fields")}
                >
                  Field Mappings ({mappingsData.field_mappings.length})
                </button>
                <button
                  type="button"
                  className={`integration-mapping-tab ${mappingsActiveTab === "statuses" ? "active" : ""}`}
                  onClick={() => setMappingsActiveTab("statuses")}
                >
                  Status Mappings ({mappingsData.status_mappings.length})
                </button>
              </div>

              {mappingsActiveTab === "fields" ? (
                <div style={{ marginTop: "12px" }}>
                  <table className="integration-mapping-table">
                    <thead>
                      <tr>
                        <th>Source Field ({mappingsModalConnection.system})</th>
                        <th>Target Canonical Field (SkyWatch)</th>
                        <th>Transform Rule</th>
                        <th>Default Value</th>
                        <th style={{ width: "80px" }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappingsData.field_mappings.map((rule, idx) => (
                        <tr key={idx}>
                          <td><code>{rule.source_field}</code></td>
                          <td><code>{rule.target_canonical_field}</code></td>
                          <td><span>{rule.transform || "identity"}</span></td>
                          <td><span>{rule.default_value !== undefined ? String(rule.default_value) : "—"}</span></td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "2px 6px", fontSize: "11px" }}
                              onClick={() => removeFieldMappingRule(idx)}
                              disabled={mappingsSaving}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  <div className="integration-mapping-form-row">
                    <label className="settings-label">Source Field
                      <input className="settings-input" value={newSourceField} onChange={(e) => setNewSourceField(e.target.value)} placeholder="e.g. summary, steps" />
                    </label>
                    <label className="settings-label">Target Canonical Field
                      <input className="settings-input" value={newTargetCanonicalField} onChange={(e) => setNewTargetCanonicalField(e.target.value)} placeholder="e.g. title, steps" />
                    </label>
                    <label className="settings-label">Transform
                      <select className="settings-select" value={newTransform} onChange={(e) => setNewTransform(e.target.value)}>
                        <option value="identity">identity</option>
                        <option value="uppercase">uppercase</option>
                        <option value="lowercase">lowercase</option>
                        <option value="trim">trim</option>
                      </select>
                    </label>
                    <label className="settings-label">Default Value
                      <input className="settings-input" value={newDefaultValue} onChange={(e) => setNewDefaultValue(e.target.value)} placeholder="Optional default" />
                    </label>
                    <button type="button" className="btn btn-secondary" onClick={addFieldMappingRule} disabled={!newSourceField.trim() || !newTargetCanonicalField.trim()}>
                      Add Rule
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: "12px" }}>
                  <table className="integration-mapping-table">
                    <thead>
                      <tr>
                        <th>Source Status ({mappingsModalConnection.system})</th>
                        <th>Target Canonical Status (SkyWatch)</th>
                        <th style={{ width: "80px" }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappingsData.status_mappings.map((rule, idx) => (
                        <tr key={idx}>
                          <td><code>{rule.source_status}</code></td>
                          <td><code>{rule.target_canonical_status}</code></td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "2px 6px", fontSize: "11px" }}
                              onClick={() => removeStatusMappingRule(idx)}
                              disabled={mappingsSaving}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  <div className="integration-mapping-form-row">
                    <label className="settings-label">Source Status
                      <input className="settings-input" value={newSourceStatus} onChange={(e) => setNewSourceStatus(e.target.value)} placeholder="e.g. PASSED, FAILED, TODO" />
                    </label>
                    <label className="settings-label">Target Canonical Status
                      <input className="settings-input" value={newTargetCanonicalStatus} onChange={(e) => setNewTargetCanonicalStatus(e.target.value)} placeholder="e.g. passed, failed, pending" />
                    </label>
                    <button type="button" className="btn btn-secondary" onClick={addStatusMappingRule} disabled={!newSourceStatus.trim() || !newTargetCanonicalStatus.trim()}>
                      Add Rule
                    </button>
                  </div>
                </div>
              )}

              <div className="integration-form-actions" style={{ marginTop: "16px" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleSaveMappings()}
                  disabled={mappingsSaving}
                >
                  {mappingsSaving ? "Saving Mappings..." : "Save Mappings"}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Read-Only Asset Viewer */}
      <div className="integration-read-panel">
        <div className="integration-section-heading compact">
          <div>
            <p className="integration-eyebrow">Enterprise asset inspection</p>
            <h3>Read-only external metadata</h3>
            <p className="settings-field-help">These views retrieve bounded records for review and AI context from Jira, Xray, or qTest.</p>
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
              {(selectedAssetConnection?.system === "jira"
                ? ["requirements"]
                : selectedAssetConnection?.system === "xray"
                ? ["test_cases", "metadata"]
                : ["metadata", "requirements", "modules", "releases", "cycles", "test_suites", "test_cases", "test_runs", "test_logs"]
              ).map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
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
