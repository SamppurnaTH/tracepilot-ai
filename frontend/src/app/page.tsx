"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import s from "@/components/ui.module.css";
import { RunView } from "@/components/RunView";
import { Logo, Severity } from "@/components/bits";
import { API_URL, backendAvailable, loadRecording, loadRecordingIndex, startLiveRun, streamRun, type RecordingIndexEntry } from "@/lib/api";
import { publicTicket } from "@/lib/report";
import { formatTally, initialState, reduce, type RunEvent, type RunState, type ScenarioSummary } from "@/lib/run";

type Action = { type: "event"; event: RunEvent } | { type: "events"; events: RunEvent[] } | { type: "reset" };

function runReducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return initialState;
  if (action.type === "events") return action.events.reduce(reduce, state);
  return reduce(state, action.event);
}

const REPO_URL = "https://github.com/SamppurnaTH/tracepilot-ai";
const SPEEDS = [4, 10, 25];
const MAX_GAP_MS = 1400;
// Average tokens per investigation before the token-economy work (three real runs, Oct 28).
const FIRST_VERSION_TOKENS = 109_600;

interface Active {
  scenario: ScenarioSummary;
  mode: "live" | "replay";
}

const STEPS = [
  ["Isolate", "The service is copied into a locked-down Docker sandbox (no network, read-only, non-root) and real traffic is replayed to produce logs."],
  ["Investigate", "Muse Spark registers each suspected cause as a hypothesis and confirms it only with cited evidence: log lines, code, reproduced requests, tests."],
  ["Patch", "With confirmed causes, it edits the sandbox copy. The tests are read-only ground truth and can't be weakened."],
  ["Verify", "The harness, not the model, compares every test before and after. A fix counts only if all failures pass and nothing regresses."],
  ["Second opinion", "Muse Spark Open, an open-weight Meta model, reviews the patch cold and rejects fixes that only game the tests."],
  ["Hand off", "You get the root causes, the patch, a PR description and a full report, ready to apply."],
];

const kTokens = (n: number) => `${Math.round(n / 1000)}K`;
const minutes = (sec: number) => (sec < 60 ? `${Math.round(sec)} s` : `${(sec / 60).toFixed(1)} min`);

function Landing({
  index,
  scenarios,
  live,
  startError,
  onReplay,
  onLive,
}: {
  index: RecordingIndexEntry[];
  scenarios: ScenarioSummary[];
  live: boolean | null;
  startError: string | null;
  onReplay: (entry: RecordingIndexEntry) => void;
  onLive: (scenario: ScenarioSummary) => void;
}) {
  const issues = index.flatMap((e) => e.issues ?? []);
  const security = issues.filter((i) => i.category === "security").length;
  const withTokens = index.filter((e) => e.tokens);
  const avgTokens = withTokens.length ? withTokens.reduce((a, e) => a + (e.tokens ?? 0), 0) / withTokens.length : 0;
  const avgTime = index.length ? index.reduce((a, e) => a + e.duration_s, 0) / index.length : 0;
  const saving = avgTokens ? Math.round((1 - avgTokens / FIRST_VERSION_TOKENS) * 100) : 0;
  const first = index[0];

  return (
    <>
      <section className={s.hero}>
        <p className={s.kicker}>
          <span className={s.kickerDot} aria-hidden="true" />
          Built on Meta Muse Spark, with an open-weight reviewer
        </p>
        <h1 className={s.heroTitle}>Root cause, patch and proof for every incident.</h1>
        <p className={s.heroText}>
          TracePilot investigates a failing service like a senior engineer: it tests hypotheses against logs, code and live requests in a sandbox, patches the code, and calls it fixed
          only when your test suite and an independent model agree.
        </p>
        <div className={s.heroActions}>
          {first && (
            <button type="button" className={`${s.btn} ${s.btnPrimary} ${s.btnLg}`} onClick={() => onReplay(first)}>
              Watch an investigation
            </button>
          )}
          <a className={`${s.btn} ${s.btnLg}`} href={REPO_URL} target="_blank" rel="noreferrer">
            View the source
          </a>
        </div>
      </section>

      {index.length > 0 && (
        <section className={s.metrics} aria-label="Results from recorded runs">
          <div className={s.metric}>
            <span className={s.metricValue}>
              {index.filter((e) => e.verified).length}/{index.length}
            </span>
            <span className={s.metricLabel}>incidents fixed and verified by tests</span>
          </div>
          <div className={s.metric}>
            <span className={s.metricValue}>{issues.length}</span>
            <span className={s.metricLabel}>
              root causes found, {security} of them security flaws
            </span>
          </div>
          <div className={s.metric}>
            <span className={s.metricValue}>{minutes(avgTime)}</span>
            <span className={s.metricLabel}>average from ticket to verified patch</span>
          </div>
          <div className={s.metric}>
            <span className={s.metricValue}>{avgTokens ? kTokens(avgTokens) : "…"}</span>
            <span className={s.metricLabel}>tokens per investigation{saving > 0 ? `, ${saving}% fewer than our first version` : ""}</span>
          </div>
        </section>
      )}

      <section className={s.section} aria-labelledby="incidents-title">
        <div className={s.sectionHead}>
          <h2 id="incidents-title" className={s.sectionTitle}>
            Incidents
          </h2>
          <p className={s.sectionText}>
            Three synthetic services with planted defects. Each recording is a real, unedited run: investigated by muse-spark-1.3, reviewed by Muse Spark Open.
          </p>
        </div>
        {startError && <p className={s.errorText}>{startError}</p>}
        <div className={s.incidents}>
          {scenarios.length === 0 && <p className={s.muted}>Loading incidents…</p>}
          {scenarios.map((scenario) => {
            const rec = index.find((e) => e.scenario.id === scenario.id);
            const ticket = publicTicket(scenario.incident).split("\n").filter((l) => /^\d+\./.test(l));
            return (
              <article key={scenario.id} className={s.incident}>
                <div className={s.incidentMain}>
                  <span className={s.service}>{scenario.service}</span>
                  <h3 className={s.incidentTitle}>{scenario.title}</h3>
                  <ul className={s.ticketList}>
                    {ticket.map((line) => (
                      <li key={line}>{line.replace(/^\d+\.\s*/, "")}</li>
                    ))}
                  </ul>
                  {rec?.issues && (
                    <div className={s.tagRow}>
                      {rec.issues.map((i) => (
                        <Severity key={i.title} level={i.severity} label={`${i.severity} · ${i.category}`} />
                      ))}
                    </div>
                  )}
                </div>
                <div className={s.incidentSide}>
                  {rec && (
                    <dl className={s.facts}>
                      <div>
                        <dt>Result</dt>
                        <dd className={rec.verified ? s.goodText : s.badText}>{rec.verified ? "Verified" : "Not verified"}</dd>
                      </div>
                      {rec.tests && (
                        <div>
                          <dt>Tests</dt>
                          <dd>
                            {formatTally(rec.tests.before).replace(" passing", "")} → {formatTally(rec.tests.after).replace(" passing", "")}
                          </dd>
                        </div>
                      )}
                      <div>
                        <dt>Time</dt>
                        <dd>{minutes(rec.duration_s)}</dd>
                      </div>
                      {rec.tokens && (
                        <div>
                          <dt>Tokens</dt>
                          <dd>{kTokens(rec.tokens)}</dd>
                        </div>
                      )}
                    </dl>
                  )}
                  <div className={s.incidentActions}>
                    {rec && (
                      <button type="button" className={`${s.btn} ${s.btnPrimary}`} onClick={() => onReplay(rec)}>
                        Replay run
                      </button>
                    )}
                    <button type="button" className={s.btn} onClick={() => onLive(scenario)} disabled={!live} title={live ? undefined : "Live runs need the backend (Docker sandbox)"}>
                      Run live
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className={s.section} id="how" aria-labelledby="how-title">
        <div className={s.sectionHead}>
          <h2 id="how-title" className={s.sectionTitle}>
            How it works
          </h2>
          <p className={s.sectionText}>The model does the reasoning. The harness owns the facts: what was tried, what changed, and whether it worked.</p>
        </div>
        <ol className={s.steps}>
          {STEPS.map(([title, text], i) => (
            <li key={title} className={s.step}>
              <span className={s.stepNum}>{String(i + 1).padStart(2, "0")}</span>
              <h3 className={s.stepTitle}>{title}</h3>
              <p className={s.stepText}>{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className={s.section} aria-labelledby="economy-title">
        <div className={s.economy}>
          <div>
            <h2 id="economy-title" className={s.sectionTitle}>
              Spend less, get more
            </h2>
            <p className={s.sectionText}>
              Every model call re-reads the whole conversation, so TracePilot does the cheap work itself and gives the model only what matters.
            </p>
          </div>
          <ul className={s.economyList}>
            <li>
              <strong>Free evidence brief.</strong> The harness groups log errors and failing tests before the first model call, saving exploratory round trips.
            </li>
            <li>
              <strong>Compact stack traces.</strong> Framework frames are dropped, keeping only your code, so a 5,000-character traceback becomes four lines.
            </li>
            <li>
              <strong>Fresh-context report.</strong> The final report is written from recorded facts instead of the full transcript.
            </li>
            <li>
              <strong>Small reviewer.</strong> The open-weight second opinion costs a few thousand tokens and seconds, not another investigation.
            </li>
          </ul>
        </div>
      </section>
    </>
  );
}

export default function Home() {
  const [index, setIndex] = useState<RecordingIndexEntry[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [live, setLive] = useState<boolean | null>(null);
  const [active, setActive] = useState<Active | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [state, dispatch] = useReducer(runReducer, initialState);

  // Replay state: the recorded events and how far playback has got.
  const [queue, setQueue] = useState<RunEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [speed, setSpeed] = useState(SPEEDS[1]);
  const closeStream = useRef<(() => void) | null>(null);

  useEffect(() => {
    loadRecordingIndex()
      .then((entries) => {
        setIndex(entries);
        setScenarios((current) => (current.length ? current : entries.map((e) => e.scenario)));
      })
      .catch(() => setIndex([]));
    backendAvailable().then(async (up) => {
      setLive(up);
      if (up) {
        const resp = await fetch(`${API_URL}/api/scenarios`).catch(() => null);
        if (resp?.ok) setScenarios(await resp.json());
      }
    });
  }, []);

  // Play the next recorded event after a gap compressed from the real timing.
  useEffect(() => {
    if (active?.mode !== "replay" || cursor >= queue.length) return;
    const prev = queue[cursor - 1]?.t ?? 0;
    const next = queue[cursor].t ?? prev;
    const delay = Math.min(Math.max(((next - prev) * 1000) / speed, 40), MAX_GAP_MS);
    const timer = setTimeout(() => {
      dispatch({ type: "event", event: queue[cursor] });
      setCursor((c) => c + 1);
    }, delay);
    return () => clearTimeout(timer);
  }, [active, cursor, queue, speed]);

  const reset = useCallback(() => {
    closeStream.current?.();
    closeStream.current = null;
    dispatch({ type: "reset" });
    setQueue([]);
    setCursor(0);
    setStartError(null);
  }, []);

  const replay = async (entry: RecordingIndexEntry) => {
    reset();
    try {
      const recording = await loadRecording(entry.file);
      setActive({ scenario: entry.scenario, mode: "replay" });
      setQueue(recording.events.filter((e) => e.type !== "tool_result" && e.type !== "message"));
      window.scrollTo({ top: 0 });
    } catch (err) {
      setStartError(err instanceof Error ? err.message : String(err));
    }
  };

  const runLive = async (scenario: ScenarioSummary) => {
    reset();
    try {
      const runId = await startLiveRun(scenario.id);
      setActive({ scenario, mode: "live" });
      window.scrollTo({ top: 0 });
      closeStream.current = streamRun(
        runId,
        (event) => dispatch({ type: "event", event }),
        () => (closeStream.current = null),
      );
    } catch (err) {
      setStartError(err instanceof Error ? err.message : String(err));
    }
  };

  const back = () => {
    reset();
    setActive(null);
  };

  const replaying = active?.mode === "replay";
  const controls = replaying ? (
    <div className={s.controls}>
      <div className={s.segmented} role="group" aria-label="Playback speed">
        {SPEEDS.map((x) => (
          <button key={x} type="button" className={x === speed ? s.segOn : undefined} onClick={() => setSpeed(x)} aria-pressed={x === speed}>
            {x}×
          </button>
        ))}
      </div>
      {cursor < queue.length && (
        <button
          type="button"
          className={`${s.btn} ${s.btnSm}`}
          onClick={() => {
            dispatch({ type: "events", events: queue.slice(cursor) });
            setCursor(queue.length);
          }}
        >
          Skip to result
        </button>
      )}
    </div>
  ) : null;

  return (
    <div className={s.app}>
      <header className={s.nav}>
        <div className={s.navInner}>
          <button type="button" className={s.brand} onClick={back} aria-label="TracePilot home">
            <Logo />
            <span>TracePilot</span>
          </button>
          <nav className={s.navLinks} aria-label="Primary">
            {!active && <a href="#how">How it works</a>}
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
            <span className={s.modePill} title={live ? "A TracePilot backend is reachable" : "This deployment replays recorded runs"}>
              <span className={`${s.modeDot} ${live ? s.modeDotLive : ""}`} aria-hidden="true" />
              {live === null ? "Connecting" : live ? "Live" : "Replay"}
            </span>
          </nav>
        </div>
      </header>

      <main className={s.main}>
        {active ? (
          <RunView scenario={active.scenario} state={state} mode={active.mode} onBack={back} controls={controls} />
        ) : (
          <Landing index={index} scenarios={scenarios} live={live} startError={startError} onReplay={replay} onLive={runLive} />
        )}
      </main>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span>TracePilot AI · built for the Meta Global AI Developer Hackathon</span>
          <span>
            muse-spark-1.3 investigates · Muse Spark Open reviews ·{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              MIT licensed
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
}
