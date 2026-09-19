import type { ExecutionSlowMode, VoiceGender } from "../types";

export const LIVE_EVENT_PREFIX = "LIVE_EVENT|";
export const VOICE_MODE_STORAGE_KEY = "ai-qa-engine:voice-mode";
export const VOICE_GENDER_HINTS: Record<VoiceGender, RegExp> = {
  male: /\b(male|man|david|mark|george|james|daniel|guy|ryan|alex|fred|tom|lee|matthew|jason|thomas)\b/i,
  female: /\b(female|woman|zira|hazel|susan|aria|jenny|samantha|victoria|karen|sara|sarah|ava|emma|allison|joanna|linda|kate|moira|fiona|veena|tessa|serena)\b/i,
};

export function findSpeechVoice(gender: VoiceGender) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return undefined;
  const voices = window.speechSynthesis.getVoices();
  const englishVoices = voices.filter((voice) => /^en(-|_)/i.test(voice.lang));
  const candidateVoices = englishVoices.length ? englishVoices : voices;
  const matchingVoice = candidateVoices.find((voice) => {
    const metadata = voice as SpeechSynthesisVoice & { gender?: string };
    const declaredGender = metadata.gender?.toLowerCase();
    return declaredGender === gender || VOICE_GENDER_HINTS[gender].test(`${voice.name} ${voice.voiceURI}`);
  });
  return matchingVoice ?? candidateVoices.find((voice) => voice.default) ?? candidateVoices[0];
}

export function parseLiveEventsFromLog(log?: string): Array<{ state: string; message: string }> {
  if (!log) return [];
  const parsedEvents: Array<{ state: string; message: string }> = [];
  for (const rawLine of log.split(/\r?\n/)) {
    if (!rawLine.startsWith(LIVE_EVENT_PREFIX)) continue;
    const parts = rawLine.split("|");
    if (parts.length < 3) continue;
    const state = parts[1]?.trim() ?? "";
    const message = parts.slice(2).join("|").trim();
    if (!state || !message) continue;
    parsedEvents.push({ state, message });
  }
  return parsedEvents;
}

export function latestLiveEvent(log?: string): { state: string; message: string } | null {
  const events = parseLiveEventsFromLog(log);
  return events.length ? events[events.length - 1] : null;
}

export function mapLiveStateToExecutionPhase(state?: string): "idle" | "queueing" | "running" | "finalizing" | "done" | "error" {
  const normalized = (state ?? "").trim().toUpperCase();
  if (!normalized) return "running";
  if (normalized === "QUEUED") return "queueing";
  if (normalized === "PASSED") return "done";
  if (normalized === "FAILED" || normalized === "CANCELLED") return "error";
  return "running";
}

export function formatLiveStateLabel(state?: string) {
  const normalized = (state ?? "").trim().toUpperCase();
  if (!normalized) return "RUNNING";
  return normalized
    .split("_")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

type ExecutionSpeechItem = {
  message: string;
  rate: number;
  voiceGender: VoiceGender;
};

let executionSpeechQueue: ExecutionSpeechItem[] = [];
let executionSpeechActive = false;

export function resolveExecutionSpeechRate(slowMode: ExecutionSlowMode = "normal"): number {
  if (slowMode === "showcase") return 0.92;
  if (slowMode === "demo") return 0.98;
  return 1.05;
}

export function pumpExecutionSpeechQueue() {
  if (executionSpeechActive || !executionSpeechQueue.length || typeof window === "undefined" || !("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") return;
  const item = executionSpeechQueue.shift();
  if (!item) return;
  const utterance = new SpeechSynthesisUtterance(item.message);
  const preferredVoice = findSpeechVoice(item.voiceGender);
  if (preferredVoice) utterance.voice = preferredVoice;
  utterance.rate = item.rate;
  utterance.pitch = item.voiceGender === "female" ? 1.06 : 0.94;
  utterance.volume = 1;
  const finish = () => {
    executionSpeechActive = false;
    pumpExecutionSpeechQueue();
  };
  utterance.onend = finish;
  utterance.onerror = finish;
  executionSpeechActive = true;
  window.speechSynthesis.speak(utterance);
}

export function stopExecutionSpeech() {
  executionSpeechQueue = [];
  executionSpeechActive = false;
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}

export function speakExecutionMessage(message: string, rate = 1, voiceGender: VoiceGender = "male", queue = false) {
  if (typeof window === "undefined" || !("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
    return false;
  }
  if (!queue) {
    stopExecutionSpeech();
  } else {
    const isStep = /^step\s+\d+/i.test(message);
    if (isStep) {
      executionSpeechQueue = executionSpeechQueue.filter((item) => !/^step\s+\d+/i.test(item.message));
    }
  }
  executionSpeechQueue.push({ message, rate, voiceGender });
  pumpExecutionSpeechQueue();
  return true;
}

export function isExecutionSpeechAction(message: string) {
  return /^(?:step\s+\d+(?:\s*(?:\/|of)\s*\d+)?\s*:\s*|opening\b|navigating\b|application loaded\b)/i.test(message);
}

export function cleanExecutionSpeech(message: string) {
  return message
    .replace(/https?:\/\/\S+/gi, "the target application")
    .replace(/#([a-zA-Z0-9_\-]+)/g, "$1 field")
    .replace(/input\[name='([^']+)'\]/g, "$1 field")
    .replace(/\b(?:label=|text=)/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}
