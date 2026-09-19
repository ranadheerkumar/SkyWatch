import type { AppIconName, Section } from "../../types";

export const navigationItems: Array<{ id: Section; label: string; icon: AppIconName }> = [
  { id: "dashboard", label: "Dashboard", icon: "overview" },
  { id: "aiGenerator", label: "Scenario Generator", icon: "ai" },
  { id: "systemMap", label: "Traceability Map", icon: "map" },
  { id: "execution", label: "Execute Tests", icon: "execution" },
  { id: "runHistory", label: "Run History", icon: "execution" },
  { id: "agents", label: "AI Recommendations", icon: "recommendations" },
  { id: "defects", label: "Defects", icon: "defects" },
  { id: "reports", label: "Reports & Analytics", icon: "reports" },
  { id: "settings", label: "AI & Settings", icon: "settings" },
];

export const navigationGroups = [
  { id: "overview", label: "Overview", sections: ["dashboard"] as Section[] },
  { id: "ai-workspace", label: "AI Workspace", sections: ["aiGenerator", "systemMap", "agents"] as Section[] },
  { id: "test-execution", label: "Test Execution", sections: ["execution", "runHistory"] as Section[] },
  { id: "reporting", label: "Reporting & Analytics", sections: ["defects", "reports"] as Section[] },
  { id: "administration", label: "Administration", sections: ["settings"] as Section[] },
];

export const sectionPaths: Record<Section, string> = {
  dashboard: "/",
  projects: "/projects",
  applications: "/applications",
  cases: "/test-cases",
  execution: "/test-execution",
  runHistory: "/run-history",
  defects: "/defects",
  suites: "/test-suites",
  reports: "/reports",
  aiGenerator: "/ai-generator",
  agents: "/agents",
  recommendations: "/agents",
  systemMap: "/system-map",
  evidence: "/evidence",
  settings: "/settings",
  audit: "/audit",
};

export const pathSections: Record<string, Section> = {
  "/": "dashboard",
  "/dashboard": "dashboard",
  "/projects": "dashboard",
  "/applications": "dashboard",
  "/test-cases": "execution",
  "/test-execution": "execution",
  "/run-history": "runHistory",
  "/defects": "defects",
  "/test-suites": "execution",
  "/reports": "reports",
  "/ai-generator": "aiGenerator",
  "/agents": "agents",
  "/system-map": "systemMap",
  "/mapping": "systemMap",
  "/evidence": "runHistory",
  "/settings": "settings",
  "/audit": "audit",
};
