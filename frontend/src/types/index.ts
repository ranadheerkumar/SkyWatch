export type Section =
	| "dashboard"
	| "projects"
	| "applications"
	| "cases"
	| "execution"
	| "defects"
	| "suites"
	| "reports"
	| "aiGenerator"
	| "agents"
	| "recommendations"
	| "systemMap"
	| "audit"
	| "settings"
	| "runHistory"
	| "evidence";
export type Platform = "web" | "android" | "ios";
export type AppIconName =
	| "overview"
	| "projects"
	| "applications"
	| "cases"
	| "execution"
	| "defects"
	| "suites"
	| "reports"
	| "ai"
	| "recommendations"
	| "map"
	| "audit"
	| "settings"
	| "logout"
	| "help"
	| "notifications"
	| "menu"
	| "close"
	| "chevron-left"
	| "chevron-right"
	| "timeout"
	| "warning";

export type Application = {
	id?: number;
	name: string;
	type: string;
	platform: Platform;
	url: string;
	cases: number;
	artifact?: string;
	target?: string;
};

export type RuntimeParameter = {
	id: string;
	key: string;
	value: string;
	sensitive: boolean;
};

export type TestCase = {
	id: number;
	application_id: number;
	title: string;
	description?: string;
	preconditions?: string;
	steps?: string;
	expected_result?: string;
	status: string;
	created_by: number;
	priority?: string;
	category?: string;
	automation_status?: string;
	tags?: string[];
	updated_at?: string;
};

export type Defect = {
	id: number;
	title: string;
	description?: string;
	priority: string;
	severity: string;
	status: string;
	application_id?: number;
	created_by: number;
	updated_at?: string;
	external_links?: Array<{
		id: number;
		system: string;
		external_key: string;
		external_url: string;
	}>;
};

export type FailureType =
	| "LOCATOR"
	| "TIMING"
	| "NAVIGATION"
	| "AUTHENTICATION"
	| "TEST_DATA"
	| "ENVIRONMENT"
	| "NETWORK"
	| "ASSERTION"
	| "APPLICATION_DEFECT"
	| "AUTOMATION_DEFECT"
	| "UNKNOWN";

export type ExecutionResult = {
	run_id: string;
	url: string;
	status: "passed" | "failed" | "error" | "cancelled";
	failure_type?: FailureType | null;
	failure_summary?: string | null;
	title?: string;
	duration_ms: number;
	audio_status?: "embedded" | "unavailable" | "disabled";
	screenshot_path?: string;
	checks: { type: string; value: string; passed: boolean; message: string }[];
	step_results?: { index: number; action: string; selector?: string; passed: boolean; message: string; duration_ms: number }[];
	step_artifacts?: { type: "screenshot" | "video" | "trace"; path: string; label: string; step_index?: number | null }[];
	artifacts?: { type: "screenshot" | "video" | "trace"; path: string; label: string }[];
	console_errors?: string[];
	network_errors?: string[];
	error?: string;
	healer_agent?: string | null;
	healed_steps?: Array<{
		index: number;
		reason?: string;
		duration_ms?: number;
		original_step?: { action?: string; selector?: string | null; value?: string | null };
		healed_step?: { action?: string; selector?: string | null; value?: string | null };
	}>;
};

export type ExecutionMode = "watch_live" | "background";
export type ExecutionSlowMode = "normal" | "demo" | "showcase";
export type ExecutionTraceMode = "off" | "on_failure" | "always";
export type VoiceGender = "male" | "female";
export type BackendExecutionState =
	| "QUEUED"
	| "STARTING"
	| "BROWSER_LAUNCHING"
	| "NAVIGATING"
	| "DISCOVERING"
	| "EXECUTING"
	| "WAITING"
	| "ASSERTING"
	| "CAPTURING_EVIDENCE"
	| "HEALING"
	| "PASSED"
	| "FAILED"
	| "CANCELLED";

export type RunStatusSnapshot = {
	status?: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	result?: ExecutionResult;
	log?: string;
	live_state?: BackendExecutionState | string;
	current_action?: string;
	detail?: string;
};

export type RunSummary = {
	run_id: string;
	application_id: number;
	batch_id?: string | null;
	build_name?: string | null;
	trigger_source?: string | null;
	status: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	created_at?: string;
	finished_at?: string;
};

export type BuildExecutionSummary = {
	build_id: string;
	application_id: number;
	name: string;
	status: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	trigger_source: string;
	total_cases: number;
	passed_count: number;
	failed_count: number;
	error_count: number;
	pass_rate: number;
	duration_ms: number;
	created_at?: string | null;
	finished_at?: string | null;
};

export type BuildCaseItem = {
	run_id: string;
	test_case_id?: number | null;
	title: string;
	status: string;
	duration_ms?: number | null;
	check_summary?: string | null;
	failure_type?: FailureType | string | null;
	failure_summary?: string | null;
	error?: string | null;
	created_at?: string | null;
	finished_at?: string | null;
	result?: ExecutionResult | null;
};

export type BuildExecutionDetail = {
	build_id: string;
	application_id: number;
	application_name: string;
	target_url: string;
	name: string;
	status: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	trigger_source: string;
	total_cases: number;
	passed_count: number;
	failed_count: number;
	error_count: number;
	pass_rate: number;
	duration_ms: number;
	created_at?: string | null;
	finished_at?: string | null;
	cases: BuildCaseItem[];
};

export type CaseExecutionSummary = {
	run_id: string;
	test_case_id: number;
	title: string;
	status: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	run_status: "queued" | "running" | "passed" | "failed" | "error" | "cancelled";
	url?: string;
	duration_ms?: number;
	check_summary?: string;
	failure_type?: FailureType | null;
	failure_summary?: string | null;
	created_at?: string;
	finished_at?: string;
};

export type CaseExecutionDetail = {
	run_id: string;
	test_case_id?: number | null;
	status: "queued" | "running" | "passed" | "failed" | "error";
	run_status: "queued" | "running" | "passed" | "failed" | "error";
	application_id?: number;
	steps?: Array<{ action: string; selector?: string; value?: string; secret_name?: string }>;
	created_at?: string;
	finished_at?: string;
	result?: ExecutionResult;
	log?: string;
	live_state?: BackendExecutionState | string;
	current_action?: string;
};

export type CaseExecutionResultItem = {
	caseId: number;
	title: string;
	order: number;
	runId?: string;
	status: "passed" | "failed" | "error" | "cancelled" | "pending" | "queued" | "running";
	durationMs?: number;
	detail?: string;
	result?: ExecutionResult | null;
};

export type BuildExecutionReport = {
	buildId: string;
	buildName?: string;
	applicationName: string;
	targetUrl: string;
	startedAt: number;
	finishedAt: number;
	totalDurationMs: number;
	totalCases: number;
	passedCount: number;
	failedCount: number;
	errorCount: number;
	passRate: number;
	overallStatus: "passed" | "failed" | "error" | "running" | "queued" | "cancelled";
	cases: CaseExecutionResultItem[];
};

export type AIGenerationMode = "provider" | "unknown";

export type AIGenerationSource = {
	mode: AIGenerationMode;
	provider: string;
	providerConfigured: boolean;
	note: string;
};

export type AIAgentStageStatus = "queued" | "running" | "completed" | "failed" | "skipped";

export type AIAgentStage = {
	key: string;
	name: string;
	responsibility: string;
	status: AIAgentStageStatus;
	progress: number;
	detail: string;
	started_at?: string | null;
	finished_at?: string | null;
	metrics?: Record<string, string | number | boolean>;
};

export type AIAgentDefinition = {
	key: string;
	name: string;
	source: string;
	version: string;
	checksum?: string | null;
};

export type AIDocumentFileAnalysis = {
	filename: string;
	extension: string;
	size_bytes: number;
	pages_parsed: number;
	requirements_found: number;
	features_identified: number;
	modules_identified: string[];
	business_rules_found: number;
	workflows_discovered: number;
	extracted_characters: number;
	warnings: string[];
};

export type AIDocumentAnalysis = {
	files: AIDocumentFileAnalysis[];
	total_files: number;
	total_pages: number;
	requirements_found: number;
	features_identified: number;
	modules_identified: string[];
	business_rules_found: number;
	workflows_discovered: number;
	extracted_characters: number;
	context_text: string;
	warnings: string[];
};

export type JiraIssueDetail = {
	key: string;
	id?: string | null;
	summary: string;
	description?: string | null;
	issue_type?: string | null;
	status?: string | null;
	priority?: string | null;
	labels: string[];
	components: string[];
	fix_versions: string[];
	assignee?: string | null;
	reporter?: string | null;
	url?: string | null;
	acceptance_criteria?: string | null;
	comments: string[];
	context_text: string;
	connection_id?: number | null;
	read_only?: boolean;
};

export type AIGenerationJob = {
	id: string;
	application_id: number;
	provider?: string | null;
	model?: string | null;
	status: "queued" | "running" | "completed" | "failed";
	phase: string;
	generated_count: number;
	valid_count: number;
	review_count: number;
	result?: {
		summary?: string;
		generation_mode?: AIGenerationMode;
		generation_note?: string;
		generation_provider?: string;
		workflow_version?: string;
		agent_definitions?: AIAgentDefinition[];
		document_names?: string[];
		application_context?: Record<string, unknown>;
		planner?: Record<string, unknown>;
		scenario_plan?: Record<string, unknown>;
		validation?: Record<string, unknown>;
		planner_used?: boolean;
		planner_provider?: string;
		planner_model?: string;
		planner_case_target?: number;
		generator_call_count?: number;
		agent_stages?: AIAgentStage[];
		case_ids?: number[];
		logs?: Array<{
			job_id?: string;
			stage?: string;
			level?: string;
			message: string;
			metadata?: Record<string, any>;
			timestamp?: number;
			iso_time?: string;
		}>;
	} | null;
	error?: string | null;
	created_at?: string | null;
	started_at?: string | null;
	finished_at?: string | null;
};

export type LiveCaseExecutionStatus = "pending" | "queued" | "running" | "passed" | "failed" | "error" | "cancelled" | "paused";

export type LiveCaseExecutionProgress = {
	caseId: number;
	title: string;
	order: number;
	status: LiveCaseExecutionStatus;
	runId?: string;
	detail: string;
	pollCount: number;
	queuedAt?: number;
	startedAt?: number;
	finishedAt?: number;
	durationMs?: number;
};

export type TestCaseAutomationReadiness = {
	test_case_id: number;
	title: string;
	status: string;
	has_automation: boolean;
	confidence_score: number;
	confidence_label: "high" | "medium" | "low";
	needs_manual_selector_review: boolean;
	reasons: string[];
};

export type TestSuite = {
	id: number;
	application_id: number;
	name: string;
	description?: string | null;
	case_ids: number[];
	case_count: number;
	created_by: number;
	created_at?: string;
	updated_at?: string;
};

export type ProjectLifecycle = "active" | "paused" | "archived";
export type ProjectHealthBucket = "healthy" | "watch" | "critical" | "noData";

export type WorkspaceProject = {
	id: string;
	name: string;
	description: string;
	lifecycle: ProjectLifecycle;
	owner: string;
	createdAt: string;
	updatedAt: string;
};

export type ProjectWorkspaceRow = {
	id: string;
	name: string;
	description: string;
	lifecycle: ProjectLifecycle;
	owner: string;
	applications: number;
	testCases: number;
	lastRunAt?: string;
	passRate: number;
	healthBucket: ProjectHealthBucket;
	healthLabel: string;
	openDefects: number;
	updatedAt: string;
};

export type ApplicationWorkspaceRow = {
	id: number | string;
	name: string;
	type: string;
	platform: Platform;
	url: string;
	totalCases: number;
	readyCases: number;
	draftCases: number;
	totalRuns: number;
	completedRuns: number;
	passRate: number;
	openDefects: number;
	lastRunAt?: string;
	automatedCases: number;
	selectorReviewCases: number;
	healthBucket: ProjectHealthBucket;
	healthLabel: string;
};

export type ProjectDetailTab = "overview" | "applications" | "cases" | "runs" | "results" | "insights";
export type ApplicationDetailTab = "overview" | "discovery";

export type ScriptFramework =
	| "playwright"
	| "cypress"
	| "selenium_python"
	| "robot"
	| "java_testng"
	| "jest_puppeteer";

export type FrameworkInfo = {
	id: string;
	name: string;
	language: string;
	file_extension: string;
};

export type ScriptOutput = {
	test_case_id: number;
	title: string;
	filename: string;
	code: string;
	framework: string;
	language: string;
};

export type ScriptSuiteOutput = {
	application_id: number;
	application_name: string;
	framework: string;
	language: string;
	total_cases: number;
	scripts: ScriptOutput[];
};

export type GitCommitResult = {
	sha: string;
	url: string;
	branch: string;
	path?: string;
	filename?: string;
	files_committed?: number;
	file_paths?: string[];
	repo?: string;
};

export type GitConnectionStatus = {
	success: boolean;
	message: string;
	provider?: string;
	repo?: string;
	default_branch?: string;
	permissions?: Record<string, boolean>;
};

export type GitRepo = {
	full_name: string;
	default_branch: string;
	private: boolean;
	html_url: string;
	description?: string;
};

// ============================================================================
// Unified Reporting Types (Jira + Xray + qTest + Execution Providers)
// ============================================================================

export type XrayPlanMetrics = {
	plan_key: string;
	plan_name: string;
	total_tests: number;
	executed_tests: number;
	passed: number;
	failed: number;
	blocked: number;
	skipped: number;
	not_executed: number;
	pass_rate: number;
	remaining_tests: number;
	environment?: string | null;
};

export type XraySetSummary = {
	set_key: string;
	name: string;
	test_count: number;
	passed: number;
	failed: number;
	pass_rate: number;
};

export type AutomationCoverageMetrics = {
	total_tests: number;
	manual_tests: number;
	automated_tests: number;
	partially_automated_tests: number;
	automation_candidates: number;
	automation_coverage_rate: number;
	automation_execution_rate: number;
	automation_pass_rate: number;
	manual_pass_rate: number;
};

export type TraceabilityGapType =
	| "NONE"
	| "REQUIREMENT_WITHOUT_TEST"
	| "TEST_WITHOUT_REQUIREMENT"
	| "UNTESTED_TEST"
	| "FAILING_WITHOUT_DEFECT"
	| "DEFECT_WITHOUT_TEST";

export type TraceabilityLink = {
	requirement_id?: string | null;
	requirement_key?: string | null;
	requirement_title?: string | null;
	requirement_source?: string | null;
	test_id: string;
	test_title: string;
	test_source: string;
	test_automation_status: string;
	last_execution_id?: string | null;
	execution_provider?: string | null;
	execution_status?: string | null;
	execution_duration_ms?: number | null;
	defect_id?: string | null;
	defect_key?: string | null;
	defect_title?: string | null;
	defect_status?: string | null;
	defect_severity?: string | null;
	defect_url?: string | null;
	release_version?: string | null;
	gap_type: TraceabilityGapType;
};

export type IntegrationHealthStatus = {
	system: string;
	name: string;
	status: "connected" | "degraded" | "disconnected" | "unconfigured";
	latency_ms?: number | null;
	last_sync_at?: string | null;
	last_error?: string | null;
	failed_sync_count: number;
	pending_jobs: number;
	base_url?: string | null;
};

export type UnifiedExecutionItem = {
	run_id: string;
	application_id?: number | null;
	test_case_id?: number | null;
	test_title: string;
	source_system: string;
	execution_provider: string;
	environment: string;
	browser?: string | null;
	device?: string | null;
	status: string;
	duration_ms: number;
	started_at?: string | null;
	finished_at?: string | null;
	artifacts?: Array<{ type: string; path: string; label: string }>;
	external_references?: Array<{ system: string; external_key: string; external_url: string; label: string }>;
};

export type DataFreshnessInfo = {
	system: string;
	last_synced_at?: string | null;
	is_live: boolean;
	sync_status: string;
};

export type UnifiedQualityReport = {
	id: string;
	project_id: string;
	application_id?: number | null;
	generated_at: string;
	summary: {
		quality_score: number;
		risk_score: number;
		release_readiness: string;
		total_cases: number;
		total_runs: number;
		completed_runs: number;
		passed_runs: number;
		failed_runs: number;
		pass_rate: number;
		failure_rate: number;
		open_defects: number;
		critical_defects: number;
		resolved_defects: number;
		automation_coverage_percent: number;
	};
	source_breakdown: Record<string, number>;
	provider_breakdown: Record<string, number>;
	xray_plans: XrayPlanMetrics[];
	xray_sets: XraySetSummary[];
	automation_metrics: AutomationCoverageMetrics;
	defect_metrics: {
		total_defects: number;
		open_defects: number;
		critical_defects: number;
		resolved_defects: number;
		aging: {
			under_3d: number;
			"3_to_7d": number;
			"7_to_14d": number;
			over_14d: number;
		};
	};
	data_freshness: Record<string, DataFreshnessInfo>;
	ai_insights: {
		facts: string[];
		analysis: string[];
		recommendations: string[];
	};
};

