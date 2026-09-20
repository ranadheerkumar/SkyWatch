import { describe, expect, it } from "vitest";
import type { ScriptFramework, FrameworkInfo } from "../types";

describe("ScriptStudio framework configurations", () => {
  const supportedFrameworks: ScriptFramework[] = [
    "playwright",
    "cypress",
    "selenium_python",
    "robot",
    "java_testng",
    "jest_puppeteer",
  ];

  it("supports all 6 enterprise test automation frameworks", () => {
    expect(supportedFrameworks).toHaveLength(6);
    expect(supportedFrameworks).toContain("playwright");
    expect(supportedFrameworks).toContain("cypress");
    expect(supportedFrameworks).toContain("selenium_python");
    expect(supportedFrameworks).toContain("robot");
    expect(supportedFrameworks).toContain("java_testng");
    expect(supportedFrameworks).toContain("jest_puppeteer");
  });

  it("maps frameworks to correct file extensions", () => {
    const extensionMap: Record<ScriptFramework, string> = {
      playwright: ".spec.ts",
      cypress: ".cy.js",
      selenium_python: ".py",
      robot: ".robot",
      java_testng: ".java",
      jest_puppeteer: ".test.js",
    };

    expect(extensionMap.playwright).toBe(".spec.ts");
    expect(extensionMap.cypress).toBe(".cy.js");
    expect(extensionMap.selenium_python).toBe(".py");
    expect(extensionMap.robot).toBe(".robot");
    expect(extensionMap.java_testng).toBe(".java");
    expect(extensionMap.jest_puppeteer).toBe(".test.js");
  });

  it("maps frameworks to correct programming languages", () => {
    const languageMap: Record<ScriptFramework, string> = {
      playwright: "TypeScript",
      cypress: "JavaScript",
      selenium_python: "Python",
      robot: "Robot",
      java_testng: "Java",
      jest_puppeteer: "JavaScript",
    };

    expect(languageMap.playwright).toBe("TypeScript");
    expect(languageMap.cypress).toBe("JavaScript");
    expect(languageMap.selenium_python).toBe("Python");
    expect(languageMap.robot).toBe("Robot");
    expect(languageMap.java_testng).toBe("Java");
    expect(languageMap.jest_puppeteer).toBe("JavaScript");
  });
});
