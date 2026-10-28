import type { Recording, RunEvent, ScenarioSummary } from "./run";

// The live backend is optional: without it the page replays recorded runs.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface RecordingIndexEntry {
  scenario: ScenarioSummary;
  file: string;
  verified: boolean;
  duration_s: number;
}

export async function backendAvailable(): Promise<boolean> {
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
