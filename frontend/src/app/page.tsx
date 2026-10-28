"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import s from "@/components/ui.module.css";
import { Console } from "@/components/Console";
import { CopyButton, Logo, cx } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import {
  API_URL,
  backendAvailable,
  loadComparison,
  loadEval,
  loadRecording,
  loadRecordingIndex,
  startLiveRun,
  streamRun,
  type ComparisonSummary,
  type EvalSummary,
  type RecordingIndexEntry,
} from "@/lib/api";
import { publicTicket } from "@/lib/report";
import { estimateCost, initialState, reduce, type RunEvent, type RunState, type ScenarioSummary } from "@/lib/run";

type Action = { type: "event"; event: RunEvent } | { type: "events"; events: RunEvent[] } | { type: "reset" };

function runReducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return initialState;
  if (action.type === "events") return action.events.reduce(reduce, state);
  return reduce(state, action.event);
}

const REPO_URL = "https://github.com/SamppurnaTH/tracepilot-ai";
const SPEEDS = [4, 10, 25];
const MAX_GAP_MS = 1400;
const DEFAULT_SCENARIO = "inventory"; // shows every step: green CI, a test written by the agent, a verified fix, a review

const kTokens = (n: number) => `${Math.round(n / 1000)}K`;
const minutes = (sec: number) => (sec < 60 ? `${Math.round(sec)} s` : `${(sec / 60).toFixed(1)} min`);
const pct = (a: number, b: number) => (b ? `${((a / b) * 100).toFixed(a === b ? 0 : 1)}%` : "—");

const SCENARIO_ICON: Record<string, [IconName, string]> = {
  orders: ["cart", s.iconViolet],
  notes: ["note", s.iconBlue],
  billing: ["receipt", s.iconGreen],
  inventory: ["box", s.iconPink],
  refunds: ["card", s.iconAmber],
};

const STEPS: [string, string, IconName, string][] = [
  ["Investigate", "Logs, code, requests", "search", s.iconViolet],
  ["Reproduce", "A failing test first", "flask", s.iconBlue],
  ["Fix", "Patch a sandbox copy", "code", s.iconGreen],
  ["Verify", "Tests + second opinion", "shieldCheck", s.iconAmber],
  ["Hand-off", "Patch, PR, report", "file", s.iconPink],
];

interface Active {
  scenario: ScenarioSummary;
  mode: "live" | "replay";
  startedAt?: number;
}

// --- sections ----------------------------------------------------------------------------

function Sidebar({ live }: { live: boolean | null }) {
  const links: [string, string, IconName][] = [
    ["Home", "#top", "home"],
    ["Example scenarios", "#scenarios", "list"],
    ["Investigation", "#investigation", "terminal"],
    ["Comparison results", "#compare", "chart"],
    ["Evaluation", "#eval", "check2"],
    ["Run on your code", "#use", "code"],
  ];
  return (
    <aside className={s.sidebar}>
      <a href="#top" className={s.brand} aria-label="TracePilot AI home">
        <Logo />
        <span className={s.brandText}>
          <span className={s.brandName}>
            TracePilot AI <span className={s.beta}>beta</span>
          </span>
          <span className={s.brandSub}>Debug. Verify. Fix.</span>
        </span>
      </a>
      <nav className={s.nav} aria-label="Sections">
        {links.map(([label, href, icon]) => (
          <a key={href} href={href} className={s.navLink}>
            <Icon name={icon} size={18} /> <span>{label}</span>
          </a>
        ))}
        <a href={`${REPO_URL}#readme`} target="_blank" rel="noreferrer" className={s.navLink}>
          <Icon name="book" size={18} /> <span>Documentation</span>
        </a>
      </nav>
      <div className={s.sideCard}>
        <span className={s.sideCardTitle}>Hackathon project</span>
        <span>Meta Global AI Developer Hackathon</span>
        <span className={s.sideMode}>
          <span className={cx(s.modeDot, live && s.modeDotLive)} aria-hidden="true" />
          {live === null ? "Connecting" : live ? "Live backend" : "Replaying real recorded runs"}
        </span>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className={s.sideLink}>
          <Icon name="github" size={15} /> GitHub
        </a>
      </div>
    </aside>
  );
}

function ProvenResults({ data }: { data: ComparisonSummary | null }) {
  const tp = data?.systems.tracepilot;
  const plain = data?.systems.plain;
  if (!tp || !plain) return null;
  const fewer = Math.round((1 - tp.avg_tokens / plain.avg_tokens) * 100);
  const faster = Math.round((1 - tp.avg_duration_s / plain.avg_duration_s) * 100);
  const tiles: [IconName, string, string, string, string][] = [
    ["checkCircle", `${tp.correct}/${tp.runs}`, "TracePilot fixed", `(${pct(tp.correct, tp.runs)}, hidden tests)`, s.iconGreen],
    ["minusCircle", `${plain.correct}/${plain.runs}`, "Plain agent fixed", `(${pct(plain.correct, plain.runs)}, same model)`, s.iconMuted],
    ["layers", `${fewer}%`, "Fewer tokens", `(avg ${kTokens(tp.avg_tokens)} vs ${kTokens(plain.avg_tokens)})`, s.iconBlue],
    ["bolt", `${faster}%`, "Less time", `(avg ${minutes(tp.avg_duration_s)} vs ${minutes(plain.avg_duration_s)})`, s.iconAmber],
  ];
  return (
    <section className={s.proven} aria-labelledby="proven-title">
      <p id="proven-title" className={s.provenTitle}>
        <span className={s.liveDot} aria-hidden="true" /> Proven results <span className={s.muted}>(same model, latest benchmark)</span>
      </p>
      <div className={s.provenGrid}>
        {tiles.map(([icon, value, label, sub, tone]) => (
          <div key={label} className={s.provenTile}>
            <span className={cx(s.provenIcon, tone)}>
              <Icon name={icon} size={20} />
            </span>
            <span>
              <span className={s.provenValue}>{value}</span>
              <span className={s.provenLabel}>{label}</span>
              <span className={s.provenSub}>{sub}</span>
            </span>
          </div>
        ))}
      </div>
      <a href="#compare" className={s.textLink}>
        View the detailed comparison <Icon name="arrowRight" size={15} />
      </a>
    </section>
  );
}

function ScenarioCards({ index, activeId, onPick }: { index: RecordingIndexEntry[]; activeId?: string; onPick: (e: RecordingIndexEntry) => void }) {
  return (
    <section className={s.section} id="scenarios" aria-labelledby="scenarios-title">
      <div className={s.sectionHead}>
        <h2 id="scenarios-title" className={s.sectionTitle}>
          Try an example scenario
        </h2>
        <p className={s.sectionText}>Each is a real, unedited run on a synthetic service. Click one to replay how TracePilot investigates, fixes and verifies it.</p>
      </div>
      <div className={s.cards}>
        {index.length === 0 && <p className={s.muted}>Loading scenarios…</p>}
        {index.map((e) => {
          const [icon, tone] = SCENARIO_ICON[e.scenario.id] ?? ["file", s.iconViolet];
          const [service, ...rest] = e.scenario.title.split(":");
          const first = publicTicket(e.scenario.incident).split("\n").find((l) => /^\d+\./.test(l))?.replace(/^\d+\.\s*/, "");
          const result = e.outcome === "no_code_change" ? "No code change needed" : e.verified ? "Fix verified" : "Not verified";
          return (
            <button key={e.scenario.id} type="button" className={cx(s.card, e.scenario.id === activeId && s.cardOn)} onClick={() => onPick(e)} aria-pressed={e.scenario.id === activeId}>
              <span className={s.cardTop}>
                <span className={cx(s.cardIcon, tone)}>
                  <Icon name={icon} size={20} />
                </span>
                <span className={s.langTag}>Python</span>
              </span>
              <span className={s.cardTitle}>{service}</span>
              <span className={s.cardText}>{rest.join(":").trim() || first}</span>
              <span className={s.cardFoot}>
                <span className={e.verified || e.outcome === "no_code_change" ? s.good : s.bad}>{result}</span>
                <Icon name="arrowRight" size={16} />
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Bars({ title, sub, a, b, fmt, lowerIsBetter }: { title: string; sub: string; a: number; b: number; fmt: (n: number) => string; lowerIsBetter?: boolean }) {
  const max = Math.max(a, b) || 1;
  const cols: [number, string, string][] = [
    [a, "TracePilot", s.barPrimary],
    [b, "Plain agent", s.barMuted],
  ];
  return (
    <div className={s.chart}>
      <p className={s.chartTitle}>{title}</p>
      <p className={s.chartSub}>{sub}</p>
      <div className={s.bars} role="img" aria-label={`${title}: TracePilot ${fmt(a)}, plain agent ${fmt(b)}${lowerIsBetter ? " (lower is better)" : ""}`}>
        {cols.map(([v, label, cls]) => (
          <div key={label} className={s.barCol}>
            <span className={s.barValue}>{fmt(v)}</span>
            <span className={s.barTrack}>
              <span className={cx(s.bar, cls)} style={{ height: `${Math.max(6, (v / max) * 100)}%` }} />
            </span>
            <span className={s.barLabel}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Comparison({ data }: { data: ComparisonSummary | null }) {
  const tp = data?.systems.tracepilot;
  const plain = data?.systems.plain;
  if (!tp || !plain) return null;
  const takeaways = [
    `Fixed ${tp.correct} of ${tp.runs} incidents, judged by hidden tests`,
    `${Math.round((1 - tp.avg_tokens / plain.avg_tokens) * 100)}% fewer tokens, about ${estimateCost(tp.avg_tokens)} per investigation`,
    `${Math.round((1 - tp.avg_duration_s / plain.avg_duration_s) * 100)}% less time to a verified answer`,
    `Writes reproducing tests (${tp.new_tests} files); never edits existing ones`,
    "Knows when not to change code (the refunds incident)",
    "Works on Python and Java (Maven) projects",
  ];
  return (
    <section className={s.section} id="compare" aria-labelledby="compare-title">
      <div className={s.compareGrid}>
        <div className={s.panel}>
          <div className={s.sectionHead}>
            <h2 id="compare-title" className={s.sectionTitle}>
              TracePilot vs a plain AI agent
            </h2>
            <p className={s.sectionText}>
              Same model (muse-spark-1.3), same sandbox, logs and tools, {tp.runs} runs each, including a real Spring Boot codebase. Every patch is judged by hidden acceptance tests
              that neither system sees.
            </p>
          </div>
          <div className={s.charts}>
            <Bars title="Success rate" sub="Higher is better" a={tp.correct / tp.runs} b={plain.correct / plain.runs} fmt={(n) => `${(n * 100).toFixed(n === 1 ? 0 : 1)}%`} />
            <Bars title="Average tokens" sub="Lower is better" a={tp.avg_tokens} b={plain.avg_tokens} fmt={kTokens} lowerIsBetter />
            <Bars title="Average time" sub="Lower is better" a={tp.avg_duration_s} b={plain.avg_duration_s} fmt={minutes} lowerIsBetter />
            <Bars title="Reproducing test files" sub="Proof that ships with the fix" a={tp.new_tests} b={plain.new_tests} fmt={String} />
          </div>
          <p className={s.footnote}>
            Honest reading: the model is strong on its own, and neither system claimed a fix that wasn&apos;t real. The plain agent&apos;s one miss changed code during an incident
            caused by an expired API key. Raw runs: <code className={s.inlineCode}>eval/comparison.json</code>.
          </p>
        </div>
        <aside className={s.panel} aria-labelledby="takeaways-title">
          <h3 id="takeaways-title" className={s.takeawaysTitle}>
            <span className={cx(s.cardIcon, s.iconAmber)}>
              <Icon name="bulb" size={18} />
            </span>
            Key takeaways
          </h3>
          <ul className={s.takeaways}>
            {takeaways.map((t) => (
              <li key={t}>
                <Icon name="checkCircle" size={18} className={s.good} /> {t}
              </li>
            ))}
          </ul>
          <p className={s.footnote}>
            Where it fits: tools like Cursor, GitHub Copilot, OpenHands and Devin also read, edit and test code. TracePilot is narrower on purpose: an incident goes in, and what comes
            out is proof, or a clear &quot;this isn&apos;t a code problem&quot;.
          </p>
        </aside>
      </div>
    </section>
  );
}

function Evaluation({ data }: { data: EvalSummary | null }) {
  if (!data || !data.agent_total.runs) return null;
  const t = data.agent_total;
  const gamed = data.reviewer.gamed;
  const reference = data.reviewer.reference;
  return (
    <section className={s.section} id="eval" aria-labelledby="eval-title">
      <div className={s.sectionHead}>
        <h2 id="eval-title" className={s.sectionTitle}>
          The second opinion catches fixes that only game the tests
        </h2>
        <p className={s.sectionText}>
          Muse Spark Open, an open-weight Meta model, reviews each patch without seeing the investigation. Benchmarked on patches that pass every visible test but don&apos;t fix the
          cause.
        </p>
      </div>
      <div className={s.statRow}>
        {gamed && (
          <div className={s.stat}>
            <span className={s.statValue}>
              {gamed.correct}/{gamed.cases}
            </span>
            <span className={s.statLabel}>test-gaming patches rejected</span>
          </div>
        )}
        {reference && (
          <div className={s.stat}>
            <span className={s.statValue}>
              {reference.correct}/{reference.cases}
            </span>
            <span className={s.statLabel}>correct patches approved</span>
          </div>
        )}
        <div className={s.stat}>
          <span className={s.statValue}>
            {t.verified}/{t.runs}
          </span>
          <span className={s.statLabel}>repeated end-to-end runs verified</span>
        </div>
      </div>
      <ul className={s.caught}>
        {data.reviewer_cases
          .filter((c) => c.kind === "gamed")
          .map((c) => (
            <li key={c.scenario}>
              <span className={cx(s.tag, c.correct ? s.sevPass : s.sevCritical)}>{c.correct ? "rejected" : "missed"}</span>
              <span>
                <span className={s.mono}>{c.scenario}</span> {c.label}
              </span>
            </li>
          ))}
      </ul>
    </section>
  );
}

const CLI = `python tracepilot.py investigate --repo path/to/service --logs app.log \\
  --incident "Orders placed on Friday are promised for Saturday"`;

function UseIt() {
  return (
    <section className={s.section} id="use" aria-labelledby="use-title">
      <div className={s.useGrid}>
        <div className={s.sectionHead}>
          <h2 id="use-title" className={s.sectionTitle}>
            Run it on your own code
          </h2>
          <p className={s.sectionText}>
            Python with pytest, or Java with Maven and JUnit. Your project runs in a local Docker sandbox with no network; you get a patch, a PR description and a report, and nothing
            is applied unless you pass <code className={s.inlineCode}>--apply</code> and the fix was verified.
          </p>
          <p className={s.sectionText}>Tested on projects it had never seen: a shipping module (fixed for about $0.08) and a 260-file Spring Boot app (fixed for about $0.42).</p>
        </div>
        <div className={s.codeCard}>
          <div className={s.codeHead}>
            <span>Terminal</span>
            <CopyButton text={CLI} label="Copy" className={s.copySmall} />
          </div>
          <pre className={s.code}>{CLI}</pre>
        </div>
      </div>
    </section>
  );
}

// --- page ---------------------------------------------------------------------------------

export default function Home() {
  const [index, setIndex] = useState<RecordingIndexEntry[]>([]);
  const [evalData, setEvalData] = useState<EvalSummary | null>(null);
  const [comparison, setComparison] = useState<ComparisonSummary | null>(null);
  const [live, setLive] = useState<boolean | null>(null);
  const [active, setActive] = useState<Active | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [state, dispatch] = useReducer(runReducer, initialState);
  const [queue, setQueue] = useState<RunEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [speed, setSpeed] = useState(SPEEDS[1]);
  const closeStream = useRef<(() => void) | null>(null);

  const reset = useCallback(() => {
    closeStream.current?.();
    closeStream.current = null;
    dispatch({ type: "reset" });
    setQueue([]);
    setCursor(0);
    setError(null);
  }, []);

  const open = useCallback(
    async (entry: RecordingIndexEntry, animate: boolean) => {
      reset();
      try {
        const rec = await loadRecording(entry.file);
        const events = rec.events.filter((e) => e.type !== "tool_result" && e.type !== "message");
        setActive({ scenario: entry.scenario, mode: "replay", startedAt: rec.started_at });
        if (animate) setQueue(events);
        else dispatch({ type: "events", events }); // show the finished run at once
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [reset],
  );

  useEffect(() => {
    loadRecordingIndex()
      .then((entries) => {
        setIndex(entries);
        const wanted = window.location.hash.slice(1);
        const first = entries.find((e) => e.scenario.id === wanted) ?? entries.find((e) => e.scenario.id === DEFAULT_SCENARIO) ?? entries[0];
        if (first) open(first, false);
      })
      .catch(() => setIndex([]));
    loadEval().then(setEvalData);
    loadComparison().then(setComparison);
    backendAvailable().then(setLive);
  }, [open]);

  // A shared "#scenario" link pasted into an already open page switches to that run.
  useEffect(() => {
    const onHash = () => {
      const entry = index.find((e) => e.scenario.id === window.location.hash.slice(1));
      if (entry && entry.scenario.id !== active?.scenario.id) open(entry, false);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [index, active, open]);

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

  const pick = (entry: RecordingIndexEntry) => {
    open(entry, true);
    try {
      history.replaceState(null, "", `#${entry.scenario.id}`);
    } catch {
      /* some embedded views refuse history changes; the replay still works */
    }
    document.getElementById("investigation")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const runLive = async () => {
    if (!active) return;
    const scenario = active.scenario;
    reset();
    try {
      const runId = await startLiveRun(scenario.id);
      setActive({ scenario, mode: "live", startedAt: Date.now() / 1000 });
      closeStream.current = streamRun(
        runId,
        (event) => dispatch({ type: "event", event }),
        () => (closeStream.current = null),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const activeEntry = index.find((e) => e.scenario.id === active?.scenario.id);
  const replaying = active?.mode === "replay" && cursor < queue.length;
  const controls = active ? (
    <>
      <span>{active.mode === "live" ? "Live run on the TracePilot backend" : "Recorded run"}</span>
      {active.mode === "replay" && (
        <>
          <div className={s.segmented} role="group" aria-label="Playback speed">
            {SPEEDS.map((x) => (
              <button key={x} type="button" className={x === speed ? s.segOn : undefined} onClick={() => setSpeed(x)} aria-pressed={x === speed}>
                {x}×
              </button>
            ))}
          </div>
          {replaying ? (
            <button
              type="button"
              className={s.miniBtn}
              onClick={() => {
                dispatch({ type: "events", events: queue.slice(cursor) });
                setCursor(queue.length);
              }}
            >
              Skip to result
            </button>
          ) : (
            activeEntry && (
              <button type="button" className={s.miniBtn} onClick={() => open(activeEntry, true)}>
                <Icon name="play" size={13} /> Replay step by step
              </button>
            )
          )}
        </>
      )}
      {live && (
        <button type="button" className={s.miniBtn} onClick={runLive}>
          <Icon name="bolt" size={13} /> Run live
        </button>
      )}
    </>
  ) : null;

  return (
    <div className={s.app} id="top">
      <Sidebar live={live} />
      <div className={s.mainCol}>
        <header className={s.topbar}>
          <a href={`${REPO_URL}#readme`} target="_blank" rel="noreferrer" className={s.topLink}>
            Docs
          </a>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={s.topLink}>
            GitHub
          </a>
          <button type="button" className={cx(s.btn, s.btnDark)} onClick={() => activeEntry && pick(activeEntry)} disabled={!activeEntry}>
            <Icon name="play" size={14} /> Watch a run
          </button>
        </header>

        <main className={s.main}>
          <div className={s.heroGrid}>
            <section className={s.hero} aria-labelledby="hero-title">
              <p className={s.kicker}>Verification-first debugging agent · built on Meta Muse Spark</p>
              <h1 id="hero-title" className={s.heroTitle}>
                From errors to <span className={s.gradient}>verified fixes</span>
              </h1>
              <p className={s.heroText}>
                TracePilot investigates a failing service, writes a test that reproduces the bug, fixes it, proves the fix with your tests and an independent model, and tells you
                exactly what to do. When the cause isn&apos;t in the code, it says so instead of patching.
              </p>
              <ol className={s.steps}>
                {STEPS.map(([title, sub, icon, tone], i) => (
                  <li key={title} className={s.stepPill}>
                    <span className={cx(s.stepIcon, tone)}>
                      <Icon name={icon} size={18} />
                    </span>
                    <span>
                      <span className={s.stepTitle}>
                        {i + 1}. {title}
                      </span>
                      <span className={s.stepSub}>{sub}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <div className={s.heroActions}>
                <a href="#use" className={cx(s.btn, s.btnDark, s.btnLg)}>
                  Run it on your code <Icon name="arrowRight" size={16} />
                </a>
                <a href="#scenarios" className={cx(s.btn, s.btnLg)}>
                  See example scenarios
                </a>
              </div>
            </section>
            <ProvenResults data={comparison} />
          </div>

          <ScenarioCards index={index} activeId={active?.scenario.id} onPick={pick} />

          {error && <p className={s.errorText}>{error}</p>}
          {active && <Console scenario={active.scenario} state={state} startedAt={active.startedAt} controls={controls} />}

          <Comparison data={comparison} />
          <Evaluation data={evalData} />
          <UseIt />
        </main>

        <footer className={s.footer}>
          <span>TracePilot AI · built for the Meta Global AI Developer Hackathon · MIT licensed</span>
          <span>Investigator: muse-spark-1.3 (Meta Model API) · Reviewer: Muse Spark Open (Baseten){API_URL ? "" : " · replaying recorded runs"}</span>
        </footer>
      </div>
    </div>
  );
}
