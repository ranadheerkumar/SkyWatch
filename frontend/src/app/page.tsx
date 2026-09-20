"use client";

import { useEffect, useMemo, useRef, useState, useDeferredValue, type ChangeEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import ApplicationCapture from "../components/ApplicationCapture";
import TestStepEditor, { parseTestSteps } from "../components/TestStepEditor";
import ParameterizedDataProfile from "../components/ParameterizedDataProfile";
import AiPromptEditor from "../components/AiPromptEditor";
import AuthScreen from "../components/auth/AuthScreen";
import { useAuth } from "../hooks/useAuth";
import { ActionBar, AppCard, EmptyState, SectionHeader, StatTile, TrendBlock } from "../components/commandCenter";
import { API_URL, apiFetch, apiFetchBlob } from "../lib/api";
import { AUTH_EXPIRED_EVENT } from "../lib/auth";
import { formatDuration, formatElapsedDuration } from "../lib/formatDuration";
import { logger } from "../lib/logger";
import { useToast } from "../hooks/useToast";
import AppIcon from "../components/navigation/AppIcon";
import WorkspaceShell from "../components/navigation/WorkspaceShell";
import {
  navigationItems as nav,
  navigationGroups,
  pathSections as PATH_SECTIONS,
  sectionPaths as SECTION_PATHS,
} from "../components/navigation/navigationConfig";
import type { ConsoleLogEntry } from "../components/AIGenerationConsole";
import type {
  IntegrationAssetResponse,
  IntegrationAssetType,
  IntegrationConnection,
  IntegrationConnectionDraft,
  IntegrationEnvironmentConfig,
  IntegrationEnvironmentUpdate,
  IntegrationTestResult,
  ConnectionMappings,
  SyncExecutionRequest,
  SyncExecutionResponse,
} from "../components/IntegrationConnectionsPanel";
import SortControl from "../components/SortControl";
import type { SortOption } from "../components/SortControl";
import { getConcurrencyLimit, runWithConcurrency } from "../lib/runWithConcurrency";
import type {
  AIGenerationMode,
  AIGenerationJob,
  AIGenerationSource,
  AIAgentStage,
  AIDocumentAnalysis,
  Application,
  ApplicationDetailTab,
  ApplicationWorkspaceRow,
  BackendExecutionState,
  BuildCaseItem,
  BuildExecutionDetail,
  BuildExecutionReport,
  BuildExecutionSummary,
  CaseExecutionDetail,
  CaseExecutionSummary,
  Defect,
  ExecutionMode,
  ExecutionResult,
  ExecutionSlowMode,
  ExecutionTraceMode,
  FailureType,
  JiraIssueDetail,
  LiveCaseExecutionProgress,
  LiveCaseExecutionStatus,
  ProjectDetailTab,
  ProjectHealthBucket,
  ProjectLifecycle,
  ProjectWorkspaceRow,
  Platform,
  RuntimeParameter,
  RunStatusSnapshot,
  RunSummary,
  ScriptFramework,
  Section,
  TestCase,
  TestCaseAutomationReadiness,
  TestSuite,
  VoiceGender,
  WorkspaceProject,
} from "../types";

const AIGenerationConsole = dynamic(() => import("../components/AIGenerationConsole"));
const AgentRecommendationsBoard = dynamic(() => import("../components/AgentRecommendationsBoard"));
const AgentTaskWorkspace = dynamic(() => import("../components/AgentTaskWorkspace"));
const ExecutionSummaryPanel = dynamic(() => import("../components/ExecutionSummaryPanel"));
const ExecutionRunConfiguration = dynamic(() => import("../components/ExecutionRunConfiguration"));
const EvidenceGalleryView = dynamic(() => import("../components/EvidenceGalleryView"));
const RunHistoryWorkspace = dynamic(() => import("../components/RunHistoryWorkspace"));
const SettingsStudio = dynamic(() => import("../components/SettingsStudio"));
const AuditLogViewer = dynamic(() => import("../components/AuditLogViewer"));
const InteractiveSystemMap = dynamic(() => import("../components/InteractiveSystemMap"));
const DefectManagementWorkspace = dynamic(() => import("../components/DefectManagementWorkspace"));
const QualityReportsWorkspace = dynamic(() => import("../components/QualityReportsWorkspace"));
const CompleteBuildReportPanel = dynamic(() => import("../components/CompleteBuildReportPanel"));
const AutonomousAuditsStudio = dynamic(() => import("../components/AutonomousAuditsStudio"));
const ObservabilityMetricsCard = dynamic(() => import("../components/ObservabilityMetricsCard"));
const GenerationLogViewer = dynamic(() => import("../components/GenerationLogViewer"));
const ScriptStudio = dynamic(() => import("../components/ScriptStudio"));
import type { GenerationLogItem } from "../components/GenerationLogViewer";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const BRAND_TITLE = process.env.NEXT_PUBLIC_BRAND_TITLE ?? "SkyWatch";
const BRAND_SUBTITLE = process.env.NEXT_PUBLIC_BRAND_SUBTITLE ?? "Autonomous QA Platform";
const WORKSPACE_NAME = process.env.NEXT_PUBLIC_WORKSPACE_NAME ?? "QA Workspace";
const PROJECT_NAME = process.env.NEXT_PUBLIC_PROJECT_NAME ?? "Default QA Project";
const PRIMARY_PROJECT_ID = process.env.NEXT_PUBLIC_PROJECT_ID ?? "default-qa-project";
const PRIMARY_PROJECT_DESCRIPTION = process.env.NEXT_PUBLIC_PROJECT_DESCRIPTION ?? "Primary QA engineering workspace for digital channels.";
import {
  PREPARED_EXECUTION_CASES_STORAGE_KEY,
  LATEST_GENERATED_CASES_STORAGE_KEY,
  EXECUTION_CONFIGURATION_STORAGE_KEY,
  TEST_DATA_PROFILE_STORAGE_KEY,
  RUNTIME_PARAMETER_KEY_PATTERN,
  DEFAULT_EXECUTION_PARALLELISM,
  DEFAULT_LOGIN_EMAIL_SELECTOR,
  DEFAULT_LOGIN_PASSWORD_SELECTOR,
  DEFAULT_LOGIN_SUBMIT_SELECTOR,
  createRuntimeParameter,
  normalizeLoginSelector,
  validateLoginSelectors,
  validateRuntimeParameters,
  buildRuntimeParameterMap,
  isSensitiveRuntimeParameter,
  buildGenerationParameterContext,
  readPreparedExecutionCaseIds,
  readLatestGeneratedCaseIds,
  sortApplicationsForDisplay,
  mapApiApplication,
  mapApiProject,
} from "../lib/runtimeParameters";

import {
  buildCategoryCoverage,
  buildExecutionTrend,
  buildDefectTrend,
  buildApplicationCaseDistribution,
  buildApplicationPassRateDistribution,
  buildDefectPriorityDistribution,
  buildDefectStatusDistribution,
  buildRunStatusDistribution,
  formatTimestamp,
  toTimestampValue,
  formatProjectLifecycle,
  formatPlatformLabel,
  inferEnvironmentLabel,
  inferProjectHealth,
  isDraftStatus,
  normaliseStatusValue,
  formatFailureTypeLabel,
} from "../lib/distributions";

import {
  LIVE_EVENT_PREFIX,
  VOICE_MODE_STORAGE_KEY,
  findSpeechVoice,
  parseLiveEventsFromLog,
  latestLiveEvent,
  mapLiveStateToExecutionPhase,
  formatLiveStateLabel,
  resolveExecutionSpeechRate,
  pumpExecutionSpeechQueue,
  stopExecutionSpeech,
  speakExecutionMessage,
  isExecutionSpeechAction,
  cleanExecutionSpeech,
} from "../lib/speech";

import {
  isVerificationOnlyLine,
  isInvalidCredentialInstruction,
  isLoginInstructionLine,
  normalizeActionTargetText,
  extractVerificationText,
  buildPollingPlan,
  getStatusMeta,
  formatConfidenceLabel,
  formatConfidenceChipLabel,
  type CaseTableDisplayRow,
  splitNonEmptyLines,
  normaliseCaseKey,
  inferRunScopeKey,
  parseAiGenerationSourceFromJob,
  normalizeGeneratedCases,
  parseStepEntries,
  buildCaseTableRows,
} from "../lib/testCaseHelpers";

import { loadAllTestCases } from "../lib/api-client";

import {
  PageTitle,
  InteractiveKpiCard,
  ProgressRing,
  TableScroll,
  Table,
  TrendLine,
  DistributionBars,
  ExecutionArtifactPreview,
  ExecutionStepEvidence,
  renderStatusChip,
  renderWorkflowStatusChip,
} from "../components/ui/DashboardWidgets";

import ExecutionDiagnosticsPanel from "../components/ExecutionDiagnosticsPanel";

const DEFAULT_AI_AGENT_STAGES: AIAgentStage[] = [
  { key: "document_analysis", name: "Document Analysis Agent", responsibility: "Extract requirements, features, business rules, and risks.", status: "queued", progress: 0, detail: "Waiting for generation input." },
  { key: "application_discovery", name: "Application Discovery Agent", responsibility: "Inspect target pages and exercise bounded safe controls for workflow signals.", status: "queued", progress: 0, detail: "Waiting for the authorized target context." },
  { key: "context_builder", name: "Context Builder Agent", responsibility: "Combine application, document, reference-case, and exploratory context.", status: "queued", progress: 0, detail: "Waiting for document and application context." },
  { key: "playwright_planner", name: "Playwright Planner Agent", responsibility: "Use observed and exploratory evidence to map coverage and exit criteria.", status: "queued", progress: 0, detail: "Waiting for context signals." },
  { key: "scenario_agent", name: "Test Scenario Agent", responsibility: "Balance positive, negative, boundary, edge, exploratory, security, and accessibility paths.", status: "queued", progress: 0, detail: "Waiting for the coverage plan." },
  { key: "test_case_generator", name: "Test Case Generator Agent", responsibility: "Generate structured cases from source and exploratory charters.", status: "queued", progress: 0, detail: "Waiting for the scenario plan." },
  { key: "test_data_generator", name: "Test Data Generator Agent", responsibility: "Synthesize realistic positive, negative, boundary, and edge test datasets informed by live application entities.", status: "queued", progress: 0, detail: "Waiting for generated test scenarios." },
  { key: "validation_agent", name: "Validation Agent", responsibility: "Check completeness, duplicates, step bounds, and coverage quality.", status: "queued", progress: 0, detail: "Waiting for generated candidates." },
  { key: "repository", name: "Repository Agent", responsibility: "Persist validated cases and compile executable automation.", status: "queued", progress: 0, detail: "Waiting for validation results." },
];

type SectionViewsMap = Record<Section, React.ReactNode>;

export default function HomePage({ initialSection }: { initialSection?: Section } = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const [section, setSection] = useState<Section>(initialSection ?? PATH_SECTIONS[pathname] ?? "dashboard");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [applications, setApplications] = useState<Application[]>([]);
  const [appName, setAppName] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem("ai-qa-engine:selected-app") ?? "";
  });
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [agentStudioTab, setAgentStudioTab] = useState<"workspace" | "recommendations" | "audits">("workspace");
  const [projectCatalog, setProjectCatalog] = useState<WorkspaceProject[]>(() => {
    const now = new Date().toISOString();
    return [{
      id: PRIMARY_PROJECT_ID,
      name: PROJECT_NAME,
      description: PRIMARY_PROJECT_DESCRIPTION,
      lifecycle: "active",
      owner: "Admin QA",
      createdAt: now,
      updatedAt: now,
    }];
  });
  const [projectSearch, setProjectSearch] = useState("");
  const [projectLifecycleFilter, setProjectLifecycleFilter] = useState<"all" | ProjectLifecycle>("all");
  const [projectHealthFilter, setProjectHealthFilter] = useState<"all" | ProjectHealthBucket>("all");
  const [projectSortBy, setProjectSortBy] = useState<"updated" | "name" | "applications" | "passRate">("updated");
  const [projectModalMode, setProjectModalMode] = useState<"create" | "edit" | null>(null);
  const [projectEditingId, setProjectEditingId] = useState<string | null>(null);
  const [projectFormName, setProjectFormName] = useState("");
  const [projectFormDescription, setProjectFormDescription] = useState("");
  const [projectFormLifecycle, setProjectFormLifecycle] = useState<ProjectLifecycle>("active");
  const [projectFormError, setProjectFormError] = useState("");
  const [savingProject, setSavingProject] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(PRIMARY_PROJECT_ID);
  const [projectDetailTab, setProjectDetailTab] = useState<ProjectDetailTab>("overview");
  const [applicationSearch, setApplicationSearch] = useState("");
  const [applicationPlatformFilter, setApplicationPlatformFilter] = useState<"all" | Platform>("all");
  const [applicationHealthFilter, setApplicationHealthFilter] = useState<"all" | ProjectHealthBucket>("all");
  const [applicationSortBy, setApplicationSortBy] = useState<"name" | "cases" | "runs" | "passRate">("name");
  const [applicationDetailTab, setApplicationDetailTab] = useState<ApplicationDetailTab>("overview");
  const [applicationEditingId, setApplicationEditingId] = useState<number | null>(null);
  const [applicationEditingOriginalName, setApplicationEditingOriginalName] = useState("");
  const [applicationFormName, setApplicationFormName] = useState("");
  const [applicationFormTarget, setApplicationFormTarget] = useState("");
  const [applicationFormPlatform, setApplicationFormPlatform] = useState<Platform>("web");
  const [applicationFormError, setApplicationFormError] = useState("");
  const [savingApplicationEdit, setSavingApplicationEdit] = useState(false);
  const [filter, setFilter] = useState("All");
  const [selectedDefectId, setSelectedDefectId] = useState<number | null>(null);
  const [defectModalMode, setDefectModalMode] = useState<"create" | "edit" | null>(null);
  const [defectEditingId, setDefectEditingId] = useState<number | null>(null);
  const [defectFormTitle, setDefectFormTitle] = useState("");
  const [defectFormDescription, setDefectFormDescription] = useState("");
  const [defectFormPriority, setDefectFormPriority] = useState("medium");
  const [defectFormSeverity, setDefectFormSeverity] = useState("major");
  const [defectFormStatus, setDefectFormStatus] = useState("open");
  const [defectFormApplicationId, setDefectFormApplicationId] = useState<number | null>(null);
  const [defectFormError, setDefectFormError] = useState("");
  const [savingDefect, setSavingDefect] = useState(false);
  const [deletingDefectId, setDeletingDefectId] = useState<number | null>(null);
  const [generated, setGenerated] = useState(false);
  const [running, setRunning] = useState(false);
  const { toast, notify } = useToast();
  const { token, ready: authReady, setToken, clearToken } = useAuth();
  const [voiceOverEnabled, setVoiceOverEnabled] = useState(false);
  const [voiceGender, setVoiceGender] = useState<VoiceGender>("male");
  const spokenExecutionEventsRef = useRef<Set<string>>(new Set());
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [liveResult, setLiveResult] = useState<ExecutionResult | null>(null);

  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState(process.env.NEXT_PUBLIC_DEFAULT_ADMIN_EMAIL ?? "");
  const [authPassword, setAuthPassword] = useState(process.env.NEXT_PUBLIC_DEFAULT_ADMIN_PASSWORD ?? "");
  const [authError, setAuthError] = useState("");
  const [authenticating, setAuthenticating] = useState(false);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [deletingTestCaseIds, setDeletingTestCaseIds] = useState<number[]>([]);
  const [defects, setDefects] = useState<Defect[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [builds, setBuilds] = useState<BuildExecutionSummary[]>([]);
  const [activeBuildReportModal, setActiveBuildReportModal] = useState<BuildExecutionReport | BuildExecutionDetail | null>(null);
  const [latestBuildReport, setLatestBuildReport] = useState<BuildExecutionReport | BuildExecutionDetail | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);
  const [runStatus, setRunStatus] = useState("Idle");
  const [runLog, setRunLog] = useState("");
  const [voiceOverEventLog, setVoiceOverEventLog] = useState<{ runId: string; log: string } | null>(null);
  const [executionRunScope, setExecutionRunScope] = useState<"all" | "draft" | "ready" | "latest" | "selected">("all");
  const [executionSelectedCaseIds, setExecutionSelectedCaseIds] = useState<number[]>([]);
  const [executionScopeDialog, setExecutionScopeDialog] = useState<{ caseIds: number[]; triggerLabel: string; fixedScope: boolean } | null>(null);
  const [executionLibrarySearch, setExecutionLibrarySearch] = useState("");
  const [executionLibraryStatusFilter, setExecutionLibraryStatusFilter] = useState<"all" | "draft" | "ready">("all");
  const [executionLibrarySortBy, setExecutionLibrarySortBy] = useState<"id" | "name" | "status" | "updated">("id");
  const [executionLibraryPageSize, setExecutionLibraryPageSize] = useState(10);
  const [executionLibraryPage, setExecutionLibraryPage] = useState(1);
  const [showCaseLibraryFilters, setShowCaseLibraryFilters] = useState(true);
  const [preparedExecutionCaseIds, setPreparedExecutionCaseIds] = useState<number[]>(readPreparedExecutionCaseIds);
  const [caseExecutions, setCaseExecutions] = useState<CaseExecutionSummary[]>([]);
  const [testSuites, setTestSuites] = useState<TestSuite[]>([]);
  const [loadingSuites, setLoadingSuites] = useState(false);
  const [suiteName, setSuiteName] = useState("");
  const [suiteDescription, setSuiteDescription] = useState("");
  const [suiteCaseSource, setSuiteCaseSource] = useState<"ready" | "all" | "latest">("ready");
  const [suiteEditingId, setSuiteEditingId] = useState<number | null>(null);
  const [suiteEditingCaseIds, setSuiteEditingCaseIds] = useState<number[] | null>(null);
  const [suiteFormError, setSuiteFormError] = useState("");
  const [creatingSuite, setCreatingSuite] = useState(false);
  const [deletingSuiteId, setDeletingSuiteId] = useState<number | null>(null);
  const [loadingCaseExecutions, setLoadingCaseExecutions] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("Generate end-to-end coverage for login, navigation, filters, and listing flows with strong assertions.");
  const [aiCaseCount, setAiCaseCount] = useState(0);
  const [replaceDraftsOnAiGenerate, setReplaceDraftsOnAiGenerate] = useState(true);
  const [aiTargetUrl, setAiTargetUrl] = useState("");
  const [aiMinSteps, setAiMinSteps] = useState(8);
  const [aiMaxSteps, setAiMaxSteps] = useState(12);
  const [aiIncludeNegative, setAiIncludeNegative] = useState(false);
  const [aiIncludeBoundary, setAiIncludeBoundary] = useState(false);
  const [aiIncludeEdge, setAiIncludeEdge] = useState(false);
  const [aiIncludeSecurity, setAiIncludeSecurity] = useState(false);
  const [aiIncludeAccessibility, setAiIncludeAccessibility] = useState(false);
  const [aiIncludeApiValidation, setAiIncludeApiValidation] = useState(false);
  const [aiIncludePerformance, setAiIncludePerformance] = useState(false);
  const [aiPerformanceBudget, setAiPerformanceBudget] = useState("");
  const [aiModuleFocus, setAiModuleFocus] = useState("");
  const [openCasesAfterGeneration, setOpenCasesAfterGeneration] = useState(false);
  const [openExecutionAfterGeneration, setOpenExecutionAfterGeneration] = useState(false);
  const [runGeneratedAfterGeneration, setRunGeneratedAfterGeneration] = useState(false);
  const [guidedDemoMode, setGuidedDemoMode] = useState(false);
  const [selectedGeneratedCaseIds, setSelectedGeneratedCaseIds] = useState<number[]>([]);
  const [consolidatingScenarios, setConsolidatingScenarios] = useState(false);
  const [bulkActionWorking, setBulkActionWorking] = useState(false);
  const [latestGeneratedCaseIds, setLatestGeneratedCaseIds] = useState<number[]>(readLatestGeneratedCaseIds);
  const [latestGenerationInput, setLatestGenerationInput] = useState<{ prompt: string; documentNames: string[] } | null>(null);
  const [savingAiTarget, setSavingAiTarget] = useState(false);
  const [refreshingData, setRefreshingData] = useState(false);
  const [importingCases, setImportingCases] = useState(false);
  const [creatingStarterCases, setCreatingStarterCases] = useState(false);
  const [clearingDrafts, setClearingDrafts] = useState(false);
  const [downloadingProgress, setDownloadingProgress] = useState(false);
  const [downloadingAiPreview, setDownloadingAiPreview] = useState(false);
  const [downloadingExecutionHistory, setDownloadingExecutionHistory] = useState(false);
  const [captureScreenshotEvidence, setCaptureScreenshotEvidence] = useState(true);
  const [highlightActionTargets, setHighlightActionTargets] = useState(true);
  const [recordVideoEvidence, setRecordVideoEvidence] = useState(true);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("watch_live");
  const [executionParallelism, setExecutionParallelism] = useState(DEFAULT_EXECUTION_PARALLELISM);
  const [executionSlowMode, setExecutionSlowMode] = useState<ExecutionSlowMode>("normal");
  const [executionTraceMode, setExecutionTraceMode] = useState<ExecutionTraceMode>("on_failure");
  const [keepBrowserOpenOnFailure, setKeepBrowserOpenOnFailure] = useState(true);
  const [keepBrowserOpenSeconds, setKeepBrowserOpenSeconds] = useState(6);
  const [runtimeParameters, setRuntimeParameters] = useState<RuntimeParameter[]>([]);
  const [generatingSmartData, setGeneratingSmartData] = useState(false);
  const [learningEntities, setLearningEntities] = useState(false);
  const resolvedRuntimeProfileApplicationRef = useRef<number | null>(null);
  const currentAiAppIdRef = useRef<number | null>(null);
  const [automationReadinessByCaseId, setAutomationReadinessByCaseId] = useState<Record<number, TestCaseAutomationReadiness>>({});
  const [authenticatedFlow, setAuthenticatedFlow] = useState(false);
  const [emailSelector, setEmailSelector] = useState(DEFAULT_LOGIN_EMAIL_SELECTOR);
  const [passwordSelector, setPasswordSelector] = useState(DEFAULT_LOGIN_PASSWORD_SELECTOR);
  const [submitSelector, setSubmitSelector] = useState(DEFAULT_LOGIN_SUBMIT_SELECTOR);
  const [aiGenerationPhase, setAiGenerationPhase] = useState<"idle" | "preparing" | "capturing" | "generating" | "publishing" | "done" | "error">("idle");
  const [aiGenerationSource, setAiGenerationSource] = useState<AIGenerationSource | null>(null);
  const [reviewingGeneratedCaseId, setReviewingGeneratedCaseId] = useState<number | null>(null);
  const [executionPhase, setExecutionPhase] = useState<"idle" | "queueing" | "running" | "finalizing" | "done" | "error">("idle");
  const [executionProgress, setExecutionProgress] = useState<{ total: number; current: number; passed: number; failed: number; activeCaseTitle: string }>({
    total: 0,
    current: 0,
    passed: 0,
    failed: 0,
    activeCaseTitle: "",
  });
  const [executionRunStartedAt, setExecutionRunStartedAt] = useState<number | null>(null);
  const [executionClockMs, setExecutionClockMs] = useState(() => Date.now());
  const [executionLiveCases, setExecutionLiveCases] = useState<LiveCaseExecutionProgress[]>([]);
  const [executionActivityLog, setExecutionActivityLog] = useState<string[]>([]);
  const [activeExecutionBatchId, setActiveExecutionBatchId] = useState<string | null>(null);
  const [stoppingExecution, setStoppingExecution] = useState(false);
  const activeBatchCancelledRef = useRef(false);

  // Playwright spec export state
  const [activePlaywrightSpecModal, setActivePlaywrightSpecModal] = useState<{ id: number; title: string; filename: string; code: string } | null>(null);
  const [fetchingPlaywrightSpec, setFetchingPlaywrightSpec] = useState(false);
  const [pushingToGit, setPushingToGit] = useState(false);
  const [gitPushMessage, setGitPushMessage] = useState("");

  // Playwright suite export state
  const [activePlaywrightSuiteModal, setActivePlaywrightSuiteModal] = useState<{
    application_id: number;
    application_name: string;
    total_specs: number;
    specs: Array<{ test_case_id: number; title: string; filename: string; code: string }>;
  } | null>(null);
  const [fetchingPlaywrightSuite, setFetchingPlaywrightSuite] = useState(false);
  const [selectedSuiteSpecIndex, setSelectedSuiteSpecIndex] = useState(0);

  // Enterprise Multi-framework Script Studio state
  const [scriptStudioOpen, setScriptStudioOpen] = useState(false);
  const [scriptStudioTestCaseId, setScriptStudioTestCaseId] = useState<number | null>(null);
  const [scriptStudioTestCaseTitle, setScriptStudioTestCaseTitle] = useState<string>("Test Case");
  const [scriptStudioApplicationId, setScriptStudioApplicationId] = useState<number | null>(null);
  const [scriptStudioApplicationName, setScriptStudioApplicationName] = useState<string>("Application");
  const [scriptStudioFramework, setScriptStudioFramework] = useState<ScriptFramework>("playwright");
  const [scriptStudioMode, setScriptStudioMode] = useState<"single" | "suite">("single");

  const openScriptStudio = (options: {
    testCaseId?: number | null;
    testCaseTitle?: string;
    applicationId?: number | null;
    applicationName?: string;
    initialFramework?: ScriptFramework;
    initialMode?: "single" | "suite";
  }) => {
    setScriptStudioTestCaseId(options.testCaseId ?? null);
    setScriptStudioTestCaseTitle(options.testCaseTitle ?? "Test Case");
    setScriptStudioApplicationId(options.applicationId ?? null);
    setScriptStudioApplicationName(options.applicationName ?? "Application");
    if (options.initialFramework) setScriptStudioFramework(options.initialFramework);
    setScriptStudioMode(options.initialMode ?? (options.testCaseId ? "single" : "suite"));
    setScriptStudioOpen(true);
  };

  // Background AI generation job tracking across navigation
  const [activeAiJobId, setActiveAiJobId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return window.sessionStorage.getItem("ai-qa-engine:active-ai-job-id");
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(EXECUTION_CONFIGURATION_STORAGE_KEY) ?? "null") as Partial<{
        executionMode: ExecutionMode;
        executionParallelism: number;
        executionSlowMode: ExecutionSlowMode;
        executionTraceMode: ExecutionTraceMode;
        voiceGender: VoiceGender;
        voiceOverEnabled: boolean;
        captureScreenshotEvidence: boolean;
        highlightActionTargets: boolean;
        recordVideoEvidence: boolean;
        keepBrowserOpenOnFailure: boolean;
        keepBrowserOpenSeconds: number;
        authenticatedFlow: boolean;
        emailSelector: string;
        passwordSelector: string;
        submitSelector: string;
        runtimeParameters: RuntimeParameter[];
      }> | null;
      if (!saved) return;
      if (saved.executionMode === "watch_live" || saved.executionMode === "background") setExecutionMode(saved.executionMode);
      const savedParallelism = saved.executionParallelism;
      if (typeof savedParallelism === "number" && Number.isInteger(savedParallelism) && savedParallelism >= 1 && savedParallelism <= 5) setExecutionParallelism(savedParallelism);
      if (saved.executionSlowMode === "normal" || saved.executionSlowMode === "demo" || saved.executionSlowMode === "showcase") setExecutionSlowMode(saved.executionSlowMode);
      if (saved.executionTraceMode === "off" || saved.executionTraceMode === "on_failure" || saved.executionTraceMode === "always") setExecutionTraceMode(saved.executionTraceMode);
      if (saved.voiceGender === "male" || saved.voiceGender === "female") setVoiceGender(saved.voiceGender);
      if (typeof saved.voiceOverEnabled === "boolean") setVoiceOverEnabled(saved.voiceOverEnabled);
      if (typeof saved.captureScreenshotEvidence === "boolean") setCaptureScreenshotEvidence(saved.captureScreenshotEvidence);
      if (typeof saved.highlightActionTargets === "boolean") setHighlightActionTargets(saved.highlightActionTargets);
      if (typeof saved.recordVideoEvidence === "boolean") setRecordVideoEvidence(saved.recordVideoEvidence);
      if (typeof saved.keepBrowserOpenOnFailure === "boolean") setKeepBrowserOpenOnFailure(saved.keepBrowserOpenOnFailure);
      const savedKeepBrowserSeconds = saved.keepBrowserOpenSeconds;
      if (typeof savedKeepBrowserSeconds === "number" && Number.isInteger(savedKeepBrowserSeconds) && savedKeepBrowserSeconds >= 0 && savedKeepBrowserSeconds <= 120) setKeepBrowserOpenSeconds(savedKeepBrowserSeconds);
      if (typeof saved.authenticatedFlow === "boolean") setAuthenticatedFlow(saved.authenticatedFlow);
      const savedEmailSelector = typeof saved.emailSelector === "string" ? saved.emailSelector.trim() : DEFAULT_LOGIN_EMAIL_SELECTOR;
      const savedPasswordSelector = typeof saved.passwordSelector === "string" ? saved.passwordSelector.trim() : DEFAULT_LOGIN_PASSWORD_SELECTOR;
      const savedSubmitSelector = typeof saved.submitSelector === "string" ? saved.submitSelector.trim() : DEFAULT_LOGIN_SUBMIT_SELECTOR;
      if (validateLoginSelectors(savedEmailSelector, savedPasswordSelector, savedSubmitSelector)) {
        setEmailSelector(DEFAULT_LOGIN_EMAIL_SELECTOR);
        setPasswordSelector(DEFAULT_LOGIN_PASSWORD_SELECTOR);
        setSubmitSelector(DEFAULT_LOGIN_SUBMIT_SELECTOR);
      } else {
        setEmailSelector(savedEmailSelector);
        setPasswordSelector(savedPasswordSelector);
        setSubmitSelector(savedSubmitSelector);
      }
      if (Array.isArray(saved.runtimeParameters)) {
        setRuntimeParameters(saved.runtimeParameters
          .filter((parameter) => parameter && typeof parameter === "object")
          .map((parameter) => ({
            id: typeof parameter.id === "string" && parameter.id ? parameter.id : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            key: typeof parameter.key === "string" ? parameter.key : "",
            value: typeof parameter.value === "string" ? parameter.value : "",
            sensitive: parameter.sensitive === true,
          })));
      }
    } catch {
      // Ignore malformed local configuration and keep the safe defaults.
    }
  }, []);

  useEffect(() => {
    try {
      const storedVoiceMode = window.localStorage.getItem(VOICE_MODE_STORAGE_KEY);
      if (storedVoiceMode === "male" || storedVoiceMode === "female") {
        setVoiceGender(storedVoiceMode);
      }
    } catch {
    }
  }, []);

  const [agentRecommendations, setAgentRecommendations] = useState<any[]>([]);
  const [preExecutionAnalysis, setPreExecutionAnalysis] = useState<any | null>(null);
  const [analyzingAgents, setAnalyzingAgents] = useState(false);

  const [evidenceGallery, setEvidenceGallery] = useState<{ total_screenshots: number; total_videos: number; screenshots: any[]; videos: any[] }>({ total_screenshots: 0, total_videos: 0, screenshots: [], videos: [] });
  const [refreshingEvidence, setRefreshingEvidence] = useState(false);

  const [aiConfigState, setAiConfigState] = useState<any | null>(null);
  const [integrationConnections, setIntegrationConnections] = useState<IntegrationConnection[]>([]);
  const [integrationEnvironmentConfiguration, setIntegrationEnvironmentConfiguration] = useState<IntegrationEnvironmentConfig | null>(null);
  const [auditLogList, setAuditLogList] = useState<any[]>([]);
  const [refreshingAuditLogs, setRefreshingAuditLogs] = useState(false);

  const [textIngestModalOpen, setTextIngestModalOpen] = useState(false);
  const [textIngestContent, setTextIngestContent] = useState("");
  const [textIngestFormat, setTextIngestFormat] = useState<"text" | "markdown_table" | "csv" | "json" | "openapi" | "db_schema">("text");
  const [textIngestPreconditions, setTextIngestPreconditions] = useState("User is logged in with authorized credentials");
  const [textIngestLoading, setTextIngestLoading] = useState(false);
  const [testCaseEditingId, setTestCaseEditingId] = useState<number | null>(null);
  const [testCaseEditorMode, setTestCaseEditorMode] = useState<"create" | "edit" | "view" | null>(null);
  const [testCaseFormTitle, setTestCaseFormTitle] = useState("");
  const [testCaseFormDescription, setTestCaseFormDescription] = useState("");
  const [testCaseFormPreconditions, setTestCaseFormPreconditions] = useState("");
  const [testCaseFormSteps, setTestCaseFormSteps] = useState("");
  const [testCaseFormExpectedResult, setTestCaseFormExpectedResult] = useState("");
  const [testCaseFormStatus, setTestCaseFormStatus] = useState("draft");
  const [testCaseFormPriority, setTestCaseFormPriority] = useState("medium");
  const [testCaseFormCategory, setTestCaseFormCategory] = useState("positive");
  const [testCaseFormError, setTestCaseFormError] = useState("");
  const [savingTestCase, setSavingTestCase] = useState(false);

  const [aiGenerationLogs, setAiGenerationLogs] = useState<ConsoleLogEntry[]>([]);
  const [backendGenerationLogs, setBackendGenerationLogs] = useState<GenerationLogItem[]>([]);
  const [activeGenJobId, setActiveGenJobId] = useState<string | null>(null);
  const [aiAgentStages, setAiAgentStages] = useState<AIAgentStage[]>(DEFAULT_AI_AGENT_STAGES);
  const [aiDocumentAnalysis, setAiDocumentAnalysis] = useState<AIDocumentAnalysis | null>(null);
  const [aiDocumentAnalysisError, setAiDocumentAnalysisError] = useState("");
  const [analyzingAiDocuments, setAnalyzingAiDocuments] = useState(false);
  const aiDocumentInputRef = useRef<HTMLInputElement>(null);

  const appendAiLog = (level: ConsoleLogEntry["level"], message: string) => {
    const now = new Date();
    const timeStr = now.toTimeString().split(" ")[0];
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      timestamp: timeStr,
      level,
      message,
    };
    setAiGenerationLogs((prev) => [...prev, entry]);
    console.log(`[AI-GENERATOR][${level.toUpperCase()}] ${message}`);
  };

  const fetchBackendGenerationLogs = async (jobId: string) => {
    if (!token) return;
    try {
      const res = await apiFetch<{ logs: GenerationLogItem[] }>(
        `/api/v1/ai-generation/jobs/${jobId}/logs`,
        {},
        token,
      );
      if (res?.logs) {
        setBackendGenerationLogs(res.logs);
      }
    } catch (e) {
      console.error("Failed to fetch backend generation logs:", e);
    }
  };

  const analyzeAiDocuments = async (files: File[]) => {
    if (!files.length) return;
    if (!token) {
      notify("Sign in before uploading requirement documents");
      return;
    }
    setAnalyzingAiDocuments(true);
    setAiDocumentAnalysisError("");
    appendAiLog("info", `📄 Uploading ${files.length} requirement document${files.length === 1 ? "" : "s"} for analysis...`);
    try {
      const formData = new FormData();
      files.forEach((file) => formData.append("files", file, file.name));
      appendAiLog("step", "🔍 Document Analysis Agent started. Extracting requirements, features, rules, and workflow signals...");
      const analysis = await apiFetch<AIDocumentAnalysis>(
        "/api/v1/ai-generation/documents/analyze",
        { method: "POST", body: formData },
        token,
      );
      setAiDocumentAnalysis(analysis);
      appendAiLog(
        "success",
        `✅ Parsed ${analysis.total_files} file${analysis.total_files === 1 ? "" : "s"}, ${analysis.requirements_found} requirement signal${analysis.requirements_found === 1 ? "" : "s"}, and ${analysis.modules_identified.length} module${analysis.modules_identified.length === 1 ? "" : "s"}.`,
      );
      appendAiLog("step", "🧠 Context Builder Agent ready. Extracted document context will be included in generation.");
      if (analysis.warnings.length) {
        analysis.warnings.forEach((warning) => appendAiLog("warn", `⚠️ ${warning}`));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to analyze requirement documents.";
      setAiDocumentAnalysisError(message);
      appendAiLog("error", `❌ Document analysis failed: ${message}`);
      notify(message);
    } finally {
      setAnalyzingAiDocuments(false);
      if (aiDocumentInputRef.current) aiDocumentInputRef.current.value = "";
    }
  };

  const clearAiDocuments = () => {
    setAiDocumentAnalysis(null);
    setAiDocumentAnalysisError("");
    if (aiDocumentInputRef.current) aiDocumentInputRef.current.value = "";
  };

  const [aiJiraInput, setAiJiraInput] = useState("");
  const [aiJiraIssue, setAiJiraIssue] = useState<JiraIssueDetail | null>(null);
  const [fetchingAiJira, setFetchingAiJira] = useState(false);
  const [aiJiraError, setAiJiraError] = useState("");

  const fetchAiJiraIssue = async (keyOrUrl?: string) => {
    const input = (keyOrUrl ?? aiJiraInput).trim();
    if (!input) {
      notify("Enter a Jira issue key or URL (e.g. ECOM-116459)");
      return;
    }
    if (!token) {
      notify("Sign in before fetching Jira requirements");
      return;
    }
    setFetchingAiJira(true);
    setAiJiraError("");
    appendAiLog("info", `🔗 Connecting to Jira to fetch issue ${input}...`);

    try {
      const issue = await apiFetch<JiraIssueDetail>(
        "/api/v1/integrations/jira/fetch-issue",
        {
          method: "POST",
          body: JSON.stringify({ issue_key_or_url: input }),
        },
        token,
      );
      setAiJiraIssue(issue);
      appendAiLog("success", `✅ Connected Jira Issue: ${issue.key} - "${issue.summary}"`);
      notify(`Jira issue ${issue.key} connected as Generation Source`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to fetch Jira issue.";
      setAiJiraError(msg);
      appendAiLog("error", `❌ Jira fetch failed: ${msg}`);
      notify(msg);
    } finally {
      setFetchingAiJira(false);
    }
  };

  const applyJiraToPrompt = (issue: JiraIssueDetail) => {
    const lines = [`Validate ${issue.key}: ${issue.summary}.`];
    if (issue.description?.trim()) {
      lines.push(`\nUser Story & Description:\n${issue.description.trim()}`);
    }
    if (issue.acceptance_criteria?.trim()) {
      lines.push(`\nAcceptance Criteria:\n${issue.acceptance_criteria.trim()}`);
    }
    setAiPrompt(lines.join("\n"));
    const focusItems = [...(issue.components || []), ...(issue.labels || [])].filter(Boolean);
    if (focusItems.length) {
      setAiModuleFocus(focusItems.join(", "));
    }
    notify(`Applied ${issue.key} requirements to Generation Prompt & Module Focus`);
  };

  const clearAiJira = () => {
    setAiJiraIssue(null);
    setAiJiraError("");
    notify("Disconnected Jira issue context");
  };

  const app = useMemo(
    () => applications.find((item) => item.id === selectedAppId)
      ?? applications.find((item) => item.name === appName)
      ?? applications[0],
    [applications, selectedAppId, appName],
  );
  const apps = applications;
  const trackedRuns = useMemo(() => runs.filter((run) => applications.some((application) => application.id === run.application_id)), [applications, runs]);
  const selectedCases = useMemo(() => {
    const tcNumber = (title: string) => {
      const match = title.match(/^TC\s*0*(\d+)/i);
      return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
    };
    return testCases
      .filter((caseItem) => caseItem.application_id === app?.id)
      .sort((left, right) => {
        const numA = tcNumber(left.title);
        const numB = tcNumber(right.title);
        if (numA !== numB) return numA - numB;
        return left.id - right.id;
      });
  }, [testCases, app?.id]);
  const deferredExecutionLibrarySearch = useDeferredValue(executionLibrarySearch);
  const deferredProjectSearch = useDeferredValue(projectSearch);
  const deferredApplicationSearch = useDeferredValue(applicationSearch);
  const deferredAiPrompt = useDeferredValue(aiPrompt);
  const deferredAiModuleFocus = useDeferredValue(aiModuleFocus);
  const deferredAiTargetUrl = useDeferredValue(aiTargetUrl);
  const deferredAiPerformanceBudget = useDeferredValue(aiPerformanceBudget);
  const executionSelectedCaseIdSet = useMemo(() => new Set(executionSelectedCaseIds), [executionSelectedCaseIds]);

  const executionLibraryFilteredCases = useMemo(() => {
    const normalizedSearch = deferredExecutionLibrarySearch.trim().toLowerCase();
    return [...selectedCases]
      .filter((caseItem) => executionLibraryStatusFilter === "all" || inferRunScopeKey(caseItem.status) === executionLibraryStatusFilter)
      .filter((caseItem) => {
        if (!normalizedSearch) return true;
        return [caseItem.title, caseItem.description, caseItem.preconditions, caseItem.steps, caseItem.expected_result, caseItem.status]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch);
      })
      .sort((left, right) => {
        if (executionLibrarySortBy === "name") return left.title.localeCompare(right.title);
        if (executionLibrarySortBy === "status") return left.status.localeCompare(right.status) || left.id - right.id;
        if (executionLibrarySortBy === "updated") return toTimestampValue(right.updated_at) - toTimestampValue(left.updated_at) || right.id - left.id;
        return left.id - right.id;
      });
  }, [deferredExecutionLibrarySearch, executionLibrarySortBy, executionLibraryStatusFilter, selectedCases]);
  const executionLibraryTotalPages = Math.max(1, Math.ceil(executionLibraryFilteredCases.length / executionLibraryPageSize));
  const executionLibraryCurrentPage = Math.min(executionLibraryPage, executionLibraryTotalPages);
  const executionLibraryPageCases = useMemo(
    () => executionLibraryFilteredCases.slice((executionLibraryCurrentPage - 1) * executionLibraryPageSize, executionLibraryCurrentPage * executionLibraryPageSize),
    [executionLibraryCurrentPage, executionLibraryFilteredCases, executionLibraryPageSize],
  );
  const executionLibraryRows = useMemo(
    () => buildCaseTableRows(executionLibraryPageCases),
    [executionLibraryPageCases],
  );
  const previewCases = useMemo(
    () => [...selectedCases]
      .sort((left, right) => {
        const leftDraft = isDraftStatus(left.status);
        const rightDraft = isDraftStatus(right.status);
        if (leftDraft !== rightDraft) return leftDraft ? -1 : 1;
        return right.id - left.id;
      })
      .slice(0, 10),
    [selectedCases],
  );
  const previewCaseRows = useMemo(
    () => buildCaseTableRows(previewCases),
    [previewCases],
  );
  const latestGeneratedCases = useMemo(
    () => selectedCases.filter((caseItem) => latestGeneratedCaseIds.includes(caseItem.id)),
    [selectedCases, latestGeneratedCaseIds],
  );
  const executionScopeOptions = useMemo(
    () => [
      { value: "all" as const, label: "All draft + ready cases" },
      { value: "draft" as const, label: "Draft cases only" },
      { value: "ready" as const, label: "Ready cases only" },
      ...(executionSelectedCaseIds.length ? [{ value: "selected" as const, label: `Selected cases (${executionSelectedCaseIds.length})` }] : []),
      ...(latestGeneratedCases.length ? [{ value: "latest" as const, label: `Latest generated (${latestGeneratedCases.length})` }] : []),
    ],
    [executionSelectedCaseIds.length, latestGeneratedCases.length],
  );
  const selectedAppSuites = useMemo(
    () => testSuites.filter((suite) => suite.application_id === app?.id),
    [testSuites, app?.id],
  );
  const suiteCandidateCases = useMemo(() => {
    if (suiteCaseSource === "all") {
      return selectedCases;
    }
    if (suiteCaseSource === "latest") {
      const latestCases = selectedCases.filter((caseItem) => latestGeneratedCaseIds.includes(caseItem.id));
      if (latestCases.length) return latestCases;
    }
    return selectedCases.filter((caseItem) => !isDraftStatus(caseItem.status));
  }, [selectedCases, suiteCaseSource, latestGeneratedCaseIds]);
  const suiteCandidateCaseIds = useMemo(
    () => suiteEditingCaseIds ?? suiteCandidateCases.map((caseItem) => caseItem.id),
    [suiteCandidateCases, suiteEditingCaseIds],
  );
  const selectedDraftCount = useMemo(
    () => testCases.filter((caseItem) => caseItem.application_id === app?.id && isDraftStatus(caseItem.status)).length,
    [testCases, app],
  );
  const aiPreviewInsights = useMemo(() => {
    const interactivePattern = /\b(click|open|tap|choose|select|type|enter|navigate|submit|search|filter|assert)\b/i;
    const caseCount = previewCases.length;
    let totalSteps = 0;
    let interactiveSteps = 0;
    let topActionCase = "";
    let topActionCount = 0;
    let highConfidence = 0;
    let mediumConfidence = 0;
    let lowConfidence = 0;
    let selectorReviewCount = 0;

    for (const caseItem of previewCases) {
      const steps = parseStepEntries(caseItem.steps);
      const actionCount = steps.filter((step) => interactivePattern.test(step.text)).length;
      totalSteps += steps.length;
      interactiveSteps += actionCount;
      if (actionCount > topActionCount) {
        topActionCount = actionCount;
        topActionCase = caseItem.title;
      }
      const readiness = automationReadinessByCaseId[caseItem.id];
      if (!readiness) continue;
      if (readiness.confidence_label === "high") highConfidence += 1;
      else if (readiness.confidence_label === "medium") mediumConfidence += 1;
      else lowConfidence += 1;
      if (readiness.needs_manual_selector_review) selectorReviewCount += 1;
    }

    return {
      caseCount,
      averageSteps: caseCount ? Math.round((totalSteps / caseCount) * 10) / 10 : 0,
      interactionDensity: totalSteps ? Math.round((interactiveSteps / totalSteps) * 100) : 0,
      topActionCase,
      topActionCount,
      highConfidence,
      mediumConfidence,
      lowConfidence,
      selectorReviewCount,
    };
  }, [previewCases, automationReadinessByCaseId]);
  const aiPromptReady = aiPrompt.trim().length >= 3;
  const aiTargetReady = app?.platform !== "web" || aiTargetUrl.trim().length > 0;
  const aiGenerationReady = !!app?.id && aiPromptReady && aiTargetReady;
  const guidedRunEnabled = guidedDemoMode && app?.platform === "web";
  const aiPhaseOrder: Record<"preparing" | "capturing" | "generating" | "publishing", number> = {
    preparing: 0,
    capturing: 1,
    generating: 2,
    publishing: 3,
  };
  const aiPhaseIndex = aiGenerationPhase in aiPhaseOrder ? aiPhaseOrder[aiGenerationPhase as keyof typeof aiPhaseOrder] : -1;
  const executionCounts = useMemo(() => {
    const counts: Record<LiveCaseExecutionStatus, number> = {
      pending: 0,
      queued: 0,
      running: 0,
      passed: 0,
      failed: 0,
      error: 0,
      cancelled: 0,
      paused: 0,
    };
    for (const caseProgress of executionLiveCases) {
      if (caseProgress.status in counts) {
        counts[caseProgress.status] += 1;
      }
    }
    return counts;
  }, [executionLiveCases]);
  const executionTotalCount = executionProgress.total || executionLiveCases.length;
  const executionCompletedCount = executionCounts.passed + executionCounts.failed + executionCounts.error;
  const executionQueuedCount = executionCounts.pending + executionCounts.queued;
  const executionProgressPercent = executionTotalCount
    ? Math.min(100, Math.round((executionCompletedCount / executionTotalCount) * 100))
    : 0;
  const executionElapsedMs = running && executionRunStartedAt ? Math.max(0, executionClockMs - executionRunStartedAt) : 0;
  const executionAverageCaseDurationMs = useMemo(() => {
    const durations = executionLiveCases
      .filter((caseProgress) => ["passed", "failed", "error"].includes(caseProgress.status))
      .map((caseProgress) => {
        if (typeof caseProgress.durationMs === "number" && caseProgress.durationMs > 0) return caseProgress.durationMs;
        if (typeof caseProgress.startedAt === "number" && typeof caseProgress.finishedAt === "number") {
          return Math.max(0, caseProgress.finishedAt - caseProgress.startedAt);
        }
        return 0;
      })
      .filter((durationMs) => durationMs > 0);
    if (!durations.length) return 0;
    const sum = durations.reduce((total, durationMs) => total + durationMs, 0);
    return Math.round(sum / durations.length);
  }, [executionLiveCases]);
  const executionRemainingCount = Math.max(0, executionTotalCount - executionCompletedCount);
  const executionEtaMs = executionAverageCaseDurationMs > 0 ? executionAverageCaseDurationMs * executionRemainingCount : 0;
  const activeExecutionCase = useMemo(() => {
    const currentlyRunning = executionLiveCases.find((caseProgress) => caseProgress.status === "running");
    if (currentlyRunning) return currentlyRunning;
    if (executionProgress.activeCaseTitle) {
      const byTitle = executionLiveCases.find((caseProgress) => caseProgress.title === executionProgress.activeCaseTitle);
      if (byTitle) return byTitle;
    }
    return executionLiveCases.find((caseProgress) => caseProgress.status === "queued") ?? executionLiveCases[0] ?? null;
  }, [executionLiveCases, executionProgress.activeCaseTitle]);
  const executionPhaseMeta = executionPhase === "done"
    ? { icon: "OK", label: "Execution completed" }
    : executionPhase === "error"
      ? { icon: "ER", label: "Execution needs attention" }
      : executionPhase === "finalizing"
        ? { icon: "FN", label: "Finalizing run summary" }
        : executionPhase === "running"
          ? { icon: "RN", label: "Running test cases" }
          : executionPhase === "queueing"
            ? { icon: "QU", label: "Queueing test cases" }
            : { icon: "ID", label: "Execution idle" };
  const navigateToSection = (nextSection: Section) => {
    const basePath = SECTION_PATHS[nextSection];
    const searchParams = new URLSearchParams(window.location.search);
    const nextUrl = searchParams.toString()
      ? `${basePath}?${searchParams.toString()}`
      : basePath;
    const currentUrl = `${window.location.pathname}${window.location.search}`;
    if (section === nextSection && currentUrl === nextUrl) {
      setMobileNavOpen(false);
      return;
    }
    setSection(nextSection);
    setMobileNavOpen(false);
    if (currentUrl !== nextUrl) {
      router.push(nextUrl, { scroll: false });
    }
  };
  const closeProjectModal = () => {
    setProjectModalMode(null);
    setProjectEditingId(null);
    setProjectFormName("");
    setProjectFormDescription("");
    setProjectFormLifecycle("active");
    setProjectFormError("");
  };

  const openCreateProjectModal = () => {
    setProjectModalMode("create");
    setProjectEditingId(null);
    setProjectFormName("");
    setProjectFormDescription("");
    setProjectFormLifecycle("active");
    setProjectFormError("");
  };

  const openEditProjectModal = (projectId: string) => {
    const project = projectCatalog.find((item) => item.id === projectId);
    if (!project) {
      notify("Selected project is unavailable");
      return;
    }
    setProjectModalMode("edit");
    setProjectEditingId(project.id);
    setProjectFormName(project.name);
    setProjectFormDescription(project.description);
    setProjectFormLifecycle(project.lifecycle);
    setProjectFormError("");
  };

  const saveProjectFromModal = async () => {
    const normalizedName = projectFormName.trim();
    if (!normalizedName) {
      setProjectFormError("Project name is required.");
      return;
    }
    const normalizedDescription = projectFormDescription.trim() || "Project description will be added during planning.";
    if (!token) {
      setProjectFormError("Your session expired. Sign in again to manage projects.");
      return;
    }
    setSavingProject(true);
    setProjectFormError("");
    try {
      const payload = {
        name: normalizedName,
        description: normalizedDescription,
        lifecycle: projectFormLifecycle,
        owner: "Admin QA",
      };
      const savedProject = await apiFetch<{
        id: string;
        name: string;
        description?: string | null;
        lifecycle: ProjectLifecycle;
        owner: string;
        created_at?: string | null;
        updated_at?: string | null;
      }>(
        projectModalMode === "edit" && projectEditingId ? `/api/v1/projects/${projectEditingId}` : "/api/v1/projects",
        {
          method: projectModalMode === "edit" && projectEditingId ? "PUT" : "POST",
          body: JSON.stringify(payload),
        },
        token,
      );
      const mappedProject = mapApiProject(savedProject);
      setProjectCatalog((current) => projectModalMode === "edit"
        ? current.map((project) => project.id === mappedProject.id ? mappedProject : project)
        : [mappedProject, ...current.filter((project) => project.id !== mappedProject.id)]);
      setSelectedProjectId(mappedProject.id);
      setProjectDetailTab("overview");
      notify(projectModalMode === "edit" ? "Project updated" : "Project created");
      closeProjectModal();
    } catch (error) {
      setProjectFormError(error instanceof Error ? error.message : "Unable to save project.");
    } finally {
      setSavingProject(false);
    }
  };

  const deleteProject = async (project: Pick<WorkspaceProject, "id" | "name">) => {
    if (!token || !window.confirm(`Delete project "${project.name}"?`)) return;
    setDeletingProjectId(project.id);
    try {
      await apiFetch<null>(`/api/v1/projects/${project.id}`, { method: "DELETE" }, token);
      const remaining = projectCatalog.filter((item) => item.id !== project.id);
      setProjectCatalog(remaining);
      if (selectedProjectId === project.id) setSelectedProjectId(remaining[0]?.id ?? "");
      notify(`Project "${project.name}" deleted`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to delete project.");
    } finally {
      setDeletingProjectId(null);
    }
  };

  const closeApplicationEditModal = () => {
    setApplicationEditingId(null);
    setApplicationEditingOriginalName("");
    setApplicationFormName("");
    setApplicationFormTarget("");
    setApplicationFormPlatform("web");
    setApplicationFormError("");
    setSavingApplicationEdit(false);
  };

  const openApplicationEditModal = (applicationName: string) => {
    const application = apps.find((item) => item.name === applicationName);
    if (!application || typeof application.id !== "number") {
      notify("Selected application cannot be edited right now");
      return;
    }
    setApplicationEditingId(application.id);
    setApplicationEditingOriginalName(application.name);
    setApplicationFormName(application.name);
    setApplicationFormTarget(application.url || application.target || "");
    setApplicationFormPlatform(application.platform);
    setApplicationFormError("");
  };

  const saveApplicationFromModal = async () => {
    if (!applicationEditingId) {
      setApplicationFormError("Select an application to edit.");
      return;
    }
    const normalizedName = applicationFormName.trim();
    const normalizedTarget = applicationFormTarget.trim();
    if (!normalizedName) {
      setApplicationFormError("Application name is required.");
      return;
    }
    if (!normalizedTarget) {
      setApplicationFormError("Application target is required.");
      return;
    }
    if (applicationFormPlatform === "web") {
      try {
        new URL(normalizedTarget);
      } catch {
        setApplicationFormError("Enter a complete URL including https://.");
        return;
      }
    } else if (normalizedTarget.startsWith("http://") || normalizedTarget.startsWith("https://")) {
      setApplicationFormError("Mobile applications must reference an uploaded package path.");
      return;
    }
    if (!token) {
      setApplicationFormError("Your session expired. Sign in again to update applications.");
      return;
    }
    setSavingApplicationEdit(true);
    try {
      const updated = await apiFetch<{ id: number; name: string; platform: string; target: string }>(
        `/api/v1/applications/${applicationEditingId}`,
        {
          method: "PUT",
          body: JSON.stringify({
            name: normalizedName,
            target: normalizedTarget,
          }),
        },
        token,
      );
      setApplications((current) => current.map((item) => (
        item.id === updated.id
          ? { ...mapApiApplication(updated, item.cases ?? 0), artifact: item.artifact }
          : item
      )));
      if (appName === applicationEditingOriginalName) {
        selectApplication(updated.name);
      }
      await loadDashboardData(token, updated.name);
      await loadAutomationReadiness(token, updated.id);
      notify("Application updated");
      closeApplicationEditModal();
    } catch (error) {
      setApplicationFormError(error instanceof Error ? error.message : "Unable to update application.");
    } finally {
      setSavingApplicationEdit(false);
    }
  };

  const chooseSelectedAppName = (nextApps: Application[], preferredAppName?: string) => {
    const stored = window.localStorage.getItem("ai-qa-engine:selected-app") ?? "";
    if (preferredAppName && nextApps.some((item) => item.name === preferredAppName)) return preferredAppName;
    if (stored && nextApps.some((item) => item.name === stored)) return stored;
    if (appName && nextApps.some((item) => item.name === appName)) return appName;
    return (
      nextApps.find((item) => item.platform === "web")?.name
      ?? nextApps[0]?.name
    );
  };

  const loadDashboardData = async (authToken: string, preferredAppName?: string) => {
    setRefreshingData(true);
    try {
      const loadedApps = await apiFetch<Array<{ id: number; name: string; platform: string; target: string }>>("/api/v1/applications", {}, authToken);
      const mappedApps: Application[] = loadedApps.map((item) => mapApiApplication(item));
      const nextApps = sortApplicationsForDisplay(mappedApps);
      setApplications(nextApps);
      void loadAllAutomationReadiness(authToken, nextApps);
      try {
        const loadedProjects = await apiFetch<Array<{
          id: string;
          name: string;
          description?: string | null;
          lifecycle: ProjectLifecycle;
          owner: string;
          created_at?: string | null;
          updated_at?: string | null;
        }>>("/api/v1/projects", {}, authToken);
        if (loadedProjects.length) setProjectCatalog(loadedProjects.map(mapApiProject));
      } catch (error) {
        console.error("Unable to load projects", error);
      }
      const selectedName = chooseSelectedAppName(nextApps, preferredAppName);
      if (selectedName) {
        setAppName(selectedName);
        const nextSelectedApp = nextApps.find((item) => item.name === selectedName);
        setSelectedAppId(nextSelectedApp?.id ?? null);
        if (nextSelectedApp) {
          window.localStorage.setItem("ai-qa-engine:selected-app", nextSelectedApp.name);
          void loadAgentRecommendations(authToken, nextSelectedApp.id);
          void loadEvidenceGallery(authToken, nextSelectedApp.id);
        }
      } else if (!applications.length) {
        setAppName("");
        setSelectedAppId(null);
      }
    } catch (error) {
      logger.warn("Unable to load applications, preserving existing cached applications", { error: String(error) });
      if (!applications.length) {
        setApplications([]);
        setAppName("");
        setSelectedAppId(null);
      }
    }
    setLoadingSuites(true);
    const [loadedTestCases, loadedDefects, loadedRuns, loadedSuites] = await Promise.all([
      loadAllTestCases(authToken).catch((error) => {
        logger.warn("Unable to load test cases, preserving current list", { error: String(error) });
        return null;
      }),
      apiFetch<Defect[]>("/api/v1/defects", {}, authToken).catch((error) => {
        logger.warn("Unable to load defects, preserving current list", { error: String(error) });
        return null;
      }),
      apiFetch<RunSummary[]>("/api/v1/execution", {}, authToken).catch((error) => {
        logger.warn("Unable to load execution history, preserving current list", { error: String(error) });
        return null;
      }),
      apiFetch<TestSuite[]>("/api/v1/test-suites", {}, authToken).catch((error) => {
        logger.warn("Unable to load test suites, preserving current list", { error: String(error) });
        return null;
      }),
    ]);
    if (loadedTestCases !== null) setTestCases(loadedTestCases);
    if (loadedDefects !== null) {
      setDefects(loadedDefects);
      setSelectedDefectId((current) => current && loadedDefects.some((defect) => defect.id === current)
        ? current
        : loadedDefects[0]?.id ?? null);
    }
    if (loadedRuns !== null) setRuns(loadedRuns);
    if (loadedSuites !== null) setTestSuites(loadedSuites);
    setLoadingSuites(false);
    setRefreshingData(false);
    void loadAiConfiguration(authToken);
    void loadIntegrationConnections(authToken);
    void loadIntegrationEnvironmentConfiguration(authToken);
    void loadAuditLogs(authToken);
  };

  const refreshExecutionHistory = async (authToken: string, applicationId?: number) => {
    if (!applicationId) {
      setRuns([]);
      setCaseExecutions([]);
      setBuilds([]);
      return;
    }
    setLoadingCaseExecutions(true);
    try {
      const [loadedRuns, history, loadedBuilds] = await Promise.all([
        apiFetch<RunSummary[]>("/api/v1/execution", {}, authToken),
        apiFetch<CaseExecutionSummary[]>(`/api/v1/execution/cases/${applicationId}`, {}, authToken),
        apiFetch<BuildExecutionSummary[]>(`/api/v1/execution/builds/${applicationId}`, {}, authToken).catch(() => []),
      ]);
      setRuns(loadedRuns);
      setCaseExecutions(history);
      setBuilds(loadedBuilds || []);
    } catch (error) {
      console.error("Unable to refresh execution history", error);
    } finally {
      setLoadingCaseExecutions(false);
    }
  };

  const openBuildReportModal = async (buildId?: string) => {
    if (!buildId) {
      if (latestBuildReport) {
        setActiveBuildReportModal(latestBuildReport);
      } else if (builds.length > 0) {
        void openBuildReportModal(builds[0].build_id);
      }
      return;
    }
    try {
      const detail = await apiFetch<BuildExecutionDetail>(
        `/api/v1/execution/builds/${buildId}/detail`,
        {},
        token,
      );
      setActiveBuildReportModal(detail);
    } catch {
      const currentReportId = latestBuildReport ? ("buildId" in latestBuildReport ? latestBuildReport.buildId : latestBuildReport.build_id) : null;
      if (latestBuildReport && currentReportId === buildId) {
        setActiveBuildReportModal(latestBuildReport);
      } else {
        notify("Unable to load build execution details.");
      }
    }
  };

  const loadAutomationReadiness = async (authToken: string, applicationId?: number) => {
    if (!applicationId) {
      setAutomationReadinessByCaseId({});
      return;
    }
    try {
      const readiness = await apiFetch<TestCaseAutomationReadiness[]>(
        `/api/v1/test-cases/application/${applicationId}/automation-readiness`,
        {},
        authToken,
      );
      setAutomationReadinessByCaseId(
        (current) => ({ ...current, ...Object.fromEntries(readiness.map((item) => [item.test_case_id, item])) }),
      );
    } catch (error) {
      console.error("Unable to load automation readiness", error);
    }
  };

  const loadAllAutomationReadiness = async (authToken: string, applicationList: Application[]) => {
    const applicationIds = applicationList
      .map((item) => item.id)
      .filter((id): id is number => typeof id === "number");
    if (!applicationIds.length) {
      setAutomationReadinessByCaseId({});
      return;
    }
    const readinessResults = await Promise.all(applicationIds.map(async (applicationId) => {
      try {
        return await apiFetch<TestCaseAutomationReadiness[]>(
          `/api/v1/test-cases/application/${applicationId}/automation-readiness`,
          {},
          authToken,
        );
      } catch (error) {
        console.error(`Unable to load automation readiness for application ${applicationId}`, error);
        return [];
      }
    }));
    setAutomationReadinessByCaseId(Object.fromEntries(readinessResults.flat().map((item) => [item.test_case_id, item])));
  };

  const createSuite = async () => {
    if (!app?.id) {
      setSuiteFormError("Select an application before creating a suite.");
      return;
    }
    const normalizedName = (suiteName.trim() || `${app.name} regression suite`).slice(0, 120);
    if (!normalizedName) {
      setSuiteFormError("Suite name is required.");
      return;
    }
    if (!suiteCandidateCaseIds.length) {
      setSuiteFormError("No test cases matched the selected case source.");
      return;
    }
    setCreatingSuite(true);
    setSuiteFormError("");
    try {
      if (!token) {
        setSuiteFormError("Your session expired. Sign in again to manage suites.");
        return;
      }
      const createdSuite = await apiFetch<TestSuite>(
        suiteEditingId ? `/api/v1/test-suites/${suiteEditingId}` : "/api/v1/test-suites",
        {
          method: suiteEditingId ? "PUT" : "POST",
          body: JSON.stringify(suiteEditingId
            ? {
              name: normalizedName,
              description: suiteDescription.trim() || null,
              case_ids: suiteCandidateCaseIds,
            }
            : {
              application_id: app.id,
              name: normalizedName,
              description: suiteDescription.trim() || null,
              case_ids: suiteCandidateCaseIds,
            }),
        },
        token,
      );
      setTestSuites((current) => suiteEditingId
        ? current.map((suite) => suite.id === createdSuite.id ? createdSuite : suite)
        : [createdSuite, ...current.filter((suite) => suite.id !== createdSuite.id)]);
      notify(`Suite "${createdSuite.name}" ${suiteEditingId ? "updated" : "created"}`);
      setSuiteName("");
      setSuiteDescription("");
      setSuiteCaseSource("ready");
      setSuiteEditingId(null);
      setSuiteEditingCaseIds(null);
    } catch (error) {
      setSuiteFormError(error instanceof Error ? error.message : "Unable to create suite.");
    } finally {
      setCreatingSuite(false);
    }
  };

  const editSuite = (suite: TestSuite) => {
    setSuiteEditingId(suite.id);
    setSuiteEditingCaseIds([...suite.case_ids]);
    setSuiteName(suite.name);
    setSuiteDescription(suite.description ?? "");
    setSuiteCaseSource("all");
    setSuiteFormError("");
  };

  const deleteSuite = async (suite: TestSuite) => {
    if (!window.confirm(`Delete suite "${suite.name}"?`)) return;
    setDeletingSuiteId(suite.id);
    setSuiteFormError("");
    try {
      if (!token) {
        setSuiteFormError("Your session expired. Sign in again to manage suites.");
        return;
      }
      await apiFetch<null>(`/api/v1/test-suites/${suite.id}`, { method: "DELETE" }, token);
      setTestSuites((current) => current.filter((item) => item.id !== suite.id));
      notify(`Suite "${suite.name}" deleted`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to delete suite.";
      setSuiteFormError(message);
      notify(message);
    } finally {
      setDeletingSuiteId(null);
    }
  };

  const loadAgentRecommendations = async (authToken: string, applicationId?: number) => {
    try {
      const url = applicationId ? `/api/v1/agents/recommendations?application_id=${applicationId}` : "/api/v1/agents/recommendations";
      const recs = await apiFetch<any[]>(url, {}, authToken);
      setAgentRecommendations(recs);
    } catch (e) {
      console.error("Failed to load agent recommendations", e);
      setAgentRecommendations([]);
    }
  };

  const loadEvidenceGallery = async (authToken: string, applicationId?: number) => {
    setRefreshingEvidence(true);
    try {
      const url = applicationId ? `/api/v1/evidence/gallery?application_id=${applicationId}` : "/api/v1/evidence/gallery";
      const gallery = await apiFetch<{ total_screenshots: number; total_videos: number; screenshots: any[]; videos: any[] }>(url, {}, authToken);
      setEvidenceGallery(gallery);
    } catch (e) {
      console.error("Failed to load evidence gallery", e);
      setEvidenceGallery({ total_screenshots: 0, total_videos: 0, screenshots: [], videos: [] });
    } finally {
      setRefreshingEvidence(false);
    }
  };

  const loadAiConfiguration = async (authToken: string): Promise<any | null> => {
    try {
      const conf = await apiFetch<any>("/api/v1/settings/ai-configuration", {}, authToken);
      setAiConfigState(conf);
      return conf;
    } catch (e) {
      console.error("Failed to load AI configuration", e);
      return null;
    }
  };

  const loadIntegrationConnections = async (authToken: string): Promise<IntegrationConnection[]> => {
    try {
      const loaded = await apiFetch<IntegrationConnection[]>("/api/v1/integrations/connections", {}, authToken);
      setIntegrationConnections(loaded);
      return loaded;
    } catch (error) {
      console.error("Failed to load integration connections", error);
      setIntegrationConnections([]);
      return [];
    }
  };

  const loadIntegrationEnvironmentConfiguration = async (authToken: string) => {
    try {
      const configuration = await apiFetch<IntegrationEnvironmentConfig>("/api/v1/integrations/environment", {}, authToken);
      setIntegrationEnvironmentConfiguration(configuration);
    } catch (error) {
      console.error("Failed to load integration environment configuration", error);
      setIntegrationEnvironmentConfiguration(null);
    }
  };

  const loadAuditLogs = async (authToken: string) => {
    setRefreshingAuditLogs(true);
    try {
      const logs = await apiFetch<any[]>("/api/v1/audit", {}, authToken);
      setAuditLogList(logs);
    } catch (e) {
      console.error("Failed to load audit logs", e);
      setAuditLogList([]);
    } finally {
      setRefreshingAuditLogs(false);
    }
  };

  const handleAnalyzeAgents = async () => {
    if (!app?.id || !token) return;
    setAnalyzingAgents(true);
    try {
      const res = await apiFetch<any>(
        "/api/v1/agents/analyze",
        {
          method: "POST",
          body: JSON.stringify({ application_id: app.id }),
        },
        token,
      );
      setPreExecutionAnalysis(res);
      await loadAgentRecommendations(token, app.id);
      notify("Pre-execution analysis complete");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setAnalyzingAgents(false);
    }
  };

  const handleReviewAgentRecommendation = async (recId: number, action: "approve" | "reject", reviewNotes?: string) => {
    if (!token) return;
    try {
      await apiFetch<any>(
        `/api/v1/agents/recommendations/${recId}/review`,
        {
          method: "POST",
          body: JSON.stringify({ action, review_notes: reviewNotes }),
        },
        token,
      );
      await loadAgentRecommendations(token, app?.id);
      if (action === "approve") {
        await loadDashboardData(token, app?.name);
      }
      notify(action === "approve" ? "Recommendation approved and applied" : "Recommendation rejected");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Failed to review recommendation");
    }
  };

  const handleCloneTestCase = async (caseId: number) => {
    if (!token) return;
    try {
      await apiFetch<any>(
        `/api/v1/test-cases/${caseId}/clone`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
        token,
      );
      await loadDashboardData(token, app?.name);
      notify("Test case cloned successfully");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Clone failed");
    }
  };

  const handleViewPlaywrightSpec = async (caseId: number) => {
    if (!token) return;
    setFetchingPlaywrightSpec(true);
    setGitPushMessage("");
    try {
      const res = await apiFetch<{ test_case_id: string; title: string; filename: string; code: string }>(
        `/api/v1/test-cases/${caseId}/export-playwright`,
        {},
        token,
      );
      setActivePlaywrightSpecModal({ id: caseId, ...res });
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to generate Playwright spec");
    } finally {
      setFetchingPlaywrightSpec(false);
    }
  };

  const handlePushPlaywrightSpecToGit = async (caseId: number) => {
    if (!token) return;
    setPushingToGit(true);
    setGitPushMessage("");
    try {
      const res = await apiFetch<{ status: string; filename: string; path: string; message: string }>(
        `/api/v1/test-cases/${caseId}/git-push`,
        { method: "POST" },
        token,
      );
      setGitPushMessage(`✅ ${res.message}`);
      notify(`Spec saved to repository: ${res.path}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Git push failed";
      setGitPushMessage(`❌ ${msg}`);
      notify(msg);
    } finally {
      setPushingToGit(false);
    }
  };

  const handleExportPlaywrightSuite = async (applicationId?: number | null) => {
    if (!token || !applicationId) {
      notify("Select an application first to export its Playwright test suite");
      return;
    }
    setFetchingPlaywrightSuite(true);
    try {
      const res = await apiFetch<{
        application_id: number;
        application_name: string;
        total_specs: number;
        specs: Array<{ test_case_id: number; title: string; filename: string; code: string }>;
      }>(
        `/api/v1/test-cases/application/${applicationId}/export-playwright-suite`,
        {},
        token,
      );
      if (!res.specs || res.specs.length === 0) {
        notify("No test cases found for this application to export into Playwright suite.");
        return;
      }
      setSelectedSuiteSpecIndex(0);
      setActivePlaywrightSuiteModal(res);
      notify(`Loaded Playwright test suite (${res.total_specs} specs) for ${res.application_name}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to export Playwright test suite");
    } finally {
      setFetchingPlaywrightSuite(false);
    }
  };

  const handleStopActiveExecution = async () => {
    if (!token) return;
    activeBatchCancelledRef.current = true;
    setStoppingExecution(true);
    try {
      if (activeExecutionBatchId) {
        await apiFetch(`/api/v1/execution/batch/${activeExecutionBatchId}/cancel`, { method: "POST" }, token);
      }
      notify("Execution cancellation requested. Stopping active workers...");
      setRunStatus("Cancelled");
      setRunLog("Execution cancelled by user.");
      setRunning(false);
      setExecutionPhase("done");
      stopExecutionSpeech();
      setExecutionLiveCases((current) => current.map((c) => (
        c.status === "running" || c.status === "queued" || c.status === "pending"
          ? { ...c, status: "cancelled", detail: "Cancelled by user" }
          : c
      )));
    } catch (err) {
      notify(err instanceof Error ? err.message : "Unable to cancel execution");
    } finally {
      setStoppingExecution(false);
    }
  };

  const handleCancelRun = async (runId: string) => {
    if (!token) return;
    try {
      await apiFetch(`/api/v1/execution/${runId}/cancel`, { method: "POST" }, token);
      notify(`Run ${runId.slice(0, 8)} stopped successfully`);
      if (running) {
        setExecutionLiveCases((current) => current.map((c) => (
          c.runId === runId ? { ...c, status: "cancelled", detail: "Cancelled by user" } : c
        )));
      }
      await refreshExecutionHistory(token, app?.id);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Unable to stop run");
    }
  };

  const handleCancelBuild = async (buildId: string) => {
    if (!token) return;
    try {
      await apiFetch(`/api/v1/execution/batch/${buildId}/cancel`, { method: "POST" }, token);
      notify(`Build ${buildId.slice(0, 16)} stopped successfully`);
      if (activeExecutionBatchId === buildId) {
        activeBatchCancelledRef.current = true;
        setRunning(false);
        setExecutionPhase("done");
        stopExecutionSpeech();
      }
      await refreshExecutionHistory(token, app?.id);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Unable to stop build");
    }
  };

  const handleRebuildBuild = async (buildId: string, caseIds?: number[]) => {
    if (!token || !app) return;
    try {
      if (caseIds && caseIds.length > 0) {
        navigateToSection("execution");
        notify(`Rebuilding batch with ${caseIds.length} test case(s)...`);
        void runApplicationCaseTests(caseIds);
        return;
      }
      const res = await apiFetch<{ build_id: string; name: string; total_cases: number }>(
        `/api/v1/execution/builds/${buildId}/rebuild?execution_mode=${executionMode}`,
        { method: "POST" },
        token,
      );
      notify(`Rebuild started: ${res.name || res.build_id} (${res.total_cases} cases)`);
      await refreshExecutionHistory(token, app.id);
      navigateToSection("runHistory");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to trigger rebuild");
    }
  };

  const handleDeleteTestCase = async (caseId: number, title: string) => {
    if (!token) return;
    if (!window.confirm(`Delete test case "${title}"?`)) return;
    setDeletingTestCaseIds([caseId]);
    try {
      await apiFetch<any>(
        `/api/v1/test-cases/${caseId}`,
        {
          method: "DELETE",
        },
        token,
      );
      reconcileDeletedTestCases([caseId]);
      await loadDashboardData(token, app?.name);
      notify("Test case deleted");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeletingTestCaseIds([]);
    }
  };

  const reconcileDeletedTestCases = (deletedIds: number[]) => {
    const deletedIdSet = new Set(deletedIds);
    setTestCases((current) => current.filter((caseItem) => !deletedIdSet.has(caseItem.id)));
    setLatestGeneratedCaseIds((current) => current.filter((caseId) => !deletedIdSet.has(caseId)));
    setExecutionSelectedCaseIds((current) => current.filter((caseId) => !deletedIdSet.has(caseId)));
    const remainingPreparedIds = preparedExecutionCaseIds.filter((caseId) => !deletedIdSet.has(caseId));
    if (remainingPreparedIds.length !== preparedExecutionCaseIds.length) {
      setPreparedExecutionCaseIds(remainingPreparedIds);
      try {
        if (remainingPreparedIds.length) window.sessionStorage.setItem(PREPARED_EXECUTION_CASES_STORAGE_KEY, JSON.stringify(remainingPreparedIds));
        else window.sessionStorage.removeItem(PREPARED_EXECUTION_CASES_STORAGE_KEY);
      } catch {
      }
    }
  };

  const handleDeleteSelectedTestCases = async () => {
    if (!token) {
      notify("Your session expired. Sign in again to delete test cases.");
      return;
    }
    const selectedIds = Array.from(new Set(executionSelectedCaseIds)).filter((caseId) => selectedCases.some((caseItem) => caseItem.id === caseId));
    if (!selectedIds.length) {
      notify("Select at least one test case to delete");
      return;
    }
    const selectedTitles = selectedIds
      .map((caseId) => selectedCases.find((caseItem) => caseItem.id === caseId)?.title ?? `Test case #${caseId}`)
      .join(", ");
    if (!window.confirm(`Delete ${selectedIds.length} selected test case${selectedIds.length === 1 ? "" : "s"}?\n\n${selectedTitles}`)) return;
    setDeletingTestCaseIds(selectedIds);
    try {
      const result = await apiFetch<{ requested_count: number; deleted_count: number }>(
        "/api/v1/test-cases/bulk",
        {
          method: "DELETE",
          body: JSON.stringify({ test_case_ids: selectedIds }),
        },
        token,
      );
      reconcileDeletedTestCases(selectedIds);
      await loadDashboardData(token, app?.name);
      notify(`${result.deleted_count} test case${result.deleted_count === 1 ? "" : "s"} deleted`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to delete selected test cases");
    } finally {
      setDeletingTestCaseIds([]);
    }
  };

  const handleBulkApproveSelectedCases = async () => {
    if (!token) {
      notify("Your session expired. Sign in again to review test cases.");
      return;
    }
    const selectedDrafts = selectedCases.filter(
      (c) => executionSelectedCaseIds.includes(c.id) && isDraftStatus(c.status),
    );
    if (!selectedDrafts.length) {
      notify("No selected test cases are in draft status.");
      return;
    }
    try {
      for (const draft of selectedDrafts) {
        await apiFetch<TestCase>(
          `/api/v1/test-cases/${draft.id}/review`,
          { method: "POST", body: JSON.stringify({ action: "approve" }) },
          token,
        );
      }
      await loadDashboardData(token, app?.name);
      notify(`${selectedDrafts.length} draft test case${selectedDrafts.length === 1 ? "" : "s"} approved and marked ready.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to approve selected test cases");
    }
  };

  const closeTestCaseEditor = () => {
    setTestCaseEditingId(null);
    setTestCaseEditorMode(null);
    setTestCaseFormTitle("");
    setTestCaseFormDescription("");
    setTestCaseFormPreconditions("");
    setTestCaseFormSteps("");
    setTestCaseFormExpectedResult("");
    setTestCaseFormStatus("draft");
    setTestCaseFormPriority("medium");
    setTestCaseFormCategory("positive");
    setTestCaseFormError("");
  };

  const openTestCaseEditor = (caseItem: TestCase) => {
    setTestCaseEditingId(caseItem.id);
    setTestCaseEditorMode("edit");
    setTestCaseFormTitle(caseItem.title);
    setTestCaseFormDescription(caseItem.description ?? "");
    setTestCaseFormPreconditions(caseItem.preconditions ?? "");
    setTestCaseFormSteps(caseItem.steps ?? "");
    setTestCaseFormExpectedResult(caseItem.expected_result ?? "");
    setTestCaseFormStatus(caseItem.status || "draft");
    setTestCaseFormPriority(caseItem.priority || "medium");
    setTestCaseFormCategory(caseItem.category || "positive");
    setTestCaseFormError("");
  };

  const openTestCaseViewer = (caseItem: TestCase) => {
    openTestCaseEditor(caseItem);
    setTestCaseEditorMode("view");
  };

  const openCreateTestCaseEditor = () => {
    if (!app?.id) {
      notify("Add an application before creating a test case");
      navigateToSection("applications");
      return;
    }
    setTestCaseEditingId(null);
    setTestCaseEditorMode("create");
    setTestCaseFormError("");

    try {
      const stored = window.localStorage.getItem(`ai-qa-engine:draft-test-case:${app.id}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed === "object" && (parsed.title || parsed.steps || parsed.description)) {
          setTestCaseFormTitle(parsed.title || "");
          setTestCaseFormDescription(parsed.description || "");
          setTestCaseFormPreconditions(parsed.preconditions || "");
          setTestCaseFormSteps(parsed.steps || "");
          setTestCaseFormExpectedResult(parsed.expectedResult || "");
          setTestCaseFormStatus(parsed.status || "draft");
          setTestCaseFormPriority(parsed.priority || "medium");
          setTestCaseFormCategory(parsed.category || "positive");
          notify("Restored unsaved test case draft");
          return;
        }
      }
    } catch {
      // Ignore parse failure
    }

    setTestCaseFormTitle("");
    setTestCaseFormDescription("");
    setTestCaseFormPreconditions("");
    setTestCaseFormSteps("");
    setTestCaseFormExpectedResult("");
    setTestCaseFormStatus("draft");
    setTestCaseFormPriority("medium");
    setTestCaseFormCategory("positive");
  };

  const saveTestCaseFromEditor = async () => {
    if (!testCaseEditorMode || testCaseEditorMode === "view") return;
    const isCreating = testCaseEditorMode === "create";
    const applicationId = app?.id;
    if (!isCreating && !testCaseEditingId) return;
    if (isCreating && !applicationId) {
      setTestCaseFormError("Select an application before creating a test case.");
      return;
    }
    if (!testCaseFormTitle.trim()) {
      setTestCaseFormError("Test case title is required.");
      return;
    }
    if (!testCaseFormSteps.trim()) {
      setTestCaseFormError("Add at least one executable step.");
      return;
    }
    if (!token) {
      setTestCaseFormError("Your session expired. Sign in again to save test cases.");
      return;
    }
    setSavingTestCase(true);
    setTestCaseFormError("");
    try {
      const savedCase = await apiFetch<TestCase>(
        isCreating ? "/api/v1/test-cases" : `/api/v1/test-cases/${testCaseEditingId}`,
        {
          method: isCreating ? "POST" : "PUT",
          body: JSON.stringify({
            ...(isCreating ? { application_id: applicationId } : {}),
            title: testCaseFormTitle.trim(),
            description: testCaseFormDescription.trim() || null,
            preconditions: testCaseFormPreconditions.trim() || null,
            steps: testCaseFormSteps.trim(),
            expected_result: testCaseFormExpectedResult.trim() || null,
            status: testCaseFormStatus,
            priority: testCaseFormPriority,
            category: testCaseFormCategory,
          }),
        },
        token,
      );
      setTestCases((current) => current.some((caseItem) => caseItem.id === savedCase.id)
        ? current.map((caseItem) => caseItem.id === savedCase.id ? savedCase : caseItem)
        : [...current, savedCase]);
      await loadAutomationReadiness(token, savedCase.application_id);
      try {
        window.localStorage.removeItem(`ai-qa-engine:draft-test-case:${savedCase.application_id}`);
      } catch {}
      notify(isCreating ? "Test case created" : "Test case updated");
      closeTestCaseEditor();
    } catch (error) {
      setTestCaseFormError(error instanceof Error ? error.message : "Unable to save test case.");
    } finally {
      setSavingTestCase(false);
    }
  };

  const updateGeneratedCaseStatus = async (caseItem: TestCase, status: "ready" | "rejected") => {
    if (!token) {
      notify("Your session expired. Sign in again to review test cases.");
      return;
    }
    setReviewingGeneratedCaseId(caseItem.id);
    try {
      const savedCase = await apiFetch<TestCase>(
        `/api/v1/test-cases/${caseItem.id}/review`,
        { method: "POST", body: JSON.stringify({ action: status === "ready" ? "approve" : "reject" }) },
        token,
      );
      setTestCases((current) => current.map((item) => item.id === savedCase.id ? savedCase : item));
      await loadAutomationReadiness(token, savedCase.application_id);
      notify(status === "ready" ? "Test case approved and ready for execution" : "Test case rejected");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to update test case review status.");
    } finally {
      setReviewingGeneratedCaseId(null);
    }
  };

  const handleConsolidateSelectedScenarios = async () => {
    if (!token || !app?.id) {
      notify("Select an application first");
      return;
    }
    if (selectedGeneratedCaseIds.length < 2) {
      notify("Select at least 2 scenarios to consolidate");
      return;
    }
    const casesToConsolidate = selectedCases.filter((c) => selectedGeneratedCaseIds.includes(c.id));
    if (!casesToConsolidate.length) return;

    setConsolidatingScenarios(true);
    try {
      const titles = casesToConsolidate.map((c) => c.title.replace(/^TC\s*\d+[:.-]?\s*/i, "").trim());
      const combinedTitle = `Consolidated E2E Flow: ${titles.slice(0, 3).join(" ➔ ")}${titles.length > 3 ? ` (+${titles.length - 3} more)` : ""}`;

      let stepIndex = 1;
      const consolidatedSteps: string[] = [];
      casesToConsolidate.forEach((c) => {
        const parsed = parseStepEntries(c.steps).filter((s) => s.text && s.text !== "—");
        if (parsed.length) {
          consolidatedSteps.push(`// --- Flow: ${c.title} ---`);
          parsed.forEach((s) => {
            consolidatedSteps.push(`${stepIndex}. ${s.text}`);
            stepIndex += 1;
          });
        }
      });

      const combinedExpected = casesToConsolidate
        .map((c) => c.expected_result?.trim())
        .filter(Boolean)
        .map((exp, i) => `${i + 1}. ${exp}`)
        .join("\n");

      const created = await apiFetch<TestCase>(
        "/api/v1/test-cases",
        {
          method: "POST",
          body: JSON.stringify({
            application_id: app.id,
            title: combinedTitle,
            steps: consolidatedSteps.join("\n"),
            expected_result: combinedExpected || "All consolidated workflow steps and assertions pass successfully.",
            status: "ready",
          }),
        },
        token,
      );
      notify(`Successfully consolidated ${casesToConsolidate.length} scenarios into "${created.title.slice(0, 45)}..."!`);
      await loadDashboardData(token, app.name);
      await loadAutomationReadiness(token, app.id);
      setSelectedGeneratedCaseIds([created.id]);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to consolidate scenarios");
    } finally {
      setConsolidatingScenarios(false);
    }
  };

  const handleBulkApproveGeneratedCases = async () => {
    if (!token || !selectedGeneratedCaseIds.length) return;
    setBulkActionWorking(true);
    try {
      await Promise.all(
        selectedGeneratedCaseIds.map(async (caseId) => {
          await apiFetch(
            `/api/v1/test-cases/${caseId}/review`,
            { method: "POST", body: JSON.stringify({ action: "approve" }) },
            token,
          ).catch(() => null);
        }),
      );
      notify(`Marked ${selectedGeneratedCaseIds.length} scenario(s) as Ready`);
      await loadDashboardData(token, app?.name);
      if (app?.id) await loadAutomationReadiness(token, app.id);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to approve scenarios");
    } finally {
      setBulkActionWorking(false);
    }
  };

  const handleBulkDeleteGeneratedCases = async () => {
    if (!token || !selectedGeneratedCaseIds.length) return;
    if (!window.confirm(`Delete ${selectedGeneratedCaseIds.length} selected scenario(s)?`)) return;
    setBulkActionWorking(true);
    try {
      await apiFetch(
        "/api/v1/test-cases/bulk",
        {
          method: "DELETE",
          body: JSON.stringify({ test_case_ids: selectedGeneratedCaseIds }),
        },
        token,
      );
      notify(`Deleted ${selectedGeneratedCaseIds.length} scenario(s)`);
      setSelectedGeneratedCaseIds([]);
      await loadDashboardData(token, app?.name);
      if (app?.id) await loadAutomationReadiness(token, app.id);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to delete scenarios");
    } finally {
      setBulkActionWorking(false);
    }
  };

  const handleBulkAssignToSuite = async (suiteId: number) => {
    if (!token || !selectedGeneratedCaseIds.length) return;
    const targetSuite = testSuites.find((s) => s.id === suiteId);
    if (!targetSuite) return;
    const merged = Array.from(new Set([...(targetSuite.case_ids || []), ...selectedGeneratedCaseIds]));
    setBulkActionWorking(true);
    try {
      await apiFetch(
        `/api/v1/test-suites/${suiteId}`,
        {
          method: "PUT",
          body: JSON.stringify({ case_ids: merged }),
        },
        token,
      );
      notify(`Assigned ${selectedGeneratedCaseIds.length} scenario(s) to suite "${targetSuite.name}"`);
      await loadDashboardData(token, app?.name);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to assign to suite");
    } finally {
      setBulkActionWorking(false);
    }
  };

  const handleBulkExportSelected = (format: "csv" | "json") => {
    if (!selectedGeneratedCaseIds.length) return;
    const casesToExport = selectedCases.filter((c) => selectedGeneratedCaseIds.includes(c.id));
    if (format === "json") {
      const blob = new Blob([JSON.stringify(casesToExport, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scenarios-${app?.name || "app"}-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const headers = ["ID", "Title", "Steps", "Expected Result", "Status"];
      const rows = casesToExport.map((c) => [
        String(c.id),
        `"${(c.title || "").replace(/"/g, '""')}"`,
        `"${(c.steps || "").replace(/"/g, '""')}"`,
        `"${(c.expected_result || "").replace(/"/g, '""')}"`,
        c.status,
      ]);
      const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scenarios-${app?.name || "app"}-${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
    notify(`Exported ${casesToExport.length} scenario(s) to ${format.toUpperCase()}`);
  };

  const closeDefectModal = (clearDraft = true) => {
    if (clearDraft) {
      try {
        window.localStorage.removeItem("ai-qa-engine:draft-defect");
      } catch {}
    }
    setDefectModalMode(null);
    setDefectEditingId(null);
    setDefectFormTitle("");
    setDefectFormDescription("");
    setDefectFormPriority("medium");
    setDefectFormSeverity("major");
    setDefectFormStatus("open");
    setDefectFormApplicationId(null);
    setDefectFormError("");
  };

  const openCreateDefectModal = () => {
    setDefectModalMode("create");
    setDefectEditingId(null);
    setDefectFormError("");

    try {
      const stored = window.localStorage.getItem("ai-qa-engine:draft-defect");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed === "object" && (parsed.title || parsed.description)) {
          setDefectFormTitle(parsed.title || "");
          setDefectFormDescription(parsed.description || "");
          setDefectFormPriority(parsed.priority || "medium");
          setDefectFormSeverity(parsed.severity || "major");
          setDefectFormStatus(parsed.status || "open");
          setDefectFormApplicationId(parsed.application_id ?? (app?.id ?? null));
          notify("Restored unsaved defect draft");
          return;
        }
      }
    } catch {}

    setDefectFormTitle("");
    setDefectFormDescription("");
    setDefectFormPriority("medium");
    setDefectFormSeverity("major");
    setDefectFormStatus("open");
    setDefectFormApplicationId(app?.id ?? null);
  };

  const openEditDefectModal = (defect: Defect) => {
    setDefectModalMode("edit");
    setDefectEditingId(defect.id);
    setDefectFormTitle(defect.title);
    setDefectFormDescription(defect.description ?? "");
    setDefectFormPriority(defect.priority.toLowerCase());
    setDefectFormSeverity(defect.severity.toLowerCase());
    setDefectFormStatus(defect.status.toLowerCase());
    setDefectFormApplicationId(defect.application_id ?? null);
    setDefectFormError("");
  };

  const saveDefectFromModal = async () => {
    const title = defectFormTitle.trim();
    if (!title) {
      setDefectFormError("Defect title is required.");
      return;
    }
    if (!token) {
      setDefectFormError("Your session expired. Sign in again to manage defects.");
      return;
    }
    setSavingDefect(true);
    setDefectFormError("");
    try {
      const payload = {
        title,
        description: defectFormDescription.trim() || null,
        priority: defectFormPriority,
        severity: defectFormSeverity,
        status: defectFormStatus,
        application_id: defectFormApplicationId,
      };
      const savedDefect = await apiFetch<Defect>(
        defectModalMode === "edit" && defectEditingId ? `/api/v1/defects/${defectEditingId}` : "/api/v1/defects",
        {
          method: defectModalMode === "edit" && defectEditingId ? "PUT" : "POST",
          body: JSON.stringify(payload),
        },
        token,
      );
      setDefects((current) => defectModalMode === "edit"
        ? current.map((defect) => defect.id === savedDefect.id ? savedDefect : defect)
        : [savedDefect, ...current]);
      setSelectedDefectId(savedDefect.id);
      try {
        window.localStorage.removeItem("ai-qa-engine:draft-defect");
      } catch {}
      notify(defectModalMode === "edit" ? "Defect updated" : "Defect reported");
      closeDefectModal(true);
    } catch (error) {
      setDefectFormError(error instanceof Error ? error.message : "Unable to save defect.");
    } finally {
      setSavingDefect(false);
    }
  };

  const deleteDefect = async (defect: Defect) => {
    if (!token || !window.confirm(`Delete defect "${defect.title}"?`)) return;
    setDeletingDefectId(defect.id);
    try {
      await apiFetch<null>(`/api/v1/defects/${defect.id}`, { method: "DELETE" }, token);
      const remaining = defects.filter((item) => item.id !== defect.id);
      setDefects(remaining);
      if (selectedDefectId === defect.id) setSelectedDefectId(remaining[0]?.id ?? null);
      notify("Defect deleted");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to delete defect.");
    } finally {
      setDeletingDefectId(null);
    }
  };

  const handleQuickDefectStatusChange = async (defect: Defect, nextStatus: string) => {
    if (!token) {
      notify("Your session expired. Sign in again to manage defects.");
      return;
    }
    try {
      const updated = await apiFetch<Defect>(
        `/api/v1/defects/${defect.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ status: nextStatus }),
        },
        token,
      );
      setDefects((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      notify(`Defect DEF-${defect.id} status updated to ${nextStatus}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to update defect status.");
    }
  };

  const handleTestAiConfig = async (provider: string, model: string, apiKey?: string, endpoint?: string) => {
    if (!token) return { status: "error", message: "Not authenticated" };
    return await apiFetch<any>(
      "/api/v1/settings/ai-configuration/test",
      {
        method: "POST",
        body: JSON.stringify({ provider, model, api_key: apiKey, endpoint }),
      },
      token,
    );
  };

  const handleSaveAiConfig = async (newConfig: {
    provider: string;
    model: string;
    api_key?: string;
    endpoint?: string;
    temperature?: number;
    max_tokens?: number;
    timeout_seconds?: number;
  }) => {
    if (!token) throw new Error("Not authenticated");
    const updated = await apiFetch<any>(
      "/api/v1/settings/ai-configuration",
      {
        method: "POST",
        body: JSON.stringify(newConfig),
      },
      token,
    );
    setAiConfigState(updated);
    notify(`AI Configuration saved successfully (${updated.provider}:${updated.model})`);
    return updated;
  };

  const handleDiscoverAiModels = async (provider: string, endpoint?: string, apiKey?: string) => {
    if (!token) return { provider, source: "catalog", models: [] };
    return await apiFetch<any>(
      "/api/v1/settings/ai-models",
      {
        method: "POST",
        body: JSON.stringify({ provider, endpoint, api_key: apiKey }),
      },
      token,
    );
  };

  const handleCreateIntegrationConnection = async (draft: IntegrationConnectionDraft) => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<IntegrationConnection>(
      "/api/v1/integrations/connections",
      { method: "POST", body: JSON.stringify(draft) },
      token,
    );
  };

  const handleUpdateIntegrationConnection = async (connectionId: number, draft: IntegrationConnectionDraft) => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<IntegrationConnection>(
      `/api/v1/integrations/connections/${connectionId}`,
      { method: "PUT", body: JSON.stringify(draft) },
      token,
    );
  };

  const handleDeleteIntegrationConnection = async (connectionId: number) => {
    if (!token) throw new Error("Not authenticated");
    await apiFetch<null>(`/api/v1/integrations/connections/${connectionId}`, { method: "DELETE" }, token);
  };

  const handleTestIntegrationConnection = async (connectionId: number): Promise<IntegrationTestResult> => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<IntegrationTestResult>(
      `/api/v1/integrations/connections/${connectionId}/test`,
      { method: "POST" },
      token,
    );
  };

  const handleSetIntegrationConnectionActive = async (connectionId: number, active: boolean) => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<IntegrationConnection>(
      `/api/v1/integrations/connections/${connectionId}/${active ? "activate" : "deactivate"}`,
      { method: "POST" },
      token,
    );
  };

  const handleLoadIntegrationAssets = async (connectionId: number, assetType: IntegrationAssetType): Promise<IntegrationAssetResponse> => {
    if (!token) throw new Error("Not authenticated");
    const connection = integrationConnections.find((item) => item.id === connectionId);
    if (!connection) throw new Error("Integration connection not found");
    const path = connection.system === "jira"
      ? `/api/v1/integrations/jira/${connectionId}/requirements`
      : connection.system === "xray"
      ? `/api/v1/integrations/xray/tests?connection_id=${connectionId}`
      : `/api/v1/integrations/qtest/${connectionId}/assets?asset_type=${encodeURIComponent(assetType)}`;
    return await apiFetch<IntegrationAssetResponse>(path, {}, token);
  };

  const handleSyncIntegrationConnection = async (connectionId: number, request: Partial<SyncExecutionRequest>): Promise<SyncExecutionResponse> => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<SyncExecutionResponse>(
      `/api/v1/integrations/connections/${connectionId}/sync`,
      {
        method: "POST",
        body: JSON.stringify({
          connection_id: connectionId,
          direction: request.direction ?? "bidirectional",
          entity_types: request.entity_types ?? ["test_case", "test_execution"],
          conflict_policy: request.conflict_policy ?? "external_wins",
          dry_run: request.dry_run ?? false,
        }),
      },
      token,
    );
  };

  const handleLoadConnectionMappings = async (connectionId: number): Promise<ConnectionMappings> => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<ConnectionMappings>(
      `/api/v1/integrations/connections/${connectionId}/mappings`,
      {},
      token,
    );
  };

  const handleSaveConnectionMappings = async (connectionId: number, mappings: ConnectionMappings): Promise<ConnectionMappings> => {
    if (!token) throw new Error("Not authenticated");
    return await apiFetch<ConnectionMappings>(
      `/api/v1/integrations/connections/${connectionId}/mappings`,
      {
        method: "PUT",
        body: JSON.stringify(mappings),
      },
      token,
    );
  };

  const handleUpdateIntegrationEnvironment = async (update: IntegrationEnvironmentUpdate): Promise<IntegrationEnvironmentConfig> => {
    if (!token) throw new Error("Not authenticated");
    const configuration = await apiFetch<IntegrationEnvironmentConfig>(
      "/api/v1/integrations/environment",
      { method: "PUT", body: JSON.stringify(update) },
      token,
    );
    setIntegrationEnvironmentConfiguration(configuration);
    return configuration;
  };

  const handleIngestText = async (useAi = false) => {
    const selectedApp = app;
    if (!selectedApp?.id || !token) {
      notify("Select an application first");
      return;
    }
    const content = textIngestContent.trim();
    if (!content) {
      notify("Please enter or paste your test case steps, user story, or table");
      return;
    }
    setTextIngestLoading(true);
    try {
      if (useAi) {
        setAiPrompt(content);
        const generated = await generateAiCases(content);
        if (generated) {
          setTextIngestModalOpen(false);
          setTextIngestContent("");
        }
      } else {
        const created = await apiFetch<TestCase[]>(
          "/api/v1/test-cases/ingest",
          {
            method: "POST",
            body: JSON.stringify({
              application_id: selectedApp.id,
              format: textIngestFormat,
              content: content,
              preconditions: textIngestPreconditions.trim() || undefined,
              target_url: selectedApp.url || selectedApp.target,
            }),
          },
          token,
        );
        setTestCases((current) => [...current, ...created]);
        await loadDashboardData(token, selectedApp.name);
        await loadAutomationReadiness(token, selectedApp.id);
        setTextIngestModalOpen(false);
        setTextIngestContent("");
        notify(`Ingested ${created.length} test case(s) successfully`);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "Failed to ingest test cases");
    } finally {
      setTextIngestLoading(false);
    }
  };

  useEffect(() => {
    if (token) void loadDashboardData(token);
  }, [token]);

  useEffect(() => {
    if (!appName) return;
    window.localStorage.setItem("ai-qa-engine:selected-app", appName);
  }, [appName]);

  useEffect(() => {
    setSection(PATH_SECTIONS[pathname] ?? "dashboard");
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (projectCatalog.some((project) => project.id === selectedProjectId)) return;
    if (!projectCatalog.length) {
      setSelectedProjectId(PRIMARY_PROJECT_ID);
      setProjectDetailTab("overview");
      return;
    }
    setSelectedProjectId(projectCatalog[0].id);
    setProjectDetailTab("overview");
  }, [projectCatalog, selectedProjectId]);

  useEffect(() => {
    const handleAuthExpired = () => {
      setAuthError("Your session expired. Please sign in again.");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  useEffect(() => {
    if (!token || !app?.id) {
      setCaseExecutions([]);
      setAutomationReadinessByCaseId({});
      setExecutionSelectedCaseIds([]);
      if (!token) {
        setTestSuites([]);
      }
      return;
    }
    void refreshExecutionHistory(token, app.id);
    void loadAutomationReadiness(token, app.id);
  }, [token, app?.id]);

  useEffect(() => {
    setExecutionSelectedCaseIds((current) => current.filter((caseId) => selectedCases.some((caseItem) => caseItem.id === caseId)));
  }, [selectedCases]);

  useEffect(() => {
    setExecutionLibraryPage(1);
  }, [app?.id, executionLibrarySearch, executionLibrarySortBy, executionLibraryStatusFilter, executionLibraryPageSize]);

  useEffect(() => {
    if (!testCases.length) return;
    const availableIds = new Set(testCases.filter((caseItem) => caseItem.application_id === app?.id).map((caseItem) => caseItem.id));
    setLatestGeneratedCaseIds((current) => current.filter((caseId) => availableIds.has(caseId)));
  }, [app?.id, testCases]);

  useEffect(() => {
    if (!app?.id) {
      currentAiAppIdRef.current = null;
      setAiTargetUrl("");
      setAiGenerationSource(null);
      return;
    }
    if (currentAiAppIdRef.current !== app.id) {
      currentAiAppIdRef.current = app.id;
      setAiTargetUrl(app.url ?? "");
      setAiGenerationSource(null);
    }
  }, [app?.id, app?.url]);

  // Automatically synchronize runtimeParameters to localStorage per application (debounced to avoid typing lag)
  useEffect(() => {
    if (!app?.id || !runtimeParameters.length) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(
          `${TEST_DATA_PROFILE_STORAGE_KEY}:${app.id}`,
          JSON.stringify(runtimeParameters)
        );
      } catch {
        // Ignore storage errors
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [app?.id, runtimeParameters]);

  // Auto-save test case draft (debounced to avoid typing lag)
  useEffect(() => {
    if (testCaseEditorMode !== "create" || !app?.id) return;
    if (!testCaseFormTitle && !testCaseFormSteps && !testCaseFormDescription) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(`ai-qa-engine:draft-test-case:${app.id}`, JSON.stringify({
          title: testCaseFormTitle,
          description: testCaseFormDescription,
          preconditions: testCaseFormPreconditions,
          steps: testCaseFormSteps,
          expectedResult: testCaseFormExpectedResult,
          status: testCaseFormStatus,
          priority: testCaseFormPriority,
          category: testCaseFormCategory,
        }));
      } catch {}
    }, 400);
    return () => window.clearTimeout(timer);
  }, [testCaseEditorMode, app?.id, testCaseFormTitle, testCaseFormSteps, testCaseFormDescription, testCaseFormPreconditions, testCaseFormExpectedResult, testCaseFormStatus, testCaseFormPriority, testCaseFormCategory]);

  // Auto-save defect draft (debounced to avoid typing lag)
  useEffect(() => {
    if (defectModalMode !== "create") return;
    if (!defectFormTitle && !defectFormDescription) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem("ai-qa-engine:draft-defect", JSON.stringify({
          title: defectFormTitle,
          description: defectFormDescription,
          priority: defectFormPriority,
          severity: defectFormSeverity,
          status: defectFormStatus,
          application_id: defectFormApplicationId,
        }));
      } catch {}
    }, 400);
    return () => window.clearTimeout(timer);
  }, [defectModalMode, defectFormTitle, defectFormDescription, defectFormPriority, defectFormSeverity, defectFormStatus, defectFormApplicationId]);

  // Unsaved changes protection before window close/reload
  useEffect(() => {
    const isEditing = Boolean(
      (testCaseEditorMode !== null && testCaseEditorMode !== "view" && (testCaseFormTitle.trim() || testCaseFormSteps.trim())) ||
      (defectModalMode !== null && defectFormTitle.trim()) ||
      (projectModalMode !== null && projectFormName.trim()) ||
      applicationEditingId !== null
    );

    if (!isEditing) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
      return "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [testCaseEditorMode, testCaseFormTitle, testCaseFormSteps, defectModalMode, defectFormTitle, projectModalMode, projectFormName, applicationEditingId]);

  const [populatingParameters, setPopulatingParameters] = useState(false);

  const autoPopulateRuntimeParameters = async (forceOverwrite = false) => {
    if (!app?.id) {
      notify("Select an application to auto-populate parameters");
      return;
    }
    if (!token) {
      return;
    }
    setPopulatingParameters(true);
    try {
      const response = await apiFetch<{
        application_id: number;
        application_name: string;
        parameters: Array<{ id: string; key: string; value: string; sensitive: boolean; source: string }>;
        detected_keys: string[];
      }>(`/api/v1/test-data/resolve-parameters/${app.id}`, {}, token);

      if (response && Array.isArray(response.parameters)) {
        setRuntimeParameters((current) => {
          const currentMap = new Map(current.map((p) => [p.key.trim().toLowerCase(), p]));
          const next: RuntimeParameter[] = [...current];

          for (const param of response.parameters) {
            const keyLower = param.key.trim().toLowerCase();
            if (!currentMap.has(keyLower)) {
              const newParam: RuntimeParameter = {
                id: param.id || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                key: param.key,
                value: param.value,
                sensitive: param.sensitive,
              };
              next.push(newParam);
              currentMap.set(keyLower, newParam);
            } else if (forceOverwrite) {
              const idx = next.findIndex((p) => p.key.trim().toLowerCase() === keyLower);
              if (idx >= 0) {
                next[idx] = {
                  ...next[idx],
                  value: param.value,
                  sensitive: param.sensitive,
                };
              }
            }
          }

          return next;
        });
        notify(`Auto-populated ${response.parameters.length} runtime parameter(s) from AI test data.`);
      }
    } catch (error) {
      notify(`Unable to auto-populate test data: ${error instanceof Error ? error.message : "API error"}`);
    } finally {
      setPopulatingParameters(false);
    }
  };

  useEffect(() => {
    const applicationId = app?.id;
    if (!applicationId) {
      resolvedRuntimeProfileApplicationRef.current = null;
      setRuntimeParameters([]);
      return;
    }
    if (resolvedRuntimeProfileApplicationRef.current === applicationId) return;
    resolvedRuntimeProfileApplicationRef.current = applicationId;
    try {
      const stored = window.localStorage.getItem(`${TEST_DATA_PROFILE_STORAGE_KEY}:${applicationId}`);
      if (stored) {
        const parsed = JSON.parse(stored) as RuntimeParameter[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setRuntimeParameters(parsed
            .filter((parameter) => parameter && typeof parameter === "object")
            .map((parameter) => ({
              id: typeof parameter.id === "string" && parameter.id ? parameter.id : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              key: typeof parameter.key === "string" ? parameter.key : "",
              value: typeof parameter.value === "string" ? parameter.value : "",
              sensitive: parameter.sensitive === true,
            })));
          return;
        }
      }
      void autoPopulateRuntimeParameters(false);
    } catch {
      void autoPopulateRuntimeParameters(false);
    }
  }, [app?.id]);

  useEffect(() => {
    if (!running) return;
    setExecutionClockMs(Date.now());
    const timer = window.setInterval(() => {
      setExecutionClockMs(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!voiceOverEnabled || !voiceOverEventLog || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    for (const event of parseLiveEventsFromLog(voiceOverEventLog.log)) {
      if (!isExecutionSpeechAction(event.message)) continue;
      const eventKey = `${voiceOverEventLog.runId}|${event.state}|${event.message}`;
      if (spokenExecutionEventsRef.current.has(eventKey)) continue;
      spokenExecutionEventsRef.current.add(eventKey);
      const spokenMessage = cleanExecutionSpeech(event.message)
        .replace(/https?:\/\/\S+/gi, "target URL")
        .replace(/(password|secret|token)[^,.;]*/gi, "$1 field");
      const speechRate = resolveExecutionSpeechRate(executionSlowMode);
      if (spokenMessage) speakExecutionMessage(spokenMessage, speechRate, voiceGender, true);
    }
  }, [executionSlowMode, voiceGender, voiceOverEnabled, voiceOverEventLog]);

  useEffect(() => {
    if (!voiceOverEnabled && typeof window !== "undefined" && "speechSynthesis" in window) {
      stopExecutionSpeech();
    }
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        stopExecutionSpeech();
      }
    };
  }, [voiceOverEnabled]);

  const appendExecutionActivity = (message: string) => {
    const stamp = `${new Date().toLocaleTimeString()} · ${message}`;
    setExecutionActivityLog((current) => [...current.slice(-19), stamp]);
  };

  const handleVoiceGenderChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextVoiceGender = event.target.value;
    if (nextVoiceGender !== "male" && nextVoiceGender !== "female") return;
    setVoiceGender(nextVoiceGender);
    try {
      window.localStorage.setItem(VOICE_MODE_STORAGE_KEY, nextVoiceGender);
    } catch {
    }
  };

  const testVoiceOver = () => {
    if (!voiceOverEnabled) return;
    const speechRate = resolveExecutionSpeechRate(executionSlowMode);
    if (!speakExecutionMessage(`Voice-over is enabled with a ${voiceGender} voice. Execution actions will be announced aloud in lockstep with test steps.`, speechRate, voiceGender)) {
      notify("Voice-over is not supported by this browser");
    }
  };

  const selectApplication = (name: string) => {
    const nextApplication = applications.find((item) => item.name === name);
    setSelectedAppId(nextApplication?.id ?? null);
    setAppName(name);
    window.localStorage.setItem("ai-qa-engine:selected-app", name);
  };

  const clearPreparedExecution = () => {
    setPreparedExecutionCaseIds([]);
    try {
      window.sessionStorage.removeItem(PREPARED_EXECUTION_CASES_STORAGE_KEY);
    } catch {
    }
  };

  const prepareTestCaseRun = (caseId: number) => {
    const preparedIds = [caseId];
    setPreparedExecutionCaseIds(preparedIds);
    setExecutionRunScope("all");
    try {
      window.sessionStorage.setItem(PREPARED_EXECUTION_CASES_STORAGE_KEY, JSON.stringify(preparedIds));
    } catch {
    }
    navigateToSection("execution");
    setExecutionScopeDialog({ caseIds: preparedIds, triggerLabel: "Run selected test case", fixedScope: true });
  };

  const focusApplication = (name: string) => {
    selectApplication(name);
    setApplicationDetailTab("overview");
  };

  const openSystemMap = (name?: string) => {
    if (name) {
      focusApplication(name);
    }
    navigateToSection("systemMap");
  };

  const openApplicationWorkspace = (name: string, target: Section) => {
    focusApplication(name);
    navigateToSection(target);
  };

  const logout = (message = "Signed out successfully") => {
    clearToken();
    setSection("dashboard");
    setApplications([]);
    setTestCases([]);
    setDefects([]);
    setRuns([]);
    setTestSuites([]);
    setCaseExecutions([]);
    setAutomationReadinessByCaseId({});
    setExecutionResult(null);
    setLiveResult(null);
    setRunStatus("Idle");
    setRunLog("");
    setExecutionRunScope("all");
    setAiGenerationPhase("idle");
    setExecutionPhase("idle");
    setExecutionProgress({ total: 0, current: 0, passed: 0, failed: 0, activeCaseTitle: "" });
    setExecutionRunStartedAt(null);
    setExecutionClockMs(Date.now());
    setExecutionLiveCases([]);
    setExecutionActivityLog([]);
    setExecutionMode("watch_live");
    setExecutionParallelism(DEFAULT_EXECUTION_PARALLELISM);
    setExecutionSlowMode("normal");
    setExecutionTraceMode("on_failure");
    setKeepBrowserOpenOnFailure(true);
    setKeepBrowserOpenSeconds(6);
    closeApplicationEditModal();
    setAuthError("");
    router.push("/");
    notify(message);
  };

  const authenticate = async (event: React.FormEvent) => {
    event.preventDefault();
    setAuthError("");
    setAuthenticating(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail, password: authPassword }),
      });
      const body = (await response.json()) as { access_token?: string; detail?: string };
      if (!response.ok || !body.access_token) {
        throw new Error(typeof body.detail === "string" ? body.detail : "Authentication failed");
      }
      setToken(body.access_token);
      setToken(body.access_token);
      await loadDashboardData(body.access_token, appName);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setAuthenticating(false);
    }
  };

  const runSelectedTests = async () => {
    if (!app || !token) return;
    if (app.platform !== "web") {
      setExecutionPhase("error");
      setRunStatus("Unavailable");
      setRunLog("Mobile execution requires a configured Appium device provider.");
      notify("Select a web application for Playwright execution");
      return;
    }
    const effectiveEmailSelector = emailSelector.trim() || DEFAULT_LOGIN_EMAIL_SELECTOR;
    const effectivePasswordSelector = passwordSelector.trim() || DEFAULT_LOGIN_PASSWORD_SELECTOR;
    const effectiveSubmitSelector = submitSelector.trim() || DEFAULT_LOGIN_SUBMIT_SELECTOR;
    const runtimeParameterError = validateRuntimeParameters(runtimeParameters, authenticatedFlow, [effectiveEmailSelector, effectivePasswordSelector, effectiveSubmitSelector]);
    if (runtimeParameterError) {
      notify(runtimeParameterError);
      return;
    }
    const executionParameters = buildRuntimeParameterMap(runtimeParameters);
    const runStartedAt = Date.now();
    spokenExecutionEventsRef.current.clear();
    setVoiceOverEventLog(null);
    stopExecutionSpeech();
    if (voiceOverEnabled) {
      speakExecutionMessage(
        `Voice-over enabled with a ${voiceGender} voice. Starting execution of one test run.`,
        resolveExecutionSpeechRate(executionSlowMode),
        voiceGender,
      );
    }
    setRunning(true);
    setExecutionResult(null);
    setRunStatus("Submitting run");
    setRunLog("Preparing browser checks...");
    try {
      const resolvedHeadless = executionMode === "background";
      const keepOpenSeconds = resolvedHeadless ? 0 : Math.max(0, Math.min(120, keepBrowserOpenSeconds));
      const steps = authenticatedFlow ? [
        { action: "type", selector: effectiveEmailSelector, value: "{{login_email}}" },
        { action: "type", selector: effectivePasswordSelector, value: "{{login_password}}" },
        { action: "click", selector: effectiveSubmitSelector },
        { action: "assert_visible", selector: "body" },
      ] : [];
      const response = await fetch(`${API_BASE_URL}/api/v1/execution/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          application_id: app.id,
          url: app.url,
          steps,
          checks: [{ type: "visible", value: "body" }],
          capture_screenshot: captureScreenshotEvidence,
          highlight_actions: highlightActionTargets,
          capture_video: recordVideoEvidence,
          capture_audio: recordVideoEvidence && voiceOverEnabled,
          voice_gender: voiceGender,
          execution_mode: executionMode,
          headless: resolvedHeadless,
          slow_mode: executionSlowMode,
          trace_mode: executionTraceMode,
          keep_browser_open_seconds: keepOpenSeconds,
          keep_browser_open_on_failure: keepBrowserOpenOnFailure,
          parameters: executionParameters,
        }),
      });
      const queued = (await response.json()) as { run_id?: string; detail?: string };
      if (!response.ok || !queued.run_id) throw new Error(queued.detail ?? "Runner returned an error");
      await refreshExecutionHistory(token, app.id);
      setRunStatus("Queued");
      setRunLog(`Run ${queued.run_id.slice(0, 8)} queued. Waiting for browser worker...`);

      const pollPlan = buildPollingPlan(steps.length, 1, executionMode);
      let result: ExecutionResult | null = null;
      for (let attempt = 0; attempt < pollPlan.maxAttempts; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, pollPlan.pollIntervalMs));
        const statusResponse = await fetch(`${API_BASE_URL}/api/v1/execution/${queued.run_id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const status = (await statusResponse.json()) as RunStatusSnapshot;
        if (!statusResponse.ok) throw new Error(status.detail ?? "Unable to read run status");
        const fallbackEvent = latestLiveEvent(status.log);
        const liveState = (status.live_state ?? fallbackEvent?.state ?? "").toUpperCase();
        const currentAction = status.current_action ?? fallbackEvent?.message ?? "";
        const terminalStatus = (status.status ?? "").toLowerCase();
        const isTerminal = ["passed", "failed", "error"].includes(terminalStatus);
        setExecutionPhase(
          isTerminal
            ? (terminalStatus === "passed" ? "done" : "error")
            : mapLiveStateToExecutionPhase(liveState),
        );
        setRunStatus(liveState ? `${formatLiveStateLabel(liveState)} · ${status.status ?? "running"}` : status.status ?? "running");
        setRunLog(currentAction || "Browser worker is processing the run...");
        setVoiceOverEventLog({ runId: queued.run_id, log: status.log ?? currentAction ?? "" });
        if (isTerminal) {
          result = status.result ?? {
            run_id: queued.run_id,
            url: app.url,
            status: (status.status as "passed" | "failed" | "error") ?? "error",
            duration_ms: 0,
            checks: [],
            error: status.log,
          };
          break;
        }
      }
      if (!result) {
        throw new Error(
          `Execution is still running after ${Math.round(pollPlan.maxWaitMs / 1000)} seconds. ` +
          "Keep this run open or check execution history.",
        );
      }
      setExecutionResult(result);
      await loadDashboardData(token, app?.name);
      await refreshExecutionHistory(token, app.id);
      setRunStatus(result.status);
      setRunLog(result.status === "passed" ? "All checks completed successfully." : result.error ?? "Checks completed with failures.");
      notify(result.status === "passed" ? "Execution passed" : `Execution ${result.status}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to reach the QA runner.";
      setExecutionResult({
        run_id: "unavailable",
        url: app.url,
        status: "error",
        duration_ms: Math.max(0, Date.now() - runStartedAt),
        checks: [],
        error: message,
      });
      setRunStatus("error");
      setRunLog(message);
      await refreshExecutionHistory(token, app.id);
      notify("QA runner unavailable");
    } finally {
      setRunning(false);
    }
  };

  const buildAutomationFromCase = (caseItem: TestCase) => {
    const effectiveEmailSelector = emailSelector.trim() || DEFAULT_LOGIN_EMAIL_SELECTOR;
    const effectivePasswordSelector = passwordSelector.trim() || DEFAULT_LOGIN_PASSWORD_SELECTOR;
    const effectiveSubmitSelector = submitSelector.trim() || DEFAULT_LOGIN_SUBMIT_SELECTOR;
    const steps: Array<{ action: "click" | "type" | "select" | "check" | "uncheck" | "navigate" | "go_back" | "reload" | "assert_visible" | "assert_text" | "assert_title" | "assert_url_contains"; selector?: string; value?: string; secret_name?: string }> = [];
    const checks: Array<{ type: "title_contains" | "visible" | "text_contains"; value: string }> = [{ type: "visible", value: "body" }];
    const stepLines = (caseItem.steps ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const normalizedStepLines = stepLines.map((line) => line.replace(/^\d+[\).:\-\s]*/, "").trim().toLowerCase());
    const pushStep = (...stepItems: Array<{ action: "click" | "type" | "select" | "check" | "uncheck" | "navigate" | "go_back" | "reload" | "assert_visible" | "assert_text" | "assert_title" | "assert_url_contains"; selector?: string; value?: string; secret_name?: string }>) => {
      for (const step of stepItems) {
        const previous = steps[steps.length - 1];
        if (
          previous
          && previous.action === step.action
          && previous.selector === step.selector
          && previous.value === step.value
          && previous.secret_name === step.secret_name
        ) {
          continue;
        }
        steps.push(step);
      }
    };
    const credentialInstructionLines = normalizedStepLines.filter((line) => isLoginInstructionLine(line));
    const hasNegativeCredentialInstruction = normalizedStepLines.some((line) => isInvalidCredentialInstruction(line));
    let loginCredentialsAdded = false;
    const appendLoginCredentialSteps = (credentialText: string) => {
      if (loginCredentialsAdded) return;
      const clauses = credentialText.split(/\s+(?:and|then)\s+|[,;]/).map((clause) => clause.trim()).filter(Boolean);
      const negativeSignal = isInvalidCredentialInstruction(credentialText);
      const emailMentioned = /\b(?:email|username|user name)\b/.test(credentialText);
      const passwordMentioned = /\b(?:password|passcode)\b/.test(credentialText);
      const broadInvalid = negativeSignal && !emailMentioned && !passwordMentioned;
      const emailInvalid = broadInvalid || clauses.some((clause) => /\b(?:invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent)\b/.test(clause) && /\b(?:email|username|user name)\b/.test(clause));
      const passwordInvalid = broadInvalid || clauses.some((clause) => /\b(?:invalid|incorrect|wrong|bad|unknown|unregistered|nonexistent|expired|locked|disabled)\b/.test(clause) && /\b(?:password|passcode)\b/.test(clause));
      pushStep(
        emailInvalid
          ? { action: "type", selector: effectiveEmailSelector, value: /\bformat\b/.test(credentialText) ? "not-an-email" : "invalid.user@example.invalid" }
          : { action: "type", selector: effectiveEmailSelector, value: "{{login_email}}" },
        passwordInvalid
          ? { action: "type", selector: effectivePasswordSelector, value: "invalid-password-for-negative-test" }
          : { action: "type", selector: effectivePasswordSelector, value: "{{login_password}}" },
        { action: "click", selector: effectiveSubmitSelector },
        { action: "assert_visible", selector: "body" },
      );
      loginCredentialsAdded = true;
    };
    const pushClickFromTarget = (target: string) => {
      const normalizedTarget = normalizeActionTargetText(target);
      if (!normalizedTarget) return;
      const splitTargets = normalizedTarget
        .split(/\s*-\s*/)
        .map((part) => normalizeActionTargetText(part))
        .filter((part) => part.length >= 2);
      if (splitTargets.length > 1) {
        for (const part of splitTargets) {
          pushStep({ action: "click", selector: `text=${part}` });
        }
        return;
      }
      pushStep({ action: "click", selector: `text=${normalizedTarget}` });
    };

    const hasExplicitLoginSteps = normalizedStepLines.some((line) => isLoginInstructionLine(line));

    if (authenticatedFlow && !credentialInstructionLines.length && !hasNegativeCredentialInstruction && !hasExplicitLoginSteps) {
      appendLoginCredentialSteps("enter valid credentials");
    }

    for (const rawLine of stepLines) {
      const line = rawLine.replace(/^\d+[\).:\-\s]*/, "").trim();
      if (!line) continue;
      const lowerLine = line.toLowerCase();
      const quoted = Array.from(line.matchAll(/"([^"]+)"|'([^']+)'/g))
        .map((match) => (match[1] ?? match[2] ?? "").trim())
        .filter(Boolean);
      const isClickInstruction = /(click|open|tap|choose)\b/.test(lowerLine);
      const urlMatch = line.match(/https?:\/\/[^\s)]+/i);
      let mappedStep = false;

      // 0. Verification / assertion lines handled FIRST
      if (isVerificationOnlyLine(lowerLine)) {
        if (lowerLine.includes("url") || lowerLine.includes("redirect")) {
          const pathQuoted = line.match(/["'](\/[^"']*)["']/)?.[1];
          const pathParen = line.match(/\((\/[^)\s]+)\)/)?.[1];
          const expectedPath = (pathQuoted ?? pathParen ?? "").trim();
          if (expectedPath) {
            pushStep({ action: "assert_url_contains", value: expectedPath });
            continue;
          }
        }
        if (lowerLine.includes("title") || lowerLine.includes("heading")) {
          if (quoted.length) {
            pushStep({ action: "assert_title", value: quoted[0] });
            continue;
          }
          const titleMatch = line.match(/(?:title|heading)\s+(?:is|contains|displayed as)\s+['"]?([^'"]+)['"]?/i);
          if (titleMatch?.[1]) {
            pushStep({ action: "assert_title", value: titleMatch[1].trim() });
            continue;
          }
        }
        const assertedText = extractVerificationText(line, quoted);
        if (assertedText && assertedText.length >= 2) {
          pushStep({ action: "assert_text", selector: "body", value: assertedText });
        } else {
          pushStep({ action: "assert_visible", selector: "body" });
        }
        continue;
      }

      if (authenticatedFlow && isLoginInstructionLine(lowerLine)) {
        if (urlMatch) pushStep({ action: "navigate", value: urlMatch[0].replace(/[.,]$/, "") });
        if (!loginCredentialsAdded) {
          appendLoginCredentialSteps(credentialInstructionLines.join(" and "));
        }
        continue;
      }
      if (/^repeat\s+step/i.test(lowerLine)) {
        continue;
      }

      // Checkbox actions
      if (/\b(check|uncheck|tick|untick)\b/i.test(lowerLine)) {
        const isUncheck = /\b(uncheck|untick)\b/i.test(lowerLine);
        const actionName = isUncheck ? "uncheck" : "check";
        const cbTarget = quoted[0] || line.match(/(?:check|uncheck|tick|untick)\s+(?:the\s+)?(.+?)(?:\s+checkbox|\s+box|\s+toggle|$)/i)?.[1];
        if (cbTarget) {
          if (cbTarget.startsWith("<") && cbTarget.includes(">")) {
            pushStep({ action: actionName, selector: cbTarget });
          } else {
            const targetClean = normalizeActionTargetText(cbTarget.replace(/\b(checkbox|box|toggle|the)\b/gi, ""));
            pushStep({ action: actionName, selector: `label=${targetClean || cbTarget}` });
          }
          continue;
        }
      }

      if (urlMatch) {
        pushStep({ action: "navigate", value: urlMatch[0].replace(/[.,]$/, "") });
        continue;
      }

      if (lowerLine.includes("navigate back")) {
        pushStep({ action: "navigate", value: app.url });
        continue;
      }

      const tabUnderMatch = line.match(/^select\s+(.+?)\s+tab\s+under\s+(.+)$/i);
      if (tabUnderMatch?.[1]) {
        const tabTarget = normalizeActionTargetText(tabUnderMatch[1]);
        if (tabTarget) {
          pushStep({ action: "click", selector: `text=${tabTarget}` });
        }
        continue;
      }

      if (isClickInstruction) {
        const hrefMatch = line.match(/\((\/[^)\s]+)\)/);
        if (hrefMatch?.[1]) {
          pushStep({ action: "click", selector: `a[href='${hrefMatch[1]}']` });
          mappedStep = true;
          continue;
        }
        const clickTarget = quoted[0];
        if (clickTarget) {
          pushClickFromTarget(clickTarget);
          mappedStep = true;
        } else {
          const clickMatch = line.match(/(?:click|open|tap|choose)\s+(?:the\s+)?(.+?)(?:\s+button|\s+link|\s+dropdown|\s+menu|$)/i);
          if (clickMatch?.[1]) {
            pushClickFromTarget(clickMatch[1]);
            mappedStep = true;
          }
        }
      }

      if (!mappedStep && lowerLine.includes("select")) {
        const selectFromDropdownMatch = line.match(/^select\s+(.+?)\s+from\s+(.+?)\s*(?:filter)?\s*dropdown/i);
        if (selectFromDropdownMatch?.[1] && selectFromDropdownMatch?.[2]) {
          const optionText = normalizeActionTargetText(selectFromDropdownMatch[1]);
          const fieldText = normalizeActionTargetText(selectFromDropdownMatch[2].replace(/\bfilter\b/i, ""));
          if (optionText && fieldText) {
            pushStep({ action: "select", selector: `label=${fieldText}`, value: optionText });
            mappedStep = true;
            continue;
          }
        }
        if (quoted.length) {
          pushClickFromTarget(quoted[0]);
          mappedStep = true;
          continue;
        }
        const selectMatch = line.match(/select\s+(.+?)(?:\s+(?:in|from)\s+.+)?$/i);
        const selectValue = normalizeActionTargetText(selectMatch?.[1]?.replace(/^the\s+/i, "") ?? "");
        if (selectValue && selectValue.length >= 2) {
          pushClickFromTarget(selectValue);
          mappedStep = true;
          continue;
        }
      }

      if (!mappedStep && (lowerLine.includes("enter") || lowerLine.includes("type") || lowerLine.includes("fill") || lowerLine.includes("set"))) {
        const inMatch = line.match(/(?:enter|type|input|fill|set)\s+(?:["']?(\{\{[^}]+\}\}|\$\{[^}]+\}|[^"'\n,]+?)["']?)\s+(?:in|into|for)\s+(?:the\s+)?["']?([a-zA-Z0-9_\s\-]+?)["']?(?:\s+field|\s+input|\s+filter|\s+box|$)/i);
        const asMatch = line.match(/(?:enter|type|input|fill|set)\s+(?:the\s+)?["']?([a-zA-Z0-9_\s\-]+?)["']?(?:\s+field|\s+input|\s+filter)?\s+(?:as|with|to)\s+["']?(\{\{[^}]+\}\}|\$\{[^}]+\}|[^"'\n,]+?)["']?/i);
        const targetField = inMatch?.[2] ?? asMatch?.[1] ?? (quoted.length >= 2 ? quoted[1] : null);
        const targetVal = inMatch?.[1] ?? asMatch?.[2] ?? (quoted.length ? quoted[0] : null);

        if (targetField && targetVal) {
          const rawFn = targetField.trim();
          const cleanFn = normalizeActionTargetText(rawFn.replace(/\b(field|input|filter|box|the)\b/gi, ""));
          const fnLower = cleanFn.toLowerCase();
          const val = targetVal.trim().replace(/^["']|["']$/g, "");
          let sel = `label=${cleanFn || rawFn}`;
          if (fnLower === "email" || fnLower === "username" || fnLower === "user" || val.includes("@")) {
            sel = effectiveEmailSelector;
          } else if (fnLower === "password" || fnLower === "passcode" || fnLower === "pass") {
            sel = effectivePasswordSelector;
          }
          pushStep({ action: "type", selector: sel, value: val });
          mappedStep = true;
          continue;
        }

        if (quoted.length) {
          const val = quoted[0];
          if (val.includes("@")) {
            pushStep({ action: "type", selector: effectiveEmailSelector, value: val });
            mappedStep = true;
            continue;
          }
          const fieldNameMatch = line.match(/(?:in|into|for)\s+(?:the\s+)?["']?([a-zA-Z0-9_\s\-]+?)["']?(?:\s+field|\s+input|\s+filter|\s+box|$)/i);
          const rawFn = fieldNameMatch?.[1] ?? (line.includes("password") ? "password" : line.includes("email") ? "email" : "Search");
          const cleanFn = normalizeActionTargetText(rawFn.replace(/\b(field|input|filter|box|the)\b/gi, ""));
          const fnLower = cleanFn.toLowerCase();
          let sel = `label=${cleanFn || rawFn}`;
          if (fnLower === "email" || fnLower === "username" || fnLower === "user") {
            sel = effectiveEmailSelector;
          } else if (fnLower === "password" || fnLower === "passcode") {
            sel = effectivePasswordSelector;
          }
          pushStep({ action: "type", selector: sel, value: val });
          mappedStep = true;
          continue;
        }

        const fieldNameMatch = line.match(/(?:in|into|for)\s+(?:the\s+)?["']?([a-zA-Z0-9_\s\-]+?)["']?(?:\s+field|\s+input|\s+filter|\s+box|$)/i);
        if (fieldNameMatch?.[1]) {
          const rawFn = fieldNameMatch[1];
          const cleanFn = normalizeActionTargetText(rawFn.replace(/\b(field|input|filter|box|the)\b/gi, ""));
          const fnLower = cleanFn.toLowerCase();
          const paramKey = fnLower.replace(/\s+/g, "_").replace(/-/g, "_");
          const val = `{{${paramKey}}}`;
          let sel = `label=${cleanFn || rawFn}`;
          if (fnLower === "email" || fnLower === "username" || fnLower === "user") {
            sel = effectiveEmailSelector;
          } else if (fnLower === "password" || fnLower === "passcode") {
            sel = effectivePasswordSelector;
          }
          pushStep({ action: "type", selector: sel, value: val });
          mappedStep = true;
          continue;
        }
      }

      if (!mappedStep && lowerLine.includes("sort")) {
        const sortMatch = line.match(/sort\s+.+?\s+by\s+(.+?)(?:\s+in\s+|$)/i);
        const sortField = normalizeActionTargetText(sortMatch?.[1] ?? "");
        if (sortField && sortField.length >= 2) {
          pushStep({ action: "click", selector: `text=${sortField}` });
          continue;
        }
      }

      if (!mappedStep && (lowerLine.includes("open the application") || lowerLine.includes("wait for the page to load"))) {
        pushStep({ action: "navigate", value: app.url });
        continue;
      }

      if (!mappedStep && quoted.length) {
        const assertedText = normalizeActionTargetText(quoted[0]);
        if (assertedText && assertedText.length >= 2) {
          pushStep({ action: "assert_text", selector: "body", value: assertedText });
        } else {
          pushStep({ action: "assert_visible", selector: "body" });
        }
        continue;
      }

      if (!mappedStep) {
        pushStep({ action: "assert_visible", selector: "body" });
      }
    }

    const expectedLines = (caseItem.expected_result ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    for (const line of expectedLines) {
      const quoted = Array.from(line.matchAll(/"([^"]+)"|'([^']+)'/g))
        .map((match) => (match[1] ?? match[2] ?? "").trim())
        .filter(Boolean);
      const candidate = quoted[0] ?? "";
      const queueMessageLike = /(queue an import job|queued successfully)/i.test(candidate);
      if (candidate.length >= 3 && !queueMessageLike) {
        checks.push({ type: "text_contains", value: candidate.slice(0, 500) });
      }
      if (checks.length >= 10) break;
    }

    return { steps, checks };
  };

  const queueCaseRun = async (
    caseItem: TestCase,
    parameters: Record<string, string>,
    batchId?: string,
    buildName?: string,
    triggerSource?: string,
  ) => {
    const generatedAutomation = buildAutomationFromCase(caseItem);
    if (generatedAutomation.steps.length || generatedAutomation.checks.length) {
      await apiFetch(
        `/api/v1/test-cases/${caseItem.id}/automation`,
        {
          method: "PUT",
          body: JSON.stringify(generatedAutomation),
        },
        token,
      );
    }

    const keepOpenSeconds = executionMode === "background"
      ? 0
      : Math.max(0, Math.min(120, keepBrowserOpenSeconds));
    const runQuery = new URLSearchParams({
      capture_screenshot: captureScreenshotEvidence ? "true" : "false",
      highlight_actions: highlightActionTargets ? "true" : "false",
      capture_video: recordVideoEvidence ? "true" : "false",
      capture_audio: recordVideoEvidence && voiceOverEnabled ? "true" : "false",
      voice_gender: voiceGender,
      execution_mode: executionMode,
      trace_mode: executionTraceMode,
      slow_mode: executionSlowMode,
      keep_browser_open_on_failure: keepBrowserOpenOnFailure ? "true" : "false",
      keep_browser_open_seconds: String(keepOpenSeconds),
      healing_enabled: "true",
      healing_attempts: "1",
    });
    if (batchId) runQuery.set("batch_id", batchId);
    if (buildName) runQuery.set("build_name", buildName);
    if (triggerSource) runQuery.set("trigger_source", triggerSource);
    if (aiConfigState?.provider) runQuery.set("ai_provider", aiConfigState.provider);
    if (aiConfigState?.model) runQuery.set("ai_model", aiConfigState.model);
    const runUrl = `/api/v1/execution/test-case/${caseItem.id}?${runQuery.toString()}`;
    const enqueue = async () => {
      const queued = await apiFetch<{ run_id: string; status: string }>(
        runUrl,
        { method: "POST", body: JSON.stringify({ parameters }) },
        token,
      );
      return {
        ...queued,
        generatedStepCount: generatedAutomation.steps.length,
        generatedCheckCount: generatedAutomation.checks.length,
      };
    };
    try {
      return await enqueue();
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      const needsAutomation = message.includes("no automation steps or checks") || message.includes("does not have automation steps");
      if (!needsAutomation) throw error;
      return await enqueue();
    }
  };

  const getRunnableExecutionCases = (caseIds?: number[]) => {
    const scopeFilteredCases = executionRunScope === "latest"
      ? latestGeneratedCases
      : executionRunScope === "selected"
        ? selectedCases.filter((caseItem) => executionSelectedCaseIds.includes(caseItem.id))
        : selectedCases.filter((caseItem) => {
          if (executionRunScope === "all") return true;
          return inferRunScopeKey(caseItem.status) === executionRunScope;
        });
    const scopedCases = caseIds?.length
      ? selectedCases.filter((caseItem) => caseIds.includes(caseItem.id))
      : scopeFilteredCases;
    const runnableCases = scopedCases.filter((caseItem) => ["draft", "ready"].includes(caseItem.status.trim().toLowerCase()));
    const tcNumber = (title: string) => {
      const match = title.match(/^TC\s*0*(\d+)/i);
      return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
    };
    return [...runnableCases].sort((left, right) => {
      const numA = tcNumber(left.title);
      const numB = tcNumber(right.title);
      if (numA !== numB) return numA - numB;
      return left.id - right.id;
    });
  };

  const openExecutionScopeDialog = (caseIds?: number[], triggerLabel = "Run tests") => {
    if (!app?.id) {
      notify("Select an application before running tests");
      return;
    }
    const runtimeParameterError = validateRuntimeParameters(runtimeParameters);
    if (runtimeParameterError) {
      notify(runtimeParameterError);
      return;
    }
    const orderedCases = getRunnableExecutionCases(caseIds);
    if (!orderedCases.length) {
      notify("No draft or ready test cases found for this execution scope");
      return;
    }
    setExecutionScopeDialog({ caseIds: orderedCases.map((caseItem) => caseItem.id), triggerLabel, fixedScope: Boolean(caseIds?.length) });
  };

  const saveExecutionConfiguration = () => {
    const effectiveEmailSelector = emailSelector.trim() || DEFAULT_LOGIN_EMAIL_SELECTOR;
    const effectivePasswordSelector = passwordSelector.trim() || DEFAULT_LOGIN_PASSWORD_SELECTOR;
    const effectiveSubmitSelector = submitSelector.trim() || DEFAULT_LOGIN_SUBMIT_SELECTOR;
    const selectorError = validateLoginSelectors(effectiveEmailSelector, effectivePasswordSelector, effectiveSubmitSelector);
    if (selectorError) {
      notify(selectorError);
      return;
    }
    try {
      setEmailSelector(effectiveEmailSelector);
      setPasswordSelector(effectivePasswordSelector);
      setSubmitSelector(effectiveSubmitSelector);
      window.localStorage.setItem(EXECUTION_CONFIGURATION_STORAGE_KEY, JSON.stringify({
        executionMode,
        executionParallelism,
        executionSlowMode,
        executionTraceMode,
        voiceGender,
        voiceOverEnabled,
        captureScreenshotEvidence,
        highlightActionTargets,
        recordVideoEvidence,
        keepBrowserOpenOnFailure,
        keepBrowserOpenSeconds,
        authenticatedFlow,
        emailSelector: effectiveEmailSelector,
        passwordSelector: effectivePasswordSelector,
        submitSelector: effectiveSubmitSelector,
        runtimeParameters: runtimeParameters.map((parameter) => ({
          key: parameter.key,
          value: parameter.sensitive ? "" : parameter.value,
          sensitive: parameter.sensitive,
        })),
      }));
      notify("Execution configuration saved locally. Sensitive runtime values were not stored.");
    } catch {
      notify("Unable to save execution configuration in this browser.");
    }
  };

  const saveTestDataProfile = () => {
    if (!app?.id) {
      notify("Select an application before saving test data");
      return;
    }
    try {
      const profile = runtimeParameters
        .filter((parameter) => parameter.key.trim())
        .map((parameter) => ({
          ...parameter,
          value: isSensitiveRuntimeParameter(parameter) ? "" : parameter.value,
          sensitive: isSensitiveRuntimeParameter(parameter),
        }));
      window.localStorage.setItem(`${TEST_DATA_PROFILE_STORAGE_KEY}:${app.id}`, JSON.stringify(profile));
      notify("Test data profile saved locally. Sensitive values were not stored.");
    } catch {
      notify("Unable to save the test data profile in this browser.");
    }
  };

  const handleSmartGenerateTestData = async () => {
    if (!app?.id || !token) {
      notify("Select an application first");
      return;
    }
    setGeneratingSmartData(true);
    try {
      const fieldNames = runtimeParameters.length
        ? runtimeParameters.map((p) => p.key).filter(Boolean)
        : ["first_name", "last_name", "email", "phone", "status"];
      const generated = await apiFetch<{
        application_id: number;
        dataset_id?: number;
        name: string;
        row_count: number;
        data_rows: Record<string, any>[];
        learned_entities_used: number;
      }>(
        `/api/v1/test-data/generate/${app.id}`,
        {
          method: "POST",
          body: JSON.stringify({
            name: `${app.name} Adaptive Dataset`,
            field_names: fieldNames,
            row_count: 10,
            save_to_database: true,
          }),
        },
        token,
      );

      if (generated.data_rows && generated.data_rows.length > 0) {
        const firstRow = generated.data_rows[0];
        setRuntimeParameters((current) => {
          const updated = [...current];
          for (const [key, val] of Object.entries(firstRow)) {
            if (key.startsWith("_")) continue;
            const existingIdx = updated.findIndex((p) => p.key.trim().toLowerCase() === key.toLowerCase());
            if (existingIdx >= 0) {
              if (!updated[existingIdx].sensitive || !updated[existingIdx].value) {
                updated[existingIdx] = { ...updated[existingIdx], value: String(val) };
              }
            } else {
              updated.push({
                id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                key,
                value: String(val),
                sensitive: isSensitiveRuntimeParameter({ id: "", key, value: "", sensitive: false }),
              });
            }
          }
          return updated;
        });
        notify(`Synthesized ${generated.row_count} test data row(s) using AI & live schema.`);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "Failed to synthesize smart test data");
    } finally {
      setGeneratingSmartData(false);
    }
  };

  const handleAutoLearnEntities = async () => {
    if (!app?.id || !token) {
      notify("Select an application first");
      return;
    }
    setLearningEntities(true);
    try {
      const learned = await apiFetch<{
        application_id: number;
        application_name: string;
        discovered_entity_pools: Record<string, string[]>;
      }>(
        `/api/v1/test-data/learned/${app.id}`,
        {},
        token,
      );

      const pools = learned.discovered_entity_pools || {};
      const poolEntries = Object.entries(pools);
      if (!poolEntries.length) {
        notify("No live entities learned yet. Run exploratory discovery or executions to harvest application data.");
        return;
      }

      setRuntimeParameters((current) => {
        const updated = [...current];
        for (const [entityType, values] of poolEntries) {
          if (!values || !values.length) continue;
          const chosenVal = values[0];
          const existingIdx = updated.findIndex((p) => p.key.trim().toLowerCase() === entityType.toLowerCase());
          if (existingIdx >= 0) {
            updated[existingIdx] = { ...updated[existingIdx], value: chosenVal };
          } else {
            updated.push({
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              key: entityType,
              value: chosenVal,
              sensitive: false,
            });
          }
        }
        return updated;
      });
      notify(`Incorporated ${poolEntries.length} learned entity types from live application memory.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Failed to retrieve learned entities");
    } finally {
      setLearningEntities(false);
    }
  };

  const confirmExecutionScopeRun = () => {
    if (!executionScopeDialog) return;
    const requestedCaseIds = executionScopeDialog.fixedScope
      ? executionScopeDialog.caseIds
      : getRunnableExecutionCases().map((caseItem) => caseItem.id);
    setExecutionScopeDialog(null);
    void runApplicationCaseTests(requestedCaseIds);
  };

  const executionScopeCaseIds = executionScopeDialog?.fixedScope
    ? executionScopeDialog.caseIds
    : executionScopeDialog
      ? getRunnableExecutionCases().map((caseItem) => caseItem.id)
      : [];

  const runApplicationCaseTests = async (caseIds?: number[]) => {
    if (!app || !token) return;
    if (app.platform !== "web") {
      setRunStatus("Unavailable");
      setRunLog("Mobile execution requires a configured Appium device provider.");
      notify("Select a web application for Playwright execution");
      return;
    }
    const effectiveEmailSelector = emailSelector.trim() || DEFAULT_LOGIN_EMAIL_SELECTOR;
    const effectivePasswordSelector = passwordSelector.trim() || DEFAULT_LOGIN_PASSWORD_SELECTOR;
    const effectiveSubmitSelector = submitSelector.trim() || DEFAULT_LOGIN_SUBMIT_SELECTOR;
    const runtimeParameterError = validateRuntimeParameters(runtimeParameters, authenticatedFlow, [effectiveEmailSelector, effectivePasswordSelector, effectiveSubmitSelector]);
    if (runtimeParameterError) {
      notify(runtimeParameterError);
      return;
    }
    const executionParameters = buildRuntimeParameterMap(runtimeParameters);

    const orderedCases = getRunnableExecutionCases(caseIds);
    const parallelWorkerCount = getConcurrencyLimit(executionParallelism, orderedCases.length);

    if (!orderedCases.length) {
      notify("No draft or ready test cases found for this application");
      return;
    }

    if (caseIds?.length) clearPreparedExecution();

    const runStartedAt = Date.now();
    const batchId = `build-${new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 8)}`;
    const buildDisplayName = `Build #${batchId.slice(-6).toUpperCase()} · ${orderedCases.length} case${orderedCases.length === 1 ? "" : "s"}`;
    spokenExecutionEventsRef.current.clear();
    setVoiceOverEventLog(null);
    stopExecutionSpeech();
    if (voiceOverEnabled) {
      speakExecutionMessage(
        `Voice-over enabled with a ${voiceGender} voice. Starting execution of ${orderedCases.length} test case${orderedCases.length === 1 ? "" : "s"}.`,
        resolveExecutionSpeechRate(executionSlowMode),
        voiceGender,
      );
    }
    activeBatchCancelledRef.current = false;
    setActiveExecutionBatchId(batchId);
    setRunning(true);
    setExecutionResult(null);
    setLatestBuildReport(null);
    setExecutionPhase("queueing");
    setExecutionProgress({ total: orderedCases.length, current: 0, passed: 0, failed: 0, activeCaseTitle: "Preparing execution queue" });
    setExecutionRunStartedAt(runStartedAt);
    setExecutionClockMs(runStartedAt);
    setExecutionLiveCases(orderedCases.map((caseItem, index) => ({
      caseId: caseItem.id,
      title: caseItem.title,
      order: index + 1,
      status: "pending",
      detail: "Waiting for queue assignment",
      pollCount: 0,
    })));
    setExecutionActivityLog([`${new Date(runStartedAt).toLocaleTimeString()} · Preparing ${orderedCases.length} test case run(s)`]);
    setRunStatus("Submitting runs");
    setRunLog(`Preparing ${orderedCases.length} test case run(s) with up to ${parallelWorkerCount} parallel workers...`);

    try {
      const completedResults = new Map<number, ExecutionResult>();

      const updateBatchProgress = (activeCaseTitle: string) => {
        const completed = [...completedResults.values()];
        const passedCount = completed.filter((result) => result.status === "passed").length;
        const failedCount = completed.length - passedCount;
        setExecutionProgress({
          total: orderedCases.length,
          current: completed.length,
          passed: passedCount,
          failed: failedCount,
          activeCaseTitle,
        });
        setRunStatus(`Completed ${completed.length}/${orderedCases.length} · ${passedCount} passed · ${failedCount} failed/error`);
        return { passedCount, failedCount };
      };

      const executeCase = async (testCase: TestCase, index: number) => {
        if (activeBatchCancelledRef.current) return;
        try {
          const queueTimestamp = Date.now();
          setExecutionPhase("queueing");
          setExecutionProgress((current) => ({
            ...current,
            activeCaseTitle: testCase.title,
          }));
          setExecutionLiveCases((current) => current.map((caseProgress) => (
            caseProgress.caseId === testCase.id
              ? {
                ...caseProgress,
                status: "queued",
                queuedAt: queueTimestamp,
                detail: "Submitting run to execution queue...",
                pollCount: 0,
              }
              : caseProgress
          )));
          setRunStatus(`Queueing ${index + 1}/${orderedCases.length}`);
          setRunLog(`Queueing "${testCase.title}"...`);
          appendExecutionActivity(`Queueing ${index + 1}/${orderedCases.length}: ${testCase.title}`);

          const queued = await queueCaseRun(testCase, executionParameters, batchId, buildDisplayName, "manual");

          setRunLog(`Run ${queued.run_id.slice(0, 8)} queued for "${testCase.title}". Waiting for worker...`);
          setExecutionLiveCases((current) => current.map((caseProgress) => (
            caseProgress.caseId === testCase.id
              ? {
                ...caseProgress,
                runId: queued.run_id,
                status: "queued",
                detail: `Run ${queued.run_id.slice(0, 8)} queued. Waiting for worker...`,
              }
              : caseProgress
          )));
          appendExecutionActivity(`Queued ${testCase.title} as ${queued.run_id.slice(0, 8)}`);

          const pollPlan = buildPollingPlan(queued.generatedStepCount, queued.generatedCheckCount, executionMode);
          let finalStatus: RunStatusSnapshot | null = null;
          let lastStatusLabel = "queued";
          let lastStatusLog = "";
          for (let attempt = 0; attempt < pollPlan.maxAttempts; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, pollPlan.pollIntervalMs));
            const status = await apiFetch<RunStatusSnapshot>(
              `/api/v1/execution/${queued.run_id}`,
              {},
              token,
            );
            const now = Date.now();
            const normalizedStatus = (status.status ?? "running").toLowerCase();
            const terminalStatus = normalizedStatus === "passed" || normalizedStatus === "failed" || normalizedStatus === "error";
            const fallbackEvent = latestLiveEvent(status.log);
            const liveState = (status.live_state ?? fallbackEvent?.state ?? "").toUpperCase();
            const livePhase = mapLiveStateToExecutionPhase(liveState);
            const liveStatus: LiveCaseExecutionStatus = terminalStatus
              ? normalizedStatus
              : normalizedStatus === "queued"
                ? "queued"
                : "running";
            const statusLog = status.current_action ?? fallbackEvent?.message ?? "Browser worker is processing the run...";
            setExecutionLiveCases((current) => current.map((caseProgress) => {
              if (caseProgress.caseId !== testCase.id) return caseProgress;
              const startedAt = caseProgress.startedAt ?? now;
              const durationMs = terminalStatus
                ? (status.result?.duration_ms && status.result.duration_ms > 0
                  ? status.result.duration_ms
                  : Math.max(0, now - startedAt))
                : caseProgress.durationMs;
              return {
                ...caseProgress,
                status: liveStatus,
                startedAt,
                finishedAt: terminalStatus ? now : caseProgress.finishedAt,
                durationMs,
                pollCount: attempt + 1,
                detail: statusLog,
              };
            }));
            if (!terminalStatus) setExecutionPhase(livePhase === "queueing" ? "queueing" : "running");
            setRunStatus(
              liveState
                ? `${formatLiveStateLabel(liveState)} · ${completedResults.size}/${orderedCases.length}`
                : `${status.status ?? "running"} · ${completedResults.size}/${orderedCases.length}`,
            );
            setRunLog(statusLog);
            setVoiceOverEventLog({ runId: queued.run_id, log: status.log ?? statusLog });
            if (lastStatusLabel !== normalizedStatus || lastStatusLog !== statusLog) {
              appendExecutionActivity(`${testCase.title}: ${statusLog}`);
              lastStatusLabel = normalizedStatus;
              lastStatusLog = statusLog;
            }
            if (terminalStatus || activeBatchCancelledRef.current || normalizedStatus === "cancelled") {
              finalStatus = (activeBatchCancelledRef.current || normalizedStatus === "cancelled")
                ? { ...status, status: "cancelled" }
                : status;
              break;
            }
          }

          if (!finalStatus) {
            throw new Error(
              `Execution is still running for "${testCase.title}" after ${Math.round(pollPlan.maxWaitMs / 1000)} seconds. ` +
              "Keep this run open or check execution history.",
            );
          }

          const terminalStatus = (finalStatus.status as "passed" | "failed" | "error" | "cancelled") ?? "error";
          const result = finalStatus.result ?? {
            run_id: queued.run_id,
            url: app.url,
            status: terminalStatus,
            duration_ms: 0,
            checks: [],
            error: finalStatus.log ?? `Execution ${terminalStatus}`,
          };
          completedResults.set(testCase.id, result);
          const finishedAt = Date.now();
          setExecutionLiveCases((current) => current.map((caseProgress) => {
            if (caseProgress.caseId !== testCase.id) return caseProgress;
            const startedAt = caseProgress.startedAt ?? caseProgress.queuedAt ?? finishedAt;
            const durationMs = result.duration_ms > 0 ? result.duration_ms : Math.max(0, finishedAt - startedAt);
            const finalEvent = latestLiveEvent(finalStatus?.log);
            const detail = result.error
              ?? finalStatus?.current_action
              ?? finalEvent?.message
              ?? (result.status === "passed" ? "Execution passed." : `Execution ${result.status}.`);
            return {
              ...caseProgress,
              status: result.status,
              startedAt,
              finishedAt,
              durationMs,
              detail,
            };
          }));
          appendExecutionActivity(
            `${testCase.title} ${result.status.toUpperCase()}${result.duration_ms > 0 ? ` (${formatDuration(result.duration_ms)})` : ""}`,
          );
          updateBatchProgress(testCase.title);
        } catch (error) {
          const message = error instanceof Error ? error.message : "Unable to complete this test case run.";
          const finishedAt = Date.now();
          const errorResult: ExecutionResult = {
            run_id: `unavailable-${testCase.id}`,
            url: app.url,
            status: "error",
            duration_ms: 0,
            checks: [],
            error: message,
          };
          completedResults.set(testCase.id, errorResult);
          setExecutionLiveCases((current) => current.map((caseProgress) => (
            caseProgress.caseId === testCase.id
              ? {
                ...caseProgress,
                status: "error",
                startedAt: caseProgress.startedAt ?? caseProgress.queuedAt ?? finishedAt,
                finishedAt,
                detail: message,
              }
              : caseProgress
          )));
          appendExecutionActivity(`${testCase.title} ERROR: ${message}`);
          updateBatchProgress(testCase.title);
        }
      };

      await runWithConcurrency(orderedCases, executionParallelism, executeCase);

      const orderedResults = orderedCases
        .map((testCase) => completedResults.get(testCase.id))
        .filter((result): result is ExecutionResult => Boolean(result));
      const passedCount = orderedResults.filter((result) => result.status === "passed").length;
      const failedCount = orderedResults.length - passedCount;
      const lastResult = orderedResults[orderedResults.length - 1] ?? null;

      setExecutionPhase("finalizing");
      if (lastResult) {
        setExecutionResult(lastResult);
      }

      const generatedBuildReport: BuildExecutionReport = {
        buildId: batchId,
        buildName: buildDisplayName,
        applicationName: app.name,
        targetUrl: app.url,
        startedAt: runStartedAt,
        finishedAt: Date.now(),
        totalDurationMs: Math.max(0, Date.now() - runStartedAt),
        totalCases: orderedCases.length,
        passedCount,
        failedCount,
        errorCount: 0,
        passRate: orderedCases.length > 0 ? Math.round((passedCount / orderedCases.length) * 100) : 0,
        overallStatus: failedCount ? "failed" : "passed",
        cases: orderedCases.map((c, idx) => {
          const res = completedResults.get(c.id);
          return {
            caseId: c.id,
            title: c.title,
            order: idx + 1,
            runId: res?.run_id,
            status: (res?.status as any) || "error",
            durationMs: res?.duration_ms,
            detail: res?.error,
            result: res,
          };
        }),
      };

      try {
        const canonicalBuildDetail = await apiFetch<BuildExecutionDetail>(
          `/api/v1/execution/builds/${batchId}/detail`,
          {},
          token,
        );
        setLatestBuildReport(canonicalBuildDetail);
      } catch {
        setLatestBuildReport(generatedBuildReport);
      }

      await loadDashboardData(token, app?.name);
      await refreshExecutionHistory(token, app.id);
      const overallStatus = failedCount ? "failed" : "passed";
      setExecutionPhase(failedCount ? "error" : "done");
      setRunStatus(overallStatus);
      setRunLog(`Completed ${orderedCases.length} case run(s): ${passedCount} passed, ${failedCount} failed/error using up to ${parallelWorkerCount} parallel workers.`);
      appendExecutionActivity(`Execution complete: ${passedCount} passed, ${failedCount} failed/error, up to ${parallelWorkerCount} parallel workers.`);
      notify(`Execution finished: ${passedCount} passed, ${failedCount} failed/error`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to reach the QA runner.";
      setExecutionPhase("error");
      setExecutionResult({
        run_id: "unavailable",
        url: app.url,
        status: "error",
        duration_ms: Math.max(0, Date.now() - runStartedAt),
        checks: [],
        error: message,
      });
      setRunStatus("error");
      setRunLog(message);
      setExecutionLiveCases((current) => current.map((caseProgress) => {
        if (["passed", "failed", "error"].includes(caseProgress.status)) return caseProgress;
        return {
          ...caseProgress,
          status: caseProgress.status === "running" ? "error" : caseProgress.status,
          detail: caseProgress.status === "running" ? message : caseProgress.detail,
          finishedAt: caseProgress.status === "running" ? Date.now() : caseProgress.finishedAt,
        };
      }));
      await refreshExecutionHistory(token, app.id);
      appendExecutionActivity(`Execution interrupted: ${message}`);
      notify("QA runner unavailable");
    } finally {
      setRunning(false);
      setActiveExecutionBatchId(null);
      setStoppingExecution(false);
    }
  };

  const deleteApplication = async (id?: number, name?: string) => {
    if (!id || !name) {
      notify("Selected application could not be deleted. Refresh and try again.");
      return;
    }
    if (!window.confirm(`Delete ${name} from this project?`)) return;
    try {
      await apiFetch(`/api/v1/applications/${id}`, { method: "DELETE" }, token);
      setApplications((current) => {
        const remaining = current.filter((item) => item.id !== id);
        if (remaining.length && appName === name) {
          selectApplication(remaining[0].name);
        }
        return remaining;
      });
      notify(`${name} deleted`);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Failed to delete application");
    }
  };

  const refreshApplicationSelection = async (selectedApp: Application) => {
    if (!token) return false;
    try {
      const loadedApps = await apiFetch<Array<{ id: number; name: string; platform: string; target: string }>>("/api/v1/applications", {}, token);
      const mappedApps = loadedApps.map((item) => mapApiApplication(item));
      const nextApps = sortApplicationsForDisplay(mappedApps);
      setApplications(nextApps);
      const remainsAvailable = nextApps.some((item) => item.id === selectedApp.id);
      if (!remainsAvailable) {
        setAppName(nextApps[0]?.name ?? "");
      }
      return remainsAvailable;
    } catch (error) {
      console.error("Unable to refresh application list", error);
      return false;
    }
  };

  const importTestCases = async (file?: File) => {
    if (!file) return;
    const selectedApp = app;
    if (!selectedApp?.id) {
      notify("Select an application before importing");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    setImportingCases(true);
    try {
      const importedCases = await apiFetch<TestCase[]>(`/api/v1/test-cases/import/${selectedApp.id}`, { method: "POST", body: formData }, token);
      setTestCases((current) => [
        ...current.filter((caseItem) => caseItem.application_id !== selectedApp.id),
        ...importedCases,
      ]);
      await loadDashboardData(token, selectedApp.name);
      await loadAutomationReadiness(token, selectedApp.id);
      setGenerated(true);
      notify(`${file.name} imported successfully`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to import test cases";
      if (message.includes("Application not found")) {
        const stillAvailable = await refreshApplicationSelection(selectedApp);
        if (!stillAvailable) {
          notify("Selected application is no longer available. Please choose it again.");
          return;
        }
      }
      notify(message);
    } finally {
      setImportingCases(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  const openImportPicker = () => {
    if (importingCases || clearingDrafts) return;
    if (!app?.id) {
      notify("Add or select an application before uploading test cases");
      navigateToSection("applications");
      return;
    }
    importInputRef.current?.click();
  };

  const createStarterCases = async () => {
    const selectedApp = app;
    if (!selectedApp?.id) {
      notify("Select an application first");
      return;
    }
    const appName = selectedApp.name || "Application";
    const targetUrl = selectedApp.url || "the application URL";
    const templates = selectedApp.platform === "web" ? [
      {
        title: `Verify ${appName} loads successfully`,
        steps: `1. Open ${targetUrl}\n2. Wait for page document ready state\n3. Verify HTTP 200 response and root container visibility`,
        expected_result: `${appName} homepage renders successfully without unhandled errors.`,
      },
      {
        title: `Verify ${appName} primary navigation and layout`,
        steps: `1. Open ${targetUrl}\n2. Validate primary navigation header and essential navigation links\n3. Confirm interactive elements respond to keyboard and mouse focus`,
        expected_result: `Primary navigation and core layout components are displayed properly for ${appName}.`,
      },
      {
        title: `Verify ${appName} console health and baseline accessibility`,
        steps: `1. Open ${targetUrl}\n2. Inspect browser console for uncaught exceptions or resource loading failures\n3. Verify page landmarks and accessible interactive controls`,
        expected_result: `No severe application errors in console and core interactive elements meet baseline criteria.`,
      },
    ] : [
      {
        title: `Launch ${appName} mobile target`,
        steps: `1. Initialize the ${appName} mobile application package\n2. Wait for initial launch view to render`,
        expected_result: `${appName} opens to the initial interactive screen.`,
      },
      {
        title: `Verify ${appName} primary mobile viewport controls`,
        steps: `1. Launch ${appName}\n2. Validate primary interaction views and control elements`,
        expected_result: `Primary mobile UI controls are visible and responsive.`,
      },
    ];
    const existingTitleKeys = new Set(
      selectedCases.map((caseItem) => normaliseCaseKey(caseItem.title)),
    );
    const templatesToCreate = templates.filter((template) => !existingTitleKeys.has(normaliseCaseKey(template.title)));
    try {
      if (!templatesToCreate.length) {
        notify("Starter test cases already exist for this application");
        return;
      }
      await Promise.all(templatesToCreate.map((template) => apiFetch("/api/v1/test-cases", {
        method: "POST",
        body: JSON.stringify({ application_id: selectedApp.id, ...template, status: "draft" }),
      }, token)));
      await loadDashboardData(token, selectedApp.name);
      setGenerated(true);
      const skippedCount = templates.length - templatesToCreate.length;
      notify(skippedCount ? `${templatesToCreate.length} starter test cases created (${skippedCount} skipped duplicates)` : `${templatesToCreate.length} starter test cases created`);
      await loadAutomationReadiness(token, selectedApp.id);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create starter test cases");
    } finally {
      setCreatingStarterCases(false);
    }
  };

  const clearAllApplicationCases = async () => {
    const selectedApp = app;
    if (!selectedApp?.id) {
      notify("Select an application first");
      return;
    }
    const totalCount = selectedCases.length;
    if (!totalCount) {
      notify("No test cases to remove");
      return;
    }
    if (!window.confirm(`Are you sure you want to delete all ${totalCount} test case(s) for ${selectedApp.name}?`)) {
      return;
    }
    setClearingDrafts(true);
    try {
      await apiFetch(`/api/v1/test-cases/application/${selectedApp.id}/all`, { method: "DELETE" }, token);
      setTestCases((current) => current.filter((caseItem) => caseItem.application_id !== selectedApp.id));
      await loadDashboardData(token, selectedApp.name);
      await loadAutomationReadiness(token, selectedApp.id);
      notify(`All ${totalCount} test case(s) removed for ${selectedApp.name}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to remove test cases");
    } finally {
      setClearingDrafts(false);
    }
  };

  const clearDraftCases = async () => {
    const selectedApp = app;
    if (!selectedApp?.id || !token) {
      if (!token) notify("Your session expired. Sign in again to clear draft test cases.");
      else notify("Select an application first");
      return;
    }
    const draftCount = testCases.filter(
      (caseItem) => caseItem.application_id === selectedApp.id && isDraftStatus(caseItem.status),
    ).length;
    if (!draftCount) {
      if (selectedCases.length > 0) {
        if (window.confirm(`No draft test cases found for ${selectedApp.name} (all ${selectedCases.length} case(s) are 'ready'). Would you like to clear all test cases for this application instead?`)) {
          await clearAllApplicationCases();
        }
        return;
      }
      notify("No test cases to remove");
      return;
    }
    setClearingDrafts(true);
    try {
      const deletion = await apiFetch<{ deleted_count?: number }>(`/api/v1/test-cases/application/${selectedApp.id}/drafts`, { method: "DELETE" }, token);
      setTestCases((current) => current.filter((caseItem) => !(caseItem.application_id === selectedApp.id && isDraftStatus(caseItem.status))));
      setLatestGeneratedCaseIds((current) => current.filter((caseId) => testCases.some((caseItem) => caseItem.id === caseId && !(caseItem.application_id === selectedApp.id && isDraftStatus(caseItem.status)))));
      setExecutionSelectedCaseIds((current) => current.filter((caseId) => testCases.some((caseItem) => caseItem.id === caseId && !(caseItem.application_id === selectedApp.id && isDraftStatus(caseItem.status)))));
      await loadDashboardData(token, selectedApp.name);
      await loadAutomationReadiness(token, selectedApp.id);
      const deletedCount = deletion.deleted_count ?? draftCount;
      notify(`${deletedCount} draft test case${deletedCount === 1 ? "" : "s"} removed`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to remove draft test cases";
      if (message.includes("Application not found")) {
        const stillAvailable = await refreshApplicationSelection(selectedApp);
        if (!stillAvailable) {
          notify("Selected application is no longer available. Please choose it again.");
          return;
        }
      }
      notify(message);
    } finally {
      setClearingDrafts(false);
    }
  };

  const generateAiCases = async (promptOverride?: string): Promise<boolean> => {
    const selectedApp = app;
    if (!selectedApp?.id) {
      notify("Select an application first");
      return false;
    }
    const prompt = (promptOverride ?? aiPrompt).trim();
    if (prompt.length < 3) {
      notify("Enter an AI prompt (at least 3 characters)");
      return false;
    }
    const targetUrl = aiTargetUrl.trim();
    const effectiveEmailSelector = emailSelector.trim() || DEFAULT_LOGIN_EMAIL_SELECTOR;
    const effectivePasswordSelector = passwordSelector.trim() || DEFAULT_LOGIN_PASSWORD_SELECTOR;
    const effectiveSubmitSelector = submitSelector.trim() || DEFAULT_LOGIN_SUBMIT_SELECTOR;
    const shouldRunImmediately = guidedRunEnabled || runGeneratedAfterGeneration;
    const shouldOpenExecution = guidedRunEnabled || openExecutionAfterGeneration;
    const shouldOpenCases = guidedRunEnabled ? false : openCasesAfterGeneration;
    if (selectedApp.platform === "web" && !targetUrl) {
      notify("Enter a valid target URL for AI generation");
      return false;
    }
    if (aiMinSteps > aiMaxSteps) {
      notify("Minimum steps cannot be greater than maximum steps");
      return false;
    }
    const generationParameterContext = buildGenerationParameterContext(runtimeParameters);
    const generationPrompt = generationParameterContext
      ? `${prompt}\n\n${generationParameterContext}`
      : prompt;
    setAiGenerating(true);
    setLatestGeneratedCaseIds([]);
    setLatestGenerationInput(null);
    try {
      window.sessionStorage.removeItem(LATEST_GENERATED_CASES_STORAGE_KEY);
    } catch {
    }
    setAiGenerationSource(null);
    setAiGenerationPhase("preparing");
    setAiGenerationLogs([]);
    setAiAgentStages(DEFAULT_AI_AGENT_STAGES.map((stage) => ({ ...stage })));

    appendAiLog("info", `🚀 Initializing AI test scenario synthesis for "${selectedApp.name}" (${selectedApp.platform.toUpperCase()})`);
    appendAiLog("ai", `🤖 Engine: ${aiConfigState?.provider || "Configured Provider"} | Model: ${aiConfigState?.model || "Active Model"} | Endpoint: ${aiConfigState?.endpoint || "Backend AI Gateway"}`);
    appendAiLog("info", `📝 Input Specification: "${prompt}"`);
    appendAiLog("info", `🎯 Scope: ${aiCaseCount === 0 ? "Dynamic AI Autonomy" : `${aiCaseCount} cases requested`} | Step bounds: ${aiMinSteps}-${aiMaxSteps} steps`);
    if (aiModuleFocus.trim()) appendAiLog("info", `🔍 Focus Module: "${aiModuleFocus.trim()}"`);
    appendAiLog("step", `⚙️ Strategy: Negative Scenarios=${aiIncludeNegative ? "Yes" : "No"} | Accessibility=${aiIncludeAccessibility ? "Yes" : "No"} | API Validations=${aiIncludeApiValidation ? "Yes" : "No"} | Performance=${aiIncludePerformance ? "Yes" : "No"}`);
    if (aiIncludePerformance && aiPerformanceBudget.trim()) appendAiLog("info", `📈 Performance budget: "${aiPerformanceBudget.trim()}"`);

    try {
      let activeConfig = aiConfigState;
      appendAiLog("step", `🔌 Checking backend API connectivity at ${API_URL}...`);
      try {
        await apiFetch<{ status: string }>("/health", { retries: 4, timeoutMs: 10_000 }, token);
      } catch (error) {
        const detail = error instanceof Error ? error.message : "The backend did not respond.";
        throw new Error(`Backend API is unavailable at ${API_URL}. Start the backend on port 8000 and try again. ${detail}`);
      }
      appendAiLog("success", "✅ Backend API is reachable.");

      activeConfig = activeConfig ?? await loadAiConfiguration(token);
      if (!activeConfig) {
        throw new Error("AI configuration could not be loaded from the backend.");
      }
      if (activeConfig.status?.configured !== true) {
        throw new Error("LLM prerequisite failed: configure an AI provider and API key in Administration > AI & Settings.");
      }
      appendAiLog("step", `🔐 Checking LLM provider connectivity (${activeConfig.provider}:${activeConfig.model})...`);
      const providerProbe = await apiFetch<{ status?: string; message?: string }>(
        "/api/v1/settings/ai-configuration/test",
        {
          method: "POST",
          body: JSON.stringify({
            provider: activeConfig.provider,
            model: activeConfig.model,
            endpoint: activeConfig.endpoint,
          }),
        },
        token,
      );
      if (providerProbe.status !== "success") {
        throw new Error(`LLM prerequisite failed: ${providerProbe.message || "provider connection test failed."}`);
      }
      appendAiLog("success", `✅ LLM prerequisite passed (${activeConfig.provider}:${activeConfig.model}).`);
      appendAiLog("info", "📨 Request received by the generation workflow. Preparing application context and source inputs...");
      if (selectedApp.platform === "web" && targetUrl !== selectedApp.url.trim()) {
        setAiGenerationPhase("capturing");
        setSavingAiTarget(true);
        appendAiLog("step", `🌐 Updating application target endpoint to: ${targetUrl}`);
        const updated = await apiFetch<{ id: number; name: string; platform: Platform; target: string }>(
          `/api/v1/applications/${selectedApp.id}`,
          {
            method: "PUT",
            body: JSON.stringify({
              name: selectedApp.name,
              target: targetUrl,
            }),
          },
          token,
        );
        setApplications((current) => current.map((item) => (
          item.id === updated.id
            ? { ...mapApiApplication(updated, item.cases ?? 0), artifact: item.artifact }
            : item
        )));
      }
        setAiGenerationPhase("generating");
        appendAiLog("ai", `🤖 Sending prompt & application context to LLM (${activeConfig.model}). Synthesizing scenarios...`);
      appendAiLog("step", "🔎 Context analyzed: application metadata, reference cases, target URL, and generation constraints are ready.");
      appendAiLog("step", "📄 Documents and source inputs parsed. Building the provider prompt...");
      appendAiLog("step", "🧾 AI prompt generated with structured QA output requirements.");

      const configuredEmail = runtimeParameters.find((p) => ["login_email", "username", "email"].includes(p.key.trim().toLowerCase()))?.value.trim();
      const configuredPassword = runtimeParameters.find((p) => ["login_password", "password"].includes(p.key.trim().toLowerCase()))?.value.trim();
      const hasAuthCredentials = Boolean(configuredEmail && configuredPassword);

      const generationJob = await apiFetch<AIGenerationJob>(
        `/api/v1/ai-generation/jobs?application_id=${selectedApp.id}`,
        {
          method: "POST",
          body: JSON.stringify({
            prompt: generationPrompt,
            max_cases: aiCaseCount > 0 ? aiCaseCount : undefined,
            replace_existing_drafts: replaceDraftsOnAiGenerate,
            target_url: selectedApp.platform === "web" ? targetUrl : undefined,
            include_authenticated_snapshot: authenticatedFlow || hasAuthCredentials,
            login_email: configuredEmail || undefined,
            login_password: configuredPassword || undefined,
            login_email_selector: selectedApp.platform === "web" && (authenticatedFlow || hasAuthCredentials) ? effectiveEmailSelector : undefined,
            login_password_selector: selectedApp.platform === "web" && (authenticatedFlow || hasAuthCredentials) ? effectivePasswordSelector : undefined,
            login_submit_selector: selectedApp.platform === "web" && (authenticatedFlow || hasAuthCredentials) ? effectiveSubmitSelector : undefined,
            min_steps_per_case: aiMinSteps,
            max_steps_per_case: aiMaxSteps,
            include_positive_scenarios: true,
            include_negative_scenarios: aiIncludeNegative,
            include_boundary_scenarios: aiIncludeBoundary,
            include_edge_cases: aiIncludeEdge,
            include_security_scenarios: aiIncludeSecurity,
            include_accessibility_checks: aiIncludeAccessibility,
            include_api_validations: aiIncludeApiValidation,
            include_performance_scenarios: aiIncludePerformance,
            performance_budget: aiPerformanceBudget.trim() || undefined,
            module_focus: aiModuleFocus.trim(),
            document_context: aiDocumentAnalysis?.context_text || undefined,
            document_names: aiDocumentAnalysis?.files.map((file) => file.filename) ?? [],
            jira_key: aiJiraIssue?.key || undefined,
            jira_link: aiJiraIssue?.url || undefined,
            jira_context: aiJiraIssue?.context_text || undefined,
            provider: activeConfig.provider,
            model: activeConfig.model,
          }),
        },
        token,
      );
      if (aiJiraIssue) {
        appendAiLog("info", `🔗 Connected Jira requirement source: ${aiJiraIssue.key} - "${aiJiraIssue.summary}"`);
      }
      appendAiLog("success", `🧵 Durable generation job queued (${generationJob.id}).`);
      setActiveGenJobId(generationJob.id);
      setBackendGenerationLogs([]);
      let completedJob = generationJob;
      let lastJobPhase = "";
      let lastStageAnnouncement = "";
      const jobStartedAt = Date.now();
      while (["queued", "running"].includes(completedJob.status)) {
        const serverStages = completedJob.result?.agent_stages;
        const activeStage = serverStages?.find((stage) => stage.status === "running");
        if (serverStages?.length) {
          setAiAgentStages(serverStages);
          if (activeStage) {
            const stageSignature = `${activeStage.key}:${activeStage.status}:${activeStage.detail}`;
            if (stageSignature !== lastStageAnnouncement) {
              lastStageAnnouncement = stageSignature;
              appendAiLog("step", `⏳ ${activeStage.name}: ${activeStage.detail}`);
            }
          }
        }
        if (completedJob.phase !== lastJobPhase) {
          lastJobPhase = completedJob.phase;
          const uiPhase = ["test_case_generator"].includes(completedJob.phase)
            ? "generating"
            : ["validation_agent", "repository", "persisting"].includes(completedJob.phase)
              ? "publishing"
              : "preparing";
          setAiGenerationPhase(uiPhase);
          if (!activeStage) appendAiLog("step", `⏳ Generation job phase: ${completedJob.phase}.`);
        }
        if (Date.now() - jobStartedAt > 900_000) {
          throw new Error("AI generation job timed out while waiting for the worker (exceeded 15 minutes).");
        }
        try {
          const logPayload = await apiFetch<{ logs: GenerationLogItem[] }>(
            `/api/v1/ai-generation/jobs/${generationJob.id}/logs`,
            {},
            token,
          );
          if (logPayload?.logs?.length) {
            setBackendGenerationLogs(logPayload.logs);
          }
        } catch {
          if (completedJob.result?.logs) {
            setBackendGenerationLogs(completedJob.result.logs as any);
          }
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
        completedJob = await apiFetch<AIGenerationJob>(`/api/v1/ai-generation/jobs/${generationJob.id}`, {}, token);
      }
      if (completedJob.status === "failed") {
        if (completedJob.result?.logs) {
          setBackendGenerationLogs(completedJob.result.logs as any);
        }
        throw new Error(completedJob.error || "AI generation job failed.");
      }
      if (completedJob.result?.logs) {
        setBackendGenerationLogs(completedJob.result.logs as any);
      }
      if (completedJob.result?.agent_stages?.length) setAiAgentStages(completedJob.result.agent_stages);
      if (completedJob.result?.planner_used) {
        appendAiLog(
          "ai",
          `🧭 AI Planner selected ${completedJob.result.planner_case_target ?? "a"} case target; AI Generator completed ${completedJob.result.generator_call_count ?? 1} provider call${completedJob.result.generator_call_count === 1 ? "" : "s"}.`,
        );
      }
      const generationSource = parseAiGenerationSourceFromJob(completedJob);
      setAiGenerationSource(generationSource);
      const persistedCaseIds = new Set(completedJob.result?.case_ids ?? []);
      const persistedCases = await apiFetch<TestCase[]>(
        `/api/v1/test-cases/application/${selectedApp.id}?limit=500&offset=0`,
        {},
        token,
      );
      const generatedCases = persistedCases.filter((caseItem) => persistedCaseIds.has(caseItem.id));
      appendAiLog("success", `📡 Durable provider job completed (${completedJob.id}).`);
      appendAiLog("success", `📥 Received ${generatedCases.length} persisted scenario definition(s) from ${generationSource.provider || aiConfigState?.provider || "LLM"}`);
      if (!generatedCases.length) {
        throw new Error("AI generation completed without persisted test cases. Review the job details and try again.");
      }

      appendAiLog("step", `🛡️ Running quality gate, deduplication, and schema validation...`);
      const normalizedGeneration = normalizeGeneratedCases(generatedCases, selectedApp.id);
      if (!normalizedGeneration.cases.length) {
        appendAiLog("error", "❌ Quality gate failed: No valid test scenarios returned.");
        throw new Error("AI generation did not return usable test cases. Refine the prompt and try again.");
      }

      const droppedCount = normalizedGeneration.duplicateCount + normalizedGeneration.invalidCount;
      appendAiLog("info", `✅ Quality gate passed: ${normalizedGeneration.cases.length} validated scenarios (${droppedCount} dropped duplicate/invalid)`);

      setTestCases((current) => [
        ...current.filter((caseItem) => caseItem.application_id !== selectedApp.id),
        ...normalizedGeneration.cases,
      ]);
      setAiGenerationPhase("publishing");
      appendAiLog("step", `💾 Persisting ${normalizedGeneration.cases.length} test case(s) into database repository...`);

      normalizedGeneration.cases.forEach((c, idx) => {
        const stepLines = (c.steps || "").split("\n").filter(Boolean).length;
        appendAiLog("step", `  [TC${idx + 1}] ${c.title} (${stepLines} steps)`);
      });

      await loadDashboardData(token, selectedApp.name);
      await loadAutomationReadiness(token, selectedApp.id);
      appendAiLog("success", "✅ Test cases saved and repository data refreshed.");
      setGenerated(true);
      setAiGenerationPhase("done");
      appendAiLog("success", `✨ Pure LLM generation complete! Created ${normalizedGeneration.cases.length} test cases.`);
      appendAiLog("success", "🖥️ UI refresh completed. Opening the generated test-case repository...");

      const generatedCaseIds = normalizedGeneration.cases.map((caseItem) => caseItem.id);
      setLatestGeneratedCaseIds(generatedCaseIds);
      setLatestGenerationInput({
        prompt,
        documentNames: [
          ...(aiJiraIssue ? [`Jira: ${aiJiraIssue.key} (${aiJiraIssue.summary})`] : []),
          ...(aiDocumentAnalysis?.files.map((file) => file.filename) ?? []),
        ],
      });
      try {
        window.sessionStorage.setItem(LATEST_GENERATED_CASES_STORAGE_KEY, JSON.stringify(generatedCaseIds));
      } catch {
      }
      const createdCount = normalizedGeneration.cases.length;
      const generationMessageCore = droppedCount
        ? `${createdCount} AI-generated test cases created (${droppedCount} dropped during quality checks)`
        : `${createdCount} AI-generated test cases created`;
      const generationMessage = generationSource.mode === "provider"
        ? `${generationMessageCore} using the configured provider model`
        : generationMessageCore;
      notify(guidedRunEnabled ? `Demo mode: ${generationMessage.toLowerCase()} and starting execution` : generationMessage);
      setSelectedGeneratedCaseIds(generatedCaseIds);
      if (shouldRunImmediately && selectedApp.platform === "web" && generatedCaseIds.length) {
        navigateToSection("execution");
        await runApplicationCaseTests(generatedCaseIds);
        return true;
      }
      if (shouldOpenCases) {
        navigateToSection("cases");
      } else if (shouldOpenExecution) {
        navigateToSection("execution");
      }
      return true;
    } catch (error) {
      setAiGenerationPhase("error");
      setAiGenerationSource(null);
      const message = error instanceof Error ? error.message : "Unable to generate AI test cases";
      appendAiLog("error", `❌ Generation failed: ${message}`);
      if (message === "Not Found") {
        notify("AI generation endpoint is unavailable. Restart the backend and try again.");
        return false;
      }
      notify(message);
      return false;
    } finally {
      setSavingAiTarget(false);
      setAiGenerating(false);
    }
  };

  const downloadProgress = async () => {
    if (!app?.id) {
      notify("Select an application before downloading progress");
      return;
    }
    setDownloadingProgress(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/test-cases/export/${app.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Unable to download test-case progress");
      const file = await response.blob();
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${app.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-test-case-progress.csv`;
      link.click();
      URL.revokeObjectURL(url);
      notify("Test-case progress downloaded");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to download test-case progress");
    } finally {
      setDownloadingProgress(false);
    }
  };

  const downloadExecutionHistory = async () => {
    if (!app?.id) {
      notify("Select an application before downloading execution history");
      return;
    }
    setDownloadingExecutionHistory(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/execution/export/${app.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Unable to download execution history");
      const file = await response.blob();
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${app.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-execution-history.csv`;
      link.click();
      URL.revokeObjectURL(url);
      notify("Execution history downloaded");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to download execution history");
    } finally {
      setDownloadingExecutionHistory(false);
    }
  };

  const downloadGeneratedPreviewTemplate = () => {
    if (!app?.id) {
      notify("Select an application before downloading the preview template");
      return;
    }
    if (!previewCaseRows.length) {
      notify("Generate test cases first to download the preview template");
      return;
    }
    setDownloadingAiPreview(true);
    try {
      const escapeCsv = (value: string) => `"${value.replace(/"/g, "\"\"")}"`;
      const rows = [
        ["Test Case", "Precondition", "Description", "Step Number", "Steps", "Expected Result", "Status"],
        ...previewCaseRows.map((row) => [
          row.isFirst ? row.testCase : "",
          row.isFirst ? row.precondition : "",
          row.isFirst ? row.description : "",
          row.stepNumber || "—",
          row.step || "—",
          row.expectedResult || "",
          row.isFirst ? row.status : "",
        ]),
      ];
      const csv = rows.map((columns) => columns.map((value) => escapeCsv(String(value ?? ""))).join(",")).join("\n");
      const file = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${app.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-ai-generated-preview-template.csv`;
      link.click();
      URL.revokeObjectURL(url);
      notify("Generated preview template downloaded");
    } finally {
      setDownloadingAiPreview(false);
    }
  };

  const selectedAppRunsForDashboard = useMemo(
    () => trackedRuns.filter((run) => run.application_id === app?.id),
    [trackedRuns, app?.id],
  );
  const passedRunsForDashboard = useMemo(
    () => selectedAppRunsForDashboard.filter((run) => run.status === "passed").length,
    [selectedAppRunsForDashboard],
  );
  const failedRunsForDashboard = useMemo(
    () => selectedAppRunsForDashboard.filter((run) => run.status === "failed" || run.status === "error").length,
    [selectedAppRunsForDashboard],
  );
  const selectedAppDefectsForDashboard = useMemo(
    () => (app?.id ? defects.filter((item) => item.application_id === app.id) : defects),
    [app?.id, defects],
  );
  const openDefectCountForDashboard = useMemo(
    () => selectedAppDefectsForDashboard.filter((item) => item.status.toLowerCase().includes("open")).length,
    [selectedAppDefectsForDashboard],
  );
  const totalExecutionsForDashboard = selectedAppRunsForDashboard.length;
  const passRateForDashboard = totalExecutionsForDashboard ? Math.round((passedRunsForDashboard / totalExecutionsForDashboard) * 100) : 0;
  const selectedAppEnvironment = inferEnvironmentLabel(app?.url);
  const moduleCoverage = useMemo(() => buildCategoryCoverage(selectedCases), [selectedCases]);
  const executionTrend = useMemo(() => buildExecutionTrend(selectedAppRunsForDashboard, 7), [selectedAppRunsForDashboard]);
  const readyCasesForSelectedApp = useMemo(
    () => selectedCases.filter((caseItem) => !isDraftStatus(caseItem.status)).length,
    [selectedCases],
  );
  const openDefects = useMemo(
    () => defects.filter((item) => item.status.toLowerCase().includes("open")).length,
    [defects],
  );
  const closedDefects = Math.max(selectedAppDefectsForDashboard.length - openDefectCountForDashboard, 0);
  const appCaseDistribution = useMemo(
    () => buildApplicationCaseDistribution(apps, testCases).map((item) => ({ ...item, tone: "info" as const })),
    [apps, testCases],
  );
  const appPassRateDistribution = useMemo(
    () => buildApplicationPassRateDistribution(apps, trackedRuns).map((item) => ({ ...item, tone: "success" as const })),
    [apps, trackedRuns],
  );
  const defectPriorityDistribution = useMemo(() => buildDefectPriorityDistribution(defects), [defects]);
  const defectStatusDistribution = useMemo(() => buildDefectStatusDistribution(defects), [defects]);
  const suiteReadinessDistribution = useMemo(
    () => apps.map((item) => {
      const appCases = testCases.filter((caseItem) => caseItem.application_id === item.id);
      const readyCount = appCases.filter((caseItem) => caseItem.status.trim().toLowerCase() === "ready").length;
      return { label: item.name, value: readyCount, tone: "success" as const };
    }),
    [apps, testCases],
  );
  const reportScopedRuns = useMemo(
    () => (app?.id ? trackedRuns.filter((run) => run.application_id === app.id) : trackedRuns),
    [app?.id, trackedRuns],
  );
  const reportScopedDefects = useMemo(
    () => (app?.id ? defects.filter((item) => item.application_id === app.id) : defects),
    [app?.id, defects],
  );
  const reportExecutionTrend = useMemo(() => buildExecutionTrend(reportScopedRuns, 7), [reportScopedRuns]);
  const reportDefectTrend = useMemo(() => buildDefectTrend(reportScopedDefects, 7), [reportScopedDefects]);
  const readyCaseIds = useMemo(
    () => selectedCases
      .filter((caseItem) => caseItem.status.trim().toLowerCase() === "ready")
      .map((caseItem) => caseItem.id),
    [selectedCases],
  );
  const aiGenerationBlocker = !app?.id
    ? "Select an application to enable generation."
    : !aiTargetReady
      ? "Provide a target URL before generating."
      : !aiPromptReady
        ? "Add a prompt (at least 3 characters)."
        : "";
  const aiGenerationSourceLabel = aiGenerationSource?.mode === "provider"
    ? "Provider-backed generation"
    : "Generation source unknown";
  const aiGenerationSourceTone = aiGenerationSource?.mode === "provider"
    ? "success"
    : "neutral";
  const aiProviderHint = aiGenerationSource?.mode === "unknown"
    ? "Verify the selected provider and connection settings before generating again."
    : "";
  const aiValidatedCases = latestGeneratedCases.length ? latestGeneratedCases : selectedCases;
  const aiCaseSummaryRows = useMemo(
    () => aiValidatedCases.map((caseItem) => {
      const readiness = automationReadinessByCaseId[caseItem.id];
      const stepCount = parseStepEntries(caseItem.steps).filter((entry) => entry.text !== "—").length;
      const expectedResultCount = splitNonEmptyLines(caseItem.expected_result).length;
      return {
        id: caseItem.id,
        title: caseItem.title,
        status: caseItem.status,
        stepCount,
        expectedResultCount,
        hasAutomation: readiness?.has_automation ?? false,
        needsReview: readiness?.needs_manual_selector_review ?? false,
        confidenceLabel: readiness ? formatConfidenceChipLabel(readiness.confidence_score, readiness.confidence_label) : "Pending analysis",
        readinessLoaded: Boolean(readiness),
      };
    }),
    [aiValidatedCases, automationReadinessByCaseId],
  );
  const aiCasesWithStructuredSteps = aiCaseSummaryRows.filter((row) => row.stepCount > 0).length;
  const aiCasesWithExpectedResults = aiCaseSummaryRows.filter((row) => row.expectedResultCount > 0).length;
  const aiReadinessLoadedCount = aiCaseSummaryRows.filter((row) => row.readinessLoaded).length;
  const aiAutomationReadyCount = aiCaseSummaryRows.filter((row) => row.hasAutomation).length;
  const aiNeedsReviewCount = aiCaseSummaryRows.filter((row) => row.needsReview).length;
  const aiValidationPercent = aiCaseSummaryRows.length
    ? Math.round(((aiCasesWithStructuredSteps + aiCasesWithExpectedResults + aiAutomationReadyCount) / (aiCaseSummaryRows.length * 3)) * 100)
    : 0;
  const aiValidationTone = aiValidationPercent >= 80 ? "success" : aiValidationPercent >= 60 ? "warning" : "danger";
  const aiReadyRunCaseIds = useMemo(
    () => (latestGeneratedCases.length ? latestGeneratedCases : selectedCases)
      .filter((caseItem) => caseItem.status.trim().toLowerCase() === "ready")
      .map((caseItem) => caseItem.id),
    [latestGeneratedCases, selectedCases],
  );
  const reportRunStatusDistribution = useMemo(() => buildRunStatusDistribution(reportScopedRuns), [reportScopedRuns]);
  const reportDefectStatusDistribution = useMemo(() => buildDefectStatusDistribution(reportScopedDefects), [reportScopedDefects]);
  const reportCompletedRuns = useMemo(
    () => reportScopedRuns.filter((run) => ["passed", "failed", "error"].includes(run.status)),
    [reportScopedRuns],
  );
  const reportPassedRuns = useMemo(
    () => reportCompletedRuns.filter((run) => run.status === "passed").length,
    [reportCompletedRuns],
  );
  const reportFailedRuns = useMemo(
    () => reportCompletedRuns.filter((run) => run.status === "failed" || run.status === "error").length,
    [reportCompletedRuns],
  );
  const reportQueuedRuns = useMemo(
    () => reportScopedRuns.filter((run) => run.status === "queued" || run.status === "running").length,
    [reportScopedRuns],
  );
  const reportPassRate = reportCompletedRuns.length ? Math.round((reportPassedRuns / reportCompletedRuns.length) * 100) : 0;
  const reportFailureRate = reportCompletedRuns.length ? Math.round((reportFailedRuns / reportCompletedRuns.length) * 100) : 0;
  const reportOpenDefects = useMemo(
    () => reportScopedDefects.filter((item) => item.status.toLowerCase().includes("open")).length,
    [reportScopedDefects],
  );
  const reportResolvedDefects = Math.max(reportScopedDefects.length - reportOpenDefects, 0);
  const reportDurationByRunId = useMemo(
    () => new Map(caseExecutions.map((entry) => [entry.run_id, entry.duration_ms ?? 0])),
    [caseExecutions],
  );
  const reportDurationSamples = useMemo(
    () => reportCompletedRuns
      .map((run) => reportDurationByRunId.get(run.run_id) ?? 0)
      .filter((duration) => duration > 0),
    [reportCompletedRuns, reportDurationByRunId],
  );
  const reportAverageDurationMs = reportDurationSamples.length
    ? Math.round(reportDurationSamples.reduce((sum, duration) => sum + duration, 0) / reportDurationSamples.length)
    : 0;
  const reportRecentFailures = useMemo(
    () => [...reportScopedRuns]
      .filter((run) => run.status === "failed" || run.status === "error")
      .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))
      .slice(0, 8),
    [reportScopedRuns],
  );
  const completedRunsForWorkspace = useMemo(
    () => trackedRuns.filter((run) => ["passed", "failed", "error"].includes(run.status)),
    [trackedRuns],
  );
  const passedRunsForWorkspace = useMemo(
    () => completedRunsForWorkspace.filter((run) => run.status === "passed").length,
    [completedRunsForWorkspace],
  );
  const workspacePassRate = completedRunsForWorkspace.length ? Math.round((passedRunsForWorkspace / completedRunsForWorkspace.length) * 100) : 0;
  const latestWorkspaceRun = useMemo(
    () => [...trackedRuns]
      .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))[0],
    [trackedRuns],
  );
  const readyWorkspaceCases = useMemo(
    () => testCases.filter((caseItem) => !isDraftStatus(caseItem.status)).length,
    [testCases],
  );
  const workflowSteps = useMemo(
    () => [
      { name: "Project creation", detail: "Workspace and ownership are configured", state: "completed" },
      { name: "Application onboarding", detail: `${apps.length} application target${apps.length === 1 ? "" : "s"} connected`, state: apps.length ? "completed" : "queued" },
      { name: "AI application analysis", detail: `${selectedCases.length} case${selectedCases.length === 1 ? "" : "s"} available for planning`, state: selectedCases.length ? "completed" : "inProgress" },
      { name: "Module identification", detail: `${moduleCoverage.filter((moduleItem) => moduleItem.caseCount > 0).length} module bucket${moduleCoverage.filter((moduleItem) => moduleItem.caseCount > 0).length === 1 ? "" : "s"} detected`, state: moduleCoverage.some((moduleItem) => moduleItem.caseCount > 0) ? "completed" : "queued" },
      { name: "Generate test cases", detail: `${selectedDraftCount} draft case${selectedDraftCount === 1 ? "" : "s"} pending review`, state: selectedCases.length ? "completed" : "queued" },
      { name: "Execute test cases", detail: `${totalExecutionsForDashboard} run${totalExecutionsForDashboard === 1 ? "" : "s"} recorded for selected application`, state: totalExecutionsForDashboard ? "completed" : "queued" },
      { name: "Defect management", detail: `${openDefectCountForDashboard} open defect${openDefectCountForDashboard === 1 ? "" : "s"} requiring triage`, state: defects.length ? "inProgress" : "queued" },
      { name: "Quality reporting", detail: `${trackedRuns.length} run${trackedRuns.length === 1 ? "" : "s"} available for reporting`, state: trackedRuns.length ? "inProgress" : "queued" },
    ] as const,
    [apps.length, selectedCases.length, moduleCoverage, selectedDraftCount, totalExecutionsForDashboard, openDefectCountForDashboard, defects.length, trackedRuns.length],
  );
  const projectRows: ProjectWorkspaceRow[] = useMemo(
    () => projectCatalog.map((project) => {
      const health = inferProjectHealth(workspacePassRate, openDefectCountForDashboard, completedRunsForWorkspace.length);
      const latestWorkspaceSignal = Math.max(
        toTimestampValue(project.updatedAt),
        toTimestampValue(latestWorkspaceRun?.finished_at ?? latestWorkspaceRun?.created_at),
      );
      return {
        id: project.id,
        name: project.name,
        description: project.description,
        lifecycle: project.lifecycle,
        owner: project.owner,
        applications: apps.length,
        testCases: testCases.length,
        lastRunAt: latestWorkspaceRun?.finished_at ?? latestWorkspaceRun?.created_at,
        passRate: workspacePassRate,
        healthBucket: project.lifecycle === "archived" ? "noData" : health.bucket,
        healthLabel: project.lifecycle === "archived" ? "Archived" : health.label,
        openDefects: openDefectCountForDashboard,
        updatedAt: latestWorkspaceSignal ? new Date(latestWorkspaceSignal).toISOString() : project.updatedAt,
      };
    }),
    [projectCatalog, workspacePassRate, openDefectCountForDashboard, completedRunsForWorkspace.length, latestWorkspaceRun, apps.length, testCases.length],
  );
  const filteredProjectRows = useMemo(
    () => {
      const normalizedProjectSearch = deferredProjectSearch.trim().toLowerCase();
      return [...projectRows]
        .filter((project) => (
          !normalizedProjectSearch
          || project.name.toLowerCase().includes(normalizedProjectSearch)
          || project.description.toLowerCase().includes(normalizedProjectSearch)
          || project.owner.toLowerCase().includes(normalizedProjectSearch)
        ))
        .filter((project) => projectLifecycleFilter === "all" || project.lifecycle === projectLifecycleFilter)
        .filter((project) => projectHealthFilter === "all" || project.healthBucket === projectHealthFilter)
        .sort((left, right) => {
          if (projectSortBy === "name") {
            return left.name.localeCompare(right.name);
          }
          if (projectSortBy === "applications") {
            return right.applications - left.applications || left.name.localeCompare(right.name);
          }
          if (projectSortBy === "passRate") {
            return right.passRate - left.passRate || left.name.localeCompare(right.name);
          }
          return toTimestampValue(right.updatedAt) - toTimestampValue(left.updatedAt) || left.name.localeCompare(right.name);
        });
    },
    [projectRows, deferredProjectSearch, projectLifecycleFilter, projectHealthFilter, projectSortBy],
  );
  const activeProjectCount = useMemo(() => projectRows.filter((project) => project.lifecycle === "active").length, [projectRows]);
  const healthyProjectCount = useMemo(() => projectRows.filter((project) => project.healthBucket === "healthy").length, [projectRows]);
  const workspaceCoveragePercent = testCases.length ? Math.round((readyWorkspaceCases / testCases.length) * 100) : 0;
  const selectedProjectRow = projectRows.find((project) => project.id === selectedProjectId) ?? projectRows[0] ?? null;
  const selectedProjectUsesWorkspaceData = Boolean(selectedProjectRow);
  const selectedProjectApplications = apps;
  const selectedProjectCases = testCases;
  const selectedProjectRuns = trackedRuns;
  const selectedProjectCompletedRuns = useMemo(
    () => selectedProjectRuns.filter((run) => ["passed", "failed", "error"].includes(run.status)),
    [selectedProjectRuns],
  );
  const selectedProjectPassedRuns = useMemo(
    () => selectedProjectCompletedRuns.filter((run) => run.status === "passed").length,
    [selectedProjectCompletedRuns],
  );
  const selectedProjectFailedRuns = useMemo(
    () => selectedProjectCompletedRuns.filter((run) => run.status === "failed" || run.status === "error").length,
    [selectedProjectCompletedRuns],
  );
  const selectedProjectQueuedRuns = useMemo(
    () => selectedProjectRuns.filter((run) => run.status === "queued" || run.status === "running").length,
    [selectedProjectRuns],
  );
  const selectedProjectPassRate = selectedProjectCompletedRuns.length ? Math.round((selectedProjectPassedRuns / selectedProjectCompletedRuns.length) * 100) : 0;
  const selectedProjectOpenDefects = useMemo(
    () => defects.filter((defect) => defect.status.toLowerCase().includes("open")),
    [defects],
  );
  const selectedProjectReadyCases = useMemo(
    () => selectedProjectCases.filter((caseItem) => !isDraftStatus(caseItem.status)).length,
    [selectedProjectCases],
  );
  const selectedProjectCoverage = selectedProjectCases.length ? Math.round((selectedProjectReadyCases / selectedProjectCases.length) * 100) : 0;
  const selectedProjectLatestRun = useMemo(
    () => [...selectedProjectRuns]
      .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))[0],
    [selectedProjectRuns],
  );
  const selectedProjectApplicationRows = useMemo(
    () => selectedProjectApplications.map((application) => {
      const appCases = selectedProjectCases.filter((caseItem) => caseItem.application_id === application.id);
      const appReadyCases = appCases.filter((caseItem) => !isDraftStatus(caseItem.status)).length;
      const appRuns = selectedProjectRuns.filter((run) => run.application_id === application.id);
      const appCompleted = appRuns.filter((run) => ["passed", "failed", "error"].includes(run.status));
      const appPassed = appCompleted.filter((run) => run.status === "passed").length;
      const appPassRate = appCompleted.length ? Math.round((appPassed / appCompleted.length) * 100) : 0;
      const appLastRun = [...appRuns]
        .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))[0];
      return {
        id: application.id ?? application.name,
        name: application.name,
        platform: application.platform,
        url: application.url,
        cases: appCases.length,
        readyCases: appReadyCases,
        passRate: appPassRate,
        lastRunAt: appLastRun?.finished_at ?? appLastRun?.created_at,
      };
    }),
    [selectedProjectApplications, selectedProjectCases, selectedProjectRuns],
  );
  const selectedProjectCasePreviewRows = useMemo(
    () => [...selectedProjectCases]
      .sort((left, right) => right.id - left.id)
      .slice(0, 8),
    [selectedProjectCases],
  );
  const selectedProjectRunPreviewRows = useMemo(
    () => [...selectedProjectRuns]
      .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))
      .slice(0, 8),
    [selectedProjectRuns],
  );
  const selectedProjectFailedRunRows = useMemo(
    () => selectedProjectRunPreviewRows.filter((run) => run.status === "failed" || run.status === "error"),
    [selectedProjectRunPreviewRows],
  );
  const selectedProjectReadinessSignals = useMemo(
    () => Object.values(automationReadinessByCaseId),
    [automationReadinessByCaseId],
  );
  const selectedProjectInsights: Array<{ title: string; detail: string; tone: "info" | "warning" | "danger" | "success" }> = useMemo(
    () => {
      const insights: Array<{ title: string; detail: string; tone: "info" | "warning" | "danger" | "success" }> = [];
      if (selectedProjectCompletedRuns.length) {
        insights.push({
          title: "Execution reliability",
          detail: `${selectedProjectPassRate}% pass rate across ${selectedProjectCompletedRuns.length} completed run${selectedProjectCompletedRuns.length === 1 ? "" : "s"}.`,
          tone: selectedProjectPassRate >= 80 ? "success" : selectedProjectPassRate >= 60 ? "warning" : "danger",
        });
      }
      if (selectedProjectOpenDefects.length) {
        insights.push({
          title: "Defect triage load",
          detail: `${selectedProjectOpenDefects.length} open defect${selectedProjectOpenDefects.length === 1 ? "" : "s"} currently require follow-up.`,
          tone: selectedProjectOpenDefects.length > 3 ? "danger" : "warning",
        });
      }
      if (selectedProjectReadinessSignals.length) {
        const selectorReviewCount = selectedProjectReadinessSignals.filter((signal) => signal.needs_manual_selector_review).length;
        insights.push({
          title: "Automation readiness",
          detail: `${selectorReviewCount} of ${selectedProjectReadinessSignals.length} readiness signal${selectedProjectReadinessSignals.length === 1 ? "" : "s"} need selector review.`,
          tone: selectorReviewCount ? "warning" : "success",
        });
      }
      if (!insights.length) {
        insights.push({
          title: "Insights pending",
          detail: "Run executions or load automation readiness signals to unlock AI insights for this project.",
          tone: "info",
        });
      }
      return insights;
    },
    [selectedProjectCompletedRuns.length, selectedProjectPassRate, selectedProjectOpenDefects.length, selectedProjectReadinessSignals],
  );
  const projectDetailTabs: Array<{ id: ProjectDetailTab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "applications", label: "Applications" },
    { id: "cases", label: "Test Cases" },
    { id: "runs", label: "Runs" },
    { id: "results", label: "Results" },
    { id: "insights", label: "AI Insights" },
  ];
  const applicationRows: ApplicationWorkspaceRow[] = useMemo(
    () => apps.map((application) => {
      const hasPersistentId = typeof application.id === "number";
      const applicationCases = hasPersistentId
        ? testCases.filter((caseItem) => caseItem.application_id === application.id)
        : [];
      const readyCaseCount = applicationCases.filter((caseItem) => !isDraftStatus(caseItem.status)).length;
      const draftCaseCount = applicationCases.filter((caseItem) => isDraftStatus(caseItem.status)).length;
      const applicationRuns = hasPersistentId
        ? trackedRuns.filter((run) => run.application_id === application.id)
        : [];
      const completedRuns = applicationRuns.filter((run) => ["passed", "failed", "error"].includes(run.status));
      const passedRuns = completedRuns.filter((run) => run.status === "passed").length;
      const passRate = completedRuns.length ? Math.round((passedRuns / completedRuns.length) * 100) : 0;
      const lastRun = [...applicationRuns]
        .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))[0];
      const openDefectCount = hasPersistentId
        ? defects.filter((defect) => defect.application_id === application.id && defect.status.toLowerCase().includes("open")).length
        : 0;
      const readinessSignals = hasPersistentId
        ? applicationCases.map((caseItem) => automationReadinessByCaseId[caseItem.id]).filter(Boolean)
        : [];
      const automatedCases = readinessSignals.filter((signal) => signal.has_automation).length;
      const selectorReviewCases = readinessSignals.filter((signal) => signal.needs_manual_selector_review).length;
      const health = inferProjectHealth(passRate, openDefectCount, completedRuns.length);
      return {
        id: application.id ?? application.name,
        name: application.name,
        type: application.type,
        platform: application.platform,
        url: application.url || application.target || "—",
        totalCases: Math.max(applicationCases.length, application.cases ?? 0),
        readyCases: readyCaseCount,
        draftCases: draftCaseCount,
        totalRuns: applicationRuns.length,
        completedRuns: completedRuns.length,
        passRate,
        openDefects: openDefectCount,
        lastRunAt: lastRun?.finished_at ?? lastRun?.created_at,
        automatedCases,
        selectorReviewCases,
        healthBucket: health.bucket,
        healthLabel: health.label,
      };
    }),
    [apps, testCases, trackedRuns, defects, automationReadinessByCaseId],
  );
  const filteredApplicationRows = useMemo(
    () => {
      const normalizedApplicationSearch = deferredApplicationSearch.trim().toLowerCase();
      return [...applicationRows]
        .filter((application) => (
          !normalizedApplicationSearch
          || application.name.toLowerCase().includes(normalizedApplicationSearch)
          || application.type.toLowerCase().includes(normalizedApplicationSearch)
          || application.url.toLowerCase().includes(normalizedApplicationSearch)
        ))
        .filter((application) => applicationPlatformFilter === "all" || application.platform === applicationPlatformFilter)
        .filter((application) => applicationHealthFilter === "all" || application.healthBucket === applicationHealthFilter)
        .sort((left, right) => {
          if (applicationSortBy === "cases") {
            return right.totalCases - left.totalCases || left.name.localeCompare(right.name);
          }
          if (applicationSortBy === "runs") {
            return right.totalRuns - left.totalRuns || left.name.localeCompare(right.name);
          }
          if (applicationSortBy === "passRate") {
            return right.passRate - left.passRate || left.name.localeCompare(right.name);
          }
          return left.name.localeCompare(right.name);
        });
    },
    [applicationRows, deferredApplicationSearch, applicationPlatformFilter, applicationHealthFilter, applicationSortBy],
  );
  const webApplicationCount = useMemo(() => applicationRows.filter((application) => application.platform === "web").length, [applicationRows]);
  const mobileApplicationCount = useMemo(() => applicationRows.filter((application) => application.platform !== "web").length, [applicationRows]);
  const applicationsWithReadyCoverage = useMemo(() => applicationRows.filter((application) => application.readyCases > 0).length, [applicationRows]);
  const applicationsWithAutomation = useMemo(() => applicationRows.filter((application) => application.automatedCases > 0).length, [applicationRows]);
  const applicationsWithExecutionBaseline = useMemo(() => applicationRows.filter((application) => application.totalRuns > 0).length, [applicationRows]);
  const criticalApplicationCount = useMemo(() => applicationRows.filter((application) => application.healthBucket === "critical").length, [applicationRows]);
  const applicationAttentionRows = useMemo(
    () => applicationRows
      .filter((application) => application.healthBucket === "critical" || application.totalCases === 0 || application.selectorReviewCases > 0)
      .slice(0, 4),
    [applicationRows],
  );
  const selectedApplicationWorkspaceRow = useMemo(
    () => applicationRows.find((application) => application.name === app?.name) ?? applicationRows[0] ?? null,
    [applicationRows, app?.name],
  );
  const selectedApplicationDiscoveryStages = useMemo(
    () => (selectedApplicationWorkspaceRow
      ? [
        {
          name: "Target onboarding",
          detail: selectedApplicationWorkspaceRow.platform === "web"
            ? selectedApplicationWorkspaceRow.url
            : `${formatPlatformLabel(selectedApplicationWorkspaceRow.platform)} package linked`,
          state: selectedApplicationWorkspaceRow.url && selectedApplicationWorkspaceRow.url !== "—" ? "completed" : "attention",
        },
        {
          name: "Baseline test design",
          detail: `${selectedApplicationWorkspaceRow.totalCases} case${selectedApplicationWorkspaceRow.totalCases === 1 ? "" : "s"} · ${selectedApplicationWorkspaceRow.readyCases} ready`,
          state: selectedApplicationWorkspaceRow.totalCases === 0
            ? "queued"
            : selectedApplicationWorkspaceRow.readyCases === 0
              ? "inProgress"
              : "completed",
        },
        {
          name: "Automation readiness",
          detail: `${selectedApplicationWorkspaceRow.automatedCases}/${selectedApplicationWorkspaceRow.totalCases || 0} case${selectedApplicationWorkspaceRow.totalCases === 1 ? "" : "s"} automated`,
          state: selectedApplicationWorkspaceRow.totalCases === 0
            ? "queued"
            : selectedApplicationWorkspaceRow.automatedCases === 0
              ? "inProgress"
              : selectedApplicationWorkspaceRow.selectorReviewCases > 0
                ? "attention"
                : "completed",
        },
        {
          name: "Execution baseline",
          detail: `${selectedApplicationWorkspaceRow.totalRuns} run${selectedApplicationWorkspaceRow.totalRuns === 1 ? "" : "s"} · ${selectedApplicationWorkspaceRow.passRate}% pass`,
          state: selectedApplicationWorkspaceRow.totalRuns === 0
            ? "queued"
            : selectedApplicationWorkspaceRow.healthBucket === "critical"
              ? "attention"
              : "completed",
        },
        {
          name: "Defect feedback loop",
          detail: `${selectedApplicationWorkspaceRow.openDefects} open defect${selectedApplicationWorkspaceRow.openDefects === 1 ? "" : "s"}`,
          state: selectedApplicationWorkspaceRow.totalRuns === 0
            ? "queued"
            : selectedApplicationWorkspaceRow.openDefects > 0
              ? "attention"
              : "completed",
        },
      ] as const
      : []),
    [selectedApplicationWorkspaceRow],
  );
  const completedDiscoveryStages = selectedApplicationDiscoveryStages.filter((stage) => stage.state === "completed").length;
  const discoveryProgressPercent = selectedApplicationDiscoveryStages.length
    ? Math.round((completedDiscoveryStages / selectedApplicationDiscoveryStages.length) * 100)
    : 0;
  const selectedCompletedRuns = selectedAppRunsForDashboard.filter((run) => ["passed", "failed", "error"].includes(run.status)).length;
  const readyCoveragePercentForDashboard = selectedCases.length ? Math.round((readyCasesForSelectedApp / selectedCases.length) * 100) : 0;
  const dashboardHealthLabel = selectedApplicationWorkspaceRow?.healthLabel ?? "No data";
  const dashboardHealthTone = selectedApplicationWorkspaceRow?.healthBucket === "healthy"
    ? "tone-success"
    : selectedApplicationWorkspaceRow?.healthBucket === "watch"
      ? "tone-warning"
      : selectedApplicationWorkspaceRow?.healthBucket === "critical"
        ? "tone-danger"
        : "tone-neutral";
  const topCoveredModules = useMemo(() => moduleCoverage.filter((moduleItem) => moduleItem.caseCount > 0).slice(0, 6), [moduleCoverage]);
  const selectedDashboardOpenDefects = useMemo(
    () => defects
      .filter((item) => item.status.toLowerCase().includes("open") && (!app?.id || item.application_id === app.id))
      .slice(0, 5),
    [defects, app?.id],
  );
  const dashboardRecentRuns = useMemo(
    () => [...selectedAppRunsForDashboard]
      .sort((left, right) => toTimestampValue(right.finished_at ?? right.created_at) - toTimestampValue(left.finished_at ?? left.created_at))
      .slice(0, 6),
    [selectedAppRunsForDashboard],
  );
  const dashboardActiveRuns = useMemo(
    () => selectedAppRunsForDashboard.filter((run) => run.status === "queued" || run.status === "running"),
    [selectedAppRunsForDashboard],
  );
  const dashboardAttentionItems = useMemo(
    () => [
      ...(selectedDraftCount > 0 ? [{ label: "Review draft coverage", detail: `${selectedDraftCount} draft case${selectedDraftCount === 1 ? "" : "s"} for ${app?.name ?? "the selected application"}`, action: "cases" as Section }] : []),
      ...(failedRunsForDashboard > 0 ? [{ label: "Investigate failed runs", detail: `${failedRunsForDashboard} failed or errored run${failedRunsForDashboard === 1 ? "" : "s"} need triage`, action: "execution" as Section }] : []),
      ...(openDefectCountForDashboard > 0 ? [{ label: "Triage open defects", detail: `${openDefectCountForDashboard} open issue${openDefectCountForDashboard === 1 ? "" : "s"} linked to this scope`, action: "defects" as Section }] : []),
      ...(app && !app.url && app.platform === "web" ? [{ label: "Complete target setup", detail: "Add a web URL before running discovery", action: "applications" as Section }] : []),
    ].slice(0, 4),
    [selectedDraftCount, app, failedRunsForDashboard, openDefectCountForDashboard],
  );

  if (!authReady) return <div className="auth-loading">Loading {WORKSPACE_NAME}...</div>;
  if (!token) {
    return (
      <AuthScreen
        brandTitle={BRAND_TITLE}
        brandSubtitle={BRAND_SUBTITLE}
        mode={authMode}
        email={authEmail}
        password={authPassword}
        error={authError}
        authenticating={authenticating}
        onModeChange={(mode) => { setAuthMode(mode); setAuthError(""); }}
        onEmailChange={setAuthEmail}
        onPasswordChange={setAuthPassword}
        onSubmit={authenticate}
      />
    );
  }

  const dashboard = (
    <>
      <section className="panel dashboard-hero dashboard-hero-modern">
        <div className="dashboard-hero-copy">
          <div className="dashboard-hero-title-row" style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <span className="eyebrow" style={{ color: "var(--brand-primary)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "10px", display: "inline-block" }}>Enterprise AI QA</span>
            <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0 }}>{selectedProjectRow ? `${selectedProjectRow.name}` : app?.name ?? "Enterprise Quality Workspace"}</h2>
            <span className={`dashboard-meta-chip ${selectedProjectRow ? `tone-${selectedProjectRow.healthBucket}` : dashboardHealthTone}`}>
              Health: {selectedProjectRow?.healthLabel ?? dashboardHealthLabel}
            </span>
            <span className="dashboard-meta-chip">Env: {selectedAppEnvironment}</span>
            <span className="dashboard-meta-chip">Platform: {app ? formatPlatformLabel(app.platform) : "Multi-Platform"}</span>
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginTop: "6px" }}>
            <label className="dashboard-scope-control" htmlFor="dashboard-project-selector" title="Switch active project scope">
              <span style={{ fontSize: "11px" }}>Project:</span>
              <select
                id="dashboard-project-selector"
                value={selectedProjectId}
                onChange={(event) => {
                  setSelectedProjectId(event.target.value);
                  notify("Project scope updated");
                }}
              >
                {projectCatalog.map((item) => (
                  <option key={`dashboard-project-${item.id}`} value={item.id}>
                    📁 {item.name} ({formatProjectLifecycle(item.lifecycle)})
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary btn-sm"
              style={{ height: "26px", padding: "0 8px", fontSize: "11px", display: "inline-flex", alignItems: "center", gap: "4px" }}
              onClick={openCreateProjectModal}
              title="Create new project"
            >
              + New
            </button>
            <label className="dashboard-scope-control" htmlFor="dashboard-scope-selector" title="Switch active target application">
              <span style={{ fontSize: "11px" }}>Target:</span>
              <select
                id="dashboard-scope-selector"
                value={app?.name ?? ""}
                onChange={(event) => selectApplication(event.target.value)}
                disabled={!apps.length}
              >
                {apps.length ? apps.map((item) => <option key={`dashboard-scope-${item.id ?? item.name}`} value={item.name}>📱 {item.name} ({formatPlatformLabel(item.platform)})</option>) : <option value="">No applications connected</option>}
              </select>
            </label>
            <button
              type="button"
              className="secondary btn-sm"
              style={{ height: "26px", padding: "0 8px", fontSize: "11px", display: "inline-flex", alignItems: "center", gap: "4px" }}
              onClick={() => navigateToSection("applications")}
              title="Add target application"
            >
              + Add App
            </button>
          </div>
        </div>
        <div className="dashboard-hero-actions dashboard-action-row">
          <button className="primary btn-sm" onClick={() => navigateToSection("aiGenerator")} disabled={!app?.id}>
            <AppIcon name="ai" />
            <span>AI Test Studio</span>
          </button>
          <button className="primary btn-sm" onClick={() => navigateToSection("systemMap")}>
            <AppIcon name="map" />
            <span>Traceability Map</span>
          </button>
          <button className="primary btn-sm" onClick={() => navigateToSection("execution")} disabled={!app?.id}>
            <AppIcon name="execution" />
            <span>Run tests</span>
          </button>
          <button className="secondary btn-sm" onClick={() => navigateToSection("projects")}>📁 Projects ({projectCatalog.length})</button>
          <button className="secondary btn-sm" onClick={() => navigateToSection("applications")}>📱 Apps ({apps.length})</button>
          <button className="secondary btn-sm" onClick={openCreateProjectModal} title="Create a new QA project">+ Project</button>
          <button className="secondary btn-sm" onClick={() => navigateToSection("applications")} title="Add target application">+ Add App</button>
          <button className="secondary btn-sm" onClick={() => void loadDashboardData(token, app?.name)} disabled={refreshingData}>
            {refreshingData ? "..." : "Refresh"}
          </button>
        </div>
      </section>

      {running && (
        <div className="live-running-banner" role="status" aria-live="polite">
          <div className="live-running-banner-left">
            <span className="live-running-pulse" />
            <div className="live-running-banner-copy">
              <strong>Test Execution in Progress</strong>
              <small>{activeExecutionCase?.title ? `Running: ${activeExecutionCase.title}` : runLog || "Playwright execution workers active"}</small>
            </div>
          </div>
          <div className="live-running-banner-right">
            <span className="live-running-kpi">{executionCompletedCount} / {executionTotalCount} Completed</span>
            <span className="live-running-kpi">{executionCounts.passed} Passed</span>
            {executionCounts.failed + executionCounts.error > 0 ? (
              <span className="live-running-kpi" style={{ color: "#f87171" }}>{executionCounts.failed + executionCounts.error} Failed</span>
            ) : null}
            <button
              type="button"
              className="primary btn-sm"
              onClick={() => navigateToSection("execution")}
            >
              View Live Stream →
            </button>
          </div>
        </div>
      )}

      <section className="dashboard-kpi-grid dashboard-kpi-grid-modern">
        <InteractiveKpiCard
          className="dashboard-kpi-card tone-brand"
          label="Enterprise projects"
          value={projectRows.length}
          detail={`${activeProjectCount} active · ${healthyProjectCount} healthy`}
          onClick={() => navigateToSection("projects")}
        />
        <InteractiveKpiCard
          className="dashboard-kpi-card tone-info"
          label="Connected targets"
          value={apps.length}
          detail={`${webApplicationCount} web · ${mobileApplicationCount} mobile · ${dashboardActiveRuns.length} active run${dashboardActiveRuns.length === 1 ? "" : "s"}`}
          onClick={() => navigateToSection("applications")}
        />
        <InteractiveKpiCard
          className="dashboard-kpi-card tone-success"
          label="Test case library"
          value={testCases.length}
          detail={`${readyWorkspaceCases} ready · ${testCases.length - readyWorkspaceCases} draft`}
          onClick={() => navigateToSection("cases")}
        />
        <InteractiveKpiCard
          className={`dashboard-kpi-card ${workspaceCoveragePercent >= 80 ? "tone-success" : workspaceCoveragePercent >= 50 ? "tone-warning" : "tone-danger"}`}
          label="Automation readiness"
          value={`${workspaceCoveragePercent}%`}
          detail={`${readyWorkspaceCases} verified automation ready`}
          onClick={() => navigateToSection("aiGenerator")}
        />
        <InteractiveKpiCard
          className={`dashboard-kpi-card ${workspacePassRate >= 80 ? "tone-success" : workspacePassRate >= 50 ? "tone-warning" : "tone-danger"}`}
          label="Pass rate"
          value={`${workspacePassRate}%`}
          detail={`${passedRunsForWorkspace} passed · ${completedRunsForWorkspace.length - passedRunsForWorkspace} failed`}
          onClick={() => navigateToSection("execution")}
        />
        <InteractiveKpiCard
          className={`dashboard-kpi-card ${selectedDashboardOpenDefects.length > 0 ? "tone-danger" : "tone-success"}`}
          label="Open quality issues"
          value={selectedDashboardOpenDefects.length}
          detail={`${closedDefects}/${defects.length || 0} resolved defects`}
          onClick={() => navigateToSection("defects")}
        />
      </section>

      <section className="panel dashboard-application-portfolio">
        <div className="dashboard-section-heading">
          <div>
            <span className="eyebrow">Application overview</span>
            <h2>Connected targets</h2>
          </div>
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <span className="muted">{applicationRows.length} target{applicationRows.length === 1 ? "" : "s"} in this workspace</span>
            <button type="button" className="primary btn-sm" onClick={() => navigateToSection("applications")}>
              + Add Target
            </button>
          </div>
        </div>
        <div className="dashboard-application-grid">
          {applicationRows.length ? applicationRows.map((row) => (
            <article className="dashboard-application-card" key={`dashboard-application-${row.id}`}>
              <div className="dashboard-application-card-head">
                <div>
                  <strong>{row.name}</strong>
                  <small>{formatPlatformLabel(row.platform)} · {row.url}</small>
                </div>
                <span className={`projects-health-badge tone-${row.healthBucket}`}>{row.healthLabel}</span>
              </div>
              <div className="dashboard-application-metrics">
                <span><strong>{row.totalCases}</strong> cases</span>
                <span><strong>{row.totalRuns}</strong> runs</span>
                <span><strong>{row.completedRuns ? `${row.passRate}%` : "—"}</strong> pass rate</span>
                <span><strong>{row.openDefects}</strong> open issues</span>
              </div>
              <div className="dashboard-application-actions">
                <button type="button" className="secondary btn-sm" onClick={() => focusApplication(row.name)}>Open workspace</button>
                <button type="button" className="secondary btn-sm" onClick={() => openSystemMap(row.name)}>Analyze with AI</button>
                <button type="button" className="secondary btn-sm" onClick={() => openApplicationEditModal(row.name)} disabled={typeof row.id !== "number"}>Edit</button>
              </div>
            </article>
          )) : <EmptyState message="Connect an application to start building coverage." />}
        </div>
      </section>

      <div className="dashboard-modern-grid">
        <AppCard className="content-panel dashboard-card dashboard-card-wide">
          <SectionHeader kicker="Operational pulse" title="What needs attention" meta={`${dashboardAttentionItems.length} action${dashboardAttentionItems.length === 1 ? "" : "s"} queued`} />
          {dashboardAttentionItems.length ? (
            <div className="dashboard-attention-list">
              {dashboardAttentionItems.map((item, index) => (
                <button key={`dashboard-attention-${item.label}`} type="button" className="dashboard-attention-item" onClick={() => navigateToSection(item.action)}>
                  <span className="dashboard-attention-index">{index + 1}</span>
                  <span className="dashboard-attention-copy"><strong>{item.label}</strong><small>{item.detail}</small></span>
                  <span className="dashboard-attention-action">Open</span>
                </button>
              ))}
            </div>
          ) : <EmptyState message="No immediate actions for this application. Keep coverage and execution baselines moving." />}
        </AppCard>

        <TrendBlock kicker="Execution trend" title="Last 7-day execution pace">
          {executionTrend.some((entry) => entry.executed > 0) ? (
            <div className="designer-line-chart cc-line-chart">
              <svg viewBox="0 0 360 140" preserveAspectRatio="none" aria-label="Dashboard execution trend chart">
                <TrendLine values={executionTrend.map((entry) => entry.executed)} className="line executed" />
                <TrendLine values={executionTrend.map((entry) => entry.passed)} className="line passed" />
              </svg>
              <div className="cc-line-labels">{executionTrend.map((entry) => <span key={`dashboard-execution-${entry.label}`}>{entry.label}</span>)}</div>
            </div>
          ) : <EmptyState message="Run this application to populate execution trend." />}
        </TrendBlock>

        <AppCard className="content-panel dashboard-card dashboard-card-wide">
          <SectionHeader
            kicker="Run history"
            title="Recent execution outcomes"
            meta={dashboardActiveRuns.length ? `${dashboardActiveRuns.length} run${dashboardActiveRuns.length === 1 ? "" : "s"} in progress` : `${dashboardRecentRuns.length} latest run${dashboardRecentRuns.length === 1 ? "" : "s"}`}
          />
          {dashboardRecentRuns.length ? (
            <div className="dashboard-recent-runs">
              {dashboardRecentRuns.map((run) => (
                <div className="dashboard-recent-run" key={`dashboard-run-${run.run_id}`}>
                  <div className="dashboard-recent-run-copy">
                    <strong>{run.run_id.slice(0, 14)}</strong>
                    <small>{formatTimestamp(run.finished_at ?? run.created_at)} · {run.status === "running" ? "Execution in progress" : run.status === "queued" ? "Waiting in queue" : "Execution finished"}</small>
                  </div>
                  <div className="dashboard-recent-run-actions">
                    {renderStatusChip(run.status)}
                    <button type="button" className="secondary btn-sm" onClick={() => router.push(`/test-execution/${run.run_id}`)}>Inspect</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState message="No execution runs recorded for this application yet." />}
        </AppCard>

        <AppCard className="content-panel dashboard-card">
          <SectionHeader
            kicker="Coverage status"
            title="Module coverage"
            meta={`${topCoveredModules.length} active module${topCoveredModules.length === 1 ? "" : "s"}`}
          />
          <div className="dashboard-module-block">
            {topCoveredModules.length ? (
              <div className="dashboard-module-list">
                {topCoveredModules.map((moduleItem) => (
                  <div key={`dashboard-category-${moduleItem.categoryName}`} className="dashboard-module-row">
                    <span>{moduleItem.categoryName}</span>
                    <span>{moduleItem.caseCount} case{moduleItem.caseCount === 1 ? "" : "s"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">Generate or import test cases to populate module coverage.</p>
            )}
          </div>
        </AppCard>

        <AppCard className="content-panel dashboard-card">
          <SectionHeader
            kicker="Enterprise health"
            title="Quality engineering lifecycle"
            meta={`${workflowSteps.filter((step) => step.state === "completed").length}/${workflowSteps.length} completed`}
          />
          <div className="dashboard-workflow-timeline">
            {workflowSteps.map((step, index) => (
              <article key={`workflow-${step.name}`} className={`dashboard-workflow-item ${step.state}`}>
                <span className="dashboard-workflow-index">{index + 1}</span>
                <div className="dashboard-workflow-copy">
                  <strong>{step.name}</strong>
                  <p className="muted">{step.detail}</p>
                </div>
                {renderWorkflowStatusChip(step.state)}
              </article>
            ))}
          </div>
        </AppCard>

        <AppCard className="content-panel dashboard-card">
          <SectionHeader
            kicker="Open issues"
            title="Defect summary"
            meta={`${selectedDashboardOpenDefects.length} active issue${selectedDashboardOpenDefects.length === 1 ? "" : "s"}`}
          />
          {selectedDashboardOpenDefects.length ? (
            <div className="dashboard-open-issues-list">
              {selectedDashboardOpenDefects.map((issue) => (
                <article key={`dashboard-open-defect-${issue.id}`} className="dashboard-open-issue">
                  <strong>{issue.title}</strong>
                  <small>{issue.priority} priority · {issue.severity} severity</small>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState message="No open issues for the selected application." />
          )}
        </AppCard>

        <AppCard className="content-panel dashboard-card">
          <SectionHeader kicker="Next actions" title="Move through QA workflow" />
          <div className="dashboard-quick-actions">
            <button className="dashboard-quick-action" onClick={() => navigateToSection("projects")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="projects" /></span>
              <span className="dashboard-quick-action-copy"><strong>Projects</strong><small>Manage workspace projects</small></span>
            </button>
            <button className="dashboard-quick-action" onClick={() => navigateToSection("applications")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="applications" /></span>
              <span className="dashboard-quick-action-copy"><strong>Applications</strong><small>Connect or refine targets</small></span>
            </button>
            <button className="dashboard-quick-action" onClick={() => navigateToSection("cases")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="cases" /></span>
              <span className="dashboard-quick-action-copy"><strong>Test Cases</strong><small>Validate generated and imported coverage</small></span>
            </button>
            <button className="dashboard-quick-action" onClick={() => navigateToSection("aiGenerator")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="ai" /></span>
              <span className="dashboard-quick-action-copy"><strong>Scenario Planner</strong><small>Produce AI-driven coverage candidates</small></span>
            </button>
            <button className="dashboard-quick-action" onClick={() => navigateToSection("execution")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="execution" /></span>
              <span className="dashboard-quick-action-copy"><strong>Execute Tests</strong><small>Run selected tests with parallel workers</small></span>
            </button>
            <button className="dashboard-quick-action" onClick={() => navigateToSection("reports")}>
              <span className="dashboard-quick-action-icon"><AppIcon name="reports" /></span>
              <span className="dashboard-quick-action-copy"><strong>Quality Reports</strong><small>Executive metrics & release confidence</small></span>
            </button>
          </div>
        </AppCard>
      </div>
    </>
  );

  const projects = (
    <>
      <section className="panel projects-hero">
        <div>
          <h2>Projects</h2>
        </div>
        <div className="projects-hero-actions">
          <button className="secondary" onClick={() => void loadDashboardData(token, app?.name)} disabled={refreshingData}>
            {refreshingData ? "Refreshing..." : "Refresh workspace"}
          </button>
          <button className="primary" onClick={openCreateProjectModal}>Create project</button>
        </div>
      </section>

      <section className="projects-kpi-grid">
        <InteractiveKpiCard
          className="projects-kpi-card"
          label="Total projects"
          value={projectRows.length}
          detail={`${activeProjectCount} active`}
          onClick={() => navigateToSection("projects")}
        />
        <InteractiveKpiCard
          className="projects-kpi-card"
          label="Applications"
          value={apps.length}
          detail={`${apps.filter((item) => item.platform === "web").length} web targets`}
          onClick={() => navigateToSection("applications")}
        />
        <InteractiveKpiCard
          className="projects-kpi-card"
          label="Automation coverage"
          value={`${workspaceCoveragePercent}%`}
          detail={`${readyWorkspaceCases}/${testCases.length || 0} ready cases`}
          onClick={() => navigateToSection("cases")}
        />
        <InteractiveKpiCard
          className="projects-kpi-card"
          label="Workspace pass rate"
          value={`${workspacePassRate}%`}
          detail={`${healthyProjectCount} project${healthyProjectCount === 1 ? "" : "s"} healthy`}
          onClick={() => navigateToSection("reports")}
        />
      </section>

      <section className="panel projects-table-shell workspace-table-surface">
        <div className="projects-table-header">
          <div>
            <h3>Manage projects</h3>
          </div>
          <span className="muted">{filteredProjectRows.length} of {projectRows.length} shown</span>
        </div>

        <div className="projects-filter-grid">
          <label className="projects-filter-field" htmlFor="project-search">
            <span>Search</span>
            <input
              id="project-search"
              type="search"
              value={projectSearch}
              onChange={(event) => setProjectSearch(event.target.value)}
              placeholder="Search by project, owner, or description"
            />
          </label>
          <label className="projects-filter-field" htmlFor="project-lifecycle-filter">
            <span>Lifecycle</span>
            <select
              id="project-lifecycle-filter"
              value={projectLifecycleFilter}
              onChange={(event) => setProjectLifecycleFilter(event.target.value as "all" | ProjectLifecycle)}
            >
              <option value="all">All lifecycles</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
          </label>
          <label className="projects-filter-field" htmlFor="project-health-filter">
            <span>Health</span>
            <select
              id="project-health-filter"
              value={projectHealthFilter}
              onChange={(event) => setProjectHealthFilter(event.target.value as "all" | ProjectHealthBucket)}
            >
              <option value="all">All health states</option>
              <option value="healthy">Healthy</option>
              <option value="watch">Watch</option>
              <option value="critical">Critical</option>
              <option value="noData">No data</option>
            </select>
          </label>
          <label className="projects-filter-field" htmlFor="project-sort-by">
            <span>Sort by</span>
            <select
              id="project-sort-by"
              value={projectSortBy}
              onChange={(event) => setProjectSortBy(event.target.value as "updated" | "name" | "applications" | "passRate")}
            >
              <option value="updated">Last updated</option>
              <option value="name">Project name</option>
              <option value="applications">Applications</option>
              <option value="passRate">Pass rate</option>
            </select>
          </label>
        </div>

        <div className="table-scroll">
          <table className="projects-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Applications</th>
                <th>Test Cases</th>
                <th>Last Run</th>
                <th>Pass Rate</th>
                <th>Status</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProjectRows.length ? filteredProjectRows.map((project) => {
                const passRateTone = !project.lastRunAt ? "neutral" : project.passRate >= 85 ? "success" : project.passRate >= 60 ? "warning" : "danger";
                return (
                  <tr key={`project-row-${project.id}`}>
                    <td>
                      <div className="projects-name-cell">
                        <strong>{project.name}</strong>
                        <p>{project.description}</p>
                        <span>Owner: {project.owner}</span>
                      </div>
                    </td>
                    <td>{project.applications}</td>
                    <td>{project.testCases}</td>
                    <td>{project.lastRunAt ? formatTimestamp(project.lastRunAt) : "No runs yet"}</td>
                    <td>
                      <span className={`projects-pass-rate tone-${passRateTone}`}>
                        {project.lastRunAt ? `${project.passRate}%` : "—"}
                      </span>
                    </td>
                    <td>
                      <div className="projects-status-cell">
                        <span className={`projects-health-badge tone-${project.healthBucket}`}>{project.healthLabel}</span>
                        <small>{formatProjectLifecycle(project.lifecycle)}</small>
                        <small>{project.openDefects} open defects</small>
                      </div>
                    </td>
                    <td>{formatTimestamp(project.updatedAt)}</td>
                    <td>
                      <div className="projects-row-actions">
                        <button
                          className="secondary btn-sm"
                          onClick={() => {
                            setSelectedProjectId(project.id);
                            setProjectDetailTab("overview");
                            notify(`${project.name} workspace opened`);
                          }}
                        >
                          Open workspace
                        </button>
                        <button className="secondary btn-sm" onClick={() => openEditProjectModal(project.id)} disabled={deletingProjectId === project.id || savingProject}>Edit</button>
                        <button className="secondary btn-sm btn-danger" onClick={() => void deleteProject(project)} disabled={deletingProjectId === project.id || savingProject}>
                          {deletingProjectId === project.id ? "Deleting..." : "Delete"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={8}>
                    <div className="projects-empty-state">
                      <strong>No projects match these filters</strong>
                      <p>Adjust search or filters to find a project, or create a new project workspace.</p>
                      <button
                        className="secondary btn-sm"
                        onClick={() => {
                          setProjectSearch("");
                          setProjectLifecycleFilter("all");
                          setProjectHealthFilter("all");
                          setProjectSortBy("updated");
                        }}
                      >
                        Reset filters
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedProjectRow && (
        <section className="panel project-detail-shell">
          <div className="project-detail-head">
            <div>
              <h3>{selectedProjectRow.name}</h3>
            </div>
            <div className="project-detail-head-actions">
              <button className="secondary btn-sm" onClick={() => openEditProjectModal(selectedProjectRow.id)}>
                Edit project
              </button>
              <button className="secondary btn-sm" onClick={() => navigateToSection("applications")}>
                Open applications
              </button>
              <button className="primary btn-sm" onClick={() => navigateToSection("execution")} disabled={!apps.length}>
                Run tests
              </button>
            </div>
          </div>

          <div className="project-detail-meta-grid">
            <div>
              <span>Lifecycle</span>
              <strong>{formatProjectLifecycle(selectedProjectRow.lifecycle)}</strong>
            </div>
            <div>
              <span>Health</span>
              <strong>{selectedProjectRow.healthLabel}</strong>
            </div>
            <div>
              <span>Owner</span>
              <strong>{selectedProjectRow.owner}</strong>
            </div>
            <div>
              <span>Last run</span>
              <strong>{selectedProjectRow.lastRunAt ? formatTimestamp(selectedProjectRow.lastRunAt) : "No runs yet"}</strong>
            </div>
            <div>
              <span>Updated</span>
              <strong>{formatTimestamp(selectedProjectRow.updatedAt)}</strong>
            </div>
          </div>

          <div className="project-detail-tablist" role="tablist" aria-label="Project detail sections">
            {projectDetailTabs.map((tab) => (
              <button
                key={`project-detail-tab-${tab.id}`}
                id={`project-detail-tab-${tab.id}`}
                role="tab"
                type="button"
                aria-selected={projectDetailTab === tab.id}
                aria-controls={`project-detail-panel-${tab.id}`}
                className={`project-detail-tab ${projectDetailTab === tab.id ? "active" : ""}`}
                onClick={() => setProjectDetailTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {projectDetailTab === "overview" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-overview"
              aria-labelledby="project-detail-tab-overview"
            >
              <div className="project-detail-overview-grid">
                <article className="project-detail-overview-card">
                  <p>Applications</p>
                  <strong>{selectedProjectRow.applications}</strong>
                  <span>Connected targets</span>
                </article>
                <article className="project-detail-overview-card">
                  <p>Test coverage</p>
                  <strong>{selectedProjectCoverage}%</strong>
                  <span>{selectedProjectReadyCases}/{selectedProjectCases.length || 0} ready cases</span>
                </article>
                <article className="project-detail-overview-card">
                  <p>Execution runs</p>
                  <strong>{selectedProjectRuns.length}</strong>
                  <span>{selectedProjectCompletedRuns.length} completed</span>
                </article>
                <article className="project-detail-overview-card">
                  <p>Open defects</p>
                  <strong>{selectedProjectOpenDefects.length}</strong>
                  <span>Quality blockers in queue</span>
                </article>
              </div>
              <div className="project-detail-overview-foot">
                <p className="muted">
                  {selectedProjectUsesWorkspaceData
                    ? `Latest execution run: ${selectedProjectLatestRun ? formatTimestamp(selectedProjectLatestRun.finished_at ?? selectedProjectLatestRun.created_at) : "No runs yet"}.`
                    : "This project has no connected applications yet. Add applications to start discovery and automation."}
                </p>
              </div>
            </div>
          )}

          {projectDetailTab === "applications" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-applications"
              aria-labelledby="project-detail-tab-applications"
            >
              {selectedProjectApplicationRows.length ? (
                <div className="table-scroll">
                  <table className="project-detail-table">
                    <thead>
                      <tr>
                        <th>Application</th>
                        <th>Platform</th>
                        <th>Target URL</th>
                        <th>Test Cases</th>
                        <th>Ready</th>
                        <th>Last Run</th>
                        <th>Pass Rate</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedProjectApplicationRows.map((application) => (
                        <tr key={`project-detail-app-${application.id}`}>
                          <td><strong>{application.name}</strong></td>
                          <td>{application.platform === "web" ? "Web" : application.platform === "android" ? "Android" : "iOS"}</td>
                          <td>{application.url || "—"}</td>
                          <td>{application.cases}</td>
                          <td>{application.readyCases}</td>
                          <td>{application.lastRunAt ? formatTimestamp(application.lastRunAt) : "No runs yet"}</td>
                          <td>{application.lastRunAt ? `${application.passRate}%` : "—"}</td>
                          <td>
                            <button
                              className="secondary btn-sm"
                              onClick={() => {
                                selectApplication(application.name);
                                navigateToSection("cases");
                              }}
                            >
                              Open cases
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="project-detail-empty">
                  <strong>No applications connected</strong>
                  <p>Connect an application to discover pages, generate tests, and track execution quality for this project.</p>
                  <button className="primary btn-sm" onClick={() => navigateToSection("applications")}>Add application</button>
                </div>
              )}
            </div>
          )}

          {projectDetailTab === "cases" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-cases"
              aria-labelledby="project-detail-tab-cases"
            >
              {selectedProjectCasePreviewRows.length ? (
                <div className="table-scroll">
                  <table className="project-detail-table">
                    <thead>
                      <tr>
                        <th>Test Case</th>
                        <th>Application</th>
                        <th>Status</th>
                        <th>Updated</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedProjectCasePreviewRows.map((caseItem) => {
                        const mappedApplication = apps.find((application) => application.id === caseItem.application_id);
                        return (
                          <tr key={`project-detail-case-${caseItem.id}`}>
                            <td>
                              <strong>{caseItem.title}</strong>
                            </td>
                            <td>{mappedApplication?.name ?? "Unknown application"}</td>
                            <td>{renderStatusChip(caseItem.status)}</td>
                            <td>{`Case #${caseItem.id}`}</td>
                            <td>
                              <button
                                className="secondary btn-sm"
                                onClick={() => {
                                  if (mappedApplication?.name) selectApplication(mappedApplication.name);
                                  navigateToSection("cases");
                                }}
                              >
                                View case
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="project-detail-empty">
                  <strong>No test cases yet</strong>
                  <p>Create starter cases or generate AI test cases once an application is connected.</p>
                  <button className="primary btn-sm" onClick={() => navigateToSection("aiGenerator")} disabled={!apps.length}>
                    Generate test cases
                  </button>
                </div>
              )}
            </div>
          )}

          {projectDetailTab === "runs" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-runs"
              aria-labelledby="project-detail-tab-runs"
            >
              {selectedProjectRunPreviewRows.length ? (
                <div className="table-scroll">
                  <table className="project-detail-table">
                    <thead>
                      <tr>
                        <th>Run ID</th>
                        <th>Application</th>
                        <th>Status</th>
                        <th>Started</th>
                        <th>Finished</th>
                        <th>Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedProjectRunPreviewRows.map((runItem) => {
                        const startedAtMs = toTimestampValue(runItem.created_at);
                        const finishedAtMs = toTimestampValue(runItem.finished_at);
                        const durationSeconds = startedAtMs && finishedAtMs && finishedAtMs >= startedAtMs
                          ? Math.round((finishedAtMs - startedAtMs) / 1000)
                          : 0;
                        const appLabel = apps.find((application) => application.id === runItem.application_id)?.name ?? `Application ${runItem.application_id}`;
                        return (
                          <tr key={`project-detail-run-${runItem.run_id}`}>
                            <td><code>{runItem.run_id.slice(0, 12)}</code></td>
                            <td>{appLabel}</td>
                            <td>{renderStatusChip(runItem.status)}</td>
                            <td>{formatTimestamp(runItem.created_at)}</td>
                            <td>{formatTimestamp(runItem.finished_at)}</td>
                            <td>{durationSeconds ? `${durationSeconds}s` : "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="project-detail-empty">
                  <strong>No execution history yet</strong>
                  <p>Run test cases to populate execution history, durations, and status trends.</p>
                  <button className="primary btn-sm" onClick={() => navigateToSection("execution")} disabled={!apps.length}>
                    Open test execution
                  </button>
                </div>
              )}
            </div>
          )}

          {projectDetailTab === "results" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-results"
              aria-labelledby="project-detail-tab-results"
            >
              {selectedProjectUsesWorkspaceData ? (
                <>
                  <div className="project-detail-results-grid">
                    <article className="project-detail-result-card"><p>Passed</p><strong>{selectedProjectPassedRuns}</strong></article>
                    <article className="project-detail-result-card"><p>Failed/Error</p><strong>{selectedProjectFailedRuns}</strong></article>
                    <article className="project-detail-result-card"><p>Queued/Running</p><strong>{selectedProjectQueuedRuns}</strong></article>
                    <article className="project-detail-result-card"><p>Pass Rate</p><strong>{selectedProjectPassRate}%</strong></article>
                  </div>
                  {selectedProjectFailedRunRows.length ? (
                    <div className="table-scroll">
                      <table className="project-detail-table">
                        <thead>
                          <tr>
                            <th>Failed Run</th>
                            <th>Application</th>
                            <th>Status</th>
                            <th>Started</th>
                            <th>Next action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedProjectFailedRunRows.map((runItem) => {
                            const appLabel = apps.find((application) => application.id === runItem.application_id)?.name ?? `Application ${runItem.application_id}`;
                            return (
                              <tr key={`project-detail-failure-${runItem.run_id}`}>
                                <td><code>{runItem.run_id.slice(0, 12)}</code></td>
                                <td>{appLabel}</td>
                                <td>{renderStatusChip(runItem.status)}</td>
                                <td>{formatTimestamp(runItem.created_at)}</td>
                                <td>
                                  <button className="secondary btn-sm" onClick={() => navigateToSection("execution")}>Inspect run</button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="project-detail-empty compact">
                      <strong>No failed runs detected</strong>
                      <p>Current completed runs do not include failed or error outcomes.</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="project-detail-empty">
                  <strong>No results available</strong>
                  <p>Results appear after this project has connected applications and executed test runs.</p>
                </div>
              )}
            </div>
          )}

          {projectDetailTab === "insights" && (
            <div
              className="project-detail-panel"
              role="tabpanel"
              id="project-detail-panel-insights"
              aria-labelledby="project-detail-tab-insights"
            >
              {selectedProjectUsesWorkspaceData ? (
                <>
                  <div className="project-detail-insight-list">
                    {selectedProjectInsights.map((insight) => (
                      <article key={`${insight.title}-${insight.detail}`} className={`project-detail-insight-card tone-${insight.tone}`}>
                        <strong>{insight.title}</strong>
                        <p>{insight.detail}</p>
                      </article>
                    ))}
                  </div>
                  {selectedProjectReadinessSignals.length ? (
                    <div className="table-scroll">
                      <table className="project-detail-table">
                        <thead>
                          <tr>
                            <th>Test Case</th>
                            <th>Automation Confidence</th>
                            <th>Selector Review</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedProjectReadinessSignals.slice(0, 6).map((signal) => (
                            <tr key={`project-detail-readiness-${signal.test_case_id}`}>
                              <td>{signal.title}</td>
                              <td>{formatConfidenceChipLabel(signal.confidence_score, signal.confidence_label)}</td>
                              <td>{signal.needs_manual_selector_review ? "Required" : "Not required"}</td>
                              <td>{renderStatusChip(signal.status)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="project-detail-empty compact">
                      <strong>No readiness signals loaded</strong>
                      <p>Open Test Cases for a connected application to load automation readiness diagnostics.</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="project-detail-empty">
                  <strong>AI insights unavailable</strong>
                  <p>AI insights appear after this project includes execution and readiness data.</p>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </>
  );

  const caseRows = buildCaseTableRows(selectedCases);
  const hasApplications = apps.length > 0;
  const hasSelectedApplication = Boolean(app?.id);
  const selectedAppRuns = trackedRuns.filter((run) => run.application_id === app?.id);
  const caseExecutionByRunId = new Map(caseExecutions.map((entry) => [entry.run_id, entry]));
  const selectedAppFailedRuns = selectedAppRuns.filter((run) => run.status === "failed" || run.status === "error").length;
  const aiPipelineStages: Array<{ key: "planner" | "generator" | "validator" | "healer"; label: string; detail: string; state: "completed" | "inProgress" | "queued" | "attention" }> = [
    {
      key: "planner",
      label: "Planner",
      detail: aiPromptReady
        ? "Intent and scope are structured for generation."
        : "Add prompt detail and coverage scope.",
      state: aiPromptReady ? "completed" : "inProgress",
    },
    {
      key: "generator",
      label: "Generator",
      detail: latestGeneratedCases.length
        ? `${latestGeneratedCases.length} latest generated case${latestGeneratedCases.length === 1 ? "" : "s"}`
        : aiGenerating
          ? "Generating test cases..."
          : "Ready to generate new coverage",
      state: latestGeneratedCases.length ? "completed" : aiGenerating ? "inProgress" : "queued",
    },
    {
      key: "validator",
      label: "Validator",
      detail: aiCaseSummaryRows.length
        ? aiNeedsReviewCount
          ? `${aiNeedsReviewCount} case${aiNeedsReviewCount === 1 ? "" : "s"} need review`
          : "All sampled cases are automation-ready"
        : "Generate cases to validate structure",
      state: aiCaseSummaryRows.length ? (aiNeedsReviewCount ? "attention" : "completed") : "queued",
    },
    {
      key: "healer",
      label: "Healer",
      detail: selectedAppFailedRuns
        ? `${selectedAppFailedRuns} failed run${selectedAppFailedRuns === 1 ? "" : "s"} available for analysis`
        : "Available after failed execution",
      state: selectedAppFailedRuns ? "attention" : "queued",
    },
  ];

  const applicationView = (
    <>
      <section className="panel projects-hero applications-page-hero">
        <div>
          <h1>Applications</h1>
        </div>
        <div className="projects-hero-actions">
          <span className="muted">{applicationRows.length} connected target{applicationRows.length === 1 ? "" : "s"}</span>
          <button className="secondary" onClick={() => void loadDashboardData(token, app?.name)} disabled={refreshingData}>
            {refreshingData ? "Refreshing..." : "Refresh inventory"}
          </button>
        </div>
      </section>
      <ApplicationCapture
        onSaved={(savedApplicationName) => {
          void loadDashboardData(token, savedApplicationName);
          notify(savedApplicationName ? `${savedApplicationName} saved` : "Application saved");
        }}
      />
      {selectedApplicationWorkspaceRow && (
        <section className="panel applications-focus-shell">
          <div className="applications-focus-head">
            <div>
              <h2>{selectedApplicationWorkspaceRow.name}</h2>
            </div>
            <div className="applications-focus-actions">
              <button className="secondary btn-sm" onClick={() => openApplicationWorkspace(selectedApplicationWorkspaceRow.name, "cases")}>
                Open test cases
              </button>
              <button className="secondary btn-sm" onClick={() => openApplicationWorkspace(selectedApplicationWorkspaceRow.name, "execution")}>
                Open execution
              </button>
              <button className="secondary btn-sm" onClick={() => openSystemMap(selectedApplicationWorkspaceRow.name)}>
                System &amp; Test Map
              </button>
              <button className="secondary btn-sm" onClick={() => openApplicationEditModal(selectedApplicationWorkspaceRow.name)}>
                Edit target
              </button>
              <button
                className="secondary btn-sm"
                onClick={() => {
                  void loadDashboardData(token, selectedApplicationWorkspaceRow.name);
                  if (typeof selectedApplicationWorkspaceRow.id === "number") {
                    void loadAutomationReadiness(token, selectedApplicationWorkspaceRow.id);
                  }
                  notify("Application workspace refreshed");
                }}
                disabled={refreshingData}
              >
                {refreshingData ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          <div className="applications-detail-tablist" role="tablist" aria-label="Application detail sections">
            <button
              id="application-detail-tab-overview"
              type="button"
              role="tab"
              aria-selected={applicationDetailTab === "overview"}
              aria-controls="application-detail-panel-overview"
              className={`applications-detail-tab ${applicationDetailTab === "overview" ? "active" : ""}`}
              onClick={() => setApplicationDetailTab("overview")}
            >
              Overview
            </button>
            <button
              id="application-detail-tab-discovery"
              type="button"
              role="tab"
              aria-selected={applicationDetailTab === "discovery"}
              aria-controls="application-detail-panel-discovery"
              className={`applications-detail-tab ${applicationDetailTab === "discovery" ? "active" : ""}`}
              onClick={() => setApplicationDetailTab("discovery")}
            >
              Discovery workflow
            </button>
          </div>
          {applicationDetailTab === "overview" && (
            <div
              className="applications-detail-panel"
              role="tabpanel"
              id="application-detail-panel-overview"
              aria-labelledby="application-detail-tab-overview"
            >
              <div className="applications-detail-grid">
                <article className="applications-detail-card">
                  <p>Platform</p>
                  <strong>{formatPlatformLabel(selectedApplicationWorkspaceRow.platform)}</strong>
                  <span>{selectedApplicationWorkspaceRow.type}</span>
                </article>
                <article className="applications-detail-card">
                  <p>Case coverage</p>
                  <strong>{selectedApplicationWorkspaceRow.totalCases}</strong>
                  <span>{selectedApplicationWorkspaceRow.readyCases} ready · {selectedApplicationWorkspaceRow.draftCases} draft</span>
                </article>
                <article className="applications-detail-card">
                  <p>Execution quality</p>
                  <strong>{selectedApplicationWorkspaceRow.totalRuns ? `${selectedApplicationWorkspaceRow.passRate}%` : "—"}</strong>
                  <span>{selectedApplicationWorkspaceRow.totalRuns} run{selectedApplicationWorkspaceRow.totalRuns === 1 ? "" : "s"}</span>
                </article>
                <article className="applications-detail-card">
                  <p>Automation readiness</p>
                  <strong>{selectedApplicationWorkspaceRow.automatedCases}/{selectedApplicationWorkspaceRow.totalCases || 0}</strong>
                  <span>{selectedApplicationWorkspaceRow.selectorReviewCases} need selector review</span>
                </article>
                <article className="applications-detail-card">
                  <p>Defects</p>
                  <strong>{selectedApplicationWorkspaceRow.openDefects}</strong>
                  <span>Open triage items</span>
                </article>
                <article className="applications-detail-card">
                  <p>Last run</p>
                  <strong>{selectedApplicationWorkspaceRow.lastRunAt ? formatTimestamp(selectedApplicationWorkspaceRow.lastRunAt) : "No runs yet"}</strong>
                  <span>{selectedApplicationWorkspaceRow.healthLabel} health state</span>
                </article>
              </div>
            </div>
          )}
          {applicationDetailTab === "discovery" && (
            <div
              className="applications-detail-panel"
              role="tabpanel"
              id="application-detail-panel-discovery"
              aria-labelledby="application-detail-tab-discovery"
            >
              <div className="applications-discovery-summary">
                <div>
                  <h3>{completedDiscoveryStages}/{selectedApplicationDiscoveryStages.length} stages complete</h3>
                </div>
                <span className="applications-discovery-percent">{discoveryProgressPercent}%</span>
              </div>
              <div className="applications-discovery-progress">
                <i style={{ width: `${discoveryProgressPercent}%` }} />
              </div>
              <ul className="applications-discovery-list">
                {selectedApplicationDiscoveryStages.map((stage) => (
                  <li key={`${selectedApplicationWorkspaceRow.name}-${stage.name}`}>
                    <div>
                      <strong>{stage.name}</strong>
                      <p>{stage.detail}</p>
                    </div>
                    {renderWorkflowStatusChip(stage.state)}
                  </li>
                ))}
              </ul>
              <div className="applications-discovery-actions">
                <button
                  className="secondary btn-sm"
                  onClick={() => { void createStarterCases(); }}
                  disabled={!app?.id || creatingStarterCases}
                >
                  {creatingStarterCases ? "Creating..." : "Create starter cases"}
                </button>
                <button className="secondary btn-sm" onClick={() => openSystemMap(selectedApplicationWorkspaceRow.name)}>
                  Traceability Map
                </button>
                <button className="primary btn-sm" onClick={() => openApplicationWorkspace(selectedApplicationWorkspaceRow.name, "execution")}>
                  Run discovery checks
                </button>
              </div>
            </div>
          )}
        </section>
      )}
      <section className="applications-kpi-grid">
        <InteractiveKpiCard
          className="applications-kpi-card"
          label="Connected applications"
          value={applicationRows.length}
          detail={`${webApplicationCount} web · ${mobileApplicationCount} mobile`}
          onClick={() => navigateToSection("applications")}
        />
        <InteractiveKpiCard
          className="applications-kpi-card"
          label="Coverage readiness"
          value={applicationsWithReadyCoverage}
          detail="Applications with ready test cases"
          onClick={() => navigateToSection("cases")}
        />
        <InteractiveKpiCard
          className="applications-kpi-card"
          label="Automation ready"
          value={applicationsWithAutomation}
          detail="Applications with compiled automation"
          onClick={() => navigateToSection("cases")}
        />
        <InteractiveKpiCard
          className="applications-kpi-card"
          label="Execution baseline"
          value={applicationsWithExecutionBaseline}
          detail="Applications with recorded runs"
          onClick={() => navigateToSection("execution")}
        />
        <InteractiveKpiCard
          className="applications-kpi-card"
          label="Critical health signals"
          value={criticalApplicationCount}
          detail={`${applicationAttentionRows.length} application${applicationAttentionRows.length === 1 ? "" : "s"} need setup or review`}
          onClick={() => navigateToSection("reports")}
        />
      </section>
      <section className="panel applications-attention-panel">
        <div className="applications-table-head">
          <div>
            <h2>Targets that need a next step</h2>
          </div>
          <span className="muted">{applicationAttentionRows.length ? `${applicationAttentionRows.length} priority target${applicationAttentionRows.length === 1 ? "" : "s"}` : "All targets have a baseline"}</span>
        </div>
        {applicationAttentionRows.length ? (
          <div className="applications-attention-grid">
            {applicationAttentionRows.map((row) => {
              const reason = row.totalCases === 0
                ? "No test cases yet"
                : row.selectorReviewCases > 0
                  ? `${row.selectorReviewCases} selector review${row.selectorReviewCases === 1 ? "" : "s"}`
                  : row.openDefects > 0
                    ? `${row.openDefects} open defect${row.openDefects === 1 ? "" : "s"}`
                    : row.healthLabel;
              return (
                <article className={`applications-attention-card tone-${row.healthBucket}`} key={`application-attention-${row.id}`}>
                  <div>
                    <strong>{row.name}</strong>
                    <span>{formatPlatformLabel(row.platform)} · {reason}</span>
                  </div>
                  <button type="button" className="secondary btn-sm" onClick={() => focusApplication(row.name)}>Open workspace</button>
                </article>
              );
            })}
          </div>
        ) : <EmptyState message="No application setup or automation issues need attention right now." />}
      </section>
      <div className="v3-chart-grid applications-chart-grid">
        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Coverage spread" title="Cases per application" />
          <DistributionBars items={appCaseDistribution} />
        </AppCard>
        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Execution quality" title="Pass rate per application" />
          <DistributionBars items={appPassRateDistribution} percent />
        </AppCard>
      </div>
      <section className="panel applications-table-shell workspace-table-surface">
        <div className="applications-table-head">
          <div>
            <h2>Manage connected targets</h2>
          </div>
          <span className="muted">{filteredApplicationRows.length} of {applicationRows.length} shown</span>
        </div>
        <div className="applications-filter-grid">
          <label className="applications-filter-field" htmlFor="application-search">
            <span>Search</span>
            <input
              id="application-search"
              type="search"
              value={applicationSearch}
              onChange={(event) => setApplicationSearch(event.target.value)}
              placeholder="Search by application, platform, or URL"
            />
          </label>
          <label className="applications-filter-field" htmlFor="application-platform-filter">
            <span>Platform</span>
            <select
              id="application-platform-filter"
              value={applicationPlatformFilter}
              onChange={(event) => setApplicationPlatformFilter(event.target.value as "all" | Platform)}
            >
              <option value="all">All platforms</option>
              <option value="web">Web</option>
              <option value="android">Android</option>
              <option value="ios">iOS</option>
            </select>
          </label>
          <label className="applications-filter-field" htmlFor="application-health-filter">
            <span>Health</span>
            <select
              id="application-health-filter"
              value={applicationHealthFilter}
              onChange={(event) => setApplicationHealthFilter(event.target.value as "all" | ProjectHealthBucket)}
            >
              <option value="all">All health states</option>
              <option value="healthy">Healthy</option>
              <option value="watch">Watch</option>
              <option value="critical">Critical</option>
              <option value="noData">No data</option>
            </select>
          </label>
          <label className="applications-filter-field" htmlFor="application-sort-by">
            <span>Sort by</span>
            <select
              id="application-sort-by"
              value={applicationSortBy}
              onChange={(event) => setApplicationSortBy(event.target.value as "name" | "cases" | "runs" | "passRate")}
            >
              <option value="name">Application name</option>
              <option value="cases">Test cases</option>
              <option value="runs">Execution runs</option>
              <option value="passRate">Pass rate</option>
            </select>
          </label>
        </div>
        <div className="table-scroll">
          <table className="applications-table">
            <thead>
              <tr>
                <th>Application</th>
                <th>Platform</th>
                <th>Target</th>
                <th>Test cases</th>
                <th>Runs</th>
                <th>Pass rate</th>
                <th>Automation</th>
                <th>Open defects</th>
                <th>Health</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredApplicationRows.length ? filteredApplicationRows.map((row) => {
                const passRateTone = row.completedRuns === 0 ? "neutral" : row.passRate >= 85 ? "success" : row.passRate >= 60 ? "warning" : "danger";
                const isSelectedRow = selectedApplicationWorkspaceRow?.name === row.name;
                return (
                  <tr key={`application-row-${row.id}`} className={isSelectedRow ? "applications-row-selected" : undefined}>
                    <td>
                      <div className="applications-name-cell">
                        <strong>{row.name}</strong>
                        <p>{row.type}</p>
                      </div>
                    </td>
                    <td>{formatPlatformLabel(row.platform)}</td>
                    <td><span className="applications-target-cell">{row.url}</span></td>
                    <td>
                      <div className="applications-metric-cell">
                        <strong>{row.totalCases}</strong>
                        <small>{row.readyCases} ready · {row.draftCases} draft</small>
                      </div>
                    </td>
                    <td>
                      <div className="applications-metric-cell">
                        <strong>{row.totalRuns}</strong>
                        <small>{row.completedRuns} completed</small>
                      </div>
                    </td>
                    <td>
                      <span className={`applications-pass-rate tone-${passRateTone}`}>
                        {row.completedRuns ? `${row.passRate}%` : "—"}
                      </span>
                    </td>
                    <td>
                      <div className="applications-metric-cell">
                        <strong>{row.automatedCases}/{row.totalCases || 0}</strong>
                        <small>{row.selectorReviewCases ? `${row.selectorReviewCases} selector review${row.selectorReviewCases === 1 ? "" : "s"}` : "No selector reviews"}</small>
                      </div>
                    </td>
                    <td>{row.openDefects}</td>
                    <td>
                      <div className="applications-health-cell">
                        <span className={`projects-health-badge tone-${row.healthBucket}`}>{row.healthLabel}</span>
                        <small>{row.lastRunAt ? `Last run ${formatTimestamp(row.lastRunAt)}` : "No runs yet"}</small>
                      </div>
                    </td>
                    <td>
                      <div className="applications-row-actions">
                        <button
                          className="secondary btn-sm"
                          onClick={() => {
                            focusApplication(row.name);
                            notify(`${row.name} selected`);
                          }}
                        >
                          Workspace
                        </button>
                        <button className="secondary btn-sm" onClick={() => openApplicationWorkspace(row.name, "cases")}>
                          Cases
                        </button>
                        <button className="secondary btn-sm" onClick={() => openApplicationWorkspace(row.name, "execution")}>
                          Run
                        </button>
                        <button className="secondary btn-sm" onClick={() => openSystemMap(row.name)} title="Interactive System & Test Traceability Map">
                          Map
                        </button>
                        <button
                          className="secondary btn-sm"
                          onClick={() => openApplicationEditModal(row.name)}
                          disabled={typeof row.id !== "number"}
                        >
                          Edit
                        </button>
                        <button
                          className="secondary btn-sm"
                          onClick={() => void deleteApplication(typeof row.id === "number" ? row.id : undefined, row.name)}
                          disabled={typeof row.id !== "number"}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={10}>
                    <div className="applications-empty-state">
                      <strong>No applications match these filters</strong>
                      <p>Adjust search or filters to find a target application.</p>
                      <button
                        className="secondary btn-sm"
                        onClick={() => {
                          setApplicationSearch("");
                          setApplicationPlatformFilter("all");
                          setApplicationHealthFilter("all");
                          setApplicationSortBy("name");
                        }}
                      >
                        Reset filters
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );

  const testRepositoryControls = (
      <div className="case-top">
        <div className="panel selected-app">
          <span className="app-mark">{app?.name?.[0] ?? "S"}</span>
          <div>
            <h2>{app?.name ?? "No app"}</h2>
            <span>{app?.type ?? "No target"} · {app?.url ?? ""}</span>
          </div>
        </div>
        <div className="panel run-control">
          <label htmlFor="case-application">Application</label>
          <select id="case-application" value={app?.name ?? ""} onChange={(event) => selectApplication(event.target.value)} disabled={!hasApplications}>
            {apps.length ? apps.map((item) => (
              <option key={`case-app-${item.id ?? item.name}`} value={item.name}>{item.name}</option>
            )) : <option value="" disabled>No applications available</option>}
          </select>
          <button className="secondary" onClick={() => void loadDashboardData(token, app?.name)} disabled={refreshingData || !hasApplications}>
            {refreshingData ? "Refreshing..." : "Refresh cases"}
          </button>
        </div>
        <div className="panel upload-box">
          <div>
            <strong>Upload or enter test scenarios</strong>
            <span>CSV, Excel, Text, Markdown, or JSON</span>
          </div>
          <input
            ref={importInputRef}
            hidden
            type="file"
            accept=".csv,.xlsx,.xls,.txt,.md,.json,.text"
            onChange={(event) => void importTestCases(event.target.files?.[0])}
            disabled={!hasApplications || importingCases || clearingDrafts}
          />
          <div className="upload-actions">
            <button
              type="button"
              className="primary"
              onClick={openCreateTestCaseEditor}
              disabled={!hasSelectedApplication || importingCases || clearingDrafts}
              title="Manually create a new structured test case"
            >
              + Create Test Case
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                if (!hasApplications) {
                  notify("Add an application before entering test cases");
                  navigateToSection("applications");
                  return;
                }
                setTextIngestModalOpen(true);
              }}
              disabled={importingCases || clearingDrafts}
              title="Enter raw text, user stories, Markdown tables, or requirements to generate test cases"
            >
              AI Scenario Ingest
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                if (!hasApplications) {
                  notify("Add an application before uploading test cases");
                  navigateToSection("applications");
                  return;
                }
                openImportPicker();
              }}
              disabled={importingCases || clearingDrafts}
            >
              {!hasApplications ? "Add application first" : importingCases ? "Importing..." : "Upload File"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void downloadProgress()}
              disabled={!hasSelectedApplication || downloadingProgress}
            >
              {downloadingProgress ? "Downloading..." : "Export CSV"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void handleExportPlaywrightSuite(app?.id)}
              disabled={!hasSelectedApplication || fetchingPlaywrightSuite}
              title="Export all test cases as compiled TypeScript Playwright test suite (.ts)"
              style={{ color: "var(--brand-primary, #b5121b)", fontWeight: 700 }}
            >
              {fetchingPlaywrightSuite ? "Generating Suite..." : "💻 Playwright Suite"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => openScriptStudio({
                applicationId: app?.id,
                applicationName: app?.name,
                initialMode: "suite",
              })}
              disabled={!hasSelectedApplication}
              title="Enterprise Script Studio: Export suite in Playwright, Cypress, Selenium, Robot, Java, Puppeteer & Push to GitHub"
              style={{ color: "#1f3a5f", fontWeight: 700 }}
            >
              ⚡ Script Studio
            </button>
            <button
              type="button"
              className="secondary btn-danger"
              onClick={() => void clearDraftCases()}
              disabled={!hasSelectedApplication || selectedCases.length === 0 || clearingDrafts}
              title={selectedDraftCount > 0 ? `Remove ${selectedDraftCount} draft test cases` : "Clear test cases for selected application"}
            >
              {clearingDrafts ? "Clearing..." : selectedDraftCount > 0 ? `Clear Drafts (${selectedDraftCount})` : "Clear Drafts"}
            </button>
            <button
              type="button"
              className="secondary btn-danger"
              onClick={() => void clearAllApplicationCases()}
              disabled={!hasSelectedApplication || selectedCases.length === 0 || clearingDrafts}
              title="Delete all test cases for selected application"
            >
              Clear All
            </button>
          </div>
        </div>
      </div>
  );

  const activeCaseLibraryFilterCount = (executionLibrarySearch.trim() ? 1 : 0) + (executionLibraryStatusFilter !== "all" ? 1 : 0) + (executionLibrarySortBy !== "id" ? 1 : 0);
  const totalCaseCount = selectedCases.length;
  const readyCaseCount = selectedCases.filter((c) => !isDraftStatus(c.status)).length;
  const draftCaseCount = selectedCases.filter((c) => isDraftStatus(c.status)).length;

  const testRepositoryWorkspace = (
    <>
      <div className="panel execution-library-view-options" aria-label="Test case table view options" style={{ padding: "8px 12px", marginBottom: "8px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "4px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <label className="capture-label flow-toggle" style={{ margin: 0, display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "12px", fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={selectedCases.length > 0 && selectedCases.every((caseItem) => executionSelectedCaseIds.includes(caseItem.id))}
                onChange={(event) => setExecutionSelectedCaseIds(event.target.checked ? selectedCases.map((caseItem) => caseItem.id) : [])}
                disabled={!selectedCases.length || running || deletingTestCaseIds.length > 0}
              />
              Select all visible
            </label>
            <span className="muted" style={{ fontSize: "11px", fontWeight: 600 }}>({executionSelectedCaseIds.length} selected)</span>
            <div className="filter-presets-bar" style={{ margin: 0, padding: 0, border: "none" }}>
              <span className="muted" style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase" }}>Presets:</span>
              <button
                type="button"
                className={`filter-preset-chip ${executionLibraryStatusFilter === "all" ? "active" : ""}`}
                onClick={() => setExecutionLibraryStatusFilter("all")}
              >
                All Cases ({totalCaseCount})
              </button>
              <button
                type="button"
                className={`filter-preset-chip ${executionLibraryStatusFilter === "ready" ? "active" : ""}`}
                onClick={() => setExecutionLibraryStatusFilter("ready")}
              >
                Ready Only ({readyCaseCount})
              </button>
              <button
                type="button"
                className={`filter-preset-chip ${executionLibraryStatusFilter === "draft" ? "active" : ""}`}
                onClick={() => setExecutionLibraryStatusFilter("draft")}
              >
                Draft Only ({draftCaseCount})
              </button>
            </div>
          </div>

          <button
            type="button"
            className="secondary btn-sm filter-toggle-btn"
            onClick={() => setShowCaseLibraryFilters((prev) => !prev)}
            title={showCaseLibraryFilters ? "Hide filter controls" : "Show filter controls"}
          >
            {showCaseLibraryFilters ? "👁 Hide Filters" : "🔍 Show Filters"}
            {activeCaseLibraryFilterCount > 0 && !showCaseLibraryFilters && (
              <span className="filter-badge-counter">{activeCaseLibraryFilterCount}</span>
            )}
          </button>
        </div>

        {showCaseLibraryFilters && (
          <div className="execution-library-view-grid" style={{ marginTop: "8px" }}>
            <label className="capture-label">
              Search cases
              <input type="search" value={executionLibrarySearch} onChange={(event) => setExecutionLibrarySearch(event.target.value)} placeholder="Title, steps, expected result" />
            </label>
            <label className="capture-label">
              Status
              <select value={executionLibraryStatusFilter} onChange={(event) => setExecutionLibraryStatusFilter(event.target.value as "all" | "draft" | "ready")}>
                <option value="all">All statuses</option>
                <option value="draft">Draft</option>
                <option value="ready">Ready</option>
              </select>
            </label>
            <label className="capture-label">
              Sort by
              <select value={executionLibrarySortBy} onChange={(event) => setExecutionLibrarySortBy(event.target.value as "id" | "name" | "status" | "updated")}>
                <option value="id">Case number</option>
                <option value="name">Title</option>
                <option value="status">Status</option>
                <option value="updated">Recently updated</option>
              </select>
            </label>
            <label className="capture-label">
              Rows per page
              <select value={String(executionLibraryPageSize)} onChange={(event) => setExecutionLibraryPageSize(Number(event.target.value))}>
                {[10, 25, 50].map((size) => <option key={`execution-library-size-${size}`} value={size}>{size}</option>)}
              </select>
            </label>
          </div>
        )}

        {/* Active Filter Tags */}
        {activeCaseLibraryFilterCount > 0 && (
          <div className="active-filter-tags">
            <span className="muted" style={{ fontSize: "11px", fontWeight: 700 }}>Active ({activeCaseLibraryFilterCount}):</span>
            {executionLibrarySearch && (
              <span className="active-filter-tag">
                "{executionLibrarySearch}"
                <button type="button" onClick={() => setExecutionLibrarySearch("")} aria-label="Clear search">✕</button>
              </span>
            )}
            {executionLibraryStatusFilter !== "all" && (
              <span className="active-filter-tag">
                Status: {executionLibraryStatusFilter}
                <button type="button" onClick={() => setExecutionLibraryStatusFilter("all")} aria-label="Clear status">✕</button>
              </span>
            )}
            {executionLibrarySortBy !== "id" && (
              <span className="active-filter-tag">
                Sort: {executionLibrarySortBy}
                <button type="button" onClick={() => setExecutionLibrarySortBy("id")} aria-label="Reset sort">✕</button>
              </span>
            )}
            <button
              type="button"
              className="table-action"
              onClick={() => { setExecutionLibrarySearch(""); setExecutionLibraryStatusFilter("all"); setExecutionLibrarySortBy("id"); }}
              style={{ fontSize: "11px" }}
            >
              Reset view
            </button>
          </div>
        )}
      </div>

      {executionSelectedCaseIds.length > 0 && (
        <div className="batch-actions-bar" role="region" aria-label="Bulk actions toolbar">
          <div className="batch-actions-info">
            <span className="batch-count-badge">{executionSelectedCaseIds.length}</span>
            <strong>Selected Test Cases</strong>
          </div>
          <div className="batch-actions-buttons">
            <button
              type="button"
              className="primary btn-sm"
              onClick={() => {
                navigateToSection("execution");
                void runApplicationCaseTests(executionSelectedCaseIds);
              }}
              disabled={running}
            >
              Run Selected ({executionSelectedCaseIds.length})
            </button>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={() => void handleBulkApproveSelectedCases()}
              disabled={running}
              title="Approve selected draft cases to ready"
            >
              Approve Drafts
            </button>
            <button
              type="button"
              className="secondary btn-sm btn-danger"
              onClick={() => void handleDeleteSelectedTestCases()}
              disabled={running || deletingTestCaseIds.length > 0}
            >
              Delete Selected
            </button>
            <button
              type="button"
              className="secondary btn-sm"
              onClick={() => setExecutionSelectedCaseIds([])}
            >
              Clear Selection
            </button>
          </div>
        </div>
      )}

      <Table title="Test case library" meta={`${executionLibraryFilteredCases.length} matching · page ${executionLibraryCurrentPage}/${executionLibraryTotalPages}`}>
        <table className="run-history-table execution-case-table" style={{ minWidth: "1280px", tableLayout: "fixed", width: "100%" }}>
          <thead>
            <tr>
              <th scope="col" style={{ width: "80px", minWidth: "80px", whiteSpace: "nowrap" }}>Select</th>
              <th scope="col" style={{ width: "95px", minWidth: "95px", whiteSpace: "nowrap" }}>Case ID</th>
              <th scope="col" style={{ minWidth: "280px" }}>Test Case &amp; Summary</th>
              <th scope="col" style={{ width: "160px", minWidth: "160px" }}>Preconditions</th>
              <th scope="col" style={{ minWidth: "240px" }}>Steps Preview</th>
              <th scope="col" style={{ minWidth: "180px" }}>Expected Result</th>
              <th scope="col" style={{ width: "130px", minWidth: "130px", whiteSpace: "nowrap" }}>Status</th>
              <th scope="col" style={{ width: "260px", minWidth: "260px", whiteSpace: "nowrap" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {executionLibraryPageCases.length ? executionLibraryPageCases.map((caseItem) => {
              const isSelected = executionSelectedCaseIdSet.has(caseItem.id);
              const parsedStepList = parseTestSteps(caseItem.steps || "");
              const readiness = automationReadinessByCaseId[caseItem.id];

              return (
                <tr key={`execution-case-row-${caseItem.id}`} className={isSelected ? "row-selected" : ""}>
                  {/* Select Checkbox */}
                  <td style={{ whiteSpace: "nowrap" }}>
                    <label className="execution-case-select" title="Include this case in selection">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(event) => {
                          const isChecked = event.target.checked;
                          setExecutionSelectedCaseIds((current) =>
                            isChecked
                              ? current.includes(caseItem.id) ? current : [...current, caseItem.id]
                              : current.filter((caseId) => caseId !== caseItem.id)
                          );
                        }}
                        disabled={running || deletingTestCaseIds.length > 0}
                        aria-label={`Select ${caseItem.title} for execution`}
                      />
                    </label>
                  </td>

                  {/* ID */}
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      type="button"
                      className="table-link defect-id-link"
                      onClick={() => openTestCaseViewer(caseItem)}
                      title="View test case details"
                    >
                      TC-{caseItem.id}
                    </button>
                  </td>

                  {/* Title & Category */}
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                        <strong style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>
                          {caseItem.title}
                        </strong>
                        {caseItem.category && (
                          <span className="badge badge-secondary" style={{ fontSize: "10px", padding: "1px 6px" }}>
                            {caseItem.category}
                          </span>
                        )}
                        {caseItem.priority && (
                          <span className={`priority ${caseItem.priority.toLowerCase()}`} style={{ fontSize: "10px", padding: "1px 6px" }}>
                            {caseItem.priority}
                          </span>
                        )}
                      </div>
                      {caseItem.description ? (
                        <small
                          className="muted"
                          style={{
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                            lineHeight: 1.35,
                          }}
                        >
                          {caseItem.description}
                        </small>
                      ) : null}
                    </div>
                  </td>

                  {/* Preconditions */}
                  <td>
                    <span className="muted" style={{ fontSize: "12px", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                      {caseItem.preconditions ? caseItem.preconditions : "—"}
                    </span>
                  </td>

                  {/* Steps Preview */}
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span className="badge badge-secondary" style={{ width: "fit-content", fontSize: "11px", fontWeight: 700 }}>
                        {parsedStepList.length} step{parsedStepList.length === 1 ? "" : "s"}
                      </span>
                      <small
                        className="muted"
                        style={{
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          lineHeight: 1.35,
                          fontSize: "12px",
                        }}
                      >
                        {parsedStepList.slice(0, 2).map((s: string, idx: number) => `${idx + 1}. ${s}`).join("  |  ") || "No steps defined"}
                      </small>
                    </div>
                  </td>

                  {/* Expected Result */}
                  <td>
                    <small
                      className="muted"
                      style={{
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        lineHeight: 1.35,
                        fontSize: "12px",
                      }}
                    >
                      {caseItem.expected_result || "—"}
                    </small>
                  </td>

                  {/* Status & Readiness */}
                  <td style={{ whiteSpace: "nowrap" }}>
                    <div className="status-cell-stack">
                      {renderStatusChip(caseItem.status)}
                      {readiness && (
                        <>
                          <span className={`automation-chip confidence-${readiness.confidence_label}`}>
                            {formatConfidenceChipLabel(readiness.confidence_score, readiness.confidence_label)}
                          </span>
                          {readiness.needs_manual_selector_review && (
                            <button
                              type="button"
                              className="automation-chip review-chip"
                              onClick={() => openTestCaseEditor(caseItem)}
                              title="Edit this test case and review its selectors"
                              aria-label={`Review selectors for ${caseItem.title}`}
                            >
                              Review selectors
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>

                  {/* Actions Toolbar */}
                  <td style={{ whiteSpace: "nowrap" }}>
                    <div className="row-actions-group" style={{ display: "flex", gap: "4px", flexWrap: "wrap", whiteSpace: "nowrap" }}>
                      <button
                        type="button"
                        onClick={() => openTestCaseViewer(caseItem)}
                        className="row-action-btn"
                        title="View test case details"
                      >
                        View
                      </button>
                      <button
                        type="button"
                        onClick={() => prepareTestCaseRun(caseItem.id)}
                        className="row-action-btn run"
                        title="Review settings and run this test case"
                      >
                        Run
                      </button>
                      <button
                        type="button"
                        onClick={() => openTestCaseEditor(caseItem)}
                        className="row-action-btn"
                        title="Edit test case"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleViewPlaywrightSpec(caseItem.id)}
                        className="row-action-btn"
                        title="View & export TypeScript Playwright spec"
                        style={{ color: "var(--brand-primary, #b5121b)", fontWeight: 700 }}
                      >
                        💻 Spec
                      </button>
                      <button
                        type="button"
                        onClick={() => openScriptStudio({
                          testCaseId: caseItem.id,
                          testCaseTitle: caseItem.title,
                          applicationId: selectedAppId,
                          applicationName: app?.name,
                          initialMode: "single",
                        })}
                        className="row-action-btn"
                        title="Enterprise Script Studio (Playwright, Cypress, Selenium, Robot, Java, Puppeteer & GitHub)"
                        style={{ color: "#1f3a5f", fontWeight: 700 }}
                      >
                        ⚡ Scripts
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleCloneTestCase(caseItem.id)}
                        className="row-action-btn"
                        title="Clone test case"
                      >
                        Clone
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteTestCase(caseItem.id, caseItem.title)}
                        className="row-action-btn danger"
                        title="Delete test case"
                        disabled={running || deletingTestCaseIds.includes(caseItem.id)}
                      >
                        {deletingTestCaseIds.includes(caseItem.id) ? "..." : "Delete"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={8} className="muted" style={{ textAlign: "center", padding: "24px" }}>No test cases exist for this application. Import a CSV/XLSX file or generate cases with AI to begin.</td></tr>}
          </tbody>
        </table>
      </Table>
      {executionLibraryTotalPages > 1 ? (
        <div className="execution-library-pagination" aria-label="Test case library pagination">
          <span>Page {executionLibraryCurrentPage} of {executionLibraryTotalPages}</span>
          <div>
            <button type="button" className="secondary btn-sm" onClick={() => setExecutionLibraryPage((current) => Math.max(1, current - 1))} disabled={executionLibraryCurrentPage === 1}>Previous</button>
            {Array.from({ length: Math.min(5, executionLibraryTotalPages) }, (_, index) => {
              const pageNumber = executionLibraryTotalPages <= 5
                ? index + 1
                : Math.min(Math.max(executionLibraryCurrentPage - 2 + index, 1), executionLibraryTotalPages - 4 + index);
              return <button type="button" className={`execution-library-page ${pageNumber === executionLibraryCurrentPage ? "active" : ""}`} key={`execution-library-page-${pageNumber}`} onClick={() => setExecutionLibraryPage(pageNumber)}>{pageNumber}</button>;
            })}
            <button type="button" className="secondary btn-sm" onClick={() => setExecutionLibraryPage((current) => Math.min(executionLibraryTotalPages, current + 1))} disabled={executionLibraryCurrentPage === executionLibraryTotalPages}>Next</button>
          </div>
        </div>
      ) : null}

      {textIngestModalOpen && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && !textIngestContent.trim()) {
              setTextIngestModalOpen(false);
            }
          }}
        >
          <div
            className="panel projects-modal"
            style={{ maxWidth: "760px", width: "95%" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="text-ingest-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="projects-modal-head">
              <div>
                <h3 id="text-ingest-modal-title">Enter Scenarios, User Stories, or Requirements · {app?.name}</h3>
              </div>
              <button type="button" className="secondary btn-sm" onClick={() => setTextIngestModalOpen(false)} aria-label="Close modal">Close</button>
            </div>
            <p className="muted">
              Paste raw text requirements, user stories, numbered steps, Markdown scenario tables, or OpenAPI/database schemas. Choose to compile with AI or ingest directly into the {app?.name} repository.
            </p>

            <div className="projects-modal-form" style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div>
                <label style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>Format / Specification Type</label>
                <select
                  value={textIngestFormat}
                  onChange={(e) => setTextIngestFormat(e.target.value as any)}
                  className="settings-select"
                >
                  <option value="text">Plain Text / User Story / Numbered Steps</option>
                  <option value="markdown_table">Markdown Scenario Table (| Step | Action | Expected |)</option>
                  <option value="csv">CSV / TSV Text Matrix</option>
                  <option value="json">JSON Scenario Array</option>
                  <option value="openapi">OpenAPI / Swagger REST Spec</option>
                  <option value="db_schema">Database Schema (DDL / Tables)</option>
                </select>
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
                  Input Text / Requirements / Test Steps <span aria-hidden="true">*</span>
                </label>
                <textarea
                  value={textIngestContent}
                  onChange={(e) => setTextIngestContent(e.target.value)}
                  rows={9}
                  placeholder={`Example (Numbered Steps):
1. Navigate to https://your-app.example.com/sign-in and log in
2. Open the account search page
3. Enter a test value in the search field
4. Submit the search
Expected Result: Matching records are listed

Example (Markdown Table):
| Step | Action | Expected Result |
| 1 | Navigate to the application and sign in | Home page loads |
| 2 | Search for a test value | Matching records displayed |`}
                  style={{ width: "100%", fontFamily: "var(--font-code)", fontSize: "12px", padding: "10px", lineHeight: "1.5" }}
                />
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
                  Preconditions (Optional)
                </label>
                <input
                  type="text"
                  value={textIngestPreconditions}
                  onChange={(e) => setTextIngestPreconditions(e.target.value)}
                  placeholder="Example: User is on the search page"
                  className="settings-input"
                />
              </div>

              <div className="projects-modal-actions" style={{ display: "flex", gap: "10px", justifyContent: "flex-end", flexWrap: "wrap", marginTop: "12px" }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setTextIngestModalOpen(false)}
                  disabled={textIngestLoading}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void handleIngestText(false)}
                  disabled={textIngestLoading || !textIngestContent.trim()}
                  title="Directly parse and compile test steps into repository"
                >
                  {textIngestLoading ? "Ingesting..." : "Direct Quick Ingest"}
                </button>
                <button
                  type="button"
                  className="btn btn-primary primary"
                  onClick={() => void handleIngestText(true)}
                  disabled={textIngestLoading || !textIngestContent.trim()}
                  title="Synthesize and generate full test matrix with AI"
                >
                  {textIngestLoading ? "Generating with AI..." : "Generate with AI & Ingest"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Playwright Spec Preview & Export Modal */}
      {activePlaywrightSpecModal && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && !pushingToGit) setActivePlaywrightSpecModal(null);
          }}
        >
          <div
            className="panel projects-modal"
            style={{ maxWidth: "880px", width: "95%", maxHeight: "90vh", overflowY: "auto" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="spec-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="projects-modal-head">
              <div>
                <h3 id="spec-modal-title">TypeScript Playwright Spec · {activePlaywrightSpecModal.filename}</h3>
                <span className="muted">{activePlaywrightSpecModal.title}</span>
              </div>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => setActivePlaywrightSpecModal(null)}
                disabled={pushingToGit}
                aria-label="Close spec modal"
              >
                ✕ Close
              </button>
            </div>

            <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                <span className="muted" style={{ fontSize: "12px" }}>
                  Executable Playwright test code compiled from verified steps, assertions, and parameterized locators.
                </span>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    type="button"
                    className="secondary btn-sm"
                    onClick={() => {
                      void navigator.clipboard.writeText(activePlaywrightSpecModal.code);
                      notify("Playwright spec copied to clipboard!");
                    }}
                  >
                    📋 Copy Code
                  </button>
                  <button
                    type="button"
                    className="secondary btn-sm"
                    onClick={() => {
                      const blob = new Blob([activePlaywrightSpecModal.code], { type: "text/typescript;charset=utf-8" });
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = activePlaywrightSpecModal.filename;
                      link.click();
                      URL.revokeObjectURL(url);
                      notify(`Downloaded ${activePlaywrightSpecModal.filename}`);
                    }}
                  >
                    💾 Download .spec.ts
                  </button>
                  <button
                    type="button"
                    className="primary btn-sm"
                    onClick={() => void handlePushPlaywrightSpecToGit(activePlaywrightSpecModal.id)}
                    disabled={pushingToGit}
                  >
                    {pushingToGit ? "Pushing..." : "🚀 Save to tests/generated/"}
                  </button>
                </div>
              </div>

              {gitPushMessage && (
                <div style={{ padding: "8px 12px", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.3)", borderRadius: "var(--radius-sm, 6px)", fontSize: "12px" }}>
                  {gitPushMessage}
                </div>
              )}

              <pre
                style={{
                  padding: "16px",
                  background: "#0f172a",
                  color: "#f8fafc",
                  borderRadius: "var(--radius-md, 8px)",
                  fontSize: "12px",
                  lineHeight: 1.5,
                  overflowX: "auto",
                  maxHeight: "480px",
                  fontFamily: "var(--font-code, monospace)",
                }}
              >
                <code>{activePlaywrightSpecModal.code}</code>
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Playwright Test Suite Modal */}
      {activePlaywrightSuiteModal && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setActivePlaywrightSuiteModal(null);
          }}
        >
          <div
            className="panel projects-modal"
            style={{ maxWidth: "980px", width: "95%", maxHeight: "90vh", overflowY: "auto" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="suite-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="projects-modal-head">
              <div>
                <h3 id="suite-modal-title">
                  TypeScript Playwright Suite · {activePlaywrightSuiteModal.application_name}
                </h3>
                <span className="muted">
                  {activePlaywrightSuiteModal.total_specs} compiled test spec{activePlaywrightSuiteModal.total_specs === 1 ? "" : "s"} ready for execution
                </span>
              </div>
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => setActivePlaywrightSuiteModal(null)}
                aria-label="Close suite modal"
              >
                ✕ Close
              </button>
            </div>

            <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {/* Spec selector tabs */}
              <div
                style={{
                  display: "flex",
                  gap: "6px",
                  overflowX: "auto",
                  paddingBottom: "6px",
                  borderBottom: "1px solid rgba(63, 63, 70, 0.4)",
                }}
              >
                {activePlaywrightSuiteModal.specs.map((spec, idx) => (
                  <button
                    key={`spec-tab-${spec.test_case_id}`}
                    type="button"
                    onClick={() => setSelectedSuiteSpecIndex(idx)}
                    className={selectedSuiteSpecIndex === idx ? "primary btn-sm" : "secondary btn-sm"}
                    style={{
                      whiteSpace: "nowrap",
                      fontSize: "11px",
                      fontFamily: "monospace",
                    }}
                  >
                    {spec.filename}
                  </button>
                ))}
              </div>

              {activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex] && (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                    <div>
                      <strong style={{ fontSize: "14px" }}>
                        {activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex].title}
                      </strong>
                      <span className="muted" style={{ fontSize: "12px", marginLeft: "8px" }}>
                        (TC-{activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex].test_case_id})
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        type="button"
                        className="secondary btn-sm"
                        onClick={() => {
                          const currentCode = activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex].code;
                          void navigator.clipboard.writeText(currentCode);
                          notify("Active spec copied to clipboard!");
                        }}
                      >
                        📋 Copy Spec
                      </button>
                      <button
                        type="button"
                        className="secondary btn-sm"
                        onClick={() => {
                          const allCode = activePlaywrightSuiteModal.specs
                            .map((s) => `// ==========================================\n// File: ${s.filename} - ${s.title}\n// ==========================================\n\n${s.code}`)
                            .join("\n\n");
                          void navigator.clipboard.writeText(allCode);
                          notify("Entire suite copied to clipboard!");
                        }}
                      >
                        📦 Copy All ({activePlaywrightSuiteModal.total_specs})
                      </button>
                      <button
                        type="button"
                        className="secondary btn-sm"
                        onClick={() => {
                          const currentSpec = activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex];
                          const blob = new Blob([currentSpec.code], { type: "text/typescript;charset=utf-8" });
                          const url = URL.createObjectURL(blob);
                          const link = document.createElement("a");
                          link.href = url;
                          link.download = currentSpec.filename;
                          link.click();
                          URL.revokeObjectURL(url);
                          notify(`Downloaded ${currentSpec.filename}`);
                        }}
                      >
                        💾 Download .spec.ts
                      </button>
                    </div>
                  </div>

                  <pre
                    style={{
                      padding: "16px",
                      background: "#0f172a",
                      color: "#f8fafc",
                      borderRadius: "var(--radius-md, 8px)",
                      fontSize: "12px",
                      lineHeight: 1.5,
                      overflowX: "auto",
                      maxHeight: "440px",
                      fontFamily: "var(--font-code, monospace)",
                    }}
                  >
                    <code>{activePlaywrightSuiteModal.specs[selectedSuiteSpecIndex].code}</code>
                  </pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Enterprise Multi-Framework Script Studio Modal */}
      {scriptStudioOpen && (
        <ScriptStudio
          isOpen={scriptStudioOpen}
          onClose={() => setScriptStudioOpen(false)}
          token={token}
          testCaseId={scriptStudioTestCaseId}
          testCaseTitle={scriptStudioTestCaseTitle}
          applicationId={scriptStudioApplicationId}
          applicationName={scriptStudioApplicationName}
          onNotify={notify}
          initialFramework={scriptStudioFramework}
          initialMode={scriptStudioMode}
        />
      )}

      {testCaseEditorMode !== null && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && (testCaseEditorMode === "view" || (!testCaseFormTitle.trim() && !testCaseFormSteps.trim()))) {
              closeTestCaseEditor();
            }
          }}
        >
          <div
            className="panel projects-modal test-case-edit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-case-edit-title"
            onClick={(event) => event.stopPropagation()}
          >
            {testCaseEditorMode === "view" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div className="test-case-inspector-header">
                  <div className="test-case-inspector-title-row">
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                      <span
                        style={{
                          background: "#e0f2fe",
                          color: "#0369a1",
                          fontWeight: 800,
                          fontSize: "12px",
                          padding: "3px 8px",
                          borderRadius: "6px",
                          fontFamily: "var(--font-code, monospace)",
                        }}
                      >
                        TC-{testCaseEditingId ?? "ID"}
                      </span>
                      <h3 id="test-case-edit-title" style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "#0f172a" }}>
                        {testCaseFormTitle}
                      </h3>
                    </div>
                    <button type="button" className="secondary btn-sm" onClick={closeTestCaseEditor}>
                      Close
                    </button>
                  </div>

                  <div className="test-case-inspector-badges">
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        padding: "2px 8px",
                        borderRadius: "999px",
                        background: testCaseFormStatus === "ready" ? "#dcfce7" : testCaseFormStatus === "rejected" ? "#fee2e2" : "#f1f5f9",
                        color: testCaseFormStatus === "ready" ? "#15803d" : testCaseFormStatus === "rejected" ? "#b91c1c" : "#475569",
                      }}
                    >
                      ● {testCaseFormStatus.toUpperCase()}
                    </span>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: "6px",
                        background: testCaseFormPriority === "critical" ? "#fee2e2" : testCaseFormPriority === "high" ? "#ffedd5" : "#f1f5f9",
                        color: testCaseFormPriority === "critical" ? "#b91c1c" : testCaseFormPriority === "high" ? "#c2410c" : "#475569",
                      }}
                    >
                      Priority: {testCaseFormPriority}
                    </span>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: "6px",
                        background: "#f3e8ff",
                        color: "#7e22ce",
                      }}
                    >
                      Category: {testCaseFormCategory}
                    </span>
                    {app?.name && (
                      <span className="muted" style={{ fontSize: "12px", marginLeft: "auto" }}>
                        App: <strong>{app.name}</strong>
                      </span>
                    )}
                  </div>
                </div>

                {testCaseFormDescription && (
                  <div className="test-case-inspector-section">
                    <span className="test-case-inspector-label">Description</span>
                    <div className="test-case-inspector-card">{testCaseFormDescription}</div>
                  </div>
                )}

                {testCaseFormPreconditions && (
                  <div className="test-case-inspector-section">
                    <span className="test-case-inspector-label">Preconditions</span>
                    <div className="test-case-inspector-card" style={{ background: "#f8fafc" }}>
                      🔒 {testCaseFormPreconditions}
                    </div>
                  </div>
                )}

                <div className="test-case-inspector-section">
                  <span className="test-case-inspector-label">Execution Steps</span>
                  <TestStepEditor value={testCaseFormSteps} onChange={setTestCaseFormSteps} disabled={true} />
                </div>

                {testCaseFormExpectedResult && (
                  <div className="test-case-inspector-section">
                    <span className="test-case-inspector-label">Expected Result</span>
                    <div
                      className="test-case-inspector-card"
                      style={{
                        background: "#f0fdf4",
                        border: "1px solid #bbf7d0",
                        color: "#166534",
                        fontWeight: 500,
                      }}
                    >
                      ✓ {testCaseFormExpectedResult}
                    </div>
                  </div>
                )}

                <div className="projects-modal-actions" style={{ borderTop: "1px solid var(--border-light, #e2e8f0)", paddingTop: "12px", marginTop: "8px" }}>
                  <button type="button" className="secondary" onClick={closeTestCaseEditor}>
                    Close
                  </button>
                  {testCaseEditingId && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void handleViewPlaywrightSpec(testCaseEditingId)}
                      style={{ color: "var(--brand-primary, #b5121b)", fontWeight: 700 }}
                      title="View & export TypeScript Playwright spec code"
                    >
                      💻 Playwright Spec
                    </button>
                  )}
                  {testCaseEditingId && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        openScriptStudio({
                          testCaseId: testCaseEditingId,
                          testCaseTitle: testCaseFormTitle || "Test Case",
                          applicationId: selectedAppId,
                          applicationName: app?.name,
                          initialMode: "single",
                        });
                      }}
                      style={{ color: "#1f3a5f", fontWeight: 700 }}
                      title="Enterprise Script Studio (Playwright, Cypress, Selenium, Robot, Java, Puppeteer & GitHub)"
                    >
                      ⚡ Script Studio
                    </button>
                  )}
                  {testCaseEditingId && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        closeTestCaseEditor();
                        prepareTestCaseRun(testCaseEditingId);
                      }}
                      title="Review parameters and execute this test case"
                    >
                      ⚡ Run Test Case
                    </button>
                  )}
                  <button
                    type="button"
                    className="primary"
                    onClick={() => setTestCaseEditorMode("edit")}
                  >
                    ✏️ Edit Test Case
                  </button>
                </div>
              </div>
            ) : (
              <form
                className="projects-modal-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveTestCaseFromEditor();
                }}
              >
                <div className="projects-modal-head" style={{ paddingBottom: "8px", borderBottom: "1px solid var(--border-light, #e2e8f0)" }}>
                  <div>
                    <h3 id="test-case-edit-title" style={{ margin: 0 }}>
                      {testCaseEditorMode === "create" ? "Create test case" : "Edit test case"}
                    </h3>
                  </div>
                  <button type="button" className="secondary btn-sm" onClick={closeTestCaseEditor} disabled={savingTestCase}>Close</button>
                </div>

                <label htmlFor="test-case-edit-title-input">Title <span aria-hidden="true">*</span></label>
                <input
                  id="test-case-edit-title-input"
                  value={testCaseFormTitle}
                  onChange={(event) => setTestCaseFormTitle(event.target.value)}
                  disabled={savingTestCase}
                  required
                  maxLength={200}
                  placeholder="e.g. TC01 - Search for an owner by name and view results"
                />

                <div className="credential-grid" style={{ marginTop: "4px" }}>
                  <label className="capture-label" htmlFor="test-case-edit-status">Status
                    <select id="test-case-edit-status" value={testCaseFormStatus} onChange={(event) => setTestCaseFormStatus(event.target.value)} disabled={savingTestCase}>
                      <option value="draft">Draft</option>
                      <option value="ready">Ready</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </label>
                  <label className="capture-label" htmlFor="test-case-edit-priority">Priority
                    <select id="test-case-edit-priority" value={testCaseFormPriority} onChange={(event) => setTestCaseFormPriority(event.target.value)} disabled={savingTestCase}>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                  </label>
                  <label className="capture-label" htmlFor="test-case-edit-category">Category
                    <select id="test-case-edit-category" value={testCaseFormCategory} onChange={(event) => setTestCaseFormCategory(event.target.value)} disabled={savingTestCase}>
                      <option value="positive">Positive</option>
                      <option value="negative">Negative</option>
                      <option value="boundary">Boundary</option>
                      <option value="security">Security</option>
                      <option value="accessibility">Accessibility</option>
                    </select>
                  </label>
                </div>

                <label htmlFor="test-case-edit-description">Description</label>
                <textarea
                  id="test-case-edit-description"
                  value={testCaseFormDescription}
                  onChange={(event) => setTestCaseFormDescription(event.target.value)}
                  disabled={savingTestCase}
                  rows={2}
                  placeholder="Summary of what this test case verifies..."
                />

                <label htmlFor="test-case-edit-preconditions">Preconditions</label>
                <textarea
                  id="test-case-edit-preconditions"
                  value={testCaseFormPreconditions}
                  onChange={(event) => setTestCaseFormPreconditions(event.target.value)}
                  disabled={savingTestCase}
                  rows={2}
                  placeholder="Prerequisites, initial page states, or environment conditions..."
                />

                <TestStepEditor value={testCaseFormSteps} onChange={setTestCaseFormSteps} disabled={savingTestCase} />

                <label htmlFor="test-case-edit-expected">Expected result</label>
                <textarea
                  id="test-case-edit-expected"
                  value={testCaseFormExpectedResult}
                  onChange={(event) => setTestCaseFormExpectedResult(event.target.value)}
                  disabled={savingTestCase}
                  rows={2}
                  placeholder="Clear assertion or expected condition upon test completion..."
                />

                {testCaseFormError && <p className="form-error">{testCaseFormError}</p>}
                <div className="projects-modal-actions" style={{ borderTop: "1px solid var(--border-light, #e2e8f0)", paddingTop: "12px", marginTop: "8px" }}>
                  <button type="button" className="secondary" onClick={closeTestCaseEditor} disabled={savingTestCase}>Cancel</button>
                  <button type="submit" className="primary" disabled={savingTestCase}>{savingTestCase ? "Saving..." : testCaseEditorMode === "create" ? "Create test case" : "Save changes"}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );

  const cases = (
    <>
      <PageTitle
        title="Test cases"
        kicker={`Application / ${app?.name ?? WORKSPACE_NAME}`}
        action={hasApplications ? (creatingStarterCases ? "Creating..." : "Create starter cases") : "Add application"}
        onAction={() => {
          if (!hasApplications) {
            notify("Add an application before uploading test cases");
            navigateToSection("applications");
            return;
          }
          void createStarterCases();
        }}
        actionDisabled={hasApplications ? (creatingStarterCases || importingCases || clearingDrafts) : false}
      />
      {testRepositoryControls}
      {testRepositoryWorkspace}
    </>
  );

  const execution = (
    <div className="execution-page">
      <div className="execution-page-header">
        <div className="execution-page-title">
          <h1>Execute Tests</h1>
          <span className="muted">{app?.name ?? "No application selected"} · {selectedCases.length} cases available</span>
        </div>
        <div className="execution-page-header-actions">
          {latestBuildReport && (
            <button
              type="button"
              className="secondary"
              onClick={() => setActiveBuildReportModal(latestBuildReport)}
              title="Open the complete build report modal"
            >
              📊 Build Report
            </button>
          )}
          {running && (
            <button
              type="button"
              className="secondary btn-danger"
              onClick={() => void handleStopActiveExecution()}
              disabled={stoppingExecution}
              title="Immediately stop all active and queued test executions"
            >
              🛑 {stoppingExecution ? "Stopping..." : "Stop Execution"}
            </button>
          )}
          <button
            type="button"
            className="secondary"
            onClick={() => openExecutionScopeDialog(
              preparedExecutionCaseIds.length
                ? preparedExecutionCaseIds
                : executionSelectedCaseIds.length
                  ? executionSelectedCaseIds
                  : undefined,
              "Configure run",
            )}
            disabled={!app?.id || running}
          >
            Configure run
          </button>
          {executionSelectedCaseIds.length > 0 && (
            <button
              type="button"
              className="primary"
              onClick={() => openExecutionScopeDialog(executionSelectedCaseIds, `Run ${executionSelectedCaseIds.length} selected cases`)}
              disabled={!app?.id || running}
              style={{ background: "#2563eb" }}
            >
              ▶ Run selected ({executionSelectedCaseIds.length})
            </button>
          )}
          <button
            type="button"
            className="primary"
            onClick={() => openExecutionScopeDialog(undefined, "Run all available cases")}
            disabled={!app?.id || !selectedCases.length || running}
          >
            Run all cases ({selectedCases.length})
          </button>
        </div>
      </div>
      {preparedExecutionCaseIds.length ? (
        <div className="panel execution-prepared-run" role="status">
          <div>
            <strong>Prepared test-case run</strong>
            <span>
              {preparedExecutionCaseIds
                .map((caseId) => testCases.find((caseItem) => caseItem.id === caseId)?.title ?? `Test case #${caseId}`)
                .join(", ")}
            </span>
            <small>Review the execution settings below before starting this run.</small>
          </div>
          <button type="button" className="secondary btn-sm" onClick={clearPreparedExecution} disabled={running}>Clear selection</button>
        </div>
      ) : null}
      <section className="execution-repository-workspace" aria-label="Test case repository">
        {testRepositoryWorkspace}
      </section>
      {running && (
        <div className="panel run-progress run-progress-enhanced">
          <div className="run-progress-head" aria-live="polite">
            <div className="run-progress-title">
              <span className="run-progress-icon">{executionPhaseMeta.icon}</span>
              <div>
                <strong>{executionPhaseMeta.label}</strong>
                <p>{runLog}</p>
              </div>
            </div>
            <div className="run-progress-kpis" style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
              <span>Mode {executionMode === "watch_live" ? "Watch Live" : "Background"}</span>
              <span>Workers {getConcurrencyLimit(executionParallelism, executionTotalCount)}</span>
              <span><b>{executionCompletedCount}</b> / {executionTotalCount} complete</span>
              <button
                type="button"
                className="secondary btn-sm btn-danger"
                onClick={() => void handleStopActiveExecution()}
                disabled={stoppingExecution}
                title="Immediately stop this execution batch"
                style={{ marginLeft: "8px", padding: "3px 10px" }}
              >
                🛑 {stoppingExecution ? "Stopping..." : "Stop Execution"}
              </button>
            </div>
          </div>

          {/* Live Counter Strip */}
          <div className="progress-strip">
            <div className="progress-item">
              <div className="progress-count">{executionQueuedCount}</div>
              <div className="progress-label">Queued</div>
            </div>
            <div className="progress-item">
              <div className="progress-count progress-running">{executionCounts.running}</div>
              <div className="progress-label">Running</div>
            </div>
            <div className="progress-item">
              <div className="progress-count progress-passed">{executionCounts.passed}</div>
              <div className="progress-label">Passed</div>
            </div>
            <div className="progress-item">
              <div className="progress-count progress-failed">{executionCounts.failed}</div>
              <div className="progress-label">Failed</div>
            </div>
            <div className="progress-item">
              <div className="progress-count progress-failed">{executionCounts.error}</div>
              <div className="progress-label">Error</div>
            </div>
          </div>

          {/* Progress Bar */}
          <div
            className="run-progress-bar"
            role="progressbar"
            aria-label="Execution progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={executionProgressPercent}
          >
            <div className="run-progress-bar-fill" style={{ width: `${executionProgressPercent}%` }} />
            <span
              className="execution-progress-runner"
              style={{ left: `${executionProgressPercent}%` }}
              aria-hidden="true"
              title={activeExecutionCase?.title ?? "Execution in progress"}
            >
              <AppIcon name="execution" />
            </span>
          </div>

          {/* Active Test Panel */}
          {activeExecutionCase && (
            <div className="active-test-panel">
              <div className="active-test-head">
                <div className="active-test-title">
                  <span className="detail-label">Active execution</span>
                  <strong>{activeExecutionCase.title}</strong>
                </div>
              </div>
              <div className="active-test-meta">
                <span className="elapsed-time">Elapsed: {formatElapsedDuration(executionElapsedMs)}</span>
                <span>•</span>
                <span>ETA: {executionEtaMs > 0 ? formatElapsedDuration(executionEtaMs) : "Calculating..."}</span>
                {activeExecutionCase.runId ? <span>Run ID: {activeExecutionCase.runId.slice(0, 8)}</span> : null}
                <span>Polls: {activeExecutionCase.pollCount}</span>
              </div>
              <p className="muted">{activeExecutionCase.detail}</p>
            </div>
          )}

          <div className="run-progress-foot">
            <span>{runStatus}</span>
            <span>{executionCompletedCount}/{executionTotalCount} complete</span>
            {running && voiceOverEnabled ? <span className="execution-live-voice-status" aria-live="polite">Voice-over on: {voiceGender} voice</span> : null}
          </div>

          {executionLiveCases.length ? (
            <div className="execution-live-progress-grid">
              <div className="execution-live-progress-list">
                <h3>Case-by-case progress</h3>
                <div className="execution-live-progress-rows">
                  {executionLiveCases.map((caseProgress) => {
                    const caseElapsedMs = caseProgress.startedAt
                      ? Math.max(0, (caseProgress.finishedAt ?? executionClockMs) - caseProgress.startedAt)
                      : 0;
                    const caseDurationLabel = typeof caseProgress.durationMs === "number" && caseProgress.durationMs > 0
                      ? formatDuration(caseProgress.durationMs)
                      : caseProgress.startedAt
                        ? formatElapsedDuration(caseElapsedMs)
                        : "Waiting";
                    return (
                      <article
                        key={`live-case-${caseProgress.caseId}`}
                        className={`execution-live-case execution-live-case-${caseProgress.status}`}
                      >
                        <header className="execution-live-case-head">
                          <div>
                            <span className="detail-label">Case {caseProgress.order}</span>
                            <strong className="execution-live-case-title">{caseProgress.title}</strong>
                          </div>
                          {renderStatusChip(caseProgress.status)}
                        </header>
                        <div className="execution-live-case-meta">
                          <span>{caseProgress.runId ? `Run ${caseProgress.runId.slice(0, 8)}` : "Run pending"}</span>
                          <span>{caseDurationLabel}</span>
                          <span>Polls: {caseProgress.pollCount}</span>
                        </div>
                        <p className="muted">{caseProgress.detail}</p>
                      </article>
                    );
                  })}
                </div>
              </div>
              <div className="execution-live-activity-panel">
                <h3>Live activity</h3>
                <div className="execution-live-activity-log">
                  {executionActivityLog.length ? [...executionActivityLog].reverse().map((entry, index) => (
                    <p key={`execution-activity-${index}-${entry}`} className="execution-live-activity-entry">{entry}</p>
                  )) : <p className="muted">Waiting for worker updates...</p>}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
      {executionScopeDialog && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setExecutionScopeDialog(null);
          }}
        >
          <div
            className="panel projects-modal execution-scope-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="execution-scope-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="projects-modal-head">
              <div>
                <h2 id="execution-scope-dialog-title">Confirm execution scope</h2>
                <p className="muted">{executionScopeDialog.triggerLabel}</p>
              </div>
              <button type="button" className="secondary btn-sm" onClick={() => setExecutionScopeDialog(null)} aria-label="Close execution scope dialog">Close</button>
            </div>
            <ExecutionRunConfiguration
              executionRunScope={executionRunScope}
              setExecutionRunScope={setExecutionRunScope}
              executionScopeOptions={executionScopeOptions}
              executionMode={executionMode}
              setExecutionMode={setExecutionMode}
              parallelExecutionCount={executionParallelism}
              setParallelExecutionCount={setExecutionParallelism}
              executionSlowMode={executionSlowMode}
              setExecutionSlowMode={setExecutionSlowMode}
              executionTraceMode={executionTraceMode}
              setExecutionTraceMode={setExecutionTraceMode}
              voiceGender={voiceGender}
              onVoiceGenderChange={handleVoiceGenderChange}
              voiceOverEnabled={voiceOverEnabled}
              setVoiceOverEnabled={setVoiceOverEnabled}
              onTestVoice={testVoiceOver}
              captureScreenshotEvidence={captureScreenshotEvidence}
              setCaptureScreenshotEvidence={setCaptureScreenshotEvidence}
              highlightActionTargets={highlightActionTargets}
              setHighlightActionTargets={setHighlightActionTargets}
              recordVideoEvidence={recordVideoEvidence}
              setRecordVideoEvidence={setRecordVideoEvidence}
              keepBrowserOpenOnFailure={keepBrowserOpenOnFailure}
              setKeepBrowserOpenOnFailure={setKeepBrowserOpenOnFailure}
              keepBrowserOpenSeconds={keepBrowserOpenSeconds}
              setKeepBrowserOpenSeconds={setKeepBrowserOpenSeconds}
              authenticatedFlow={authenticatedFlow}
              setAuthenticatedFlow={setAuthenticatedFlow}
              emailSelector={emailSelector}
              setEmailSelector={setEmailSelector}
              passwordSelector={passwordSelector}
              setPasswordSelector={setPasswordSelector}
              submitSelector={submitSelector}
              setSubmitSelector={setSubmitSelector}
              runtimeParameters={runtimeParameters}
              setRuntimeParameters={setRuntimeParameters}
              onAutoPopulateParameters={() => void autoPopulateRuntimeParameters(true)}
              populatingParameters={populatingParameters}
              onSaveConfiguration={saveExecutionConfiguration}
              onDownloadHistory={() => void downloadExecutionHistory()}
              downloadingExecutionHistory={downloadingExecutionHistory}
            />
            <div className="execution-scope-summary-grid">
              <div><span>Application</span><strong>{app?.name ?? "—"}</strong></div>
              <div><span>Cases</span><strong>{executionScopeCaseIds.length}</strong></div>
              <div><span>Workers</span><strong>{getConcurrencyLimit(executionParallelism, executionScopeCaseIds.length)}</strong></div>
              <div><span>Mode</span><strong>{executionMode === "watch_live" ? "Watch live" : "Background"}</strong></div>
              <div><span>Evidence</span><strong>{highlightActionTargets ? "Highlighted screenshots" : captureScreenshotEvidence ? "Screenshots" : recordVideoEvidence ? "Video only" : "No screenshot"}</strong></div>
            </div>
            <div className="execution-scope-options">
              <span>{highlightActionTargets ? "Action highlights are enabled and will be included in step screenshots." : "Action highlights are disabled."}</span>
              <span>{runtimeParameters.filter((parameter) => parameter.key.trim()).length} runtime parameter{runtimeParameters.filter((parameter) => parameter.key.trim()).length === 1 ? "" : "s"} configured</span>
            </div>
            <div className="execution-scope-case-list">
              {executionScopeCaseIds.map((caseId, index) => (
                <span key={caseId}>{index + 1}. {selectedCases.find((caseItem) => caseItem.id === caseId)?.title ?? `Test case #${caseId}`}</span>
              ))}
            </div>
            <div className="projects-modal-actions">
              <button type="button" className="secondary" onClick={() => setExecutionScopeDialog(null)}>Cancel</button>
              <button type="button" className="primary" onClick={confirmExecutionScopeRun}>Start run ({executionScopeCaseIds.length})</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const runHistory = (
    <>
      <PageTitle
        title="Run History"
        kicker={`Application / ${app?.name ?? WORKSPACE_NAME}`}
        action={loadingCaseExecutions ? "Refreshing..." : "Refresh history"}
        onAction={() => { void refreshExecutionHistory(token, app?.id); }}
        actionDisabled={loadingCaseExecutions || !app?.id}
      />
      <RunHistoryWorkspace
        appName={app?.name ?? WORKSPACE_NAME}
        application={app}
        runs={selectedAppRuns}
        caseExecutions={caseExecutions}
        builds={builds}
        loading={loadingCaseExecutions}
        onRefresh={() => { void refreshExecutionHistory(token, app?.id); }}
        onViewBuildReport={openBuildReportModal}
        onViewRunReport={openBuildReportModal}
        hasBuildReport={Boolean(latestBuildReport || builds.length > 0)}
        onCancelRun={handleCancelRun}
        onCancelBuild={handleCancelBuild}
        onRebuild={handleRebuildBuild}
        onRunCase={prepareTestCaseRun}
      />
    </>
  );

  const defectView = (
    <>
      <PageTitle
        title="Defects"
        kicker={`Quality management / ${app?.name ?? WORKSPACE_NAME}`}
        action="+ Report defect"
        onAction={openCreateDefectModal}
      />
      <DefectManagementWorkspace
        appName={app?.name ?? WORKSPACE_NAME}
        application={app}
        applications={apps}
        defects={defects}
        loading={refreshingData}
        token={token}
        onReportDefect={openCreateDefectModal}
        onEditDefect={openEditDefectModal}
        onDeleteDefect={deleteDefect}
        onQuickStatusChange={handleQuickDefectStatusChange}
        deletingDefectId={deletingDefectId}
        onRefresh={() => void loadDashboardData(token, app?.name)}
        notify={notify}
      />
    </>
  );

  const suitesView = (
    <>
      <PageTitle
        title="Test suites"
        kicker={`Coverage organization / ${app?.name ?? WORKSPACE_NAME}`}
        action={suiteEditingId ? "+ New suite" : undefined}
        onAction={() => {
          setSuiteName("");
          setSuiteDescription("");
          setSuiteCaseSource("ready");
          setSuiteEditingId(null);
          setSuiteEditingCaseIds(null);
          setSuiteFormError("");
        }}
      />
      <div className="suites-content-stack">
        <AppCard className="content-panel">
          <SectionHeader kicker="Suite composition" title={suiteEditingId ? "Edit reusable suite coverage" : "Create reusable suites from real test-case inventory"} />
          <p className="muted">Suites are now persisted in backend APIs and linked to your selected application context.</p>
          <div className="credential-grid">
            <label className="capture-label">
              Suite name
              <input
                value={suiteName}
                onChange={(event) => {
                  setSuiteName(event.target.value);
                  setSuiteFormError("");
                }}
                placeholder={app ? `${app.name} regression suite` : "Select an application first"}
                disabled={!app || creatingSuite}
              />
            </label>
            <label className="capture-label">
              Case source
              <select
                value={suiteCaseSource}
                onChange={(event) => {
                  setSuiteCaseSource(event.target.value as "ready" | "all" | "latest");
                  setSuiteEditingCaseIds(null);
                  setSuiteFormError("");
                }}
                disabled={!app || creatingSuite}
              >
                <option value="ready">Ready cases</option>
                <option value="all">All app cases</option>
                <option value="latest">Latest AI generated (fallback to ready)</option>
              </select>
            </label>
          </div>
          <label className="capture-label">
            Description
            <textarea
              value={suiteDescription}
              onChange={(event) => {
                setSuiteDescription(event.target.value);
                setSuiteFormError("");
              }}
              rows={3}
              placeholder="What this suite validates and when to run it"
              disabled={!app || creatingSuite}
            />
          </label>
          {suiteFormError && <p className="form-error">{suiteFormError}</p>}
          <p className="muted">
            {app
              ? `${suiteCandidateCaseIds.length} case${suiteCandidateCaseIds.length === 1 ? "" : "s"} will be included from ${suiteCaseSource === "all" ? "all cases" : suiteCaseSource === "latest" ? "latest generated scope" : "ready cases"}.`
              : "Select an application to build suites."}
          </p>
          <div className="projects-modal-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setSuiteName("");
                setSuiteDescription("");
                setSuiteCaseSource("ready");
                setSuiteEditingId(null);
                setSuiteEditingCaseIds(null);
                setSuiteFormError("");
              }}
              disabled={creatingSuite}
            >
              Reset
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => { void createSuite(); }}
              disabled={creatingSuite || loadingSuites || !app || !suiteCandidateCaseIds.length}
            >
              {creatingSuite ? (suiteEditingId ? "Saving..." : "Creating...") : suiteEditingId ? "Save suite" : "Create suite"}
            </button>
          </div>
        </AppCard>
        <AppCard className="designer-card v3-visual-card">
          <SectionHeader kicker="Suite readiness" title="Ready-case distribution by application" />
          <DistributionBars items={suiteReadinessDistribution} />
        </AppCard>
        <Table
          title="Saved suites"
          meta={loadingSuites ? "Refreshing..." : `${selectedAppSuites.length} suite${selectedAppSuites.length === 1 ? "" : "s"} for ${app?.name ?? "selected app"}`}
        >
          <table>
            <thead><tr><th>Suite</th><th>Cases</th><th>Updated</th><th>Case coverage</th><th /></tr></thead>
            <tbody>
              {selectedAppSuites.length ? selectedAppSuites.map((suite) => {
                const previewTitles = suite.case_ids
                  .map((caseId) => selectedCases.find((caseItem) => caseItem.id === caseId)?.title ?? `Case ${caseId}`)
                  .slice(0, 3);
                const overflowCount = Math.max(suite.case_ids.length - previewTitles.length, 0);
                return (
                  <tr key={`saved-suite-${suite.id}`}>
                    <td>
                      <strong>{suite.name}</strong>
                      <br />
                      <span className="muted">{suite.description?.trim() || "No description provided."}</span>
                    </td>
                    <td>{suite.case_count}</td>
                    <td>{formatTimestamp(suite.updated_at ?? suite.created_at)}</td>
                    <td>
                      {previewTitles.join(", ")}
                      {overflowCount ? ` +${overflowCount} more` : ""}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary btn-sm"
                        onClick={() => editSuite(suite)}
                        disabled={deletingSuiteId === suite.id || creatingSuite}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="secondary btn-sm"
                        onClick={() => { void deleteSuite(suite); }}
                        disabled={deletingSuiteId === suite.id}
                      >
                        {deletingSuiteId === suite.id ? "Deleting..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                );
              }) : (
                <tr><td colSpan={5} className="muted">No suites saved for this application yet.</td></tr>
              )}
            </tbody>
          </table>
        </Table>
        <Table title="Current suite candidates" meta={`${testCases.length} test cases available`}>
          <table>
            <thead><tr><th>Application</th><th>Draft cases</th><th>Ready cases</th><th>Suggested suite</th></tr></thead>
            <tbody>
              {apps.length ? apps.map((item) => {
                const appCases = testCases.filter((caseItem) => caseItem.application_id === item.id);
                const draftCount = appCases.filter((caseItem) => isDraftStatus(caseItem.status)).length;
                const readyCount = appCases.filter((caseItem) => caseItem.status.trim().toLowerCase() === "ready").length;
                return <tr key={`suite-${item.name}`}><td>{item.name}</td><td>{draftCount}</td><td>{readyCount}</td><td>{item.name} core flow</td></tr>;
              }) : <tr><td colSpan={4} className="muted">No applications found. Add one in Applications to prepare suite grouping.</td></tr>}
            </tbody>
          </table>
        </Table>
      </div>
    </>
  );

  const reportsView = (
    <>
      <PageTitle
        title="Quality & Release Intelligence"
        kicker={`Quality insights / ${app?.name ?? WORKSPACE_NAME}`}
        action={refreshingData ? "Refreshing..." : "Refresh report data"}
        onAction={() => { void loadDashboardData(token, app?.name); notify("Report data refreshed"); }}
        actionDisabled={refreshingData}
      />
      <QualityReportsWorkspace
        appName={app?.name ?? WORKSPACE_NAME}
        application={app}
        applications={apps}
        testCases={testCases}
        runs={trackedRuns}
        defects={defects}
        builds={builds}
        loading={refreshingData}
        onRefresh={() => void loadDashboardData(token, app?.name)}
        onNavigateToSection={(section) => navigateToSection(section as Section)}
        onInspectRun={(runId) => router.push(`/test-execution/${runId}`)}
        onReportDefect={openCreateDefectModal}
        notify={notify}
      />
    </>
  );

  const aiGeneratorView = (
    <>
      <div className="agent-hero-banner">
        <div className="agent-hero-head">
          <div>
            <div className="agent-hero-badge">
              <span className="agent-hero-pulse"></span>
              AI Test Design Studio
            </div>
            <h2 className="agent-hero-title">AI-Powered Test Generation · {app?.name || "Application"}</h2>
          </div>
          <button
            type="button"
            onClick={() => document.getElementById("ai-generation-workflow")?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="btn btn-indigo btn-sm"
            style={{ padding: "4px 12px", fontSize: "12px" }}
          >
            ↓ Generation workflow
          </button>
        </div>
      </div>

      <div className="panel" style={{ padding: "8px 12px", margin: "0 0 10px" }}>
        <div className="ai-simple-action-row" style={{ alignItems: "center" }}>
          <button className="primary btn-sm" onClick={() => void generateAiCases()} disabled={!aiGenerationReady || aiGenerating}>
            {aiGenerating || savingAiTarget ? "Generating..." : "⚡ Generate test cases"}
          </button>
          <button
            className="primary btn-sm"
            onClick={() => { navigateToSection("execution"); void runApplicationCaseTests(aiReadyRunCaseIds); }}
            disabled={!app?.id || running || aiReadyRunCaseIds.length === 0}
          >
            ▶ Run ready tests ({aiReadyRunCaseIds.length})
          </button>
          <button
            className="secondary btn-sm"
            onClick={() => { navigateToSection("execution"); void runApplicationCaseTests(latestGeneratedCaseIds); }}
            disabled={!app?.id || running || latestGeneratedCases.length === 0}
          >
            Run latest ({latestGeneratedCases.length})
          </button>
          <button className="secondary btn-sm" onClick={() => void createStarterCases()} disabled={!app?.id || creatingStarterCases}>
            {creatingStarterCases ? "Creating..." : "Create starter cases"}
          </button>
          <button
            className="secondary btn-sm btn-danger"
            onClick={() => void clearDraftCases()}
            disabled={!app?.id || selectedCases.length === 0 || clearingDrafts}
          >
            {clearingDrafts ? "Clearing..." : selectedDraftCount > 0 ? `Clear drafts (${selectedDraftCount})` : "Clear drafts"}
          </button>
          <button className="secondary btn-sm" onClick={() => navigateToSection("cases")}>Open Test Cases</button>
          <button className="secondary btn-sm" onClick={downloadGeneratedPreviewTemplate} disabled={!app?.id || !previewCaseRows.length || downloadingAiPreview}>
            {downloadingAiPreview ? "Downloading..." : "Download template"}
          </button>
        </div>
        {!aiGenerationReady ? <p className="muted" style={{ margin: "4px 0 0", fontSize: "11px" }}>{aiGenerationBlocker}</p> : null}
      </div>

      <div className="ai-simple-grid" id="ai-generation-workflow">
        <AppCard className="content-panel ai-simple-card">
          <SectionHeader
            kicker="Step 1"
            title="Describe the workflow you want to test"
            meta={app ? `Target: ${app.name}` : "Select an application to continue"}
          />

          {/* Jira Requirement Integration Ingest */}
          <div className="ai-jira-source">
            <div className="ai-jira-source-copy">
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontSize: "14px" }}>🔷</span>
                <strong>Jira User Story / Issue Source</strong>
              </div>
              <span>Import user stories, acceptance criteria, and requirements from Jira (e.g. ECOM-116459 or URL)</span>
            </div>
            <div className="ai-jira-input-group">
              <input
                type="text"
                value={aiJiraInput}
                onChange={(e) => setAiJiraInput(e.target.value)}
                placeholder="e.g. PROJ-123 or https://your-domain.atlassian.net/browse/PROJ-123"
                disabled={fetchingAiJira}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void fetchAiJiraIssue();
                  }
                }}
              />
              <button
                type="button"
                className="secondary btn-sm"
                onClick={() => void fetchAiJiraIssue()}
                disabled={fetchingAiJira || !aiJiraInput.trim()}
              >
                {fetchingAiJira ? "Connecting..." : "Fetch Jira Story"}
              </button>
            </div>
          </div>

          {aiJiraError ? (
            <div className="ai-document-analysis-error" role="alert">
              <span>{aiJiraError}</span>
              <button type="button" className="table-action" onClick={() => setAiJiraError("")}>Dismiss</button>
            </div>
          ) : null}

          {aiJiraIssue && (
            <div className="ai-jira-card" aria-label="Connected Jira Issue Requirements">
              <div className="ai-jira-card-header">
                <div className="ai-jira-key-badge-group">
                  <span className="ai-jira-key-badge">{aiJiraIssue.key}</span>
                  {aiJiraIssue.issue_type && <span className="badge badge-secondary" style={{ fontSize: "11px" }}>{aiJiraIssue.issue_type}</span>}
                  {aiJiraIssue.priority && <span className={`priority ${aiJiraIssue.priority.toLowerCase()}`} style={{ fontSize: "11px" }}>{aiJiraIssue.priority}</span>}
                  {aiJiraIssue.status && renderStatusChip(aiJiraIssue.status)}
                </div>
                <div className="ai-jira-card-actions">
                  <button
                    type="button"
                    className="secondary btn-sm"
                    onClick={() => applyJiraToPrompt(aiJiraIssue)}
                    title="Auto-fill generation prompt and module focus with this Jira Story"
                  >
                    ⚡ Apply to Prompt
                  </button>
                  <button
                    type="button"
                    className="table-action"
                    onClick={clearAiJira}
                    title="Disconnect this Jira issue"
                  >
                    Disconnect
                  </button>
                </div>
              </div>

              <div className="ai-jira-card-summary">
                <strong>{aiJiraIssue.summary}</strong>
              </div>

              {aiJiraIssue.description && (
                <div className="ai-jira-card-description">
                  <span style={{ fontWeight: 700, display: "block", marginBottom: "3px", color: "#0052cc" }}>User Story &amp; Requirements</span>
                  <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{aiJiraIssue.description}</p>
                </div>
              )}

              {aiJiraIssue.acceptance_criteria && (
                <div className="ai-jira-card-criteria">
                  <span style={{ fontWeight: 700, display: "block", marginBottom: "3px", color: "#059669" }}>Acceptance Criteria</span>
                  <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{aiJiraIssue.acceptance_criteria}</p>
                </div>
              )}

              <div className="ai-jira-card-meta">
                {aiJiraIssue.labels?.length > 0 && (
                  <span>Labels: <strong>{aiJiraIssue.labels.join(", ")}</strong></span>
                )}
                {aiJiraIssue.components?.length > 0 && (
                  <span>Components: <strong>{aiJiraIssue.components.join(", ")}</strong></span>
                )}
                {aiJiraIssue.reporter && (
                  <span>Reporter: <strong>{aiJiraIssue.reporter}</strong></span>
                )}
                {aiJiraIssue.url && (
                  <a className="ai-jira-link" href={aiJiraIssue.url} target="_blank" rel="noopener noreferrer">
                    Open in Jira ↗
                  </a>
                )}
              </div>
            </div>
          )}

          <div className="ai-document-source">
            <div className="ai-document-source-copy">
              <strong>Requirement documents</strong>
              <span>PDF, DOCX, TXT, CSV, XLSX, JSON, or Markdown</span>
            </div>
            <input
              ref={aiDocumentInputRef}
              hidden
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.csv,.xlsx,.json,.md,.markdown"
              onChange={(event) => void analyzeAiDocuments(Array.from(event.target.files ?? []))}
              disabled={analyzingAiDocuments}
            />
            <button
              type="button"
              className="secondary btn-sm"
              onClick={() => aiDocumentInputRef.current?.click()}
              disabled={analyzingAiDocuments || !token}
            >
              {analyzingAiDocuments ? "Analyzing documents..." : "Upload documents"}
            </button>
          </div>
          {aiDocumentAnalysisError ? (
            <div className="ai-document-analysis-error" role="alert">
              <span>{aiDocumentAnalysisError}</span>
              <button type="button" className="table-action" onClick={() => setAiDocumentAnalysisError("")}>Dismiss</button>
            </div>
          ) : null}
          {aiDocumentAnalysis ? (
            <div className="ai-document-analysis" aria-label="Document analysis summary">
              <div className="ai-document-analysis-heading">
                <div className="ai-document-file-list">
                  {aiDocumentAnalysis.files.map((file, index) => <span key={`${file.filename}-${index}`}>{file.filename}</span>)}
                </div>
                <button type="button" className="table-action" onClick={clearAiDocuments}>Reset context</button>
              </div>
              <div className="ai-document-metrics">
                <span><strong>{aiDocumentAnalysis.total_files}</strong> files uploaded</span>
                <span><strong>{aiDocumentAnalysis.total_pages}</strong> pages</span>
                <span><strong>{aiDocumentAnalysis.requirements_found}</strong> requirements</span>
                <span><strong>{aiDocumentAnalysis.features_identified}</strong> features</span>
                <span><strong>{aiDocumentAnalysis.modules_identified.length}</strong> modules</span>
                <span><strong>{aiDocumentAnalysis.business_rules_found}</strong> rules</span>
                <span><strong>{aiDocumentAnalysis.workflows_discovered}</strong> workflows</span>
              </div>
              {aiDocumentAnalysis.modules_identified.length ? (
                <div className="ai-document-modules">
                  <span>Modules</span>
                  {aiDocumentAnalysis.modules_identified.map((module) => <span key={module}>{module}</span>)}
                </div>
              ) : null}
              {aiDocumentAnalysis.warnings.length ? (
                <ul className="ai-document-warnings">
                  {aiDocumentAnalysis.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              ) : null}
            </div>
          ) : null}

          <AiPromptEditor
            value={aiPrompt}
            onChange={setAiPrompt}
            disabled={aiGenerating}
          />
        </AppCard>

        <AppCard className="content-panel ai-simple-card">
          <SectionHeader
            kicker="Step 2"
            title="Generation settings"
            meta="Choose coverage and approved test data"
          />
          <div className="ai-source-summary" aria-label="Generation source summary">
            <div>
              <span className="detail-label">Generation source</span>
              <strong>
                {aiJiraIssue && aiDocumentAnalysis
                  ? `Jira (${aiJiraIssue.key}) + Requirements + Prompt`
                  : aiJiraIssue
                  ? `Jira (${aiJiraIssue.key}) + Prompt`
                  : aiDocumentAnalysis
                  ? "Uploaded requirements + prompt"
                  : "Prompt"}
              </strong>
            </div>
            <div>
              <span className="detail-label">Context</span>
              <strong>
                {aiJiraIssue && aiDocumentAnalysis
                  ? `${aiJiraIssue.key} (${aiJiraIssue.summary.slice(0, 35)}...), ${aiDocumentAnalysis.files.length} doc(s)`
                  : aiJiraIssue
                  ? `${aiJiraIssue.key}: ${aiJiraIssue.summary}`
                  : aiDocumentAnalysis
                  ? `${aiDocumentAnalysis.files.length} document${aiDocumentAnalysis.files.length === 1 ? "" : "s"}, ${aiDocumentAnalysis.requirements_found} requirement${aiDocumentAnalysis.requirements_found === 1 ? "" : "s"}`
                  : "Describe the workflow in Step 1"}
              </strong>
            </div>
            <div>
              <span className="detail-label">Target</span>
              <strong>{app?.name ?? "Select an application"}</strong>
            </div>
          </div>
          <div className="ai-simple-settings-grid">
            <label className="capture-label" htmlFor="ai-application">
              Application
              <select id="ai-application" value={app?.name ?? ""} onChange={(event) => selectApplication(event.target.value)}>
                {apps.length ? apps.map((item) => (
                  <option key={`ai-app-${item.id ?? item.name}`} value={item.name}>{item.name}</option>
                )) : <option value="" disabled>No applications available</option>}
              </select>
            </label>
            <label className="capture-label" htmlFor="ai-case-count">
              Coverage & Scope Strategy
              <select id="ai-case-count" value={String(aiCaseCount)} onChange={(event) => setAiCaseCount(Number(event.target.value))}>
                <option value="0">⚡ Dynamic (Auto-determined by AI based on context & complexity)</option>
                <option value="6">Smoke suite (approx. 6 cases)</option>
                <option value="10">Target suite (approx. 10 cases)</option>
                <option value="15">Extended suite (approx. 15 cases)</option>
                <option value="25">Deep regression (approx. 25 cases)</option>
              </select>
            </label>
            <label className="capture-label">
              Module focus (optional)
              <input
                value={aiModuleFocus}
                onChange={(event) => setAiModuleFocus(event.target.value)}
                placeholder="Example: Authentication, Search, Listing"
              />
            </label>
            <label className="capture-label">
              Target URL
              <input
                value={aiTargetUrl}
                onChange={(event) => setAiTargetUrl(event.target.value)}
                placeholder="https://example.com"
                disabled={app?.platform !== "web" || aiGenerating || savingAiTarget}
              />
            </label>
          </div>
          <ParameterizedDataProfile
            parameters={runtimeParameters}
            setParameters={setRuntimeParameters}
            applicationName={app?.name}
            onLoginAdded={() => setAuthenticatedFlow(true)}
            onSaveProfile={saveTestDataProfile}
            onSmartGenerate={handleSmartGenerateTestData}
            onAutoLearnEntities={handleAutoLearnEntities}
            generatingSmartData={generatingSmartData}
            learningEntities={learningEntities}
          />
          <div className="ai-simple-toggle-grid">
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeNegative} onChange={(event) => setAiIncludeNegative(event.target.checked)} />
              Include negative scenarios
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeBoundary} onChange={(event) => setAiIncludeBoundary(event.target.checked)} />
              Include boundary scenarios
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeEdge} onChange={(event) => setAiIncludeEdge(event.target.checked)} />
              Include edge cases
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeSecurity} onChange={(event) => setAiIncludeSecurity(event.target.checked)} />
              Include security scenarios
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeAccessibility} onChange={(event) => setAiIncludeAccessibility(event.target.checked)} />
              Include accessibility checks
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludeApiValidation} onChange={(event) => setAiIncludeApiValidation(event.target.checked)} />
              Include API contract scenarios
            </label>
            <label className="capture-label flow-toggle">
              <input type="checkbox" checked={aiIncludePerformance} onChange={(event) => setAiIncludePerformance(event.target.checked)} />
              Include performance scenarios
            </label>
          </div>
          {aiIncludePerformance ? (
            <label className="capture-label ai-performance-budget-field">
              Performance budget (optional)
              <input
                value={aiPerformanceBudget}
                onChange={(event) => setAiPerformanceBudget(event.target.value)}
                placeholder="Example: p95 under 800ms at 50 concurrent users"
                maxLength={500}
              />
              <span className="muted">Generated cases define bounded measurement criteria; they do not create unbounded load against the target.</span>
            </label>
          ) : null}
        </AppCard>
      </div>

      <AppCard className="content-panel ai-simple-card ai-simple-actions-card">
        <SectionHeader
          kicker="Step 3"
          title="Workflow trace &amp; review"
          meta={`Current phase: ${aiGenerationPhase}`}
        />
        <div className="ai-simple-summary-grid">
          <article><span>Coverage mode</span><strong>{aiCaseCount === 0 ? "Dynamic AI" : `${aiCaseCount} cases`}</strong></article>
          <article><span>Generated</span><strong>{aiCaseSummaryRows.length}</strong></article>
          <article><span>Automation ready</span><strong>{aiAutomationReadyCount}</strong></article>
          <article><span>Needs review</span><strong>{aiNeedsReviewCount}</strong></article>
          <article><span>Validation health</span><strong>{aiValidationPercent}%</strong></article>
          <article><span>Generation readiness</span><strong>{aiGenerationReady ? "Ready" : "Needs setup"}</strong></article>
        </div>
        {aiGenerationSource ? (
          <div className={`ai-generation-source-card tone-${aiGenerationSourceTone}`}>
            <div className="ai-generation-source-head">
              <strong>{aiGenerationSourceLabel}</strong>
              <span className={`ai-generation-source-badge tone-${aiGenerationSourceTone}`}>
                {aiGenerationSource.mode === "provider" ? "Provider" : "Unknown"}
              </span>
            </div>
            <p className="muted">
              AI provider: {aiGenerationSource.providerConfigured ? aiGenerationSource.provider : "Not configured"}
            </p>
            {aiGenerationSource.note ? <p className="muted">{aiGenerationSource.note}</p> : null}
            {aiProviderHint ? <p className="muted">{aiProviderHint}</p> : null}
          </div>
        ) : null}

        <AIGenerationConsole
          logs={aiGenerationLogs}
          phase={aiGenerationPhase}
          active={aiGenerating}
          agentStages={aiAgentStages}
          onClear={() => setAiGenerationLogs([])}
        />

        {/* Backend Generation Logs & Execution Trace */}
        <div style={{ marginTop: "16px" }}>
          <GenerationLogViewer
            jobId={activeGenJobId}
            logs={backendGenerationLogs}
            status={aiGenerating ? "running" : backendGenerationLogs.length > 0 ? "completed" : "idle"}
            phase={aiGenerationPhase}
            onRefresh={activeGenJobId ? () => void fetchBackendGenerationLogs(activeGenJobId) : undefined}
          />
        </div>

        <p className="muted" style={{ marginTop: "10px" }}>Generated draft rows appear in Test Cases. Ready cases can be executed from the Execution page.</p>
      </AppCard>

      {latestGenerationInput ? (
        <div className="panel ai-generation-input-summary" aria-label="Current generation input">
          <strong>Current generation input</strong>
          {latestGenerationInput.documentNames.length ? (
            <span>Uploaded: {latestGenerationInput.documentNames.join(", ")}</span>
          ) : null}
          <span>Prompt: {latestGenerationInput.prompt}</span>
        </div>
      ) : null}

      {/* Grouped Actions & Consolidation Bar */}
      <div
        className="panel"
        style={{
          padding: "12px 18px",
          margin: "16px 0 12px",
          background: selectedGeneratedCaseIds.length > 0 ? "rgba(181, 18, 27, 0.04)" : "var(--bg-card, #ffffff)",
          border: `1px solid ${selectedGeneratedCaseIds.length > 0 ? "var(--brand-primary, #b5121b)" : "var(--border-light, #e2e8f0)"}`,
          borderRadius: "var(--radius-md, 8px)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontWeight: 600, fontSize: "13px" }}>
            <input
              type="checkbox"
              checked={aiCaseSummaryRows.length > 0 && selectedGeneratedCaseIds.length === aiCaseSummaryRows.length}
              onChange={(e) => {
                if (e.target.checked) {
                  setSelectedGeneratedCaseIds(aiCaseSummaryRows.map((r) => r.id));
                } else {
                  setSelectedGeneratedCaseIds([]);
                }
              }}
              disabled={aiCaseSummaryRows.length === 0}
            />
            <span>Select All ({aiCaseSummaryRows.length})</span>
          </label>
          {selectedGeneratedCaseIds.length > 0 && (
            <span
              className="badge badge-primary"
              style={{ fontSize: "12px", fontWeight: 700, padding: "3px 8px" }}
            >
              {selectedGeneratedCaseIds.length} scenario{selectedGeneratedCaseIds.length === 1 ? "" : "s"} selected
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {/* Consolidate Action */}
          <button
            type="button"
            className="primary btn-sm"
            onClick={() => void handleConsolidateSelectedScenarios()}
            disabled={selectedGeneratedCaseIds.length < 2 || consolidatingScenarios || bulkActionWorking}
            title={selectedGeneratedCaseIds.length < 2 ? "Select 2 or more scenarios to consolidate into a single E2E flow" : "Merge selected scenarios into a unified end-to-end journey"}
            style={{ fontWeight: 700, background: selectedGeneratedCaseIds.length >= 2 ? "linear-gradient(135deg, #b5121b, #8a0c13)" : undefined }}
          >
            {consolidatingScenarios ? "Consolidating..." : `⚡ Consolidate Scenarios (${selectedGeneratedCaseIds.length >= 2 ? selectedGeneratedCaseIds.length : 0})`}
          </button>

          {/* Add to Suite Dropdown */}
          {selectedAppSuites.length > 0 && (
            <select
              className="btn-sm"
              value=""
              onChange={(e) => {
                if (e.target.value) {
                  void handleBulkAssignToSuite(Number(e.target.value));
                  e.target.value = "";
                }
              }}
              disabled={selectedGeneratedCaseIds.length === 0 || bulkActionWorking}
              style={{ fontSize: "12px", padding: "4px 8px" }}
            >
              <option value="" disabled>📁 Add to Test Suite...</option>
              {selectedAppSuites.map((s) => (
                <option key={`suite-opt-${s.id}`} value={s.id}>
                  {s.name} ({s.case_ids?.length || 0} cases)
                </option>
              ))}
            </select>
          )}

          {/* Bulk Approve */}
          <button
            type="button"
            className="secondary btn-sm"
            onClick={() => void handleBulkApproveGeneratedCases()}
            disabled={selectedGeneratedCaseIds.length === 0 || bulkActionWorking}
            title="Mark selected scenarios as Ready for execution"
          >
            ✓ Mark Ready
          </button>

          {/* Run Selected */}
          <button
            type="button"
            className="secondary btn-sm"
            onClick={() => {
              if (selectedGeneratedCaseIds.length) {
                navigateToSection("execution");
                void runApplicationCaseTests(selectedGeneratedCaseIds);
              }
            }}
            disabled={selectedGeneratedCaseIds.length === 0 || running}
            title="Execute only the selected scenarios"
            style={{ fontWeight: 600 }}
          >
            🚀 Run Selected ({selectedGeneratedCaseIds.length})
          </button>

          {/* Export Dropdown */}
          <button
            type="button"
            className="secondary btn-sm"
            onClick={() => handleBulkExportSelected("csv")}
            disabled={selectedGeneratedCaseIds.length === 0}
            title="Export selected scenarios as CSV"
          >
            📥 CSV
          </button>
          <button
            type="button"
            className="secondary btn-sm"
            onClick={() => handleBulkExportSelected("json")}
            disabled={selectedGeneratedCaseIds.length === 0}
            title="Export selected scenarios as JSON"
          >
            📥 JSON
          </button>

          {/* Bulk Delete */}
          <button
            type="button"
            className="secondary btn-danger btn-sm"
            onClick={() => void handleBulkDeleteGeneratedCases()}
            disabled={selectedGeneratedCaseIds.length === 0 || bulkActionWorking}
            title="Delete selected scenarios"
          >
            🗑 Delete
          </button>

          {selectedGeneratedCaseIds.length > 0 && (
            <button
              type="button"
              className="table-action"
              onClick={() => setSelectedGeneratedCaseIds([])}
              style={{ fontSize: "12px", marginLeft: "4px" }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <Table
        title="Generated case preview"
        meta={aiCaseSummaryRows.length ? `${aiCaseSummaryRows.length} case${aiCaseSummaryRows.length === 1 ? "" : "s"}` : "No generated cases yet"}
        containedScroll={false}
      >
        <table>
          <thead>
            <tr>
              <th scope="col" style={{ width: "36px", textAlign: "center" }}>
                <input
                  type="checkbox"
                  checked={aiCaseSummaryRows.length > 0 && selectedGeneratedCaseIds.length === aiCaseSummaryRows.length}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedGeneratedCaseIds(aiCaseSummaryRows.map((r) => r.id));
                    } else {
                      setSelectedGeneratedCaseIds([]);
                    }
                  }}
                  aria-label="Select all scenarios"
                />
              </th>
              <th scope="col">Case ID</th>
              <th scope="col">Test case</th>
              <th scope="col">Steps</th>
              <th scope="col">Status</th>
              <th scope="col">Automation readiness</th>
              <th scope="col">Review</th>
            </tr>
          </thead>
          <tbody>
            {aiCaseSummaryRows.length ? aiCaseSummaryRows.map((row) => {
              const isSelected = selectedGeneratedCaseIds.includes(row.id);
              return (
                <tr
                  key={`ai-summary-${row.id}`}
                  style={{ backgroundColor: isSelected ? "rgba(181, 18, 27, 0.03)" : undefined }}
                >
                  <td style={{ textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => {
                        setSelectedGeneratedCaseIds((curr) =>
                          curr.includes(row.id) ? curr.filter((id) => id !== row.id) : [...curr, row.id]
                        );
                      }}
                      aria-label={`Select test case ${row.title}`}
                    />
                  </td>
                  <td>#{row.id}</td>
                  <td><strong>{row.title}</strong></td>
                  <td>{row.stepCount || "—"}</td>
                  <td>{renderStatusChip(row.status)}</td>
                  <td>
                    <div className="status-cell-stack">
                      <span>{row.confidenceLabel}</span>
                      {row.needsReview ? (
                        <button
                          type="button"
                          className="automation-chip review-chip"
                          onClick={() => {
                            const caseItem = selectedCases.find((item) => item.id === row.id);
                            if (caseItem) openTestCaseEditor(caseItem);
                          }}
                          title="Edit this test case and review its selectors"
                          aria-label={`Review selectors for ${row.title}`}
                        >
                          Review selectors
                        </button>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    <div className="table-actions">
                      {row.status.toLowerCase() !== "ready" ? (
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => {
                            const caseItem = selectedCases.find((item) => item.id === row.id);
                            if (caseItem) void updateGeneratedCaseStatus(caseItem, "ready");
                          }}
                          disabled={reviewingGeneratedCaseId === row.id}
                        >
                          {reviewingGeneratedCaseId === row.id ? "Saving..." : "Approve"}
                        </button>
                      ) : null}
                      {row.status.toLowerCase() !== "rejected" ? (
                        <button
                          type="button"
                          className="table-action btn-danger"
                          onClick={() => {
                            const caseItem = selectedCases.find((item) => item.id === row.id);
                            if (caseItem) void updateGeneratedCaseStatus(caseItem, "rejected");
                          }}
                          disabled={reviewingGeneratedCaseId === row.id}
                        >
                          Reject
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={7} className="muted">Generate cases to preview them here.</td></tr>}
          </tbody>
        </table>
      </Table>

    </>
  );

  const agentsView = (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-3 px-2">
        <button
          onClick={() => setAgentStudioTab("workspace")}
          className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
            agentStudioTab === "workspace"
              ? "bg-red-600 text-white shadow-md"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
          }`}
        >
          <span>⚡</span> Autonomous QA Agent Studio
        </button>
        <button
          onClick={() => setAgentStudioTab("recommendations")}
          className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
            agentStudioTab === "recommendations"
              ? "bg-red-600 text-white shadow-md"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
          }`}
        >
          <span>📋</span> AI Recommendations Board
        </button>
        <button
          onClick={() => setAgentStudioTab("audits")}
          className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
            agentStudioTab === "audits"
              ? "bg-red-600 text-white shadow-md"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
          }`}
        >
          <span>🎯</span> Autonomous Audits & Campaigns
        </button>
      </div>

      {agentStudioTab === "workspace" ? (
        <AgentTaskWorkspace
          token={token}
          applications={applications}
          selectedAppId={app?.id}
        />
      ) : agentStudioTab === "recommendations" ? (
        <AgentRecommendationsBoard
          appName={app?.name || "Application"}
          appId={app?.id}
          recommendations={agentRecommendations}
          analysis={preExecutionAnalysis}
          analyzing={analyzingAgents}
          onAnalyze={handleAnalyzeAgents}
          onReview={handleReviewAgentRecommendation}
          onOpenTestCases={() => navigateToSection("cases")}
        />
      ) : (
        <AutonomousAuditsStudio
          application={app}
          token={token}
          onNavigateToSection={navigateToSection}
        />
      )}
    </div>
  );

  const evidenceView = (
    <EvidenceGalleryView
      appName={app?.name || "Application"}
      token={token}
      screenshots={evidenceGallery.screenshots || []}
      videos={evidenceGallery.videos || []}
      onRefresh={() => loadEvidenceGallery(token, app?.id)}
      refreshing={refreshingEvidence}
    />
  );

  const settingsView = (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      <ObservabilityMetricsCard token={token} appId={app?.id} appName={app?.name} />
      <SettingsStudio
        config={aiConfigState}
        token={token}
        apiUrl={API_BASE_URL}
        onRefresh={() => loadAiConfiguration(token)}
        onTest={handleTestAiConfig}
        onSave={handleSaveAiConfig}
        onDiscoverModels={handleDiscoverAiModels}
      auditLogs={auditLogList}
      refreshingAuditLogs={refreshingAuditLogs}
      onRefreshAuditLogs={() => loadAuditLogs(token)}
      initialTab={section === "audit" ? "audit" : "ai"}
      integrations={{
        connections: integrationConnections,
        environmentConfiguration: integrationEnvironmentConfiguration,
        onRefresh: async () => {
          if (token) {
            await loadIntegrationConnections(token);
            await loadIntegrationEnvironmentConfiguration(token);
          }
        },
        onCreate: handleCreateIntegrationConnection,
        onUpdate: handleUpdateIntegrationConnection,
        onDelete: handleDeleteIntegrationConnection,
        onTest: handleTestIntegrationConnection,
        onSetActive: handleSetIntegrationConnectionActive,
        onLoadAssets: handleLoadIntegrationAssets,
        onUpdateEnvironment: handleUpdateIntegrationEnvironment,
        onSync: handleSyncIntegrationConnection,
        onLoadMappings: handleLoadConnectionMappings,
        onSaveMappings: handleSaveConnectionMappings,
      }}
    />
    </div>
  );

  const systemMapView = (
    <InteractiveSystemMap
      applications={apps}
      selectedApplication={app}
      testCases={testCases}
      automationReadinessByCaseId={automationReadinessByCaseId}
      runtimeParameters={runtimeParameters}
      onSelectApplication={selectApplication}
      onNavigateToSection={navigateToSection}
      onRunTestCase={(caseId) => {
        prepareTestCaseRun(caseId);
      }}
      onEditTestCase={(caseItem) => {
        openTestCaseEditor(caseItem);
      }}
      onGenerateForApp={(appName) => {
        focusApplication(appName);
        navigateToSection("aiGenerator");
      }}
    />
  );

  const executionWithResult = (
    <>
      {latestBuildReport ? (
        <CompleteBuildReportPanel
          report={latestBuildReport}
          token={token}
          onRetry={(failedIds) => { void runApplicationCaseTests(failedIds); }}
          onInspectRun={(runId) => router.push(`/test-execution/${runId}`)}
          onDismiss={() => setLatestBuildReport(null)}
          onReportDefect={openCreateDefectModal}
          onNavigateToHistory={() => navigateToSection("runHistory")}
        />
      ) : executionResult ? (
        <ExecutionSummaryPanel
          result={executionResult}
          token={token}
          onRetry={() => { void runApplicationCaseTests(); }}
          onInspect={() => router.push(`/test-execution/${executionResult.run_id}`)}
          onLogDefect={openCreateDefectModal}
        />
      ) : null}
      {execution}
    </>
  );

  const projectModalNode = projectModalMode && (
    <div
      className="projects-modal-overlay"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !projectFormName.trim() && !projectFormDescription.trim()) {
          closeProjectModal();
        }
      }}
    >
      <div
        className="panel projects-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="projects-modal-head">
          <div>
            <h3 id="project-modal-title">{projectModalMode === "create" ? "New project setup" : "Update project details"}</h3>
          </div>
          <button type="button" className="secondary btn-sm" onClick={closeProjectModal} aria-label="Close project modal">Close</button>
        </div>
        <p className="muted">Define the project context to keep applications, runs, and quality metrics organized.</p>
        <form
          className="projects-modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveProjectFromModal();
          }}
        >
          <label htmlFor="project-name">
            Project name <span aria-hidden="true">*</span>
          </label>
          <input
            id="project-name"
            value={projectFormName}
            onChange={(event) => {
              setProjectFormName(event.target.value);
              if (projectFormError) setProjectFormError("");
            }}
            placeholder="Example: Checkout Reliability"
            required
          />
          <label htmlFor="project-description">Description</label>
          <textarea
            id="project-description"
            value={projectFormDescription}
            onChange={(event) => setProjectFormDescription(event.target.value)}
            placeholder="Summarize scope, ownership, and quality goals."
          />
          <label htmlFor="project-lifecycle">Lifecycle</label>
          <select
            id="project-lifecycle"
            value={projectFormLifecycle}
            onChange={(event) => setProjectFormLifecycle(event.target.value as ProjectLifecycle)}
          >
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
          {projectFormError && <p className="form-error">{projectFormError}</p>}
          <div className="projects-modal-actions">
            <button type="button" className="secondary" onClick={closeProjectModal} disabled={savingProject}>Cancel</button>
            <button type="submit" className="primary" disabled={savingProject}>{savingProject ? "Saving..." : projectModalMode === "create" ? "Create project" : "Save changes"}</button>
          </div>
        </form>
      </div>
    </div>
  );

  const applicationModalNode = applicationEditingId !== null && (
    <div
      className="projects-modal-overlay"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !applicationFormName.trim() && !applicationFormTarget.trim()) {
          closeApplicationEditModal();
        }
      }}
    >
      <div
        className="panel projects-modal applications-edit-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="application-edit-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="projects-modal-head">
          <div>
            <h3 id="application-edit-modal-title">Update target and name</h3>
          </div>
          <button type="button" className="secondary btn-sm" onClick={closeApplicationEditModal} aria-label="Close application edit modal">
            Close
          </button>
        </div>
        <p className="muted">Keep application details current so AI discovery and execution run against the correct target.</p>
        <form
          className="projects-modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveApplicationFromModal();
          }}
        >
          <label htmlFor="application-edit-name">
            Application name <span aria-hidden="true">*</span>
          </label>
          <input
            id="application-edit-name"
            value={applicationFormName}
            onChange={(event) => {
              setApplicationFormName(event.target.value);
              setApplicationFormError("");
            }}
            placeholder="e.g. Customer Portal"
          />
          <label htmlFor="application-edit-platform">Platform</label>
          <input id="application-edit-platform" value={formatPlatformLabel(applicationFormPlatform)} disabled />
          <label htmlFor="application-edit-target">
            {applicationFormPlatform === "web" ? "Target URL" : "Package path"} <span aria-hidden="true">*</span>
          </label>
          <input
            id="application-edit-target"
            value={applicationFormTarget}
            onChange={(event) => {
              setApplicationFormTarget(event.target.value);
              setApplicationFormError("");
            }}
            placeholder={applicationFormPlatform === "web" ? "https://your-app.example.com" : "uploads/application-build.apk"}
          />
          {applicationFormError && <p className="form-error">{applicationFormError}</p>}
          <div className="projects-modal-actions">
            <button type="button" className="secondary" onClick={closeApplicationEditModal} disabled={savingApplicationEdit}>
              Cancel
            </button>
            <button type="submit" className="primary" disabled={savingApplicationEdit}>
              {savingApplicationEdit ? "Saving..." : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );

  const defectModalNode = defectModalMode && (
    <div
      className="projects-modal-overlay"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !defectFormTitle.trim() && !defectFormDescription.trim()) {
          closeDefectModal(false);
        }
      }}
    >
      <div
        className="panel projects-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="defect-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="projects-modal-head">
          <div>
            <h3 id="defect-modal-title">{defectModalMode === "create" ? "Capture a quality issue" : "Update defect details"}</h3>
          </div>
          <button type="button" className="secondary btn-sm" onClick={() => closeDefectModal(false)} disabled={savingDefect}>Close</button>
        </div>
        <form
          className="projects-modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveDefectFromModal();
          }}
        >
          <label htmlFor="defect-title">Title <span aria-hidden="true">*</span></label>
          <input id="defect-title" value={defectFormTitle} onChange={(event) => setDefectFormTitle(event.target.value)} required maxLength={200} placeholder="Brief summary of the issue" />
          <label htmlFor="defect-description">Description</label>
          <textarea id="defect-description" value={defectFormDescription} onChange={(event) => setDefectFormDescription(event.target.value)} rows={4} maxLength={4000} placeholder="Steps to reproduce, expected vs actual behavior, logs, or error messages..." />
          <div className="credential-grid">
            <label className="capture-label" htmlFor="defect-priority">Priority
              <select id="defect-priority" value={defectFormPriority} onChange={(event) => setDefectFormPriority(event.target.value)}>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
            <label className="capture-label" htmlFor="defect-severity">Severity
              <select id="defect-severity" value={defectFormSeverity} onChange={(event) => setDefectFormSeverity(event.target.value)}>
                <option value="critical">Critical</option>
                <option value="major">Major</option>
                <option value="minor">Minor</option>
              </select>
            </label>
            <label className="capture-label" htmlFor="defect-status">Status
              <select id="defect-status" value={defectFormStatus} onChange={(event) => setDefectFormStatus(event.target.value)}>
                <option value="open">Open</option>
                <option value="in progress">In progress</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
            </label>
            <label className="capture-label" htmlFor="defect-application">Application
              <select id="defect-application" value={defectFormApplicationId ? String(defectFormApplicationId) : ""} onChange={(event) => setDefectFormApplicationId(event.target.value ? Number(event.target.value) : null)}>
                <option value="">Unlinked</option>
                {apps.map((item) => <option key={`defect-app-${item.id}`} value={item.id}>{item.name}</option>)}
              </select>
            </label>
          </div>
          {defectFormError && <p className="form-error">{defectFormError}</p>}
          <div className="projects-modal-actions">
            <button type="button" className="secondary" onClick={() => closeDefectModal(false)} disabled={savingDefect}>Cancel</button>
            <button type="submit" className="primary" disabled={savingDefect}>{savingDefect ? "Saving..." : defectModalMode === "create" ? "Report defect" : "Save changes"}</button>
          </div>
        </form>
      </div>
    </div>
  );

  const views: SectionViewsMap = {
    dashboard,
    projects,
    applications: applicationView,
    cases,
    execution: executionWithResult,
    suites: suitesView,
    runHistory,
    evidence: evidenceView,
    defects: defectView,
    reports: reportsView,
    aiGenerator: aiGeneratorView,
    agents: agentsView,
    recommendations: agentsView,
    systemMap: systemMapView,
    settings: settingsView,
    audit: (
      <AutonomousAuditsStudio
        application={app}
        token={token}
        onNavigateToSection={navigateToSection}
      />
    ),
  };
  const navSections = navigationGroups.map((group) => ({
    id: group.id,
    label: group.label,
    items: nav.filter((item) => group.sections.includes(item.id)),
  }));

  return (
    <WorkspaceShell
      brandTitle={BRAND_TITLE}
      section={section}
      apps={apps}
      selectedApplication={app}
      projects={projectCatalog}
      selectedProjectId={selectedProjectId}
      onSelectProject={(projectId) => setSelectedProjectId(projectId)}
      onCreateProject={openCreateProjectModal}
      onCreateApplication={() => navigateToSection("applications")}
      mobileNavOpen={mobileNavOpen}
      navigationGroups={navSections}
      toast={toast}
      onMobileNavOpenChange={setMobileNavOpen}
      onSelectApplication={selectApplication}
      onNavigate={navigateToSection}
      onLogout={logout}
      onNotify={notify}
    >
      {views[section]}

      {projectModalNode}

      {applicationModalNode}

      {defectModalNode}

      {activeBuildReportModal && (
        <div
          className="projects-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setActiveBuildReportModal(null);
          }}
        >
          <div
            className="panel projects-modal"
            style={{
              maxWidth: "1150px",
              width: "95vw",
              maxHeight: "92vh",
              overflowY: "auto",
              padding: "16px",
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="build-report-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <CompleteBuildReportPanel
              report={activeBuildReportModal}
              token={token}
              onRetry={(failedIds) => {
                setActiveBuildReportModal(null);
                navigateToSection("execution");
                void runApplicationCaseTests(failedIds);
              }}
              onRebuild={(buildId, caseIds) => {
                setActiveBuildReportModal(null);
                void handleRebuildBuild(buildId, caseIds);
              }}
              onStopBuild={(buildId) => {
                void handleCancelBuild(buildId);
              }}
              onInspectRun={(runId) => {
                setActiveBuildReportModal(null);
                router.push(`/test-execution/${runId}`);
              }}
              onDismiss={() => setActiveBuildReportModal(null)}
              onReportDefect={() => {
                setActiveBuildReportModal(null);
                openCreateDefectModal();
              }}
              onNavigateToHistory={() => {
                setActiveBuildReportModal(null);
                navigateToSection("runHistory");
              }}
            />
          </div>
        </div>
      )}
    </WorkspaceShell>
  );
}
