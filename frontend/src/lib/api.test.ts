import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, apiFetchCached, clearApiCache } from "./api";

describe("API client policy", () => {
  afterEach(() => {
    clearApiCache();
    vi.restoreAllMocks();
  });

  it("invalidates cached reads after a successful mutation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ version: 1 }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ version: 2 }), { status: 200, headers: { "content-type": "application/json" } }));

    await expect(apiFetchCached<{ version: number }>("/api/v1/projects", 60_000)).resolves.toEqual({ version: 1 });
    await expect(apiFetchCached<{ version: number }>("/api/v1/projects", 60_000)).resolves.toEqual({ version: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await apiFetch("/api/v1/projects", { method: "POST", body: JSON.stringify({ name: "QA" }) });
    await expect(apiFetchCached<{ version: number }>("/api/v1/projects", 60_000)).resolves.toEqual({ version: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("throws typed errors with response status and URL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Project not found", code: "PROJECT_NOT_FOUND" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(apiFetch("/api/v1/projects/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      url: "http://127.0.0.1:8000/api/v1/projects/missing",
      code: "PROJECT_NOT_FOUND",
      message: "Project not found",
    });
  });
});
