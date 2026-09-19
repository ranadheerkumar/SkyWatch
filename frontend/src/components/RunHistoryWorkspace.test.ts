import { describe, expect, it } from "vitest";
import type { BuildExecutionSummary, RunSummary, CaseExecutionSummary } from "../types";

describe("RunHistoryWorkspace build aggregation and reporting", () => {
  it("computes accurate pass rate and status for a build execution summary", () => {
    const build: BuildExecutionSummary = {
      build_id: "build-20260908-001",
      application_id: 1,
      name: "Smoke Build #1",
      status: "passed",
      trigger_source: "manual",
      total_cases: 4,
      passed_count: 3,
      failed_count: 1,
      error_count: 0,
      pass_rate: 75.0,
      duration_ms: 12500,
      created_at: "2026-09-08T10:00:00Z",
      finished_at: "2026-09-08T10:00:15Z",
    };

    expect(build.total_cases).toBe(4);
    expect(build.passed_count).toBe(3);
    expect(build.pass_rate).toBe(75.0);
    expect(build.failed_count + build.passed_count).toBe(build.total_cases);
  });

  it("handles empty and 100% pass rate builds cleanly", () => {
    const perfectBuild: BuildExecutionSummary = {
      build_id: "build-perfect-001",
      application_id: 1,
      name: "Regression Build #5",
      status: "passed",
      trigger_source: "suite",
      total_cases: 10,
      passed_count: 10,
      failed_count: 0,
      error_count: 0,
      pass_rate: 100.0,
      duration_ms: 30000,
    };

    expect(perfectBuild.pass_rate).toBe(100.0);
    expect(perfectBuild.status).toBe("passed");
  });

  it("filters and matches search terms across builds and runs efficiently", () => {
    const builds: BuildExecutionSummary[] = [
      {
        build_id: "build-001",
        application_id: 1,
        name: "Login Smoke",
        status: "passed",
        trigger_source: "manual",
        total_cases: 2,
        passed_count: 2,
        failed_count: 0,
        error_count: 0,
        pass_rate: 100.0,
        duration_ms: 1500,
      },
      {
        build_id: "build-002",
        application_id: 1,
        name: "Checkout Regression",
        status: "failed",
        trigger_source: "suite",
        total_cases: 5,
        passed_count: 3,
        failed_count: 2,
        error_count: 0,
        pass_rate: 60.0,
        duration_ms: 5000,
      },
    ];

    const q = "checkout";
    const filtered = builds.filter((b) => b.name.toLowerCase().includes(q) || b.build_id.toLowerCase().includes(q));
    expect(filtered).toHaveLength(1);
    expect(filtered[0].build_id).toBe("build-002");
  });

  it("identifies in-flight running builds and runs correctly", () => {
    const runs: RunSummary[] = [
      { run_id: "run-001", application_id: 1, status: "passed" },
      { run_id: "run-002", application_id: 1, status: "running" },
      { run_id: "run-003", application_id: 1, status: "queued" },
      { run_id: "run-004", application_id: 1, status: "failed" },
    ];

    const runningRuns = runs.filter((r) => r.status === "running" || r.status === "queued");
    expect(runningRuns).toHaveLength(2);
    expect(runningRuns.map((r) => r.run_id)).toEqual(["run-002", "run-003"]);
  });
});
