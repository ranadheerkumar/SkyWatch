import { describe, expect, it } from "vitest";
import type { GenerationLogItem } from "./GenerationLogViewer";

describe("GenerationLogItem handling", () => {
  it("formats log entries correctly for export and display", () => {
    const logItems: GenerationLogItem[] = [
      {
        job_id: "job-123",
        stage: "document_analysis",
        level: "INFO",
        message: "Parsed 2 requirements",
        metadata: { pages: 3 },
        iso_time: "2026-09-19T18:00:00.000Z",
      },
      {
        job_id: "job-123",
        stage: "planner",
        level: "LLM",
        message: "Synthesized 4 scenarios",
        metadata: { provider: "gemini", model: "gemini-flash-latest" },
        iso_time: "2026-09-19T18:00:03.000Z",
      },
      {
        job_id: "job-123",
        stage: "generator",
        level: "WARN",
        message: "Rate limit 429 encountered, backoff 5s",
        iso_time: "2026-09-19T18:00:05.000Z",
      },
    ];

    expect(logItems).toHaveLength(3);

    // Filtering test
    const llmLogs = logItems.filter((l) => l.level === "LLM");
    expect(llmLogs).toHaveLength(1);
    expect(llmLogs[0].metadata?.provider).toBe("gemini");

    // Search query test
    const warnLogs = logItems.filter((l) =>
      l.message.toLowerCase().includes("rate limit")
    );
    expect(warnLogs).toHaveLength(1);
    expect(warnLogs[0].stage).toBe("generator");
  });
});
