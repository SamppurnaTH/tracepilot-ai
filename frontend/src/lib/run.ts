// Event stream from the TracePilot backend, and the view state derived from it.
// Live runs (SSE) and recorded runs (replay) both feed the same reducer.

export type Outcome = "passed" | "failed" | "error";
export type HypothesisStatus = "open" | "confirmed" | "rejected";

export interface Hypothesis {
  id: string;
  claim: string;
  symptom: string;
  next_check: string;
  status: HypothesisStatus;
  evidence: string[];
  reason: string;
  fix_in?: "code" | "config" | "data" | "external";
}

export interface Issue {
  title: string;
  category: string;
  severity: "critical" | "high" | "medium" | "low";
  root_cause: string;
  evidence: string[];
  fix: string;
  hypothesis_ids: string[];
}

export interface Verification {
  attempt?: number;
  verified: boolean;
  fixed: string[];
  still_failing: string[];
  regressions: string[];
  before: Record<string, number>;
  after: Record<string, number>;
  tests?: Record<string, Outcome>;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cached_tokens?: number;
  model_calls: number;
  tool_calls: number;
  by_phase?: Record<string, number>;
}

// Independent review of the confirmed causes and the patch by Muse Spark Open (Meta open weights).
export interface SecondOpinion {
  verdict: "approve" | "concerns" | "reject" | "unavailable";
  confidence?: "high" | "medium" | "low";
  summary?: string;
  hypotheses?: { id: string; assessment: "supported" | "weak" | "unsupported"; note: string }[];
  risks?: string[];
  model?: string;
  tokens?: number;
  duration_s?: number;
  error?: string;
}

export interface Report {
  incident: string;
  model: string;
  isolation: string;
  hypotheses: Hypothesis[];
  findings: { summary: string; issues: Issue[] };
  diff: string;
  verification: Verification;
  second_opinion?: SecondOpinion | null;
  // "fixed" | "not_verified" | "no_code_change" (the cause is outside the code) | "no_root_cause"
  outcome?: string;
  usage: Usage;
  duration_s: number;
}

// One event as emitted by backend/app/agent.py. Fields depend on `type`.
export interface RunEvent {
  seq: number;
  t?: number;
  type: string;
  [key: string]: unknown;
}

export interface ScenarioSummary {
  id: string;
  title: string;
  service: string;
  incident: string;
  screenshots?: string[];
}

export interface Recording {
  id: string;
  started_at?: number; // unix seconds
  scenario: string;
  status: string;
  verified: boolean | null;
  report: Report | null;
  events: RunEvent[];
}

export type Phase = "starting" | "investigate" | "fix" | "review" | "report" | "done" | "failed";

// The stages of a run, in order, as shown in the progress stepper.
export const STAGES = ["sandbox", "investigate", "fix", "verify", "review", "report"] as const;
export type Stage = (typeof STAGES)[number];

export interface TimelineItem {
  seq: number;
  t: number;
  kind: "phase" | "tool" | "hypothesis" | "resolve" | "patch" | "verify" | "note" | "alert";
  title: string;
  detail?: string;
  tone?: "good" | "bad" | "neutral" | "signal";
}

export interface RunState {
  phase: Phase;
  model?: string;
  isolation?: string;
  elapsed: number;
  hypotheses: Hypothesis[];
  baseline?: Record<string, Outcome>;
  verification?: Verification;
  secondOpinion?: SecondOpinion;
  diff: string;
  report?: Report;
  error?: string;
  toolCalls: number;
  timeline: TimelineItem[];
  reached: Stage[];
  brief?: string;
  regressionTests: string[]; // tests the agent wrote that reproduce a bug
  images: string[]; // screenshots given to the model as evidence
  reviewRetries: number;
}

export const initialState: RunState = {
  phase: "starting",
  elapsed: 0,
  hypotheses: [],
  diff: "",
  toolCalls: 0,
  timeline: [],
  reached: [],
  regressionTests: [],
  images: [],
  reviewRetries: 0,
};

const TOOL_LABELS: Record<string, string> = {
  read_log: "Read logs",
  read_file: "Read code",
  send_request: "Sent request",
  run_tests: "Ran tests",
  edit_file: "Edited code",
  show_diff: "Reviewed diff",
  write_regression_test: "Wrote a reproducing test",
};

function describeTool(tool: string, args: Record<string, unknown>): string {
  switch (tool) {
    case "read_log": {
      const filters = ["level", "path_contains", "request_id"].filter((k) => args[k]).map((k) => `${k}=${args[k]}`);
      return filters.length ? filters.join(", ") : `service ${args.service ?? ""}`.trim();
    }
    case "read_file": {
      const range = args.start_line ? ` (from line ${args.start_line})` : "";
      return `${args.path}${range}`;
    }
    case "send_request": {
      const headers = (args.headers ?? {}) as Record<string, string>;
      const auth = headers.Authorization ?? headers.authorization;
      const who = auth ? ` as ${auth.replace("Bearer token-", "")}` : "";
      return `${args.method} ${args.path}${who}`;
    }
    case "run_tests":
      return (args.selector as string) || "full suite";
    case "edit_file":
    case "write_regression_test":
      return String(args.path ?? "");
    default:
      return "";
  }
}

function upsert(list: Hypothesis[], h: Hypothesis): Hypothesis[] {
  const i = list.findIndex((x) => x.id === h.id);
  if (i === -1) return [...list, h];
  const next = list.slice();
  next[i] = h;
  return next;
}

export function reduce(state: RunState, e: RunEvent): RunState {
  const t = typeof e.t === "number" ? e.t : state.elapsed;
  const s: RunState = { ...state, elapsed: Math.max(state.elapsed, t) };
  const add = (item: Omit<TimelineItem, "seq" | "t">) => {
    s.timeline = [...s.timeline, { seq: e.seq, t, ...item }];
  };
  const reach = (stage: Stage) => {
    if (!s.reached.includes(stage)) s.reached = [...s.reached, stage];
  };

  switch (e.type) {
    case "start":
      s.model = e.model as string;
      s.isolation = e.isolation as string;
      reach("sandbox");
      add({ kind: "note", title: "Sandbox ready", detail: `${e.isolation} isolation, ${e.model}`, tone: "neutral" });
      break;
    case "seeded": {
      const statuses = (e.statuses as number[]) ?? [];
      const errors = statuses.filter((x) => x >= 500).length;
      add({ kind: "note", title: `Replayed ${e.requests} requests`, detail: errors ? `${errors} returned 5xx` : "all succeeded", tone: "neutral" });
      break;
    }
    case "baseline":
      s.baseline = e.tests as Record<string, Outcome>;
      break;
    case "evidence_image":
      s.images = [...s.images, e.name as string];
      add({ kind: "note", title: "Screenshot given to the model", detail: e.name as string, tone: "signal" });
      break;
    case "brief":
      s.brief = e.text as string;
      add({ kind: "note", title: "Evidence brief prepared", detail: "log patterns and failing tests, computed by the harness at no token cost", tone: "neutral" });
      break;
    case "phase": {
      const phase = e.phase as Phase;
      s.phase = phase;
      if (phase === "investigate" || phase === "fix" || phase === "review" || phase === "report") reach(phase);
      const titles: Record<string, string> = { investigate: "Investigating", fix: "Fixing in the sandbox", review: "Independent review", report: "Writing the report" };
      add({ kind: "phase", title: titles[phase] ?? phase });
      break;
    }
    case "hypothesis": {
      const h = e as unknown as Hypothesis;
      s.hypotheses = upsert(s.hypotheses, { ...h, evidence: h.evidence ?? [] });
      add({ kind: "hypothesis", title: `${h.id} proposed`, detail: h.claim, tone: "signal" });
      break;
    }
    case "hypothesis_update": {
      const h = e as unknown as Hypothesis;
      s.hypotheses = upsert(s.hypotheses, h);
      add({ kind: "resolve", title: `${h.id} ${h.status}`, detail: h.reason, tone: h.status === "confirmed" ? "good" : "bad" });
      break;
    }
    case "tool_call": {
      const tool = e.tool as string;
      s.toolCalls += 1;
      add({ kind: "tool", title: TOOL_LABELS[tool] ?? tool, detail: describeTool(tool, (e.args ?? {}) as Record<string, unknown>) });
      break;
    }
    case "patch":
      s.diff = (e.diff as string) ?? s.diff;
      add({ kind: "patch", title: "Patched the sandbox copy", detail: e.path as string, tone: "signal" });
      break;
    case "blocked":
      add({ kind: "alert", title: "Blocked an edit to the tests", detail: "Tests are the ground truth", tone: "bad" });
      break;
    case "verification": {
      const v = e as unknown as Verification;
      s.verification = v;
      reach("verify");
      add({
        kind: "verify",
        title: v.verified ? "Fix verified" : "Fix not verified",
        detail: `${formatTally(v.before)} → ${formatTally(v.after)}`,
        tone: v.verified ? "good" : "bad",
      });
      break;
    }
    case "second_opinion": {
      const o = e as unknown as SecondOpinion;
      s.secondOpinion = o;
      const labels = { approve: "approved the fix", concerns: "raised concerns", reject: "rejected the fix", unavailable: "unavailable" };
      add({
        kind: "verify",
        title: `Reviewer ${labels[o.verdict] ?? o.verdict}`,
        detail: o.verdict === "unavailable" ? o.error : o.summary,
        tone: o.verdict === "approve" ? "good" : o.verdict === "unavailable" ? "neutral" : "bad",
      });
      break;
    }
    case "regression_test": {
      const tests = Object.keys((e.tests ?? {}) as Record<string, Outcome>);
      if (e.accepted) {
        s.regressionTests = [...s.regressionTests.filter((t) => !t.startsWith(e.path as string)), ...tests];
        s.baseline = { ...(s.baseline ?? {}), ...Object.fromEntries(tests.map((t) => [t, "failed" as Outcome])) };
        add({ kind: "resolve", title: "Reproducing test kept", detail: `${tests.length} new test${tests.length === 1 ? "" : "s"} fail on the current code`, tone: "signal" });
      } else {
        add({ kind: "alert", title: "Test not kept", detail: "it didn't fail on the current code, so it reproduces nothing", tone: "neutral" });
      }
      break;
    }
    case "review_retry":
      s.reviewRetries += 1;
      add({ kind: "alert", title: "Reviewer objections sent back", detail: "one more fix round with the reviewer's risks", tone: "bad" });
      break;
    case "recovered":
      add({ kind: "alert", title: "Recovered the conversation", detail: e.reason as string, tone: "neutral" });
      break;
    case "budget":
      add({ kind: "alert", title: "Step budget reached", detail: `in ${e.phase}`, tone: "neutral" });
      break;
    case "skip_fix":
      add({ kind: "alert", title: "No fix attempted", detail: e.reason as string, tone: "neutral" });
      break;
    case "report":
      s.report = e.report as Report;
      s.diff = s.report.diff || s.diff;
      s.verification = s.verification ?? s.report.verification;
      s.secondOpinion = s.secondOpinion ?? s.report.second_opinion ?? undefined;
      s.phase = "done";
      break;
    case "error":
      s.error = e.message as string;
      s.phase = "failed";
      add({ kind: "alert", title: "Investigation failed", detail: s.error, tone: "bad" });
      break;
  }
  return s;
}

// Measured, not list price: the Meta Model API billing page showed $2.51 spent for about 2.0M tokens
// on Oct 28 (cache hits make input cheaper). The open-weight reviewer runs on separate Baseten credits.
export const USD_PER_MILLION_TOKENS = 1.25;

export function estimateCost(tokens: number): string {
  const usd = (tokens / 1_000_000) * USD_PER_MILLION_TOKENS;
  return usd < 0.01 ? "<$0.01" : `$${usd.toFixed(2)}`;
}

export function formatTally(tally: Record<string, number> | undefined): string {
  if (!tally) return "";
  const passed = tally.passed ?? 0;
  const total = Object.values(tally).reduce((a, b) => a + b, 0);
  return `${passed}/${total} passing`;
}

export function shortTest(nodeId: string): string {
  return nodeId.split("::").pop()?.replace(/^test_/, "").replaceAll("_", " ") ?? nodeId;
}
