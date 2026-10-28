import type { Recording, RunEvent, ScenarioSummary } from "./run";

// The live backend is optional: without it the page replays recorded runs.
// A deployed build only contacts a backend when NEXT_PUBLIC_API_URL is set; local dev defaults to localhost.
const DEFAULT_API = process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API).replace(/\/$/, "");

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

export async function loadRecordingIndex(): Promise<RecordingIndexEntry[]> {
  const resp = await fetch("/recordings/index.json");
  return resp.ok ? resp.json() : [];
}

export async function loadRecording(file: string): Promise<Recording> {
  const resp = await fetch(`/recordings/${file}`);
  if (!resp.ok) throw new Error(`Recording ${file} could not be loaded`);
  return resp.json();
}

export async function startLiveRun(scenario: string): Promise<string> {
  const resp = await fetch(`${API_URL}/api/investigations`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail ?? `The backend refused the run (HTTP ${resp.status})`);
  return data.id as string;
}

/** Subscribe to a live run's events. Returns a function that closes the stream. */
export function streamRun(runId: string, onEvent: (e: RunEvent) => void, onEnd: () => void): () => void {
  const source = new EventSource(`${API_URL}/api/investigations/${runId}/events`);
  source.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  source.addEventListener("end", () => {
    source.close();
    onEnd();
  });
  source.onerror = () => {
    source.close();
    onEnd();
  };
  return () => source.close();
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
export async function startCustomRun(form: FormData): Promise<RunSummary> {
  return json(await fetch(`${API_URL}/api/investigations/custom`, { method: "POST", body: form }));
}

export async function cancelRun(id: string): Promise<RunSummary> {
  return json(await fetch(`${API_URL}/api/investigations/${id}/cancel`, { method: "POST" }));
}

export async function getRun(id: string): Promise<RunSummary> {
  return json(await fetch(`${API_URL}/api/investigations/${id}`));
}

export async function listSavedRuns(): Promise<SavedRun[]> {
  return json(await fetch(`${API_URL}/api/runs`));
}

export async function loadSavedRun(name: string): Promise<Recording> {
  return json(await fetch(`${API_URL}/api/runs/${encodeURIComponent(name)}`));
}
