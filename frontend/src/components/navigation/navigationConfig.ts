import type { AppIconName, Section } from "../../types";

export const navigationItems: Array<{ id: Section; label: string; icon: AppIconName }> = [
  { id: "dashboard", label: "Dashboard", icon: "overview" },
  { id: "projects", label: "Projects", icon: "projects" },
  { id: "applications", label: "Applications", icon: "applications" },
  { id: "cases", label: "Test Cases", icon: "cases" },
  { id: "suites", label: "Test Suites", icon: "suites" },
  { id: "aiGenerator", label: "Scenario Generator", icon: "ai" },
  { id: "systemMap", label: "Traceability Map", icon: "map" },
  { id: "execution", label: "Execute Tests", icon: "execution" },
  { id: "runHistory", label: "Run History", icon: "execution" },
  { id: "evidence", label: "Evidence Gallery", icon: "overview" },
  { id: "agents", label: "AI Recommendations", icon: "recommendations" },
  { id: "defects", label: "Defects", icon: "defects" },
  { id: "reports", label: "Reports & Analytics", icon: "reports" },
  { id: "settings", label: "AI & Settings", icon: "settings" },
];

export const navigationGroups = [
  { id: "workspace", label: "Workspace Scope", sections: ["dashboard", "projects", "applications"] as Section[] },
  { id: "ai-workspace", label: "AI QA Studio", sections: ["aiGenerator", "systemMap", "agents"] as Section[] },
  { id: "quality", label: "Test Management", sections: ["cases", "suites", "execution", "runHistory", "evidence"] as Section[] },
  { id: "reporting", label: "Reporting & Quality", sections: ["defects", "reports"] as Section[] },
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
  "/projects": "projects",
  "/applications": "applications",
  "/test-cases": "cases",
  "/test-execution": "execution",
  "/run-history": "runHistory",
  "/defects": "defects",
  "/test-suites": "suites",
  "/reports": "reports",
  "/ai-generator": "aiGenerator",
  "/agents": "agents",
  "/system-map": "systemMap",
  "/mapping": "systemMap",
  "/evidence": "evidence",
  "/settings": "settings",
  "/audit": "audit",
};
