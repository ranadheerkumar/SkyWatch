"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useDeferredValue } from "react";
import AppIcon from "./navigation/AppIcon";
import type { Application, Platform, RuntimeParameter, Section, TestCase, TestCaseAutomationReadiness } from "../types";

export interface InteractiveSystemMapProps {
  applications: Application[];
  selectedApplication: Application | null;
  testCases: TestCase[];
  automationReadinessByCaseId?: Record<number, TestCaseAutomationReadiness>;
  runtimeParameters?: RuntimeParameter[];
  onSelectApplication: (appName: string) => void;
  onNavigateToSection: (section: Section) => void;
  onRunTestCase?: (caseId: number) => void;
  onEditTestCase?: (caseItem: TestCase) => void;
  onGenerateForApp?: (appName: string) => void;
}

function formatPlatformLabel(platform: Platform) {
  if (platform === "web") return "Web";
  if (platform === "android") return "Android";
  return "iOS";
}

interface ArchNode {
  id: string;
  name: string;
  column: 1 | 2 | 3 | 4;
  group?: string;
  subtitle: string;
  badge?: string;
  badgeColor?: string;
  techStack?: string;
  stats?: string;
  applicationId?: number;
  appName?: string;
  url?: string;
  mappedCaseIds: number[];
  connectedNodeIds: string[];
  endpoints?: string[];
  tables?: string[];
  description?: string;
}

interface ArchLink {
  id: string;
  fromId: string;
  toId: string;
  category?: string;
}

interface ApiEndpointMapping {
  id: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | "REST";
  path: string;
  purpose: string;
  authRequired: boolean;
  requestParams: string[];
  expectedResponses: string[];
  mappedCaseIds: number[];
  applicationId: number;
  appName: string;
}

interface DatabaseEntityMapping {
  id: string;
  name: string;
  description: string;
  operationType: "Read / Query" | "Insert / Create" | "Update" | "Delete" | "State Verification";
  fields: string[];
  parameterTokens: string[];
  mappedCaseIds: number[];
  applicationId: number;
  appName: string;
}

interface UseCaseMapping {
  id: string;
  code: string;
  title: string;
  description: string;
  category: string;
  mappedCaseIds: number[];
  apiEndpoints: string[];
  databaseEntities: string[];
  readinessScore: number;
  applicationId: number;
  appName: string;
}

function inferUseCase(title: string, steps: string, category: string): { code: string; title: string; category: string } {
  const combined = `${title} ${steps} ${category}`.toLowerCase();
  if (combined.includes("login") || combined.includes("sign in") || combined.includes("auth") || combined.includes("credential") || combined.includes("password")) {
    return { code: "UC-AUTH", title: "Authentication & Access Control", category: "Security & Access" };
  }
  if (combined.includes("search") || combined.includes("filter") || combined.includes("find") || combined.includes("sort") || combined.includes("lookup")) {
    return { code: "UC-SRCH", title: "Search, Parameterized Query & Filtering", category: "Data Retrieval" };
  }
  if (combined.includes("create") || combined.includes("add") || combined.includes("save") || combined.includes("insert") || combined.includes("register") || combined.includes("submit")) {
    return { code: "UC-CRUD", title: "Entity Creation & Lifecycle Ingestion", category: "Core Business" };
  }
  if (combined.includes("edit") || combined.includes("update") || combined.includes("modify") || combined.includes("change")) {
    return { code: "UC-EDIT", title: "Entity Modification & State Updates", category: "Core Business" };
  }
  if (combined.includes("delete") || combined.includes("remove") || combined.includes("clear") || combined.includes("archive")) {
    return { code: "UC-DEL", title: "Entity Deletion & Archive Governance", category: "Data Governance" };
  }
  if (combined.includes("api") || combined.includes("contract") || combined.includes("schema") || combined.includes("endpoint") || combined.includes("json")) {
    return { code: "UC-API", title: "API Contract & Service Integration", category: "Integration Tier" };
  }
  if (combined.includes("performance") || combined.includes("latency") || combined.includes("load") || combined.includes("concurrency") || combined.includes("budget")) {
    return { code: "UC-PERF", title: "Performance, Latency & Load Resilience", category: "Non-Functional" };
  }
  if (combined.includes("keyboard") || combined.includes("accessibility") || combined.includes("a11y") || combined.includes("focus") || combined.includes("contrast")) {
    return { code: "UC-A11Y", title: "Accessibility & Assistive Navigation", category: "Compliance & UX" };
  }
  if (combined.includes("error") || combined.includes("invalid") || combined.includes("reject") || combined.includes("boundary") || combined.includes("negative")) {
    return { code: "UC-VAL", title: "Data Validation & Error Handling", category: "Boundary & Error" };
  }
  return { code: "UC-GEN", title: "Application Navigation & Workflow Verification", category: "Functional" };
}

function extractApiEndpointsFromCase(steps: string, targetUrl: string, appId: number, appName: string, caseId: number): ApiEndpointMapping[] {
  const endpoints: ApiEndpointMapping[] = [];
  const lines = steps.split(/\r?\n/);
  const foundPaths = new Set<string>();

  for (const line of lines) {
    const apiMatch = line.match(/\b(GET|POST|PUT|DELETE|PATCH)\s+([/\w\-_.]+)/i);
    if (apiMatch) {
      const method = apiMatch[1].toUpperCase() as ApiEndpointMapping["method"];
      const path = apiMatch[2];
      if (!foundPaths.has(path)) {
        foundPaths.add(path);
        endpoints.push({
          id: `${appId}-${method}-${path}`,
          method,
          path,
          purpose: `Endpoint verified in ${appName}`,
          authRequired: path.includes("auth") || path.includes("admin") || path.includes("cases") || path.includes("execution"),
          requestParams: line.includes("{{") ? Array.from(line.matchAll(/\{\{([A-Za-z0-9_.-]+)\}\}/g)).map((m) => m[1]) : [],
          expectedResponses: line.match(/\b(200|201|400|401|404|422|500)\b/) ? [line.match(/\b(200|201|400|401|404|422|500)\b/)![0]] : ["200 OK"],
          mappedCaseIds: [caseId],
          applicationId: appId,
          appName,
        });
      }
    }

    const routeMatch = line.match(/\bnavigate\s+(?:to\s+)?([/\w\-_.]+)/i) || line.match(/https?:\/\/[^\s)]+(\/[A-Za-z0-9_.\-/]+)/i);
    if (routeMatch && routeMatch[1].startsWith("/")) {
      const path = routeMatch[1];
      if (!foundPaths.has(path)) {
        foundPaths.add(path);
        endpoints.push({
          id: `${appId}-GET-${path}`,
          method: "GET",
          path,
          purpose: `UI Route Navigation for ${appName}`,
          authRequired: false,
          requestParams: [],
          expectedResponses: ["200 OK (DOM Ready)"],
          mappedCaseIds: [caseId],
          applicationId: appId,
          appName,
        });
      }
    }
  }

  if (!endpoints.length && targetUrl) {
    try {
      const parsed = new URL(targetUrl);
      const defaultPath = parsed.pathname || "/";
      endpoints.push({
        id: `${appId}-GET-${defaultPath}`,
        method: "GET",
        path: defaultPath,
        purpose: `Primary Target Endpoint for ${appName}`,
        authRequired: false,
        requestParams: [],
        expectedResponses: ["200 OK"],
        mappedCaseIds: [caseId],
        applicationId: appId,
        appName,
      });
    } catch {
      // ignore
    }
  }

  return endpoints;
}

function extractDatabaseEntitiesFromCase(
  title: string,
  steps: string,
  preconditions: string,
  appId: number,
  appName: string,
  caseId: number,
  runtimeParams: RuntimeParameter[],
): DatabaseEntityMapping[] {
  const entities: DatabaseEntityMapping[] = [];
  const text = `${title} ${steps} ${preconditions}`.toLowerCase();
  const foundEntities = new Set<string>();

  const entityKeywords: Record<string, { desc: string; fields: string[] }> = {
    users: { desc: "User identity, credentials, roles, and session tokens", fields: ["id", "email", "password_hash", "role", "created_at"] },
    applications: { desc: "Application workspace targets, URLs, and platforms", fields: ["id", "name", "platform", "target", "created_by"] },
    test_cases: { desc: "Structured test case definitions, steps, and expected results", fields: ["id", "title", "steps", "expected_result", "status", "priority"] },
    test_runs: { desc: "Execution runs, logs, durations, and status snapshots", fields: ["run_id", "application_id", "status", "duration_ms", "created_at"] },
    test_datasets: { desc: "Parameterized test data, test inputs, and boundary values", fields: ["id", "name", "data_rows", "application_id"] },
    defects: { desc: "Defect logs, failure categories, and severity ratings", fields: ["id", "title", "severity", "status", "run_id"] },
    audit_logs: { desc: "Security audit trail, user actions, and change records", fields: ["id", "action", "user_id", "resource_type", "created_at"] },
    clinics: { desc: "Clinic entities, locations, specialties, and schedules", fields: ["id", "name", "city", "specialty", "phone"] },
    owners: { desc: "Customer and owner profile records and addresses", fields: ["id", "first_name", "last_name", "address", "city", "telephone"] },
    orders: { desc: "Transaction records, line items, and checkout totals", fields: ["id", "order_number", "customer_id", "total_amount", "status"] },
  };

  for (const [entityName, meta] of Object.entries(entityKeywords)) {
    if (text.includes(entityName) || text.includes(entityName.replace(/s$/, "")) || (entityName === "clinics" && text.includes("clinic")) || (entityName === "owners" && text.includes("owner"))) {
      if (!foundEntities.has(entityName)) {
        foundEntities.add(entityName);
        const opType: DatabaseEntityMapping["operationType"] = text.includes("insert") || text.includes("create") || text.includes("add")
          ? "Insert / Create"
          : text.includes("update") || text.includes("edit")
            ? "Update"
            : text.includes("delete")
              ? "Delete"
              : "Read / Query";

        const paramsInStep = Array.from(text.matchAll(/\{\{([A-Za-z0-9_.-]+)\}\}/g)).map((m) => m[1]);

        entities.push({
          id: `${appId}-${entityName}`,
          name: entityName,
          description: meta.desc,
          operationType: opType,
          fields: meta.fields,
          parameterTokens: paramsInStep,
          mappedCaseIds: [caseId],
          applicationId: appId,
          appName,
        });
      }
    }
  }

  const explicitParams = Array.from(new Set(Array.from(text.matchAll(/\{\{([A-Za-z0-9_.-]+)\}\}/g)).map((m) => m[1])));
  if (explicitParams.length > 0 && !foundEntities.has("parameter_store")) {
    entities.push({
      id: `${appId}-runtime-parameters`,
      name: "runtime_parameters",
      description: "Ephemeral runtime test data and parameterized execution variables",
      operationType: "Read / Query",
      fields: explicitParams,
      parameterTokens: explicitParams,
      mappedCaseIds: [caseId],
      applicationId: appId,
      appName,
    });
  }

  return entities;
}

export default function InteractiveSystemMap({
  applications,
  selectedApplication,
  testCases,
  automationReadinessByCaseId = {},
  runtimeParameters = [],
  onSelectApplication,
  onNavigateToSection,
  onRunTestCase,
  onEditTestCase,
  onGenerateForApp,
}: InteractiveSystemMapProps) {
  const [filterScope, setFilterScope] = useState<string>(selectedApplication?.name ?? "ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const deferredSearchQuery = useDeferredValue(searchQuery);

  // Interactive Graph States
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [expandedStepsCaseId, setExpandedStepsCaseId] = useState<number | null>(null);
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number; width: number; height: number }>>({});
  const [highlightAllPaths, setHighlightAllPaths] = useState(false);

  // Filter test cases by selected app or all
  const filteredCases = useMemo(() => {
    if (filterScope === "ALL") return testCases;
    const targetApp = applications.find((a) => a.name === filterScope);
    if (!targetApp || typeof targetApp.id !== "number") return testCases;
    return testCases.filter((tc) => tc.application_id === targetApp.id);
  }, [testCases, filterScope, applications]);

  const activeApps = useMemo(() => {
    if (filterScope === "ALL") return applications;
    return applications.filter((a) => a.name === filterScope);
  }, [applications, filterScope]);

  // Dynamic Analysis Derived Strictly From Workspace Data & Test Cases
  const analysis = useMemo(() => {
    const apiMap = new Map<string, ApiEndpointMapping>();
    const dbMap = new Map<string, DatabaseEntityMapping>();
    const useCaseMap = new Map<string, UseCaseMapping>();
    const externalSystemMap = new Map<string, { id: string; name: string; subtitle: string; badge: string; mappedCaseIds: number[]; applicationId: number; appName: string }>();

    for (const caseItem of filteredCases) {
      const app = applications.find((a) => a.id === caseItem.application_id) ?? {
        id: caseItem.application_id,
        name: `App ${caseItem.application_id}`,
        platform: "web" as Platform,
        url: "",
        cases: 0,
      };

      const stepsText = caseItem.steps || "";
      const preText = caseItem.preconditions || "";
      const cat = (caseItem.category || "functional").toLowerCase();
      const useCaseInfo = inferUseCase(caseItem.title, stepsText, cat);
      const readiness = automationReadinessByCaseId[caseItem.id] ?? {
        confidence_score: 85,
        confidence_label: "high" as const,
        needs_manual_selector_review: false,
        reasons: [],
      };

      // Extract APIs
      const targetUrl = app.url || ("target" in app && typeof app.target === "string" ? app.target : "") || "";
      const apis = extractApiEndpointsFromCase(stepsText, targetUrl, app.id ?? 0, app.name, caseItem.id);
      const apiTouchpointNames: string[] = [];
      for (const api of apis) {
        apiTouchpointNames.push(`${api.method} ${api.path}`);
        if (apiMap.has(api.id)) {
          const existing = apiMap.get(api.id)!;
          if (!existing.mappedCaseIds.includes(caseItem.id)) {
            existing.mappedCaseIds.push(caseItem.id);
          }
        } else {
          apiMap.set(api.id, { ...api });
        }
      }

      // Extract DB Entities
      const dbs = extractDatabaseEntitiesFromCase(caseItem.title, stepsText, preText, app.id ?? 0, app.name, caseItem.id, runtimeParameters);
      const dbTouchpointNames: string[] = [];
      for (const db of dbs) {
        dbTouchpointNames.push(db.name);
        if (dbMap.has(db.id)) {
          const existing = dbMap.get(db.id)!;
          if (!existing.mappedCaseIds.includes(caseItem.id)) {
            existing.mappedCaseIds.push(caseItem.id);
          }
        } else {
          dbMap.set(db.id, { ...db });
        }
      }

      // Populate Use Case Map
      const ucKey = `${app.id}-${useCaseInfo.code}`;
      if (useCaseMap.has(ucKey)) {
        const existing = useCaseMap.get(ucKey)!;
        if (!existing.mappedCaseIds.includes(caseItem.id)) {
          existing.mappedCaseIds.push(caseItem.id);
        }
        for (const apiName of apiTouchpointNames) {
          if (!existing.apiEndpoints.includes(apiName)) existing.apiEndpoints.push(apiName);
        }
        for (const dbName of dbTouchpointNames) {
          if (!existing.databaseEntities.includes(dbName)) existing.databaseEntities.push(dbName);
        }
      } else {
        useCaseMap.set(ucKey, {
          id: ucKey,
          code: useCaseInfo.code,
          title: useCaseInfo.title,
          description: `Covers ${useCaseInfo.title.toLowerCase()} for ${app.name}`,
          category: useCaseInfo.category,
          mappedCaseIds: [caseItem.id],
          apiEndpoints: [...apiTouchpointNames],
          databaseEntities: [...dbTouchpointNames],
          readinessScore: readiness.confidence_score,
          applicationId: app.id ?? 0,
          appName: app.name,
        });
      }

      // Check for external services mentioned in steps (e.g. Jira, Email, Payment, Twilio, OAuth)
      const lowerCombined = `${caseItem.title} ${stepsText} ${preText}`.toLowerCase();
      const checkExternalServices = [
        { key: "jira", name: "Jira Issue Tracking", badge: "Issue Tracker", test: /\bjira\b/ },
        { key: "qtest", name: "qTest Test Ops", badge: "Test Management", test: /\bqtest\b/ },
        { key: "email", name: "Email / Notification Service", badge: "Notification", test: /\b(email|sendgrid|mail|smtp|inbox)\b/ },
        { key: "payment", name: "Payment Gateway", badge: "Payment", test: /\b(payment|stripe|card|checkout|billing|invoice)\b/ },
        { key: "sms", name: "SMS / Telephony Service", badge: "SMS Gateway", test: /\b(sms|twilio|phone|otp|text message)\b/ },
        { key: "auth0", name: "SSO / Identity Provider", badge: "OAuth / SSO", test: /\b(oauth|sso|saml|identity provider|auth0|cognito)\b/ },
      ];
      for (const ext of checkExternalServices) {
        if (ext.test.test(lowerCombined)) {
          const extId = `${app.id}-${ext.key}`;
          if (externalSystemMap.has(extId)) {
            const existing = externalSystemMap.get(extId)!;
            if (!existing.mappedCaseIds.includes(caseItem.id)) {
              existing.mappedCaseIds.push(caseItem.id);
            }
          } else {
            externalSystemMap.set(extId, {
              id: extId,
              name: ext.name,
              subtitle: `External touchpoint in ${app.name}`,
              badge: ext.badge,
              mappedCaseIds: [caseItem.id],
              applicationId: app.id ?? 0,
              appName: app.name,
            });
          }
        }
      }
    }

    const apisList = Array.from(apiMap.values());
    const dbList = Array.from(dbMap.values());
    const useCasesList = Array.from(useCaseMap.values());
    const externalsList = Array.from(externalSystemMap.values());

    return {
      apis: apisList,
      databases: dbList,
      useCases: useCasesList,
      externals: externalsList,
      totalAppsCount: activeApps.length,
      totalCasesCount: filteredCases.length,
      readyCasesCount: filteredCases.filter((tc) => tc.status === "ready").length,
      apiCoverageCount: apisList.length,
      dbEntitiesCount: dbList.length,
      useCasesCount: useCasesList.length,
    };
  }, [filteredCases, activeApps, applications, automationReadinessByCaseId, runtimeParameters]);

  // Dynamic Multi-Column Graph Derived Purely From Real Data
  const architectureGraph = useMemo(() => {
    const col1Nodes: ArchNode[] = [];
    const col2Nodes: ArchNode[] = [];
    const col3Nodes: ArchNode[] = [];
    const col4Nodes: ArchNode[] = [];
    const links: ArchLink[] = [];

    // ── Column 1: Front-End Applications ──
    for (const appItem of activeApps) {
      const appCases = filteredCases.filter((tc) => tc.application_id === appItem.id);
      const caseIds = appCases.map((tc) => tc.id);
      const appId = `app-${appItem.id}`;

      col1Nodes.push({
        id: appId,
        name: appItem.name,
        column: 1,
        group: appItem.name.toUpperCase(),
        subtitle: `${formatPlatformLabel(appItem.platform)} · ${appCases.length} test case(s)`,
        badge: formatPlatformLabel(appItem.platform),
        badgeColor: "#3b82f6",
        techStack: `${formatPlatformLabel(appItem.platform)} Platform`,
        url: appItem.url || ("target" in appItem && typeof appItem.target === "string" ? appItem.target : "") || "",
        applicationId: appItem.id,
        appName: appItem.name,
        mappedCaseIds: caseIds,
        connectedNodeIds: [],
        description: `Client application target ${appItem.name} (${formatPlatformLabel(appItem.platform)})`,
      });
    }

    // ── Column 2: BFF & API Services ──
    if (analysis.apis.length > 0) {
      for (const api of analysis.apis) {
        const apiNodeId = `api-${api.id}`;
        col2Nodes.push({
          id: apiNodeId,
          name: `${api.method} ${api.path}`,
          column: 2,
          group: api.appName.toUpperCase(),
          subtitle: `${api.purpose} · ${api.mappedCaseIds.length} case(s)`,
          badge: api.authRequired ? "Auth JWT" : "HTTP Route",
          badgeColor: "#6366f1",
          techStack: "REST Endpoint",
          endpoints: [api.path],
          mappedCaseIds: api.mappedCaseIds,
          connectedNodeIds: [],
          applicationId: api.applicationId,
          appName: api.appName,
          description: `Discovered API endpoint (${api.method} ${api.path}) validated during test execution.`,
        });

        // Link from app to this API
        const appNodeId = `app-${api.applicationId}`;
        if (col1Nodes.some((n) => n.id === appNodeId)) {
          links.push({
            id: `l-${appNodeId}-${apiNodeId}`,
            fromId: appNodeId,
            toId: apiNodeId,
          });
        }
      }
    } else {
      // Fallback if no specific endpoints extracted: create clean API/Router per app
      for (const appItem of activeApps) {
        const appCases = filteredCases.filter((tc) => tc.application_id === appItem.id);
        const apiNodeId = `api-gw-${appItem.id}`;
        col2Nodes.push({
          id: apiNodeId,
          name: `${appItem.name} API Gateway`,
          column: 2,
          group: appItem.name.toUpperCase(),
          subtitle: `HTTP Navigation & API routes (${appCases.length} cases)`,
          badge: "API Gateway",
          badgeColor: "#6366f1",
          techStack: "HTTP Router",
          endpoints: [appItem.url || "/"],
          mappedCaseIds: appCases.map((tc) => tc.id),
          connectedNodeIds: [],
          applicationId: appItem.id,
          appName: appItem.name,
          description: `API and navigation gateway for ${appItem.name}.`,
        });

        const appNodeId = `app-${appItem.id}`;
        links.push({
          id: `l-${appNodeId}-${apiNodeId}`,
          fromId: appNodeId,
          toId: apiNodeId,
        });
      }
    }

    // ── Column 3: Data Stores ──
    if (analysis.databases.length > 0) {
      for (const db of analysis.databases) {
        const dbNodeId = `db-${db.id}`;
        col3Nodes.push({
          id: dbNodeId,
          name: db.name,
          column: 3,
          group: db.appName.toUpperCase(),
          subtitle: `${db.operationType} · ${db.mappedCaseIds.length} case(s)`,
          badge: db.name.includes("parameter") ? "Parameters" : "Schema Entity",
          badgeColor: "#f59e0b",
          techStack: "Database / State",
          tables: db.fields,
          mappedCaseIds: db.mappedCaseIds,
          connectedNodeIds: [],
          applicationId: db.applicationId,
          appName: db.appName,
          description: db.description,
        });

        // Link from APIs sharing the same app/case to this DB
        const matchingApiNodes = col2Nodes.filter(
          (apiNode) => apiNode.applicationId === db.applicationId && apiNode.mappedCaseIds.some((cid) => db.mappedCaseIds.includes(cid)),
        );
        if (matchingApiNodes.length > 0) {
          for (const apiNode of matchingApiNodes) {
            links.push({
              id: `l-${apiNode.id}-${dbNodeId}`,
              fromId: apiNode.id,
              toId: dbNodeId,
            });
          }
        } else {
          // Link first matching app API or any API in the app
          const appApiNode = col2Nodes.find((apiNode) => apiNode.applicationId === db.applicationId);
          if (appApiNode) {
            links.push({
              id: `l-${appApiNode.id}-${dbNodeId}`,
              fromId: appApiNode.id,
              toId: dbNodeId,
            });
          }
        }
      }
    } else {
      // Fallback state store per app
      for (const appItem of activeApps) {
        const appCases = filteredCases.filter((tc) => tc.application_id === appItem.id);
        const dbNodeId = `db-store-${appItem.id}`;
        col3Nodes.push({
          id: dbNodeId,
          name: `${appItem.name} State Store`,
          column: 3,
          group: appItem.name.toUpperCase(),
          subtitle: "Runtime parameters & session store",
          badge: "State Storage",
          badgeColor: "#f59e0b",
          techStack: "Storage & State",
          tables: ["session_context", "runtime_params"],
          mappedCaseIds: appCases.map((tc) => tc.id),
          connectedNodeIds: [],
          applicationId: appItem.id,
          appName: appItem.name,
          description: `Local storage, cookies, session cache, and parameter state for ${appItem.name}.`,
        });

        const appApiNodes = col2Nodes.filter((apiNode) => apiNode.applicationId === appItem.id);
        for (const apiNode of appApiNodes) {
          links.push({
            id: `l-${apiNode.id}-${dbNodeId}`,
            fromId: apiNode.id,
            toId: dbNodeId,
          });
        }
      }
    }

    // ── Column 4: External Systems & Scenarios ──
    if (analysis.useCases.length > 0) {
      for (const uc of analysis.useCases) {
        const scenNodeId = `scen-${uc.id}`;
        col4Nodes.push({
          id: scenNodeId,
          name: uc.title,
          column: 4,
          group: uc.appName.toUpperCase(),
          subtitle: `${uc.category} · ${uc.mappedCaseIds.length} scenario(s)`,
          badge: uc.code,
          badgeColor: "#10b981",
          techStack: `${uc.mappedCaseIds.length} Test Scenario(s)`,
          mappedCaseIds: uc.mappedCaseIds,
          connectedNodeIds: [],
          applicationId: uc.applicationId,
          appName: uc.appName,
          description: uc.description,
        });

        // Link from DB nodes that share cases with this scenario
        const matchingDbNodes = col3Nodes.filter(
          (dbNode) => dbNode.applicationId === uc.applicationId && dbNode.mappedCaseIds.some((cid) => uc.mappedCaseIds.includes(cid)),
        );
        if (matchingDbNodes.length > 0) {
          for (const dbNode of matchingDbNodes) {
            links.push({
              id: `l-${dbNode.id}-${scenNodeId}`,
              fromId: dbNode.id,
              toId: scenNodeId,
            });
          }
        } else {
          // Link first matching DB in the app
          const appDbNode = col3Nodes.find((dbNode) => dbNode.applicationId === uc.applicationId);
          if (appDbNode) {
            links.push({
              id: `l-${appDbNode.id}-${scenNodeId}`,
              fromId: appDbNode.id,
              toId: scenNodeId,
            });
          }
        }
      }
    }

    // Also add any external services detected in test cases
    for (const ext of analysis.externals) {
      const extNodeId = `ext-${ext.id}`;
      col4Nodes.push({
        id: extNodeId,
        name: ext.name,
        column: 4,
        group: ext.appName.toUpperCase(),
        subtitle: `${ext.subtitle} (${ext.mappedCaseIds.length} case(s))`,
        badge: ext.badge,
        badgeColor: "#10b981",
        techStack: "External Service",
        mappedCaseIds: ext.mappedCaseIds,
        connectedNodeIds: [],
        applicationId: ext.applicationId,
        appName: ext.appName,
        description: `External partner or service dependency (${ext.name}) verified in test cases.`,
      });

      // Link DB/API to this external service
      const appDbNode = col3Nodes.find((dbNode) => dbNode.applicationId === ext.applicationId);
      if (appDbNode) {
        links.push({
          id: `l-${appDbNode.id}-${extNodeId}`,
          fromId: appDbNode.id,
          toId: extNodeId,
        });
      }
    }

    // Deduplicate links
    const uniqueLinks: ArchLink[] = [];
    const seenLinkKeys = new Set<string>();
    for (const link of links) {
      const key = `${link.fromId}->${link.toId}`;
      if (!seenLinkKeys.has(key)) {
        seenLinkKeys.add(key);
        uniqueLinks.push(link);
      }
    }

    const allNodes = [...col1Nodes, ...col2Nodes, ...col3Nodes, ...col4Nodes];

    return {
      nodes: allNodes,
      links: uniqueLinks,
      column1: col1Nodes,
      column2: col2Nodes,
      column3: col3Nodes,
      column4: col4Nodes,
    };
  }, [activeApps, filteredCases, analysis]);

  // Compute Active Connected Node IDs
  const activeFocusId = hoveredNodeId || selectedNodeId;
  const connectedNodeIds = useMemo(() => {
    if (!activeFocusId) return new Set<string>();
    const visited = new Set<string>([activeFocusId]);
    const queue = [activeFocusId];

    while (queue.length) {
      const current = queue.shift()!;
      for (const link of architectureGraph.links) {
        if (link.fromId === current && !visited.has(link.toId)) {
          visited.add(link.toId);
          queue.push(link.toId);
        }
        if (link.toId === current && !visited.has(link.fromId)) {
          visited.add(link.fromId);
          queue.push(link.fromId);
        }
      }
    }
    return visited;
  }, [activeFocusId, architectureGraph.links]);

  // Measure and update DOM bounding positions for SVG connection lines
  const updateNodePositions = useCallback(() => {
    if (!containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const newPositions: Record<string, { x: number; y: number; width: number; height: number }> = {};

    for (const node of architectureGraph.nodes) {
      const el = document.getElementById(`arch-node-${node.id}`);
      if (el) {
        const rect = el.getBoundingClientRect();
        newPositions[node.id] = {
          x: rect.left - containerRect.left,
          y: rect.top - containerRect.top,
          width: rect.width,
          height: rect.height,
        };
      }
    }
    setNodePositions(newPositions);
  }, [architectureGraph.nodes]);

  useEffect(() => {
    const timer = setTimeout(() => {
      updateNodePositions();
    }, 100);
    const handleResize = () => updateNodePositions();
    window.addEventListener("resize", handleResize);

    const observer = new ResizeObserver(() => updateNodePositions());
    if (containerRef.current) observer.observe(containerRef.current);

    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", handleResize);
      observer.disconnect();
    };
  }, [updateNodePositions, architectureGraph]);

  const handleDownloadJson = () => {
    const filename = `system-architecture-flow-${filterScope.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
    const blob = new Blob([JSON.stringify({ analysis, graph: architectureGraph }, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Selected Node Data for Inspector
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return architectureGraph.nodes.find((n) => n.id === selectedNodeId) ?? null;
  }, [selectedNodeId, architectureGraph.nodes]);

  const selectedNodeTestCases = useMemo(() => {
    if (!selectedNode) return [];
    if (selectedNode.mappedCaseIds.length > 0) {
      return testCases.filter((tc) => selectedNode.mappedCaseIds.includes(tc.id));
    }
    return testCases.filter((tc) => tc.application_id === selectedNode.applicationId);
  }, [selectedNode, testCases]);

  return (
    <div className="interactive-system-map-workspace" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {/* ─── HERO HEADER BANNER ─── */}
      <div className="agent-hero-banner" style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #172554 100%)", padding: "8px 14px", marginBottom: "4px" }}>
        <div className="agent-hero-head">
          <div>
            <div className="agent-hero-badge" style={{ background: "rgba(59, 130, 246, 0.2)", borderColor: "rgba(96, 165, 250, 0.4)", color: "#93c5fd" }}>
              <span className="agent-hero-pulse" style={{ background: "#60a5fa", boxShadow: "0 0 8px #60a5fa" }} />
              Architecture &amp; Test Flow Diagram
            </div>
            <h2 className="agent-hero-title">System Architecture &amp; Test Flow Engine</h2>
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={handleDownloadJson} title="Export architecture flow graph as JSON">
              Export Flow JSON
            </button>
            {onGenerateForApp ? (
              <button
                type="button"
                className="btn btn-emerald btn-sm"
                onClick={() => onGenerateForApp(filterScope === "ALL" ? (applications[0]?.name ?? "") : filterScope)}
              >
                + Generate Test Scenarios
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {/* ─── ARCHITECTURE & FLOW DIAGRAM PANEL ─── */}
      <div className="arch-diagram-wrapper">
        {/* Real Dynamic Stat Counters */}
        <div className="arch-stat-counters-row">
          <div className="arch-stat-card">
            <span className="arch-stat-label">APPLICATIONS</span>
            <strong className="arch-stat-value">{analysis.totalAppsCount}</strong>
          </div>
          <div className="arch-stat-card">
            <span className="arch-stat-label">DISCOVERED APIS</span>
            <strong className="arch-stat-value" style={{ color: "#2563eb" }}>{analysis.apiCoverageCount}</strong>
          </div>
          <div className="arch-stat-card">
            <span className="arch-stat-label">DATABASE ENTITIES</span>
            <strong className="arch-stat-value" style={{ color: "#d97706" }}>{analysis.dbEntitiesCount}</strong>
          </div>
          <div className="arch-stat-card">
            <span className="arch-stat-label">TEST SCENARIOS</span>
            <strong className="arch-stat-value" style={{ color: "#059669" }}>{analysis.totalCasesCount}</strong>
          </div>
        </div>

        {/* Scope Controls & Canvas Toolbar */}
        <div className="arch-diagram-toolbar">
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <label htmlFor="system-map-app-select" style={{ fontWeight: 700, fontSize: "13px", display: "flex", alignItems: "center", gap: "6px" }}>
              Scope:
              <select
                id="system-map-app-select"
                value={filterScope}
                onChange={(e) => {
                  setFilterScope(e.target.value);
                  if (e.target.value !== "ALL") onSelectApplication(e.target.value);
                }}
                className="settings-select"
                style={{ fontWeight: 600, minWidth: "200px" }}
              >
                <option value="ALL">🌐 All Applications (Global Topology)</option>
                {applications.map((app) => (
                  <option key={`map-app-opt-${app.id}`} value={app.name}>
                    {app.name} ({formatPlatformLabel(app.platform)})
                  </option>
                ))}
              </select>
            </label>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search systems, APIs, tables, or cases..."
                className="settings-input"
                style={{ minWidth: "260px" }}
              />
              {searchQuery && (
                <button type="button" className="table-action" onClick={() => setSearchQuery("")}>
                  Clear
                </button>
              )}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {selectedNodeId ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => { setSelectedNodeId(null); setHoveredNodeId(null); }}
              >
                Reset Focus
              </button>
            ) : null}
            <button
              type="button"
              className={`btn ${highlightAllPaths ? "btn-indigo" : "btn-secondary"} btn-sm`}
              onClick={() => setHighlightAllPaths(!highlightAllPaths)}
            >
              {highlightAllPaths ? "✓ Showing All Paths" : "Highlight All Paths"}
            </button>
          </div>
        </div>

        {/* Canvas Container with Multi-Column Blocks & SVG Curved Arrows */}
        <div className="arch-canvas-container" ref={containerRef}>
          {/* SVG Overlay for Bezier Connectors */}
          <svg className="arch-svg-overlay">
            <defs>
              <marker
                id="arrow-default"
                viewBox="0 0 10 10"
                refX="6"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 1 L 8 5 L 0 9 z" fill="#94a3b8" />
              </marker>
              <marker
                id="arrow-active"
                viewBox="0 0 10 10"
                refX="6"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 1 L 8 5 L 0 9 z" fill="#4f46e5" />
              </marker>
              <marker
                id="arrow-connected"
                viewBox="0 0 10 10"
                refX="6"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 1 L 8 5 L 0 9 z" fill="#10b981" />
              </marker>
            </defs>

            {/* Draw All Link Curves */}
            {architectureGraph.links.map((link) => {
              const fromPos = nodePositions[link.fromId];
              const toPos = nodePositions[link.toId];
              if (!fromPos || !toPos) return null;

              const x1 = fromPos.x + fromPos.width;
              const y1 = fromPos.y + fromPos.height / 2;
              const x2 = toPos.x;
              const y2 = toPos.y + toPos.height / 2;

              const dx = Math.max(24, Math.abs(x2 - x1) * 0.45);
              const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

              const isDirectLink = activeFocusId === link.fromId || activeFocusId === link.toId;
              const isConnectedPath = (connectedNodeIds.has(link.fromId) && connectedNodeIds.has(link.toId)) || highlightAllPaths;
              const isDimmed = Boolean(activeFocusId && !isDirectLink && !isConnectedPath);

              return (
                <path
                  key={`curve-${link.id}`}
                  d={pathD}
                  fill="none"
                  stroke={isDirectLink ? "#4f46e5" : isConnectedPath ? "#10b981" : "#94a3b8"}
                  strokeWidth={isDirectLink ? 2.5 : isConnectedPath ? 2 : 1.25}
                  strokeOpacity={isDimmed ? 0.08 : isDirectLink ? 1 : isConnectedPath ? 0.85 : 0.35}
                  strokeDasharray={isDirectLink || (highlightAllPaths && isConnectedPath) ? "6 4" : undefined}
                  style={{
                    animation: isDirectLink ? "archDashFlow 1.2s linear infinite" : undefined,
                    transition: "stroke 0.2s ease, stroke-width 0.2s ease, stroke-opacity 0.2s ease",
                  }}
                  markerEnd={isDirectLink ? "url(#arrow-active)" : isConnectedPath ? "url(#arrow-connected)" : "url(#arrow-default)"}
                />
              );
            })}
          </svg>

          {/* 4 Architectural Columns */}
          <div className="arch-columns-grid">
            {/* Column 1: FRONT-END APPLICATIONS */}
            <div className="arch-column">
              <div className="arch-column-header">
                <span className="arch-column-title">FRONT-END APPLICATIONS</span>
                <span className="arch-column-subtitle">Client Web, Android, iOS Platforms</span>
              </div>
              <div className="arch-node-list">
                {architectureGraph.column1.map((node) => {
                  const isActive = selectedNodeId === node.id || hoveredNodeId === node.id;
                  const isConnected = connectedNodeIds.has(node.id) && !isActive;
                  const isDimmed = Boolean(activeFocusId && !isActive && !isConnected);
                  const isSearchMatch = Boolean(deferredSearchQuery && node.name.toLowerCase().includes(deferredSearchQuery.toLowerCase()));

                  return (
                    <div
                      key={`node-${node.id}`}
                      id={`arch-node-${node.id}`}
                      className={`arch-node-card ${isActive ? "active" : ""} ${isConnected ? "connected" : ""} ${isDimmed ? "dimmed" : ""}`}
                      style={{ borderColor: isSearchMatch ? "#4f46e5" : undefined }}
                      onClick={() => setSelectedNodeId(selectedNodeId === node.id ? null : node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      <div className="arch-node-head">
                        <strong className="arch-node-name">{node.name}</strong>
                        {node.badge && (
                          <span className="arch-node-badge" style={{ background: isActive ? "rgba(79, 70, 229, 0.15)" : undefined, color: isActive ? "#4f46e5" : undefined }}>
                            {node.badge}
                          </span>
                        )}
                      </div>
                      <span className="arch-node-sub">{node.subtitle}</span>
                      {node.mappedCaseIds.length > 0 && (
                        <div className="arch-node-tc-pill">
                          <span>✓</span>
                          <span>{node.mappedCaseIds.length} Test Cases Mapped</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Column 2: BFF & API SERVICES */}
            <div className="arch-column">
              <div className="arch-column-header">
                <span className="arch-column-title">BFF &amp; API SERVICES</span>
                <span className="arch-column-subtitle">REST Gateways, Routes &amp; Microservices</span>
              </div>
              <div className="arch-node-list">
                {architectureGraph.column2.map((node) => {
                  const isActive = selectedNodeId === node.id || hoveredNodeId === node.id;
                  const isConnected = connectedNodeIds.has(node.id) && !isActive;
                  const isDimmed = Boolean(activeFocusId && !isActive && !isConnected);
                  const isSearchMatch = Boolean(deferredSearchQuery && node.name.toLowerCase().includes(deferredSearchQuery.toLowerCase()));

                  return (
                    <div
                      key={`node-${node.id}`}
                      id={`arch-node-${node.id}`}
                      className={`arch-node-card ${isActive ? "active" : ""} ${isConnected ? "connected" : ""} ${isDimmed ? "dimmed" : ""}`}
                      style={{ borderColor: isSearchMatch ? "#6366f1" : undefined }}
                      onClick={() => setSelectedNodeId(selectedNodeId === node.id ? null : node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      <div className="arch-node-head">
                        <strong className="arch-node-name">{node.name}</strong>
                        {node.badge && (
                          <span className="arch-node-badge" style={{ background: isActive ? "rgba(99, 102, 241, 0.15)" : undefined, color: isActive ? "#4338ca" : undefined }}>
                            {node.badge}
                          </span>
                        )}
                      </div>
                      <span className="arch-node-sub">{node.subtitle}</span>
                      {node.mappedCaseIds.length > 0 && (
                        <div className="arch-node-tc-pill" style={{ color: "#059669", background: "#ecfdf5", borderColor: "#a7f3d0" }}>
                          <span>⚡</span>
                          <span>{node.mappedCaseIds.length} Cases Covered</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Column 3: DATA STORES */}
            <div className="arch-column">
              <div className="arch-column-header">
                <span className="arch-column-title">DATA STORES</span>
                <span className="arch-column-subtitle">Database Tables &amp; Parameters</span>
              </div>
              <div className="arch-node-list">
                {architectureGraph.column3.map((node) => {
                  const isActive = selectedNodeId === node.id || hoveredNodeId === node.id;
                  const isConnected = connectedNodeIds.has(node.id) && !isActive;
                  const isDimmed = Boolean(activeFocusId && !isActive && !isConnected);
                  const isSearchMatch = Boolean(deferredSearchQuery && node.name.toLowerCase().includes(deferredSearchQuery.toLowerCase()));

                  return (
                    <div
                      key={`node-${node.id}`}
                      id={`arch-node-${node.id}`}
                      className={`arch-node-card ${isActive ? "active" : ""} ${isConnected ? "connected" : ""} ${isDimmed ? "dimmed" : ""}`}
                      style={{ borderColor: isSearchMatch ? "#f59e0b" : undefined }}
                      onClick={() => setSelectedNodeId(selectedNodeId === node.id ? null : node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      <div className="arch-node-head">
                        <strong className="arch-node-name">{node.name}</strong>
                        {node.badge && (
                          <span className="arch-node-badge" style={{ background: isActive ? "rgba(245, 158, 11, 0.15)" : undefined, color: isActive ? "#b45309" : undefined }}>
                            {node.badge}
                          </span>
                        )}
                      </div>
                      <span className="arch-node-sub">{node.subtitle}</span>
                      {node.tables && (
                        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" }}>
                          {Array.from(new Set(node.tables)).slice(0, 3).map((t, tIdx) => (
                            <code key={`tbl-${node.id}-${t}-${tIdx}`} style={{ fontSize: "9px", padding: "1px 4px" }}>{t}</code>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Column 4: EXTERNAL SYSTEMS & TEST SCENARIOS */}
            <div className="arch-column">
              <div className="arch-column-header">
                <span className="arch-column-title">EXTERNAL SYSTEMS &amp; SCENARIOS</span>
                <span className="arch-column-subtitle">Use Cases, Integrations &amp; Workflows</span>
              </div>
              <div className="arch-node-list">
                {architectureGraph.column4.map((node) => {
                  const isActive = selectedNodeId === node.id || hoveredNodeId === node.id;
                  const isConnected = connectedNodeIds.has(node.id) && !isActive;
                  const isDimmed = Boolean(activeFocusId && !isActive && !isConnected);
                  const isSearchMatch = Boolean(deferredSearchQuery && node.name.toLowerCase().includes(deferredSearchQuery.toLowerCase()));

                  return (
                    <div
                      key={`node-${node.id}`}
                      id={`arch-node-${node.id}`}
                      className={`arch-node-card ${isActive ? "active" : ""} ${isConnected ? "connected" : ""} ${isDimmed ? "dimmed" : ""}`}
                      style={{ borderColor: isSearchMatch ? "#10b981" : undefined }}
                      onClick={() => setSelectedNodeId(selectedNodeId === node.id ? null : node.id)}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                    >
                      <div className="arch-node-head">
                        <strong className="arch-node-name">{node.name}</strong>
                        {node.badge && (
                          <span className="arch-node-badge" style={{ background: isActive ? "rgba(16, 185, 129, 0.15)" : undefined, color: isActive ? "#047857" : undefined }}>
                            {node.badge}
                          </span>
                        )}
                      </div>
                      <span className="arch-node-sub">{node.subtitle}</span>
                      {node.mappedCaseIds.length > 0 && (
                        <div className="arch-node-tc-pill" style={{ color: "#0f766e", background: "#f0fdfa", borderColor: "#99f6e4" }}>
                          <span>🔗</span>
                          <span>{node.mappedCaseIds.length} Tests Linked</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* ─── INTERACTIVE COVERAGE & TRACEABILITY INSPECTOR DRAWER ─── */}
        {selectedNode && (
          <div className="arch-inspector-panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span className="badge badge-indigo" style={{ fontSize: "11px", textTransform: "uppercase" }}>
                    Column {selectedNode.column} · {selectedNode.badge || "System Block"}
                  </span>
                  {selectedNode.techStack && (
                    <span className="badge badge-emerald" style={{ fontSize: "11px" }}>
                      {selectedNode.techStack}
                    </span>
                  )}
                </div>
                <h3 style={{ margin: "6px 0 2px", fontSize: "20px", fontWeight: 800, color: "var(--text-primary)" }}>
                  {selectedNode.name}
                </h3>
                <p className="muted" style={{ margin: 0, fontSize: "13px" }}>
                  {selectedNode.description || selectedNode.subtitle}
                </p>
              </div>

              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                {onGenerateForApp && selectedNode.appName ? (
                  <button
                    type="button"
                    className="btn btn-emerald btn-sm"
                    onClick={() => onGenerateForApp(selectedNode.appName!)}
                  >
                    + Generate AI Tests
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedNodeId(null)}
                >
                  Close Inspector ✕
                </button>
              </div>
            </div>

            {/* Inspector Content Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
              {/* Connected Architecture Paths */}
              <div style={{ padding: "14px", background: "var(--bg-layer-2)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", gap: "8px" }}>
                <strong style={{ fontSize: "13px", color: "var(--text-primary)" }}>Connected Architecture Dependencies:</strong>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {Array.from(connectedNodeIds).filter((id) => id !== selectedNode.id).map((nodeId) => {
                    const target = architectureGraph.nodes.find((n) => n.id === nodeId);
                    if (!target) return null;
                    return (
                      <button
                        key={`dep-btn-${nodeId}`}
                        type="button"
                        className="badge badge-indigo"
                        style={{ cursor: "pointer", border: "1px solid #c7d2fe", fontSize: "11px", padding: "4px 8px" }}
                        onClick={() => setSelectedNodeId(target.id)}
                        title="Click to jump to this connected component"
                      >
                        → {target.name} ({target.badge})
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* API & Data Details */}
              {(selectedNode.endpoints || selectedNode.tables) && (
                <div style={{ padding: "14px", background: "var(--bg-layer-2)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", gap: "8px" }}>
                  <strong style={{ fontSize: "13px", color: "var(--text-primary)" }}>
                    {selectedNode.endpoints ? "Verified API Routes:" : "Persistent Data Schema / Tables:"}
                  </strong>
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                    {Array.from(new Set(selectedNode.endpoints || [])).map((ep, epIdx) => (
                      <code key={`ep-${selectedNode.id}-${ep}-${epIdx}`} style={{ fontSize: "11px", padding: "2px 6px" }}>{ep}</code>
                    ))}
                    {Array.from(new Set(selectedNode.tables || [])).map((t, tIdx) => (
                      <code key={`tbl-${selectedNode.id}-${t}-${tIdx}`} style={{ fontSize: "11px", padding: "2px 6px" }}>{t}</code>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Test Cases Table with Direct Run / Edit */}
            <div style={{ marginTop: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <strong style={{ fontSize: "14px" }}>
                  Mapped Test Cases ({selectedNodeTestCases.length}):
                </strong>
                <span className="muted" style={{ fontSize: "12px" }}>
                  {selectedNodeTestCases.filter((tc) => tc.status === "ready").length} ready for execution
                </span>
              </div>

              {selectedNodeTestCases.length > 0 ? (
                <div className="table-scroll" style={{ maxHeight: "300px", overflowY: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Case ID</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Priority</th>
                        <th>Steps</th>
                        <th>Expected Result</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedNodeTestCases.map((tc) => (
                        <tr key={`insp-tc-${tc.id}`}>
                          <td><strong>TC#{tc.id}</strong></td>
                          <td><strong>{tc.title}</strong></td>
                          <td>
                            <span className={`badge ${tc.status === "ready" ? "badge-emerald" : "badge-amber"}`}>
                              {tc.status.toUpperCase()}
                            </span>
                          </td>
                          <td><span className={`priority ${(tc.priority || "medium").toLowerCase()}`}>{tc.priority || "Medium"}</span></td>
                          <td>
                            <button
                              type="button"
                              className="table-action"
                              onClick={() => setExpandedStepsCaseId(expandedStepsCaseId === tc.id ? null : tc.id)}
                            >
                              {expandedStepsCaseId === tc.id ? "Hide Steps ▲" : "View Steps ▼"}
                            </button>
                          </td>
                          <td><small style={{ display: "block", maxWidth: "200px" }}>{tc.expected_result || "Verified"}</small></td>
                          <td>
                            <div style={{ display: "flex", gap: "6px" }}>
                              {onRunTestCase ? (
                                <button
                                  type="button"
                                  className="table-action"
                                  style={{ color: "var(--brand-primary)", fontWeight: 700 }}
                                  onClick={() => onRunTestCase(tc.id)}
                                >
                                  ▶ Run
                                </button>
                              ) : null}
                              {onEditTestCase ? (
                                <button
                                  type="button"
                                  className="table-action"
                                  onClick={() => onEditTestCase(tc)}
                                >
                                  ✏️ Edit
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted" style={{ fontSize: "13px", margin: "6px 0" }}>
                  No test cases currently mapped directly to this component. Click &quot;+ Generate AI Tests&quot; above to create automated verification cases.
                </p>
              )}

              {/* Expanded Steps Drawer */}
              {expandedStepsCaseId && (
                <div style={{ marginTop: "10px", padding: "12px", background: "#f8fafc", borderRadius: "var(--radius-md)", border: "1px solid #e2e8f0" }}>
                  {(() => {
                    const expandedCase = testCases.find((tc) => tc.id === expandedStepsCaseId);
                    if (!expandedCase) return null;
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        <strong style={{ fontSize: "13px" }}>Step Sequence for TC#{expandedCase.id} ({expandedCase.title}):</strong>
                        <pre style={{ margin: 0, padding: "10px", background: "#0f172a", color: "#f8fafc", borderRadius: "var(--radius-sm)", fontSize: "12px", whiteSpace: "pre-wrap" }}>
                          {expandedCase.steps || "No steps defined."}
                        </pre>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
