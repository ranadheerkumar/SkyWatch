export const AUTH_TOKEN_KEY = "ai-qa-engine:token";
export const LEGACY_AUTH_TOKEN_KEY = "ai-qa-engine:token";
export const AUTH_EXPIRED_EVENT = "ai-qa-engine:auth-expired";

let memoryToken = "";

function readStorage(storage: Storage, key: string): string {
  try {
    return storage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeStorage(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value);
  } catch {
  }
}

function removeStorage(storage: Storage, key: string): void {
  try {
    storage.removeItem(key);
  } catch {
  }
}

export function getAuthToken(): string {
  if (memoryToken) return memoryToken;
  if (typeof window === "undefined") return "";

  const sessionToken = readStorage(window.sessionStorage, AUTH_TOKEN_KEY);
  if (sessionToken) {
    memoryToken = sessionToken;
    return sessionToken;
  }

  const legacyToken = readStorage(window.localStorage, LEGACY_AUTH_TOKEN_KEY);
  if (!legacyToken) return "";

  memoryToken = legacyToken;
  writeStorage(window.sessionStorage, AUTH_TOKEN_KEY, legacyToken);
  removeStorage(window.localStorage, LEGACY_AUTH_TOKEN_KEY);
  return legacyToken;
}

export function setAuthToken(token: string): void {
  memoryToken = token;
  if (typeof window === "undefined") return;
  writeStorage(window.sessionStorage, AUTH_TOKEN_KEY, token);
  removeStorage(window.localStorage, LEGACY_AUTH_TOKEN_KEY);
}

export function clearAuthToken(): void {
  memoryToken = "";
  if (typeof window === "undefined") return;
  removeStorage(window.sessionStorage, AUTH_TOKEN_KEY);
  removeStorage(window.localStorage, LEGACY_AUTH_TOKEN_KEY);
}
