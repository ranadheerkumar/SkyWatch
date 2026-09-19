import { apiFetch, apiFetchCached, clearApiCache } from "./api";
import type { Application, Defect, RunSummary, TestCase, WorkspaceProject } from "../types";

export const TEST_CASE_PAGE_SIZE = 500;

export async function loadAllTestCases(authToken: string): Promise<TestCase[]> {
  const allCases: TestCase[] = [];
  let offset = 0;

  while (true) {
    const page = await apiFetch<TestCase[]>(
      `/api/v1/test-cases?limit=${TEST_CASE_PAGE_SIZE}&offset=${offset}`,
      {},
      authToken,
    );
    allCases.push(...page);
    if (page.length < TEST_CASE_PAGE_SIZE) return allCases;
    offset += page.length;
  }
}

export async function loadApplications(authToken: string): Promise<Application[]> {
  return await apiFetch<Application[]>("/api/v1/applications", {}, authToken);
}

export async function loadDefects(authToken: string, applicationId?: number): Promise<Defect[]> {
  const url = applicationId ? `/api/v1/defects?application_id=${applicationId}` : "/api/v1/defects";
  return await apiFetch<Defect[]>(url, {}, authToken);
}

export async function loadRuns(authToken: string, applicationId?: number): Promise<RunSummary[]> {
  const url = applicationId ? `/api/v1/execution/runs?application_id=${applicationId}` : "/api/v1/execution/runs";
  return await apiFetch<RunSummary[]>(url, {}, authToken);
}

export { apiFetch, apiFetchCached, clearApiCache };
