import type { Recording, RunEvent, ScenarioSummary } from "./run";

// The live backend is optional: without it the page replays recorded runs.
// A deployed build only contacts a backend when NEXT_PUBLIC_API_URL is set; local dev defaults to localhost.
const DEFAULT_API = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API).replace(/\/$/, "");

let bearerToken = "";
export function setApiToken(token: string) { bearerToken = token; }
export async function apiFetch(url: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (bearerToken) headers.set("Authorization", `Bearer ${bearerToken}`);
  const response = await fetch(url, { ...options, headers });
  return response;
}

export interface RecordingIndexEntry {
  scenario: ScenarioSummary;
  file: string;
  verified: boolean;
  outcome?: string | null;
  duration_s: number;
  tests?: { before: Record<string, number>; after: Record<string, number> };
  issues?: { title: string; severity: "critical" | "high" | "medium" | "low"; category: string }[];
  tokens?: number;
  model_calls?: number;
  review?: string | null;
  started_at?: number;
}

export async function backendAvailable(): Promise<boolean> {
  if (!API_URL) return false;
  try {
    const resp = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(2500) });
    return resp.ok;
  } catch {
    return false;
  }
}

/** Whether the backend wants an access key before it investigates uploaded or cloned code. */
export async function uploadsNeedKey(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(2500) });
    return Boolean((await resp.json()).uploads_need_key);
  } catch {
    return false;
  }
}

export async function loadRecordingIndex(): Promise<RecordingIndexEntry[]> {
  const resp = await fetch("/recordings/index.json");
  if (!resp.ok) throw new Error("The scenario library could not be loaded");
  return resp.json();
}

export async function loadRecording(file: string): Promise<Recording> {
  const resp = await fetch(`/recordings/${file}`);
  if (!resp.ok) throw new Error(`Recording ${file} could not be loaded`);
  return resp.json();
}

export class LiveRunError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export function recordingFallback(error: unknown): string | null {
  if (error instanceof LiveRunError) {
    if (error.status === 429) return "capacity";
    if (error.status >= 500) return "unavailable";
    return null; // Permission and validation errors must remain visible.
  }
  return error instanceof TypeError || (error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name)) ? "unavailable" : null;
}

export async function startLiveRun(scenario: string): Promise<string> {
  const resp = await apiFetch(`${API_URL}/api/investigations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scenario }),
    signal: AbortSignal.timeout(15000),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new LiveRunError(data.detail ?? `The backend refused the run (HTTP ${resp.status})`, resp.status);
  return data.id as string;
}

/** Subscribe to a live run's events. Returns a function that closes the stream. */
export function streamRun(runId: string, onEvent: (e: RunEvent) => void, onEnd: () => void, onError?: (error: unknown) => void): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await apiFetch(`${API_URL}/api/investigations/${encodeURIComponent(runId)}/events`, { signal: controller.signal });
      if (!response.ok) throw new LiveRunError(`Investigation stream unavailable (HTTP ${response.status})`, response.status);
      if (!response.body) throw new TypeError("Investigation stream unavailable");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      let terminal = false;
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
        let boundary: number;
        while ((boundary = pending.indexOf("\n\n")) !== -1) {
          const frame = pending.slice(0, boundary);
          pending = pending.slice(boundary + 2);
          const lines = frame.split("\n");
          if (lines.some((line) => line === "event: end")) { await reader.cancel(); onEnd(); return; }
          const data = lines.filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
          if (data) {
            const event = JSON.parse(data);
            terminal ||= ["report", "cancelled", "error"].includes(event.type);
            onEvent(event);
          }
        }
      }
      if (!controller.signal.aborted && !terminal) throw new TypeError("Live stream closed before an outcome");
    } catch (error) { if (controller.signal.aborted) return; console.error("Investigation stream ended", error); onError?.(error); }
    onEnd();
  })();
  return () => controller.abort();
}

export interface EvalSummary {
  agent: Record<
    string,
    { runs: number; verified: number; approved: number; avg_tokens: number; avg_reviewer_tokens: number; avg_duration_s: number; regression_tests: number; review_retries: number }
  >;
  agent_total: { runs: number; verified: number; approved: number };
  reviewer: Partial<Record<"reference" | "gamed", { cases: number; correct: number; avg_tokens: number }>>;
  reviewer_cases: { scenario: string; kind: "reference" | "gamed"; label: string; verdict: string; correct: boolean; summary: string; tokens: number }[];
}

export async function loadEval(): Promise<EvalSummary | null> {
  const resp = await fetch("/eval.json").catch(() => null);
  return resp?.ok ? resp.json() : null;
}

interface ComparisonSystem {
  runs: number;
  correct: number;
  false_success: number;
  honest_failure: number;
  new_tests: number;
  runs_editing_tests: number;
  avg_tokens: number;
  avg_duration_s: number;
}

export interface ComparisonSummary {
  systems: Partial<Record<"plain" | "tracepilot", ComparisonSystem>>;
  cases: Record<string, Partial<Record<"plain" | "tracepilot", { runs: number; correct: number; false_success: number; avg_tokens: number; avg_duration_s: number }>>>;
}

export async function loadComparison(): Promise<ComparisonSummary | null> {
  const resp = await fetch("/comparison.json").catch(() => null);
  return resp?.ok ? resp.json() : null;
}

// --- backend-only calls (a live TracePilot API) ---------------------------------------------

export interface RunSummary {
  id: string;
  scenario: string;
  title: string;
  status: "running" | "completed" | "failed" | "cancelled";
  outcome?: string | null;
  started_at: number;
  verified?: boolean | null;
  error?: string | null;
}

export interface SavedRun {
  name: string;
  scenario: string;
  title?: string;
  status: string;
  verified?: boolean | null;
  outcome?: string | null;
  started_at?: number;
  duration_s?: number | null;
  tokens?: number;
}

async function json<T>(resp: Response): Promise<T> {
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error((data as { detail?: string }).detail ?? `The backend answered HTTP ${resp.status}`);
  return data as T;
}

/** Start an investigation of your own project: a ZIP upload or a public repository URL, with optional attachments. */
export async function startCustomRun(form: FormData, accessKey?: string): Promise<RunSummary> {
  const headers: Record<string, string> = accessKey ? { "X-TracePilot-Key": accessKey } : {};
  return json(await apiFetch(`${API_URL}/api/investigations/custom`, { method: "POST", body: form, headers }));
}

export async function cancelRun(id: string): Promise<RunSummary> {
  return json(await apiFetch(`${API_URL}/api/investigations/${id}/cancel`, { method: "POST" }));
}

export async function getRun(id: string): Promise<RunSummary> {
  return json(await apiFetch(`${API_URL}/api/investigations/${id}`));
}

export async function listSavedRuns(): Promise<SavedRun[]> {
  return json(await apiFetch(`${API_URL}/api/runs`));
}

export async function loadSavedRun(name: string): Promise<Recording> {
  return json(await apiFetch(`${API_URL}/api/runs/${encodeURIComponent(name)}`));
}
