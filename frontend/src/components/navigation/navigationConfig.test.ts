import { describe, expect, it } from "vitest";
import {
  navigationGroups,
  navigationItems,
  pathSections,
  sectionPaths,
} from "./navigationConfig";

describe("navigationConfig routing and section integrity", () => {
  it("maps URL paths to dedicated functional sections without collapsing to dashboard", () => {
    expect(pathSections["/projects"]).toBe("projects");
    expect(pathSections["/applications"]).toBe("applications");
    expect(pathSections["/test-cases"]).toBe("cases");
    expect(pathSections["/test-suites"]).toBe("suites");
    expect(pathSections["/evidence"]).toBe("evidence");
    expect(pathSections["/dashboard"]).toBe("dashboard");
    expect(pathSections["/run-history"]).toBe("runHistory");
    expect(pathSections["/defects"]).toBe("defects");
    expect(pathSections["/reports"]).toBe("reports");
  });

  it("maps sections to their canonical URL paths", () => {
    expect(sectionPaths.projects).toBe("/projects");
    expect(sectionPaths.applications).toBe("/applications");
    expect(sectionPaths.cases).toBe("/test-cases");
    expect(sectionPaths.suites).toBe("/test-suites");
    expect(sectionPaths.evidence).toBe("/evidence");
    expect(sectionPaths.dashboard).toBe("/");
  });

  it("includes projects and applications in navigationItems", () => {
    const itemIds = navigationItems.map((item) => item.id);
    expect(itemIds).toContain("projects");
    expect(itemIds).toContain("applications");
    expect(itemIds).toContain("cases");
    expect(itemIds).toContain("suites");
    expect(itemIds).toContain("evidence");
  });

  it("includes workspace and quality navigation groups with appropriate sections", () => {
    const workspaceGroup = navigationGroups.find((g) => g.id === "workspace");
    expect(workspaceGroup).toBeDefined();
    expect(workspaceGroup?.sections).toEqual(["dashboard", "projects", "applications"]);

    const qualityGroup = navigationGroups.find((g) => g.id === "quality");
    expect(qualityGroup).toBeDefined();
    expect(qualityGroup?.sections).toContain("cases");
    expect(qualityGroup?.sections).toContain("suites");
    expect(qualityGroup?.sections).toContain("execution");
  });
});
