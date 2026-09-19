import { beforeEach, describe, expect, it } from "vitest";
import {
  AUTH_TOKEN_KEY,
  clearAuthToken,
  getAuthToken,
  setAuthToken,
} from "./auth";

function createStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

describe("auth token boundary", () => {
  beforeEach(() => {
    Object.defineProperty(window, "sessionStorage", { configurable: true, value: createStorage() });
    Object.defineProperty(window, "localStorage", { configurable: true, value: createStorage() });
    clearAuthToken();
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it("stores new tokens in session storage and memory", () => {
    setAuthToken("session-token");

    expect(getAuthToken()).toBe("session-token");
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("session-token");
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });

  it("migrates a legacy local-storage token once", () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "legacy-token");

    expect(getAuthToken()).toBe("legacy-token");
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("legacy-token");
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });

  it("clears both storage locations and memory", () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, "legacy-token");
    expect(getAuthToken()).toBe("legacy-token");

    clearAuthToken();

    expect(getAuthToken()).toBe("");
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });
});
