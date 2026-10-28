"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import s from "@/components/app.module.css";
import { EmptyState, SkeletonCards } from "@/components/ScreenState";
import { AppShell } from "@/components/AppShell";
import { CopyButton, cx } from "@/components/bits";
import { Console } from "@/components/Console";
import { Icon } from "@/components/icons";
import { RunResult } from "@/components/RunResult";
import { cancelRun, getRun, loadRecording, loadSavedRun } from "@/lib/api";
import type { ScenarioSummary } from "@/lib/run";
import { SPEEDS, useRun } from "@/lib/useRun";
import { useData } from "@/lib/useData";

function RunPage() {
  const params = useSearchParams();
  const id = params.get("id");
  const liveId = params.get("live");
  const saved = params.get("saved");
  const replay = params.get("replay") === "1";
  const { index, live } = useData();
  const run = useRun();
  const [scenario, setScenario] = useState<ScenarioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [watching, setWatching] = useState(false);
  const { show, follow } = run;

  useEffect(() => {
    setError(null);
    if (id && index) {
      const entry = index.find((e) => e.scenario.id === id);
      if (!entry) return setError(`No recorded run called "${id}".`);
      setScenario(entry.scenario);
      loadRecording(entry.file)
        .then((rec) => show(rec, replay))
        .catch((err) => setError(String(err)));
    } else if (liveId) {
      getRun(liveId)
        .then((summary) => {
          setScenario({ id: summary.scenario === "custom" ? "custom" : summary.scenario, title: summary.title || "Investigation", service: "", incident: "" });
          follow(liveId, summary.started_at);
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    } else if (saved) {
      loadSavedRun(saved)
        .then((rec) => {
          setScenario({ id: rec.scenario, title: (rec as { title?: string }).title || rec.scenario, service: "", incident: "" });
          show(rec, false);
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    }
  }, [id, liveId, saved, index, show, follow, replay]);

  const state = run.state;
  const view = scenario ? { ...scenario, incident: scenario.incident || state.incident || "" } : null;
  const done = state.phase === "done" && !run.replaying;
  const running = run.mode === "live" && state.phase !== "done" && state.phase !== "failed";

  const stop = async () => {
    if (!liveId) return;
    setStopping(true);
    try {
      await cancelRun(liveId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const replayFromStart = async () => {
    const entry = index?.find((e) => e.scenario.id === id);
    if (!entry) return;
    try {
      setError(null);
      show(await loadRecording(entry.file), true);
      setWatching(true);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  };

  const controls = (
    <>
      {run.mode === "replay" && (
        <>
          <span>Recorded run</span>
          <div className={s.segmented} role="group" aria-label="Playback speed">
            {SPEEDS.map((x) => (
              <button key={x} type="button" className={x === run.speed ? s.segOn : undefined} onClick={() => run.setSpeed(x)} aria-pressed={x === run.speed}>
                {x}×
              </button>
            ))}
          </div>
          {run.replaying && (
            <button type="button" className={cx(s.btn, s.btnSm)} onClick={run.skip}>
              Skip to result
            </button>
          )}
        </>
      )}
      {running && (
        <button type="button" className={cx(s.btn, s.btnSm, s.btnDanger)} onClick={stop} disabled={stopping}>
          {stopping ? "Stopping…" : "Stop"}
        </button>
      )}
    </>
  );

  return (
    <AppShell live={live}>
      <div className={s.runHead}>
        <div>
          <Link href={liveId || saved ? "/runs" : "/examples"} className={s.muted}>
            ← {liveId || saved ? "My runs" : "Example scenarios"}
          </Link>
          <h1 className={s.pageTitle}>{view?.title ?? "Investigation"}</h1>
        </div>
        <div className={s.runActions}>
          {done && id && (
            <button type="button" className={s.btn} onClick={replayFromStart}>
              <Icon name="play" size={14} /> Watch step by step
            </button>
          )}
          {done && watching && <span className={s.muted}>Replay finished</span>}
          <CopyButton text={typeof window === "undefined" ? "" : window.location.href} label="Share" className={s.btn} />
        </div>
      </div>
      {error && <EmptyState icon="minusCircle" title="Investigation unavailable" text={error} href="/examples" action="Browse scenarios" />}
      {!view && !error && (id || liveId || saved) && <SkeletonCards count={2} />}
      {view && (done && state.report ? <RunResult scenario={view} state={state} startedAt={run.startedAt} /> : <Console scenario={view} state={state} startedAt={run.startedAt} controls={controls} recorded={run.mode === "replay"} />)}
      {!id && !liveId && !saved && <EmptyState icon="search" title="Every fix starts with an investigation" text="Choose an example to explore the workflow, or connect your own project." href="/examples" action="Explore scenarios" />}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <RunPage />
    </Suspense>
  );
}
