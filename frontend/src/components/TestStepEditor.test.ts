import { describe, expect, it } from "vitest";
import { parseTestSteps, serializeTestSteps } from "./TestStepEditor";

describe("TestStepEditor step format", () => {
  it("normalizes numbered and unnumbered generated steps", () => {
    expect(parseTestSteps("1. Open the login page\n2) Enter credentials\nVerify the dashboard")).toEqual([
      "Open the login page",
      "Enter credentials",
      "Verify the dashboard",
    ]);
  });

  it("serializes edited steps for the existing API contract", () => {
    const steps = parseTestSteps("1. Open the login page\n2. Enter credentials");
    steps.splice(1, 1);
    steps.push("Verify the dashboard");
    expect(serializeTestSteps(steps)).toBe("1. Open the login page\n2. Verify the dashboard");
  });
});
