"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import s from "@/components/ui.module.css";
import { RunView } from "@/components/RunView";
import { API_URL, backendAvailable, loadRecording, loadRecordingIndex, startLiveRun, streamRun, type RecordingIndexEntry } from "@/lib/api";
import { initialState, reduce, type RunEvent, type RunState, type ScenarioSummary } from "@/lib/run";

type Action = { type: "event"; event: RunEvent } | { type: "events"; events: RunEvent[] } | { type: "reset" };

function runReducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return initialState;
  if (action.type === "events") return action.events.reduce(reduce, state);
  return reduce(state, action.event);
}

const SPEEDS = [4, 10, 25];
const MAX_GAP_MS = 1400;

interface Active {
  scenario: ScenarioSummary;
  mode: "live" | "replay";
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
    } catch (err) {
      setStartError(err instanceof Error ? err.message : String(err));
    }
  };

  const runLive = async (scenario: ScenarioSummary) => {
    reset();
    try {
      const runId = await startLiveRun(scenario.id);
      setActive({ scenario, mode: "live" });
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

  const replayControls =
    active?.mode === "replay" ? (
      <>
        <span>Recorded run, played at</span>
        {SPEEDS.map((x) => (
          <button key={x} type="button" className={`${s.button} ${x === speed ? s.primary : ""}`} onClick={() => setSpeed(x)} aria-pressed={x === speed}>
            {x}×
          </button>
        ))}
        {cursor < queue.length && (
          <button
            type="button"
            className={s.button}
            onClick={() => {
              dispatch({ type: "events", events: queue.slice(cursor) });
              setCursor(queue.length);
            }}
          >
            Skip to result
          </button>
        )}
      </>
    ) : (
      <span>Live run against the TracePilot backend</span>
    );

  return (
    <div className={s.shell}>
      <div className={s.topbar}>
        <div className={s.brand}>
          <span>
            Trace<span className={s.brandMark}>Pilot</span> AI
          </span>
          <span className={s.brandSub}>Built on Meta Muse Spark</span>
        </div>
        <span className={s.connection}>
          <span className={`${s.dot} ${live ? s.dotLive : ""}`} aria-hidden="true" />
          {live === null ? "Checking for a live backend…" : live ? "Live backend connected" : "Replay mode: recorded runs"}
        </span>
      </div>

      {active ? (
        <RunView scenario={active.scenario} state={state} mode={active.mode} onBack={back} replayControls={replayControls} />
      ) : (
        <>
          <section className={s.hero}>
            <p className={s.eyebrow}>Evidence-first debugging</p>
            <h1 className={s.heroTitle}>The AI debugger that proves its fix</h1>
            <p className={s.heroText}>
              TracePilot reads an incident ticket, forms hypotheses, tests each one against logs, code and real requests, then patches a sandboxed copy of the app. A fix counts
              only when the test suite says so.
            </p>
            <ul className={s.steps} aria-label="How an investigation runs">
              <li>sandbox</li>
              <li>hypothesize</li>
              <li>gather evidence</li>
              <li>confirm or reject</li>
              <li>patch</li>
              <li>verify with tests</li>
            </ul>
          </section>

          {startError && <p className={s.errorText}>{startError}</p>}

          <section className={s.scenarios} aria-label="Incident scenarios">
            {scenarios.length === 0 && <p className={s.empty}>Loading scenarios…</p>}
            {scenarios.map((scenario) => {
              const recording = index.find((e) => e.scenario.id === scenario.id);
              return (
                <article key={scenario.id} className={s.scenario}>
                  <span className={s.service}>{scenario.service}</span>
                  <h2 className={s.scenarioTitle}>{scenario.title}</h2>
                  <p className={s.ticket}>{scenario.incident}</p>
                  <div className={s.actions}>
                    {recording && (
                      <button type="button" className={`${s.button} ${s.primary}`} onClick={() => replay(recording)}>
                        Watch recorded run
                      </button>
                    )}
                    <button type="button" className={s.button} onClick={() => runLive(scenario)} disabled={!live} title={live ? undefined : "Start the backend to run live"}>
                      Run live
                    </button>
                  </div>
                  {recording && (
                    <span className={s.hint}>
                      Recorded: {recording.verified ? "fix verified" : "not verified"} in {Math.round(recording.duration_s / 60)} min of real time
                    </span>
                  )}
                </article>
              );
            })}
          </section>
        </>
      )}
    </div>
  );
}
