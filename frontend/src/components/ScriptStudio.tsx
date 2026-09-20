"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { apiFetch } from "../lib/api";
import type {
  ScriptFramework,
  FrameworkInfo,
  ScriptOutput,
  ScriptSuiteOutput,
  GitCommitResult,
} from "../types";

export interface ScriptStudioProps {
  isOpen: boolean;
  onClose: () => void;
  token?: string | null;
  testCaseId?: number | null;
  testCaseTitle?: string;
  applicationId?: number | null;
  applicationName?: string;
  onNotify: (message: string) => void;
  initialFramework?: ScriptFramework;
  initialMode?: "single" | "suite";
}

const DEFAULT_FRAMEWORKS: FrameworkInfo[] = [
  { id: "playwright", name: "Playwright", language: "TypeScript", file_extension: ".spec.ts" },
  { id: "cypress", name: "Cypress", language: "JavaScript", file_extension: ".cy.js" },
  { id: "selenium_python", name: "Selenium", language: "Python", file_extension: ".py" },
  { id: "robot", name: "Robot Framework", language: "Robot", file_extension: ".robot" },
  { id: "java_testng", name: "Java TestNG", language: "Java", file_extension: ".java" },
  { id: "jest_puppeteer", name: "Jest + Puppeteer", language: "JavaScript", file_extension: ".test.js" },
];

const FRAMEWORK_ICONS: Record<string, string> = {
  playwright: "🎭",
  cypress: "🌲",
  selenium_python: "🐍",
  robot: "🤖",
  java_testng: "☕",
  jest_puppeteer: "🎪",
};

const FRAMEWORK_BADGE_COLORS: Record<string, string> = {
  playwright: "#2e7d32",
  cypress: "#00838f",
  selenium_python: "#1565c0",
  robot: "#00695c",
  java_testng: "#d84315",
  jest_puppeteer: "#c2185b",
};

export default function ScriptStudio({
  isOpen,
  onClose,
  token,
  testCaseId,
  testCaseTitle = "Test Case",
  applicationId,
  applicationName = "Application",
  onNotify,
  initialFramework = "playwright",
  initialMode = "single",
}: ScriptStudioProps) {
  const [activeFramework, setActiveFramework] = useState<ScriptFramework>(initialFramework);
  const [supportedFrameworks, setSupportedFrameworks] = useState<FrameworkInfo[]>(DEFAULT_FRAMEWORKS);
  const [viewMode, setViewMode] = useState<"single" | "suite">(
    testCaseId ? initialMode : applicationId ? "suite" : "single"
  );

  // Single script state
  const [singleScript, setSingleScript] = useState<ScriptOutput | null>(null);
  const [loadingScript, setLoadingScript] = useState(false);

  // Suite script state
  const [suiteOutput, setSuiteOutput] = useState<ScriptSuiteOutput | null>(null);
  const [loadingSuite, setLoadingSuite] = useState(false);
  const [selectedSuiteIndex, setSelectedSuiteIndex] = useState<number>(0);
  const [suiteSearchQuery, setSuiteSearchQuery] = useState("");

  // Commit & Git state
  const [showCommitDrawer, setShowCommitDrawer] = useState(false);
  const [commitBranch, setCommitBranch] = useState("");
  const [commitMessage, setCommitMessage] = useState("");
  const [commitBasePath, setCommitBasePath] = useState("tests/skywatch/");
  const [committingToGit, setCommittingToGit] = useState(false);
  const [commitResult, setCommitResult] = useState<GitCommitResult | null>(null);
  const [commitError, setCommitError] = useState<string | null>(null);

  // Local push (legacy compat) state
  const [localPushing, setLocalPushing] = useState(false);
  const [localPushMessage, setLocalPushMessage] = useState<string | null>(null);

  // Load supported frameworks from backend
  useEffect(() => {
    if (!isOpen) return;
    let mounted = true;

    async function fetchFrameworks() {
      try {
        const res = await apiFetch<{ total: number; frameworks: FrameworkInfo[] }>(
          "/api/v1/integrations/git/supported-frameworks",
          {},
          token || undefined
        );
        if (mounted && res?.frameworks?.length > 0) {
          setSupportedFrameworks(res.frameworks);
        }
      } catch {
        // Fallback to static frameworks
      }
    }

    void fetchFrameworks();
    return () => {
      mounted = false;
    };
  }, [isOpen, token]);

  // Load single script
  const loadSingleScript = useCallback(
    async (caseId: number, framework: ScriptFramework) => {
      if (!token) return;
      setLoadingScript(true);
      setCommitResult(null);
      setCommitError(null);
      setLocalPushMessage(null);
      try {
        const res = await apiFetch<ScriptOutput>(
          `/api/v1/test-cases/${caseId}/export-script?framework=${framework}`,
          {},
          token
        );
        setSingleScript(res);
      } catch (err) {
        onNotify(err instanceof Error ? err.message : `Failed to generate ${framework} script`);
      } finally {
        setLoadingScript(false);
      }
    },
    [token, onNotify]
  );

  // Load suite scripts
  const loadSuiteScripts = useCallback(
    async (appId: number, framework: ScriptFramework) => {
      if (!token) return;
      setLoadingSuite(true);
      setCommitResult(null);
      setCommitError(null);
      try {
        const res = await apiFetch<ScriptSuiteOutput>(
          `/api/v1/test-cases/application/${appId}/export-script-suite?framework=${framework}`,
          {},
          token
        );
        setSuiteOutput(res);
        setSelectedSuiteIndex(0);
        if (!res.scripts || res.scripts.length === 0) {
          onNotify("No test cases found for this application to export.");
        }
      } catch (err) {
        onNotify(err instanceof Error ? err.message : `Failed to export ${framework} suite`);
      } finally {
        setLoadingSuite(false);
      }
    },
    [token, onNotify]
  );

  // Trigger loads when framework or mode changes
  useEffect(() => {
    if (!isOpen) return;
    if (viewMode === "single" && testCaseId) {
      void loadSingleScript(testCaseId, activeFramework);
    } else if (viewMode === "suite" && applicationId) {
      void loadSuiteScripts(applicationId, activeFramework);
    }
  }, [isOpen, viewMode, activeFramework, testCaseId, applicationId, loadSingleScript, loadSuiteScripts]);

  // Filtered suite scripts
  const filteredSuiteScripts = useMemo(() => {
    if (!suiteOutput?.scripts) return [];
    if (!suiteSearchQuery.trim()) return suiteOutput.scripts;
    const q = suiteSearchQuery.toLowerCase();
    return suiteOutput.scripts.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.filename.toLowerCase().includes(q) ||
        String(s.test_case_id).includes(q)
    );
  }, [suiteOutput, suiteSearchQuery]);

  // Active code for copy/download
  const activeScript = viewMode === "single"
    ? singleScript
    : suiteOutput?.scripts?.[selectedSuiteIndex] || null;

  // Handle Copy Code
  const handleCopyCode = () => {
    if (!activeScript) return;
    void navigator.clipboard.writeText(activeScript.code);
    onNotify(`Copied ${activeScript.filename} to clipboard!`);
  };

  // Handle Download Code
  const handleDownload = () => {
    if (!activeScript) return;
    const blob = new Blob([activeScript.code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = activeScript.filename;
    link.click();
    URL.revokeObjectURL(url);
    onNotify(`Downloaded ${activeScript.filename}`);
  };

  // Handle Copy All Suite Code
  const handleCopyAllSuite = () => {
    if (!suiteOutput?.scripts) return;
    const combined = suiteOutput.scripts
      .map((s) => `// ==========================================\n// File: ${s.filename} - ${s.title} (TC-${s.test_case_id})\n// Framework: ${s.framework}\n// ==========================================\n\n${s.code}`)
      .join("\n\n");
    void navigator.clipboard.writeText(combined);
    onNotify(`Copied entire ${suiteOutput.framework} suite (${suiteOutput.total_cases} scripts) to clipboard!`);
  };

  // Handle Remote GitHub Commit (Single or Suite)
  const handleGitCommit = async () => {
    if (!token) return;
    setCommittingToGit(true);
    setCommitError(null);
    setCommitResult(null);

    const payload: Record<string, string> = {
      framework: activeFramework,
    };
    if (commitBranch.trim()) payload.branch = commitBranch.trim();
    if (commitBasePath.trim()) payload.base_path = commitBasePath.trim();
    if (commitMessage.trim()) payload.commit_message = commitMessage.trim();

    try {
      if (viewMode === "single" && testCaseId) {
        const res = await apiFetch<GitCommitResult>(
          `/api/v1/test-cases/${testCaseId}/git-commit`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          },
          token
        );
        setCommitResult(res);
        onNotify(`Committed to GitHub branch: ${res.branch} (${res.sha.slice(0, 7)})`);
      } else if (viewMode === "suite" && applicationId) {
        const res = await apiFetch<GitCommitResult>(
          `/api/v1/test-cases/application/${applicationId}/git-commit-suite`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          },
          token
        );
        setCommitResult(res);
        onNotify(`Committed ${res.files_committed} files to GitHub branch: ${res.branch} (${res.sha.slice(0, 7)})`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "GitHub commit failed";
      setCommitError(msg);
      onNotify(msg);
    } finally {
      setCommittingToGit(false);
    }
  };

  // Handle Local Save (Legacy git-push endpoint compatibility)
  const handleLocalSave = async () => {
    if (!token || !testCaseId) return;
    setLocalPushing(true);
    setLocalPushMessage(null);
    try {
      const res = await apiFetch<{ status: string; filename: string; path: string; message: string }>(
        `/api/v1/test-cases/${testCaseId}/git-push`,
        { method: "POST" },
        token
      );
      setLocalPushMessage(`Saved locally to ${res.path}`);
      onNotify(`Spec saved locally: ${res.path}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Local save failed";
      setLocalPushMessage(`Error: ${msg}`);
      onNotify(msg);
    } finally {
      setLocalPushing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="projects-modal-overlay"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !committingToGit && !loadingScript && !loadingSuite) {
          onClose();
        }
      }}
    >
      <div
        className="panel projects-modal script-studio-modal"
        style={{
          maxWidth: "1100px",
          width: "95%",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="script-studio-title"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="projects-modal-head" style={{ flexShrink: 0, padding: "16px 20px", borderBottom: "1px solid var(--border-light)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #1f3a5f 0%, #b5121b 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "18px",
                color: "#ffffff",
                boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
              }}
            >
              ⚡
            </div>
            <div>
              <h3 id="script-studio-title" style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
                Enterprise Script Studio · Multi-Framework Code Generator
              </h3>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "2px" }}>
                <span className="muted" style={{ fontSize: "12px" }}>
                  {viewMode === "single"
                    ? `Case: ${testCaseTitle} (TC-${testCaseId})`
                    : `Application Suite: ${applicationName} (App #${applicationId})`}
                </span>
                {testCaseId && applicationId && (
                  <div style={{ display: "inline-flex", gap: "4px", marginLeft: "6px" }}>
                    <button
                      type="button"
                      className={`btn-xs ${viewMode === "single" ? "primary" : "secondary"}`}
                      onClick={() => setViewMode("single")}
                      style={{ padding: "2px 8px", fontSize: "11px" }}
                    >
                      Single Case
                    </button>
                    <button
                      type="button"
                      className={`btn-xs ${viewMode === "suite" ? "primary" : "secondary"}`}
                      onClick={() => setViewMode("suite")}
                      style={{ padding: "2px 8px", fontSize: "11px" }}
                    >
                      Full Suite
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="secondary btn-sm"
            onClick={onClose}
            disabled={committingToGit}
            aria-label="Close Script Studio"
          >
            ✕ Close
          </button>
        </div>

        {/* Framework Selector Bar */}
        <div
          style={{
            flexShrink: 0,
            padding: "10px 20px",
            background: "var(--bg-layer-2)",
            borderBottom: "1px solid var(--border-light)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginRight: "4px" }}>
              Target Framework:
            </span>
            {supportedFrameworks.map((fw) => {
              const isSelected = activeFramework === fw.id;
              const badgeColor = FRAMEWORK_BADGE_COLORS[fw.id] || "#1f3a5f";
              return (
                <button
                  key={fw.id}
                  type="button"
                  onClick={() => setActiveFramework(fw.id as ScriptFramework)}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "5px 12px",
                    borderRadius: "6px",
                    fontSize: "12px",
                    fontWeight: isSelected ? 700 : 500,
                    border: isSelected ? `2px solid ${badgeColor}` : "1px solid var(--border-light)",
                    background: isSelected ? "var(--bg-surface)" : "transparent",
                    color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    boxShadow: isSelected ? "0 2px 6px rgba(0,0,0,0.08)" : "none",
                  }}
                >
                  <span>{FRAMEWORK_ICONS[fw.id] || "📄"}</span>
                  <span>{fw.name}</span>
                  <span
                    style={{
                      fontSize: "10px",
                      padding: "1px 5px",
                      borderRadius: "4px",
                      background: isSelected ? badgeColor : "var(--border-light)",
                      color: isSelected ? "#ffffff" : "var(--text-secondary)",
                      fontWeight: 600,
                    }}
                  >
                    {fw.file_extension}
                  </span>
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={handleCopyCode}
              disabled={!activeScript || loadingScript || loadingSuite}
              title="Copy current script code"
            >
              📋 Copy Code
            </button>
            {viewMode === "suite" && (
              <button
                type="button"
                className="secondary btn-sm"
                onClick={handleCopyAllSuite}
                disabled={!suiteOutput || loadingSuite}
                title="Copy all test scripts in suite"
              >
                📦 Copy All ({suiteOutput?.total_cases || 0})
              </button>
            )}
            <button
              type="button"
              className="secondary btn-sm"
              onClick={handleDownload}
              disabled={!activeScript || loadingScript || loadingSuite}
              title="Download script file"
            >
              💾 Download {activeScript?.filename || "Script"}
            </button>
            <button
              type="button"
              className="primary btn-sm"
              onClick={() => setShowCommitDrawer(!showCommitDrawer)}
              style={{
                background: "linear-gradient(135deg, #24292e 0%, #1f3a5f 100%)",
                border: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span>🐙</span>
              <span>{showCommitDrawer ? "Hide Git Commit" : "Commit to GitHub"}</span>
            </button>
          </div>
        </div>

        {/* Git Commit Config Drawer (Expandable) */}
        {showCommitDrawer && (
          <div
            style={{
              flexShrink: 0,
              padding: "14px 20px",
              background: "#0d1117",
              color: "#e6edf3",
              borderBottom: "1px solid #30363d",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              animation: "fadeIn 0.2s ease",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "16px" }}>🐙</span>
                <strong style={{ fontSize: "13px", color: "#f0f6fc" }}>
                  Remote GitHub REST API Commit
                </strong>
                <span style={{ fontSize: "11px", color: "#8b949e" }}>
                  {viewMode === "single"
                    ? "Single-file Contents API commit"
                    : `Atomic multi-file Git Trees commit (${suiteOutput?.total_cases || 0} files)`}
                </span>
              </div>
              <span style={{ fontSize: "11px", color: "#58a6ff" }}>
                Branch auto-detection enabled (detects default branch or creates new)
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.5fr auto", gap: "10px", alignItems: "end" }}>
              <div>
                <label style={{ display: "block", fontSize: "11px", color: "#8b949e", marginBottom: "4px" }}>
                  Target Branch (empty = auto-detect)
                </label>
                <input
                  type="text"
                  placeholder="e.g. main or skywatch/tests"
                  value={commitBranch}
                  onChange={(e) => setCommitBranch(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 10px",
                    background: "#161b22",
                    border: "1px solid #30363d",
                    borderRadius: "6px",
                    color: "#f0f6fc",
                    fontSize: "12px",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "11px", color: "#8b949e", marginBottom: "4px" }}>
                  Repo Directory / Base Path
                </label>
                <input
                  type="text"
                  placeholder="tests/skywatch/"
                  value={commitBasePath}
                  onChange={(e) => setCommitBasePath(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 10px",
                    background: "#161b22",
                    border: "1px solid #30363d",
                    borderRadius: "6px",
                    color: "#f0f6fc",
                    fontSize: "12px",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "11px", color: "#8b949e", marginBottom: "4px" }}>
                  Commit Message
                </label>
                <input
                  type="text"
                  placeholder={`test(automation): add ${activeFramework} tests for ${viewMode === "single" ? testCaseTitle : applicationName}`}
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 10px",
                    background: "#161b22",
                    border: "1px solid #30363d",
                    borderRadius: "6px",
                    color: "#f0f6fc",
                    fontSize: "12px",
                  }}
                />
              </div>

              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  type="button"
                  className="primary btn-sm"
                  onClick={() => void handleGitCommit()}
                  disabled={committingToGit || (!singleScript && !suiteOutput)}
                  style={{
                    background: "#238636",
                    borderColor: "#2ea043",
                    whiteSpace: "nowrap",
                    padding: "6px 16px",
                    fontSize: "12px",
                    fontWeight: 700,
                  }}
                >
                  {committingToGit
                    ? "Pushing via API..."
                    : viewMode === "single"
                    ? "🚀 Commit File"
                    : `🚀 Commit Suite (${suiteOutput?.total_cases || 0})`}
                </button>
                {testCaseId && (
                  <button
                    type="button"
                    className="secondary btn-sm"
                    onClick={() => void handleLocalSave()}
                    disabled={localPushing}
                    title="Save locally to tests/generated/ without remote Git"
                    style={{
                      background: "#21262d",
                      borderColor: "#30363d",
                      color: "#c9d1d9",
                      whiteSpace: "nowrap",
                      fontSize: "11px",
                    }}
                  >
                    {localPushing ? "Saving..." : "📁 Local Save"}
                  </button>
                )}
              </div>
            </div>

            {/* Commit Success Banner */}
            {commitResult && (
              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(35, 134, 54, 0.2)",
                  border: "1px solid #238636",
                  borderRadius: "6px",
                  fontSize: "12px",
                  color: "#3fb950",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "8px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span>✅</span>
                  <span>
                    Successfully committed to branch <strong>{commitResult.branch}</strong> (SHA:{" "}
                    <code>{commitResult.sha.slice(0, 7)}</code>)
                    {commitResult.files_committed && ` · ${commitResult.files_committed} files`}
                  </span>
                </div>
                {commitResult.url && (
                  <a
                    href={commitResult.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#58a6ff", textDecoration: "underline", fontSize: "11px" }}
                  >
                    View on GitHub ↗
                  </a>
                )}
              </div>
            )}

            {/* Commit Error Banner */}
            {commitError && (
              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(218, 54, 51, 0.2)",
                  border: "1px solid #da3633",
                  borderRadius: "6px",
                  fontSize: "12px",
                  color: "#f85149",
                }}
              >
                ❌ {commitError}
              </div>
            )}

            {/* Local Save Message */}
            {localPushMessage && (
              <div
                style={{
                  padding: "6px 10px",
                  background: "rgba(56, 139, 253, 0.15)",
                  border: "1px solid #388bfd",
                  borderRadius: "6px",
                  fontSize: "11px",
                  color: "#58a6ff",
                }}
              >
                ℹ️ {localPushMessage}
              </div>
            )}
          </div>
        )}

        {/* Content Body: Single vs Suite */}
        <div
          style={{
            flex: 1,
            display: "flex",
            overflow: "hidden",
            background: "#0f172a",
          }}
        >
          {/* Suite Sidebar */}
          {viewMode === "suite" && (
            <div
              style={{
                width: "280px",
                flexShrink: 0,
                borderRight: "1px solid rgba(255,255,255,0.08)",
                background: "#0b1120",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <div style={{ padding: "12px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                <input
                  type="text"
                  placeholder="Filter test scripts..."
                  value={suiteSearchQuery}
                  onChange={(e) => setSuiteSearchQuery(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 10px",
                    background: "#1e293b",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: "6px",
                    color: "#f8fafc",
                    fontSize: "11px",
                  }}
                />
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginTop: "6px",
                    fontSize: "11px",
                    color: "#94a3b8",
                  }}
                >
                  <span>{filteredSuiteScripts.length} of {suiteOutput?.total_cases || 0} cases</span>
                  <span>{activeFramework}</span>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto", padding: "6px" }}>
                {loadingSuite ? (
                  <div style={{ padding: "24px", textAlign: "center", color: "#94a3b8", fontSize: "12px" }}>
                    Generating {activeFramework} suite...
                  </div>
                ) : filteredSuiteScripts.length === 0 ? (
                  <div style={{ padding: "24px", textAlign: "center", color: "#94a3b8", fontSize: "12px" }}>
                    No matching scripts found.
                  </div>
                ) : (
                  filteredSuiteScripts.map((script, idx) => {
                    const isSelected = selectedSuiteIndex === idx;
                    return (
                      <button
                        key={`suite-item-${script.test_case_id}`}
                        type="button"
                        onClick={() => setSelectedSuiteIndex(idx)}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          padding: "8px 10px",
                          borderRadius: "6px",
                          marginBottom: "4px",
                          background: isSelected ? "rgba(59, 130, 246, 0.2)" : "transparent",
                          border: isSelected ? "1px solid rgba(59, 130, 246, 0.5)" : "1px solid transparent",
                          color: isSelected ? "#ffffff" : "#cbd5e1",
                          cursor: "pointer",
                          transition: "all 0.12s ease",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <strong style={{ fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {script.title}
                          </strong>
                          <span style={{ fontSize: "10px", color: "#94a3b8", marginLeft: "4px" }}>
                            TC-{script.test_case_id}
                          </span>
                        </div>
                        <div style={{ fontSize: "10px", color: "#64748b", fontFamily: "monospace", marginTop: "2px" }}>
                          {script.filename}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* Code Viewer Panel */}
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              background: "#0f172a",
            }}
          >
            {/* Code Metadata Bar */}
            <div
              style={{
                flexShrink: 0,
                padding: "8px 16px",
                background: "#0b1120",
                borderBottom: "1px solid rgba(255,255,255,0.08)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span
                  style={{
                    fontSize: "11px",
                    padding: "2px 8px",
                    borderRadius: "4px",
                    background: FRAMEWORK_BADGE_COLORS[activeFramework] || "#1f3a5f",
                    color: "#ffffff",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  {activeScript?.language || activeFramework}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: "12px", color: "#f8fafc", fontWeight: 600 }}>
                  {activeScript?.filename || "generating..."}
                </span>
                {activeScript?.test_case_id && (
                  <span style={{ fontSize: "11px", color: "#64748b" }}>
                    (TC-{activeScript.test_case_id})
                  </span>
                )}
              </div>

              <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                {activeScript?.code ? `${activeScript.code.split("\n").length} lines` : ""}
              </div>
            </div>

            {/* Code Body */}
            <div style={{ flex: 1, overflow: "auto", padding: "16px" }}>
              {loadingScript || loadingSuite ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    height: "100%",
                    gap: "12px",
                    color: "#94a3b8",
                  }}
                >
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "50%",
                      border: "3px solid rgba(255,255,255,0.1)",
                      borderTopColor: "#3b82f6",
                      animation: "spin 0.8s linear infinite",
                    }}
                  />
                  <span style={{ fontSize: "13px" }}>
                    Generating {activeFramework} automation script...
                  </span>
                </div>
              ) : activeScript?.code ? (
                <pre
                  style={{
                    margin: 0,
                    fontFamily: "var(--font-code, 'Fira Code', 'Roboto Mono', monospace)",
                    fontSize: "12.5px",
                    lineHeight: 1.6,
                    color: "#f8fafc",
                    whiteSpace: "pre",
                    tabSize: 2,
                  }}
                >
                  <code>{activeScript.code}</code>
                </pre>
              ) : (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: "100%",
                    color: "#64748b",
                    fontSize: "13px",
                  }}
                >
                  No script code generated for this test case.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
