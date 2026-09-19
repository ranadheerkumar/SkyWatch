import { describe, expect, it } from "vitest";
import { normalizeHttpUrl, requiredField } from "./validations";

describe("shared validation helpers", () => {
  it("normalizes valid HTTP(S) targets", () => {
    expect(normalizeHttpUrl(" https://example.com/path ")).toBe("https://example.com/path");
    expect(normalizeHttpUrl("http://localhost:8000")).toBe("http://localhost:8000/");
  });

  it("rejects empty, malformed, and non-web targets", () => {
    expect(normalizeHttpUrl("")).toBeNull();
    expect(normalizeHttpUrl("example.com")).toBeNull();
    expect(normalizeHttpUrl("ftp://example.com/file")).toBeNull();
  });

  it("returns a useful required-field message", () => {
    expect(requiredField("  ", "Project name")).toBe("Project name is required.");
    expect(requiredField("QA workspace", "Project name")).toBeNull();
  });
});
