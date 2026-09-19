"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useAgentTaskWebSocket } from "../hooks/useAgentTaskWebSocket";
import { apiFetch } from "../lib/api";
import type { Application } from "../types";

export type StepStatus = "queued" | "in_progress" | "waiting_approval" | "completed" | "failed" | "skipped";

export type PlanStep = {
  id: string;
  index: number;
  goal: string;
  description: string;
  suggested_tools: string[];
  success_criteria: string;
  requires_approval: boolean;
  status: StepStatus;
  result_summary?: string;
  error?: string;
};

export type TaskPlan = {
  objective: string;
  steps: PlanStep[];
  rationale: string;
};

export type TraceItem = {
  id: string;
  timestamp: string;
  event_type: string;
  description: string;
  thought?: string;
  tool_call?: {
    call_id: string;
    tool_name: string;
    arguments: Record<string, unknown>;
  };
  tool_result?: {
    call_id: string;
    tool_name: string;
    success: boolean;
    data?: unknown;
    error?: string;
  };
};

export type AgentTask = {
  id: string;
  objective: string;
  application_id: number | null;
  status: string;
  plan?: TaskPlan | null;
  memory?: Record<string, unknown> | null;
  trace?: TraceItem[] | null;
  artifacts?: Record<string, unknown> | null;
  error?: string | null;
  total_steps: number;
  completed_steps: number;
  total_llm_calls: number;
  duration_ms?: number | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

type Props = {
  token: string | null;
  applications: Application[];
  selectedAppId?: number;
};

const PRESET_OBJECTIVES = [
  {
    title: "Full Smoke & Regression Suite",
    prompt: "Perform complete regression test generation for the target application: analyze key pages, discover input forms, and synthesize test cases with Playwright automation steps.",
  },
  {
    title: "Authentication & Security Scan",
    prompt: "Generate end-to-end security and authentication validation test cases covering invalid logins, SQL injection inputs, CSRF boundary checks, and session expiration.",
  },
  {
    title: "Accessibility & Responsive UX Check",
    prompt: "Scan key application pages for accessibility violations (ARIA tags, alt text, tab navigation) and test responsive layouts across desktop and mobile viewports.",
  },
  {
    title: "Executive QA & Risk Report",
    prompt: "Evaluate current test coverage, open defects, and recent execution runs to generate a comprehensive QA release readiness report with quality and risk scores.",
  },
];

export default function AgentTaskWorkspace({ token, applications, selectedAppId }: Props) {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [currentTask, setCurrentTask] = useState<AgentTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [approvalFeedback, setApprovalFeedback] = useState("");

  // New task form state
  const [objective, setObjective] = useState("");
  const [targetAppId, setTargetAppId] = useState<number | undefined>(selectedAppId);
  const [maxIterations, setMaxIterations] = useState(20);
  const [activeTab, setActiveTab] = useState<"plan" | "trace" | "artifacts" | "report">("plan");
  const [traceFilter, setTraceFilter] = useState<"all" | "thoughts" | "tools" | "errors">("all");
  const [autoScroll, setAutoScroll] = useState(true);

  const traceEndRef = useRef<HTMLDivElement>(null);

  // Load tasks list
  async function loadTasks() {
    if (!token) return;
    try {
      setLoading(true);
      const data = await apiFetch<AgentTask[]>("/api/v1/agent/tasks?limit=30", {}, token);
      setTasks(data || []);
      if (!selectedTaskId && data && data.length > 0) {
        setSelectedTaskId(data[0].id);
      }
    } catch (err) {
      console.warn("Failed to load agent tasks:", err);
    } finally {
      setLoading(false);
    }
  }

  // Load selected task details
  async function loadTaskDetail(id: string) {
    if (!token) return;
    try {
      const data = await apiFetch<AgentTask>(`/api/v1/agent/tasks/${id}`, {}, token);
      setCurrentTask(data);
    } catch (err) {
      console.warn(`Failed to load task ${id}:`, err);
    }
  }

  useEffect(() => {
    loadTasks();
  }, [token]);

  useEffect(() => {
    if (selectedTaskId) {
      loadTaskDetail(selectedTaskId);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedAppId && !targetAppId) {
      setTargetAppId(selectedAppId);
    }
  }, [selectedAppId]);

  // WebSocket for real-time live trace streaming
  const { isConnected } = useAgentTaskWebSocket(
    currentTask?.status === "executing" || currentTask?.status === "planning" || currentTask?.status === "waiting_approval"
      ? selectedTaskId
      : null,
    token,
    (event) => {
      if (event.type === "trace_entry" && event.entry) {
        setCurrentTask((prev) => {
          if (!prev || prev.id !== event.task_id) return prev;
          const currentTrace = prev.trace || [];
          return {
            ...prev,
            trace: [...currentTrace, event.entry as TraceItem],
          };
        });
      } else if (event.type === "task_completed") {
        if (selectedTaskId) {
          loadTaskDetail(selectedTaskId);
          loadTasks();
        }
      }
    }
  );

  // Auto-scroll trace view
  useEffect(() => {
    if (autoScroll && activeTab === "trace") {
      traceEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [currentTask?.trace, autoScroll, activeTab]);

  // Polling fallback when running
  useEffect(() => {
    if (!currentTask || !["planning", "executing", "waiting_approval", "queued"].includes(currentTask.status)) {
      return;
    }
    const interval = setInterval(() => {
      if (selectedTaskId) {
        loadTaskDetail(selectedTaskId);
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [currentTask?.status, selectedTaskId]);

  async function handleCreateTask(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !objective.trim()) return;

    try {
      setSubmitting(true);
      const newTask = await apiFetch<AgentTask>(
        "/api/v1/agent/tasks",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            objective: objective.trim(),
            application_id: targetAppId || null,
            max_iterations: maxIterations,
            context: {},
          }),
        },
        token
      );
      setObjective("");
      setTasks((prev) => [newTask, ...prev]);
      setSelectedTaskId(newTask.id);
      setCurrentTask(newTask);
      setActiveTab("plan");
    } catch (err) {
      alert(`Failed to launch agent task: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApproveStep(stepId: string | undefined, approved: boolean) {
    if (!token || !selectedTaskId) return;
    try {
      setApproving(true);
      const updated = await apiFetch<AgentTask>(
        `/api/v1/agent/tasks/${selectedTaskId}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            step_id: stepId,
            approved,
            feedback: approvalFeedback.trim() || undefined,
          }),
        },
        token
      );
      setCurrentTask(updated);
      setApprovalFeedback("");
      loadTasks();
    } catch (err) {
      alert(`Approval error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setApproving(false);
    }
  }

  async function handleCancelTask() {
    if (!token || !selectedTaskId) return;
    if (!confirm("Are you sure you want to cancel this running agent task?")) return;
    try {
      const updated = await apiFetch<AgentTask>(
        `/api/v1/agent/tasks/${selectedTaskId}/cancel`,
        { method: "POST" },
        token
      );
      setCurrentTask(updated);
      loadTasks();
    } catch (err) {
      alert(`Failed to cancel: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // Filtered trace
  const filteredTrace = useMemo(() => {
    const list = currentTask?.trace || [];
    if (traceFilter === "all") return list;
    if (traceFilter === "thoughts") return list.filter((t) => Boolean(t.thought));
    if (traceFilter === "tools") return list.filter((t) => Boolean(t.tool_call || t.tool_result));
    if (traceFilter === "errors") return list.filter((t) => t.tool_result && !t.tool_result.success);
    return list;
  }, [currentTask?.trace, traceFilter]);

  // Status badge styling
  function renderStatusBadge(status: string) {
    const map: Record<string, { bg: string; text: string; label: string }> = {
      queued: { bg: "bg-amber-950/60 border-amber-500/40 text-amber-300", text: "Queued", label: "Queued" },
      planning: { bg: "bg-blue-950/60 border-blue-500/40 text-blue-300 animate-pulse", text: "Planning", label: "Planning..." },
      executing: { bg: "bg-indigo-950/60 border-indigo-500/40 text-indigo-300 animate-pulse", text: "Executing", label: "Executing ReAct Loop" },
      waiting_approval: { bg: "bg-yellow-950/70 border-yellow-500 text-yellow-300 animate-bounce", text: "Waiting Approval", label: "Approval Required" },
      completed: { bg: "bg-emerald-950/60 border-emerald-500/40 text-emerald-300", text: "Completed", label: "Completed" },
      failed: { bg: "bg-red-950/60 border-red-500/40 text-red-300", text: "Failed", label: "Failed" },
      cancelled: { bg: "bg-zinc-800 border-zinc-600 text-zinc-400", text: "Cancelled", label: "Cancelled" },
    };
    const conf = map[status] || { bg: "bg-zinc-800 border-zinc-700 text-zinc-300", label: status };
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full border ${conf.bg}`}>
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {conf.label}
      </span>
    );
  }

  // Step status badge
  function renderStepBadge(status: StepStatus) {
    const map: Record<StepStatus, { color: string; label: string }> = {
      queued: { color: "text-zinc-400 bg-zinc-800/80 border-zinc-700", label: "Queued" },
      in_progress: { color: "text-blue-300 bg-blue-950/80 border-blue-600 animate-pulse", label: "In Progress" },
      waiting_approval: { color: "text-yellow-300 bg-yellow-950/80 border-yellow-500", label: "Needs Approval" },
      completed: { color: "text-emerald-300 bg-emerald-950/80 border-emerald-600", label: "Done" },
      failed: { color: "text-red-300 bg-red-950/80 border-red-600", label: "Failed" },
      skipped: { color: "text-zinc-500 bg-zinc-900 border-zinc-800", label: "Skipped" },
    };
    const c = map[status] || map.queued;
    return (
      <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${c.color}`}>
        {c.label}
      </span>
    );
  }

  const currentApprovalStep = currentTask?.plan?.steps.find((s) => s.status === "waiting_approval");

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-red-500">⚡</span> Autonomous QA Agent Studio
            </h1>
            {isConnected && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-700/50 px-2 py-0.5 rounded-full font-mono">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                Live WebSocket
              </span>
            )}
          </div>
          <p className="text-sm text-zinc-400 mt-1">
            ReAct (Reasoning + Acting) autonomous agent with dynamic task decomposition, real Playwright browser tools, self-correction, and human approval gates.
          </p>
        </div>
      </div>

      {/* Main Grid: Form + Mission Control */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Form & History (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Submit New Objective Card */}
          <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-5 shadow-lg backdrop-blur">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <span>🎯</span> Define Agent Objective
            </h2>
            <form onSubmit={handleCreateTask} className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">
                  Target Application
                </label>
                <select
                  value={targetAppId || ""}
                  onChange={(e) => setTargetAppId(e.target.value ? Number(e.target.value) : undefined)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-red-500"
                >
                  <option value="">-- All / Standalone Target --</option>
                  {applications.map((app) => (
                    <option key={app.id} value={app.id}>
                      {app.name} ({app.url || app.platform})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">
                  High-Level Objective / Instructions
                </label>
                <textarea
                  rows={4}
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  placeholder="e.g. Test the shopping cart checkout with discount coupons, verify form validations, and generate a release QA report..."
                  required
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-red-500 resize-none font-sans"
                />
              </div>

              {/* Presets */}
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-2">
                  Quick Presets
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {PRESET_OBJECTIVES.map((preset) => (
                    <button
                      key={preset.title}
                      type="button"
                      onClick={() => setObjective(preset.prompt)}
                      className="text-left text-xs bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700 p-2 rounded-lg text-zinc-300 transition-colors"
                    >
                      <div className="font-medium text-zinc-200 truncate">{preset.title}</div>
                      <div className="text-[10px] text-zinc-500 line-clamp-1 mt-0.5">{preset.prompt}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-zinc-400 pt-1">
                <span>Max ReAct Iterations:</span>
                <input
                  type="number"
                  min={5}
                  max={50}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  className="w-16 bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-center text-zinc-200"
                />
              </div>

              <button
                type="submit"
                disabled={submitting || !objective.trim()}
                className="mt-2 w-full flex items-center justify-center gap-2 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 disabled:opacity-50 text-white font-medium py-2.5 px-4 rounded-lg shadow-md transition-all text-sm cursor-pointer"
              >
                {submitting ? (
                  <>
                    <span className="inline-block animate-spin">🌀</span> Launching Agent...
                  </>
                ) : (
                  <>
                    <span>🚀</span> Deploy Autonomous Agent
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Past Tasks List Card */}
          <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-4 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>📋</span> Agent Runs ({tasks.length})
              </h2>
              <button
                onClick={loadTasks}
                className="text-xs text-zinc-400 hover:text-white transition-colors"
                title="Refresh list"
              >
                ↻ Refresh
              </button>
            </div>

            <div className="flex flex-col gap-2 max-h-[380px] overflow-y-auto pr-1">
              {tasks.length === 0 && !loading && (
                <div className="text-xs text-zinc-500 text-center py-6">
                  No agent tasks created yet. Launch one above!
                </div>
              )}
              {tasks.map((task) => {
                const isSelected = task.id === selectedTaskId;
                return (
                  <button
                    key={task.id}
                    onClick={() => setSelectedTaskId(task.id)}
                    className={`text-left p-3 rounded-lg border transition-all text-xs flex flex-col gap-1.5 cursor-pointer ${
                      isSelected
                        ? "bg-zinc-800 border-red-500/60 shadow-md"
                        : "bg-zinc-950/60 hover:bg-zinc-800/60 border-zinc-800 text-zinc-300"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-zinc-500 truncate">
                        {task.id.slice(0, 8)}...
                      </span>
                      {renderStatusBadge(task.status)}
                    </div>
                    <div className="font-medium text-zinc-200 line-clamp-2">
                      {task.objective}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-zinc-400 pt-1 border-t border-zinc-800/80">
                      <span>{task.completed_steps}/{task.total_steps} steps</span>
                      <span>{task.duration_ms ? `${Math.round(task.duration_ms / 1000)}s` : "..."}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column: Mission Control & Live Details (8 cols) */}
        <div className="lg:col-span-8 flex flex-col gap-5">
          {!currentTask ? (
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-12 text-center text-zinc-500 flex flex-col items-center justify-center min-h-[400px]">
              <span className="text-4xl mb-3">🤖</span>
              <p className="text-base font-medium text-zinc-300">No Agent Task Selected</p>
              <p className="text-sm mt-1 max-w-md">
                Select an existing run from the left panel or launch a new autonomous QA objective to inspect live reasoning and execution.
              </p>
            </div>
          ) : (
            <>
              {/* Task Header Card */}
              <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-5 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-zinc-800">
                  <div className="flex items-center gap-3">
                    {renderStatusBadge(currentTask.status)}
                    <span className="font-mono text-xs text-zinc-400">ID: {currentTask.id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {["planning", "executing", "waiting_approval"].includes(currentTask.status) && (
                      <button
                        onClick={handleCancelTask}
                        className="text-xs bg-red-950/60 hover:bg-red-900/80 border border-red-700/60 text-red-300 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                      >
                        🛑 Cancel Task
                      </button>
                    )}
                  </div>
                </div>

                {/* Objective Quote */}
                <div className="mt-3 text-sm text-zinc-200 font-medium bg-zinc-950/70 border border-zinc-800/80 rounded-lg p-3">
                  <span className="text-red-400 font-bold mr-1">Goal:</span> {currentTask.objective}
                </div>

                {/* Progress Bar & Stats */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
                  <div className="bg-zinc-950/60 border border-zinc-800 p-2.5 rounded-lg">
                    <span className="text-zinc-500 block">Steps Progress</span>
                    <span className="text-base font-semibold text-zinc-200 mt-0.5 block">
                      {currentTask.completed_steps} / {currentTask.total_steps || "?"}
                    </span>
                  </div>
                  <div className="bg-zinc-950/60 border border-zinc-800 p-2.5 rounded-lg">
                    <span className="text-zinc-500 block">LLM Decisions</span>
                    <span className="text-base font-semibold text-zinc-200 mt-0.5 block">
                      {currentTask.total_llm_calls} calls
                    </span>
                  </div>
                  <div className="bg-zinc-950/60 border border-zinc-800 p-2.5 rounded-lg">
                    <span className="text-zinc-500 block">Duration</span>
                    <span className="text-base font-semibold text-zinc-200 mt-0.5 block">
                      {currentTask.duration_ms ? `${(currentTask.duration_ms / 1000).toFixed(1)}s` : "Running..."}
                    </span>
                  </div>
                  <div className="bg-zinc-950/60 border border-zinc-800 p-2.5 rounded-lg">
                    <span className="text-zinc-500 block">Trace Events</span>
                    <span className="text-base font-semibold text-zinc-200 mt-0.5 block">
                      {currentTask.trace?.length || 0} events
                    </span>
                  </div>
                </div>
              </div>

              {/* Human-in-the-Loop Approval Banner (if paused) */}
              {currentTask.status === "waiting_approval" && (
                <div className="bg-yellow-950/50 border-2 border-yellow-500/80 rounded-xl p-4 shadow-xl">
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">⚠️</span>
                    <div className="flex-1">
                      <h3 className="text-sm font-bold text-yellow-300">
                        Action Requires Human Approval
                      </h3>
                      <p className="text-xs text-yellow-200/90 mt-1">
                        Step: <span className="font-semibold">{currentApprovalStep?.goal || "Critical Action"}</span>
                      </p>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {currentApprovalStep?.description || "This step has safety or external impact guardrails and requires your explicit confirmation before execution."}
                      </p>

                      <div className="mt-3 flex flex-col sm:flex-row gap-2">
                        <input
                          type="text"
                          value={approvalFeedback}
                          onChange={(e) => setApprovalFeedback(e.target.value)}
                          placeholder="Optional guidance / feedback for the agent..."
                          className="flex-1 bg-zinc-950 border border-yellow-700/60 rounded px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none"
                        />
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleApproveStep(currentApprovalStep?.id, true)}
                            disabled={approving}
                            className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs px-4 py-1.5 rounded transition-colors cursor-pointer"
                          >
                            ✓ Approve Step
                          </button>
                          <button
                            onClick={() => handleApproveStep(currentApprovalStep?.id, false)}
                            disabled={approving}
                            className="bg-red-700 hover:bg-red-600 text-white font-medium text-xs px-3 py-1.5 rounded transition-colors cursor-pointer"
                          >
                            ✕ Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tabs Navigation */}
              <div className="flex items-center gap-2 border-b border-zinc-800 text-sm">
                <button
                  onClick={() => setActiveTab("plan")}
                  className={`px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === "plan"
                      ? "border-red-500 text-white"
                      : "border-transparent text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <span>🗺️</span> Decomposed Plan ({currentTask.plan?.steps?.length || 0})
                </button>
                <button
                  onClick={() => setActiveTab("trace")}
                  className={`px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === "trace"
                      ? "border-red-500 text-white"
                      : "border-transparent text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <span>🧠</span> ReAct Trace ({currentTask.trace?.length || 0})
                </button>
                <button
                  onClick={() => setActiveTab("artifacts")}
                  className={`px-4 py-2.5 font-medium border-b-2 transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === "artifacts"
                      ? "border-red-500 text-white"
                      : "border-transparent text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <span>📦</span> Generated Artifacts
                </button>
              </div>

              {/* Tab 1: Decomposed Plan View */}
              {activeTab === "plan" && (
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-5 shadow-lg flex flex-col gap-4">
                  {currentTask.plan?.rationale && (
                    <div className="bg-zinc-950/80 border border-zinc-800 p-3 rounded-lg text-xs text-zinc-300">
                      <span className="font-semibold text-red-400">Agent Strategy:</span> {currentTask.plan.rationale}
                    </div>
                  )}

                  <div className="flex flex-col gap-3">
                    {(!currentTask.plan || !currentTask.plan.steps || currentTask.plan.steps.length === 0) && (
                      <div className="text-zinc-500 text-xs py-8 text-center">
                        {currentTask.status === "planning"
                          ? "LLM is analyzing objective and synthesizing plan steps..."
                          : "No plan steps recorded."}
                      </div>
                    )}

                    {currentTask.plan?.steps?.map((step, idx) => (
                      <div
                        key={step.id || idx}
                        className="bg-zinc-950/70 border border-zinc-800 rounded-lg p-4 flex flex-col gap-2"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span className="h-6 w-6 rounded-full bg-zinc-800 text-zinc-300 flex items-center justify-center font-mono text-xs font-bold">
                              {idx + 1}
                            </span>
                            <span className="font-semibold text-zinc-100 text-sm">{step.goal}</span>
                          </div>
                          {renderStepBadge(step.status)}
                        </div>

                        <p className="text-xs text-zinc-400 pl-8">{step.description}</p>

                        <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-500 pl-8 pt-1">
                          {step.suggested_tools && step.suggested_tools.length > 0 && (
                            <span>Tools: <span className="font-mono text-zinc-300">{step.suggested_tools.join(", ")}</span></span>
                          )}
                          {step.requires_approval && (
                            <span className="text-yellow-400">⚠️ Needs Approval</span>
                          )}
                        </div>

                        {step.result_summary && (
                          <div className="mt-2 text-xs bg-zinc-900/90 border border-zinc-800 rounded p-2.5 text-emerald-300 pl-3">
                            <span className="font-medium text-emerald-400">Outcome:</span> {step.result_summary}
                          </div>
                        )}
                        {step.error && (
                          <div className="mt-2 text-xs bg-red-950/40 border border-red-900/60 rounded p-2.5 text-red-300 pl-3">
                            <span className="font-medium text-red-400">Error:</span> {step.error}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tab 2: ReAct Trace Stream View */}
              {activeTab === "trace" && (
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-4 shadow-lg flex flex-col gap-3">
                  {/* Trace Toolbar */}
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-zinc-800 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-500 font-medium">Filter:</span>
                      {(["all", "thoughts", "tools", "errors"] as const).map((filter) => (
                        <button
                          key={filter}
                          onClick={() => setTraceFilter(filter)}
                          className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                            traceFilter === filter
                              ? "bg-zinc-800 text-white font-medium"
                              : "text-zinc-400 hover:text-zinc-200"
                          }`}
                        >
                          {filter.toUpperCase()}
                        </button>
                      ))}
                    </div>
                    <label className="flex items-center gap-1.5 text-zinc-400 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={autoScroll}
                        onChange={(e) => setAutoScroll(e.target.checked)}
                        className="rounded bg-zinc-950 border-zinc-700 text-red-600 focus:ring-0"
                      />
                      Auto-scroll
                    </label>
                  </div>

                  {/* Trace Entries Container */}
                  <div className="flex flex-col gap-2.5 max-h-[520px] overflow-y-auto font-mono text-xs pr-1">
                    {filteredTrace.length === 0 && (
                      <div className="text-zinc-500 text-center py-12">
                        No trace entries matching filter.
                      </div>
                    )}
                    {filteredTrace.map((entry, idx) => {
                      const isTool = Boolean(entry.tool_call || entry.tool_result);
                      const isThought = Boolean(entry.thought);
                      const isError = entry.tool_result && !entry.tool_result.success;

                      return (
                        <div
                          key={entry.id || idx}
                          className={`p-3 rounded-lg border flex flex-col gap-1.5 transition-all ${
                            isError
                              ? "bg-red-950/30 border-red-800/60 text-red-200"
                              : isTool
                              ? "bg-zinc-950/80 border-indigo-900/50 text-indigo-200"
                              : isThought
                              ? "bg-zinc-950/80 border-purple-900/50 text-purple-200"
                              : "bg-zinc-950/60 border-zinc-800 text-zinc-300"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2 text-[10px] text-zinc-500">
                            <span className="font-semibold uppercase tracking-wider text-zinc-400">
                              {entry.event_type}
                            </span>
                            <span>{new Date(entry.timestamp).toLocaleTimeString()}</span>
                          </div>

                          <div className="text-zinc-200 font-sans text-xs">
                            {entry.description}
                          </div>

                          {entry.thought && (
                            <div className="bg-purple-950/40 border border-purple-800/40 rounded p-2 text-purple-300 text-[11px] whitespace-pre-wrap">
                              <span className="font-semibold text-purple-400">Thinking: </span>
                              {entry.thought}
                            </div>
                          )}

                          {entry.tool_call && (
                            <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-[11px] text-zinc-300 overflow-x-auto">
                              <span className="font-bold text-indigo-400">
                                Tool Call → {entry.tool_call.tool_name}
                              </span>
                              <pre className="text-[10px] text-zinc-400 mt-1">
                                {JSON.stringify(entry.tool_call.arguments, null, 2)}
                              </pre>
                            </div>
                          )}

                          {entry.tool_result && (
                            <div
                              className={`border rounded p-2 text-[11px] overflow-x-auto ${
                                entry.tool_result.success
                                  ? "bg-emerald-950/30 border-emerald-800/40 text-emerald-300"
                                  : "bg-red-950/40 border-red-800/50 text-red-300"
                              }`}
                            >
                              <span className="font-bold">
                                Outcome ({entry.tool_result.tool_name}):{" "}
                                {entry.tool_result.success ? "SUCCESS" : "FAILURE"}
                              </span>
                              {entry.tool_result.error && (
                                <div className="text-red-400 mt-1">{entry.tool_result.error}</div>
                              )}
                              {Boolean(entry.tool_result.data) && (
                                <pre className="text-[10px] text-zinc-300 mt-1">
                                  {JSON.stringify(entry.tool_result.data, null, 2)}
                                </pre>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                    <div ref={traceEndRef} />
                  </div>
                </div>
              )}

              {/* Tab 3: Artifacts & QA Report */}
              {activeTab === "artifacts" && (
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-5 shadow-lg flex flex-col gap-4">
                  <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <span>📦</span> Task Artifacts
                    </h3>
                  </div>

                  {!currentTask.artifacts || Object.keys(currentTask.artifacts).length === 0 ? (
                    <div className="text-zinc-500 text-xs py-8 text-center">
                      No artifacts generated for this task yet.
                    </div>
                  ) : (
                    <div className="flex flex-col gap-4">
                      {Object.entries(currentTask.artifacts).map(([key, value]) => (
                        <div key={key} className="bg-zinc-950/80 border border-zinc-800 rounded-lg p-4">
                          <h4 className="text-xs font-bold text-red-400 uppercase tracking-wide mb-2">
                            {key}
                          </h4>
                          {typeof value === "string" ? (
                            <pre className="text-xs text-zinc-300 font-mono whitespace-pre-wrap bg-zinc-900 p-3 rounded border border-zinc-800 max-h-80 overflow-y-auto">
                              {value}
                            </pre>
                          ) : (
                            <pre className="text-xs text-zinc-300 font-mono whitespace-pre-wrap bg-zinc-900 p-3 rounded border border-zinc-800 max-h-80 overflow-y-auto">
                              {JSON.stringify(value, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
