"use client";

import { useEffect, useRef, useState } from "react";
import s from "./console.module.css";
import { CopyButton, cx } from "./bits";
import { Icon, type IconName } from "./icons";
import { downloadText, markdownReport, prDescription, publicTicket } from "@/lib/report";
import { estimateCost, formatTally, needsReview, shortTest, type Outcome, type RunState, type ScenarioSummary, type TimelineItem } from "@/lib/run";
import { minutes } from "@/lib/useData";

const kTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}K` : String(n));
const passing = (tally?: Record<string, number>) => formatTally(tally).replace(" passing", "");
const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

function tallyOf(tests: Record<string, Outcome>): Record<string, number> {
  const t: Record<string, number> = {};
  Object.values(tests).forEach((o) => (t[o] = (t[o] ?? 0) + 1));
  return t;
}

// --- diff helpers -------------------------------------------------------------------

export interface FileDiff {
  path: string;
  isNew: boolean;
  lines: string[];
}

export function splitDiff(diff: string): FileDiff[] {
  const files: FileDiff[] = [];
  const lines = diff.replace(/\n$/, "").split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith("--- ") && lines[i + 1]?.startsWith("+++ b/")) {
      const isNew = lines[i] === "--- /dev/null" || Boolean(lines[i + 2]?.startsWith("@@ -0,0 "));
      files.push({ path: lines[i + 1].slice(6), isNew, lines: [lines[i], lines[i + 1]] });
      i++;
    } else if (files.length) {
      files[files.length - 1].lines.push(lines[i]);
    }
  }
  return files;
}

export const isTestPath = (p: string) => p.startsWith("tests/") || p.startsWith("src/test/") || /(^|\/)test_[^/]*$/.test(p);

export function DiffBlock({ files }: { files: FileDiff[] }) {
  return (
    <div className={s.diffFiles}>
      {files.map((f) => {
        const added = f.lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
        const removed = f.lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
        return (
          <div key={f.path} className={s.diffFile}>
            <div className={s.diffFileHead}>
              <span className="mono">{f.path}</span>
              <span>
                {f.isNew && <span className={s.newTag}>new file</span>} <span className={s.plus}>+{added}</span> <span className={s.minus}>−{removed}</span>
              </span>
            </div>
            <pre className={s.diff}>
              {f.lines.slice(2).map((line, i) => (
                <code key={i} className={cx(s.diffLine, line.startsWith("@@") ? s.hunk : line.startsWith("+") ? s.add : line.startsWith("-") ? s.del : undefined)}>
                  {line || " "}
                </code>
              ))}
            </pre>
          </div>
        );
      })}
    </div>
  );
}

// --- stepper ----------------------------------------------------------------------------

type StepState = "done" | "current" | "pending" | "skipped";

function stepStates(state: RunState): [string, string, StepState][] {
  const done = state.phase === "done";
  const noCode = state.report?.outcome === "no_code_change";
  const reached = (stage: string) => state.reached.includes(stage as never);
  const baselineFailing = Object.values(state.baseline ?? {}).some((o) => o !== "passed");
  const reproduced = baselineFailing || state.regressionTests.length > 0;
  const raw: [string, string, boolean, boolean][] = [
    ["Investigate", "Analyze logs & code", reached("investigate"), false],
    ["Reproduce", "Failing test first", reproduced && (reached("fix") || done), noCode],
    ["Fix", "Patch the sandbox copy", reached("verify") || (done && reached("fix")), noCode],
    ["Verify", "Run the tests", reached("verify"), noCode],
    ["Review", "Second opinion", Boolean(state.secondOpinion), noCode],
    ["Complete", "Hand-off report", done, false],
  ];
  let currentSet = false;
  return raw.map(([title, sub, isDone, skipped]) => {
    if (skipped && done) return [title, sub, "skipped"];
    if (isDone) return [title, sub, "done"];
    if (done) return [title, sub, "skipped"];
    if (!currentSet && state.phase !== "failed") {
      currentSet = true;
      return [title, sub, "current"];
    }
    return [title, sub, "pending"];
  });
}

export function Stepper({ state }: { state: RunState }) {
  return (
    <ol className={s.stepper} aria-label="Progress">
      {stepStates(state).map(([title, sub, st], i) => (
        <li key={title} className={cx(s.step, s[`step_${st}`])} aria-current={st === "current" ? "step" : undefined}>
          <span className={s.stepNum} aria-hidden="true">
            {st === "done" ? <Icon name="check" size={14} /> : st === "skipped" ? "–" : i + 1}
          </span>
          <span className={s.stepText}>
            <span className={s.stepTitle}>{title}</span>
            <span className={s.stepSub}>{st === "skipped" ? "Not needed" : sub}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

// --- live progress ------------------------------------------------------------------------

export function Terminal({ items, startedAt }: { items: TimelineItem[]; startedAt?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Follow the newest line inside the terminal only; never scroll the page.
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  const stamp = (t: number) => {
    if (!startedAt) return clock(t);
    const d = new Date((startedAt + t) * 1000);
    return d.toISOString().slice(11, 19);
  };
  const tone = { good: s.tGood, bad: s.tBad, signal: s.tAccent, neutral: undefined };
  return (
    <div ref={ref} className={s.terminal} role="log" aria-label="Investigation log">
      {items.length === 0 && <p className={s.tMuted}>Waiting for the sandbox…</p>}
      {items.map((item) =>
        item.kind === "phase" ? (
          <p key={item.seq} className={s.tPhase}>
            ── {item.title} ──
          </p>
        ) : item.kind === "thought" ? (
          <p key={item.seq} className={cx(s.tLine, s.tThought)}>
            <span className={s.tTime}>[{stamp(item.t)}]</span>
            <span className={s.tText}>
              <span className={s.tThoughtWho}>{item.title}:</span> “{item.detail}”
            </span>
          </p>
        ) : (
          <p key={item.seq} className={s.tLine}>
            <span className={s.tTime}>[{stamp(item.t)}]</span>
            <span className={cx(s.tText, item.tone && tone[item.tone])}>
              {item.title}
              {item.detail && <span className={s.tDetail}> {item.detail}</span>}
            </span>
          </p>
        ),
      )}
    </div>
  );
}

export function OutcomeCard({ state }: { state: RunState }) {
  const r = state.report;
  const stopped = state.error === "Stopped by the user";
  if (!r) {
    const last = [...state.timeline].reverse().find((i) => i.kind !== "phase" && i.kind !== "thought");
    return (
      <div className={s.outcome}>
        <div className={s.outcomeHead}>
          <span className={cx(s.outcomeIcon, s.outcomeRunning)}>
            <span className={s.pulse} />
          </span>
          <div>
            <p className={s.outcomeTitle}>{state.phase === "failed" ? (stopped ? "Investigation stopped" : "Investigation failed") : "Investigating"}</p>
            <p className={s.outcomeSub}>{state.error ?? last?.title ?? "Starting the sandbox"}</p>
          </div>
        </div>
        {last?.detail && <p className={s.outcomeText}>{last.detail}</p>}
        {state.thought && state.phase !== "failed" && (
          <p className={s.thought}>
            <span className={s.thoughtLabel}>Muse Spark is thinking</span>
            {state.thought}
          </p>
        )}
      </div>
    );
  }
  const noCode = r.outcome === "no_code_change";
  const reviewRequired = needsReview(state);
  const ok = state.verification?.verified && !reviewRequired;
  const issues = r.findings.issues;
  return (
    <div className={s.outcome}>
      <div className={s.outcomeHead}>
        <span className={cx(s.outcomeIcon, noCode || ok ? s.outcomeGood : s.outcomeBad)}>
          <Icon name={noCode || ok ? "check" : "minusCircle"} size={20} />
        </span>
        <div>
          <p className={cx(s.outcomeTitle, noCode || ok ? s.good : s.bad)}>{noCode ? "Root cause found" : reviewRequired ? "Review required" : ok ? "Fix verified" : "Not verified"}</p>
          <p className={s.outcomeSub}>
            {noCode ? "No code change needed" : state.verification ? `Tests ${passing(state.verification.before)} → ${passing(state.verification.after)}` : ""}
          </p>
        </div>
      </div>
      <p className={s.outcomeText}>{r.findings.summary}</p>
      {issues.length > 0 && (
        <>
          <p className={s.outcomeLabel}>{noCode ? "Recommended action" : "What changed"}</p>
          <ol className={s.actions}>
            {issues.map((i, n) => (
              <li key={n}>{i.fix}</li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

// --- other tabs ---------------------------------------------------------------------------

export function RootCauses({ state }: { state: RunState }) {
  const issues = state.report?.findings.issues ?? [];
  const sev = { critical: s.sevBad, high: s.sevWarn, medium: s.sevWarn, low: s.sevMuted };
  const status = { open: s.sevAccent, confirmed: s.sevGood, rejected: s.sevMuted };
  return (
    <div className={s.stack}>
      {issues.map((issue, i) => (
        <article key={i} className={s.card}>
          <div className={s.tags}>
            <span className={cx(s.tag, sev[issue.severity])}>{issue.severity}</span>
            <span className={s.tagPlain}>{issue.category}</span>
          </div>
          <h4 className={s.cardTitle}>{issue.title}</h4>
          <p className={s.cardText}>{issue.root_cause}</p>
          {issue.evidence.length > 0 && (
            <ul className={s.bullets}>
              {issue.evidence.map((e, n) => (
                <li key={n}>{e}</li>
              ))}
            </ul>
          )}
        </article>
      ))}
      <p className={s.sectionLabel}>Hypotheses ({state.hypotheses.filter((h) => h.status === "confirmed").length} confirmed)</p>
      {state.hypotheses.length === 0 && <p className={s.muted}>The agent registers each suspected cause before testing it.</p>}
      {state.hypotheses.map((h) => (
        <div key={h.id} className={s.hyp}>
          <span className={s.hypId}>{h.id}</span>
          <div>
            <p className={s.hypClaim}>{h.claim}</p>
            {(h.reason || h.next_check) && <p className={s.muted}>{h.status === "open" ? `Next check: ${h.next_check}` : h.reason}</p>}
            {h.status === "confirmed" && h.fix_in && h.fix_in !== "code" && <p className={s.muted}>Fix belongs in: {h.fix_in}, not the code</p>}
          </div>
          <span className={cx(s.tag, status[h.status])}>{h.status}</span>
        </div>
      ))}
    </div>
  );
}

export function Evidence({ scenario, state }: { scenario: ScenarioSummary; state: RunState }) {
  return (
    <div className={s.stack}>
      <p className={s.sectionLabel}>Incident ticket</p>
      <pre className={s.pre}>{publicTicket(scenario.incident)}</pre>
      {state.images.length > 0 && (
        <>
          <p className={s.sectionLabel}>Attached screenshots: given to Muse Spark as images</p>
          {state.images.map((name) => (
            <figure key={name} className={s.shot}>
              {/* eslint-disable-next-line @next/next/no-img-element -- a static recording asset, shown at its own size */}
              <img src={`/recordings/${name}`} alt={`Screenshot attached to the incident: ${name}`} loading="lazy" />
              <figcaption>{name}</figcaption>
            </figure>
          ))}
        </>
      )}
      <p className={s.sectionLabel}>Evidence brief: computed by the harness before the first model call, at no token cost</p>
      <pre className={s.pre}>{state.brief ?? "The brief appears once the sandbox has replayed traffic and run the tests."}</pre>
    </div>
  );
}

export function ReproTests({ state, files }: { state: RunState; files: FileDiff[] }) {
  const tests = files.filter((f) => f.isNew && isTestPath(f.path));
  const failingBefore = Object.entries(state.baseline ?? {}).filter(([, o]) => o !== "passed");
  if (tests.length) {
    return (
      <div className={s.stack}>
        <p className={s.muted}>Written by the agent and kept only because each test failed on the original code. They ship with the patch.</p>
        <p className={s.muted}>Check that these assertion failures match the incident. Fail→pass alone does not prove a test failed for the right reason.</p>
        {Object.entries(state.regressionReasons ?? {}).map(([test, reason]) => <div className={s.card} key={test}><strong className="mono">{test}</strong><pre className={s.pre}>{reason}</pre></div>)}
        <DiffBlock files={tests} />
      </div>
    );
  }
  if (state.report?.outcome === "no_code_change") return <p className={s.muted}>No code change was needed, so there was no code bug to reproduce.</p>;
  if (failingBefore.length) {
    return (
      <div className={s.stack}>
        <p className={s.muted}>Existing tests already failed before any change, so they serve as the reproduction:</p>
        <ul className={s.testList}>
          {failingBefore.map(([t]) => (
            <li key={t}>
              <span className={cx(s.tag, s.sevBad)}>failing</span> <span className="mono">{shortTest(t)}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return <p className={s.muted}>No reproducing test yet.</p>;
}

export function TestResults({ state }: { state: RunState }) {
  const v = state.verification;
  const baseline = state.baseline;
  if (!baseline) return <p className={s.muted}>The harness runs the tests before any change.</p>;
  const cells = (tests?: Record<string, Outcome>) => (
    <div className={s.cells} aria-hidden="true">
      {Object.entries(tests ?? {})
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([id, o]) => (
          <span key={id} className={cx(s.cell, o === "passed" ? s.cellPass : s.cellFail)} />
        ))}
    </div>
  );
  return (
    <div className={s.stack}>
      {state.excludedTests?.length ? <p className={s.muted}>Outside verification: {state.excludedTests.length} infrastructure test classes excluded ({state.excludedTests.join(", ")}).</p> : null}
      <div className={s.gauge}>
        <div>
          <p className={s.gaugeLabel}>Before</p>
          <p className={s.gaugeValue}>{passing(tallyOf(baseline))}</p>
          {cells(baseline)}
        </div>
        <Icon name="arrowRight" size={22} className={s.muted} />
        <div>
          <p className={s.gaugeLabel}>After</p>
          <p className={s.gaugeValue}>{v ? passing(v.after) : "…"}</p>
          {cells(v?.tests)}
        </div>
      </div>
      {v && (
        <ul className={s.testList}>
          {v.fixed.map((t) => (
            <li key={t}>
              <span className={cx(s.tag, s.sevGood)}>{state.regressionTests.includes(t) ? "new · fixed" : "fixed"}</span> <span className="mono">{shortTest(t)}</span>
            </li>
          ))}
          {v.regressions.map((t) => (
            <li key={t}>
              <span className={cx(s.tag, s.sevBad)}>broke</span> <span className="mono">{shortTest(t)}</span>
            </li>
          ))}
          {v.still_failing.map((t) => (
            <li key={t}>
              <span className={cx(s.tag, s.sevWarn)}>failing</span> <span className="mono">{shortTest(t)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className={s.muted}>Decided by the harness comparing every test before and after, never by the model.</p>
    </div>
  );
}

export function Review({ state }: { state: RunState }) {
  const o = state.secondOpinion;
  if (!o) return <p className={s.muted}>{state.report?.outcome === "no_code_change" ? "No patch, so nothing to review." : "Muse Spark Open reviews the patch once the tests pass."}</p>;
  const tone = { approve: s.sevGood, concerns: s.sevWarn, reject: s.sevBad, unavailable: s.sevMuted }[o.verdict];
  const assess = { supported: s.sevGood, weak: s.sevWarn, unsupported: s.sevBad };
  return (
    <div className={s.stack}>
      <div className={s.tags}>
        <span className={cx(s.tag, tone)}>{VERDICT[o.verdict]}</span>
        <span className={s.tagPlain}>
          {o.model} · {o.confidence} confidence{o.tokens ? ` · ${kTokens(o.tokens)} tokens` : ""}
        </span>
      </div>
      <p className={s.cardText}>{o.verdict === "unavailable" ? o.error : o.summary}</p>
      {o.hypotheses?.map((h) => (
        <div key={h.id} className={s.hyp}>
          <span className={s.hypId}>{h.id}</span>
          <p className={s.cardText}>{h.note}</p>
          <span className={cx(s.tag, assess[h.assessment])}>{h.assessment}</span>
        </div>
      ))}
      {o.risks && o.risks.length > 0 && (
        <>
          <p className={s.sectionLabel}>Risks it raised</p>
          <ul className={s.bullets}>
            {o.risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </>
      )}
      <p className={s.muted}>An independent open-weight model that saw the facts and the patch, never the investigation transcript.</p>
    </div>
  );
}

// --- summary -------------------------------------------------------------------------------

const VERDICT = { approve: "Approved", concerns: "Concerns raised", reject: "Rejected", unavailable: "Unavailable" };

/**
 * Seconds since the run started, ticking every second while it is live. It counts on from the newest event's own
 * time, so a browser clock that differs from the server's can't skew it.
 */
export function useElapsed(state: RunState, live: boolean): number {
  const [anchor, setAnchor] = useState({ elapsed: state.elapsed, at: 0 });
  const [now, setNow] = useState(0);
  useEffect(() => setAnchor({ elapsed: state.elapsed, at: Date.now() }), [state.elapsed]);
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);
  return live && anchor.at && now > anchor.at ? anchor.elapsed + (now - anchor.at) / 1000 : state.elapsed;
}

export function Summary({ scenario, state, files, elapsed }: { scenario: ScenarioSummary; state: RunState; files: FileDiff[]; elapsed?: number }) {
  const r = state.report;
  const usage = r?.usage;
  const tokens = usage ? usage.input_tokens + usage.output_tokens : undefined;
  const noCode = r?.outcome === "no_code_change";
  const code = files.filter((f) => !isTestPath(f.path));
  const added = code.reduce((a, f) => a + f.lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length, 0);
  const removed = code.reduce((a, f) => a + f.lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length, 0);
  const newTests = files.filter((f) => f.isNew && isTestPath(f.path)).length;
  const confirmed = state.hypotheses.filter((h) => h.status === "confirmed");
  const status = state.phase === "done" ? "Completed" : state.phase === "failed" ? (state.error === "Stopped by the user" ? "Stopped" : "Failed") : "Running";
  const outcome = !r ? "…" : noCode ? "No code change needed" : needsReview(state) ? "Review required" : state.verification?.verified ? "Fix verified" : "Not verified";
  const rows: [string, React.ReactNode, string?][] = [
    ["Status", status, state.phase === "done" ? s.good : state.phase === "failed" ? s.bad : s.accent],
    ["Outcome", outcome, !r ? undefined : noCode || (state.verification?.verified && !needsReview(state)) ? s.good : s.bad],
    ["Root cause", r?.findings.issues[0]?.title ?? confirmed[0]?.claim ?? "…"],
    ["Hypotheses", `${confirmed.length} of ${state.hypotheses.length} confirmed`],
    ["Checks run", String(state.toolCalls)],
    ["Tests written", newTests ? `${newTests} file${newTests > 1 ? "s" : ""}` : "None"],
    ["Code changes", code.length ? `${code.length} file${code.length > 1 ? "s" : ""}, +${added} −${removed}` : r ? "None" : "…"],
    ["Second opinion", state.secondOpinion ? VERDICT[state.secondOpinion.verdict] : r ? "Not needed" : "…", state.secondOpinion?.verdict === "approve" ? s.good : undefined],
    ["Execution time", minutes(r ? r.duration_s : (elapsed ?? state.elapsed))],
    ["Tokens used", tokens ? tokens.toLocaleString() : "…"],
    ["Est. investigator cost", tokens ? `${estimateCost(tokens)} (reviewer/hosting excluded)` : "…"],
  ];
  return (
    <aside className={s.summary} aria-labelledby="summary-title">
      <div className={s.summaryHead}>
        <h3 id="summary-title" className={s.summaryTitle}>
          Investigation summary
        </h3>
      </div>
      <dl className={s.rows}>
        {rows.map(([k, v, tone]) => (
          <div key={k} className={s.row}>
            <dt>{k}</dt>
            <dd className={tone}>{v}</dd>
          </div>
        ))}
      </dl>
      {r && (
        <div className={s.summaryActions}>
          <button type="button" className={cx(s.btn, s.btnPrimary)} onClick={() => downloadText(`tracepilot-${scenario.id}-report.md`, markdownReport(scenario, state))}>
            <Icon name="download" size={16} /> Download report
          </button>
          {!noCode && <CopyButton text={prDescription(scenario, state)} label="Copy PR description" className={s.btn} />}
          {state.diff && <CopyButton text={state.diff} label="Copy patch" className={s.btn} />}
        </div>
      )}
    </aside>
  );
}

// --- the console -------------------------------------------------------------------------

const TABS: [string, string, IconName][] = [
  ["progress", "Live progress", "terminal"],
  ["causes", "Root causes", "search"],
  ["evidence", "Evidence", "logs"],
  ["tests", "Reproducing tests", "test"],
  ["patch", "Proposed patch", "diff"],
  ["results", "Test results", "checkCircle"],
  ["review", "Second opinion", "eye"],
];

export function Console({
  scenario,
  state,
  startedAt,
  controls,
  recorded = false,
}: {
  scenario: ScenarioSummary;
  state: RunState;
  startedAt?: number;
  controls?: React.ReactNode;
  recorded?: boolean;
}) {
  const [tab, setTab] = useState("progress");
  const files = splitDiff(state.diff || "");
  const r = state.report;
  const elapsed = useElapsed(state, !recorded && !r && state.phase !== "done" && state.phase !== "failed");
  const tokens = r ? r.usage.input_tokens + r.usage.output_tokens : undefined;
  const [service, ...rest] = scenario.title.split(":");
  const date = startedAt ? new Date(startedAt * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) : null;
  const statusPill =
    state.phase === "done" ? (
      <span className={cx(s.pill, s.pillGood)}>
        <Icon name="check" size={13} /> Completed
      </span>
    ) : state.phase === "failed" ? (
      <span className={cx(s.pill, state.error === "Stopped by the user" ? s.pillAccent : s.pillBad)}>{state.error === "Stopped by the user" ? "Stopped" : "Failed"}</span>
    ) : (
      <span className={cx(s.pill, s.pillAccent)}>
        <span className={s.pulse} /> {recorded ? "Replaying" : "Running"}
      </span>
    );
  const patchFiles = files.filter((f) => !isTestPath(f.path));
  return (
    <section className={s.console} id="investigation" aria-labelledby="console-title">
      <header className={s.head}>
        <div className={s.headLeft}>
          <span className={s.headIcon}>
            <Icon name="shieldCheck" size={18} />
          </span>
          <h2 id="console-title" className={s.headTitle}>
            Investigation: {rest.length ? `${service.replace(/ API$/, "")} · ${rest.join(":").trim()}` : scenario.title}
          </h2>
          <span className={s.lang}>{scenario.language === "java" ? "Java" : "Python"}</span>
          {statusPill}
        </div>
        <div className={s.headMeta}>
          <span>
            <Icon name="clock" size={15} /> {minutes(r ? r.duration_s : elapsed)}
          </span>
          {tokens && (
            <span>
              <Icon name="layers" size={15} /> {kTokens(tokens)} tokens
            </span>
          )}
          {date && <span className={s.hideNarrow}>{date} UTC</span>}
          <CopyButton
            text={typeof window === "undefined" ? "" : window.location.href}
            label="Share"
            className={s.ghostBtn}
          />
        </div>
      </header>
      <Stepper state={state} />
      {!recorded && !r && state.phase !== "failed" && <div className={s.controls} role="status"><strong>Now: {({ starting: "preparing the isolated sandbox", investigate: "checking hypotheses and reproducing the incident", fix: "patching the sandbox and running tests", review: "reviewing the patch in a separate model context", report: "assembling the evidence report", done: "complete", failed: "stopped" })[state.phase]}</strong><span>Elapsed {clock(elapsed)} · Typical Python demo: 2–4 minutes; Java and custom projects can take longer. {elapsed > 240 ? "This run is taking longer than typical; you can stop it or open a recorded example." : "This is an estimate, not a countdown."}</span></div>}
      {controls && <div className={s.controls}>{controls}</div>}
      <div className={s.body}>
        <div className={s.main}>
          <div className={s.tabs} role="tablist" aria-label="Investigation views">
            {TABS.map(([id, label, icon]) => (
              <button key={id} type="button" role="tab" id={`console-tab-${id}`} aria-controls="console-panel" aria-selected={tab === id} className={cx(s.tab, tab === id && s.tabOn)} onClick={() => setTab(id)}>
                <Icon name={icon} size={15} /> {label}
              </button>
            ))}
          </div>
          <div className={s.tabBody} role="tabpanel" id="console-panel" aria-labelledby={`console-tab-${tab}`}>
            {tab === "progress" && (
              <div className={s.progress}>
                <Terminal items={state.timeline} startedAt={startedAt} />
                <OutcomeCard state={state} />
              </div>
            )}
            {tab === "causes" && <RootCauses state={state} />}
            {tab === "evidence" && <Evidence scenario={scenario} state={state} />}
            {tab === "tests" && <ReproTests state={state} files={files} />}
            {tab === "patch" &&
              (patchFiles.length ? (
                <DiffBlock files={patchFiles} />
              ) : (
                <p className={s.muted}>{r?.outcome === "no_code_change" ? "No patch: the root cause is outside the code." : "The patch appears here once the agent edits the sandbox copy."}</p>
              ))}
            {tab === "results" && <TestResults state={state} />}
            {tab === "review" && <Review state={state} />}
          </div>
        </div>
        <Summary scenario={scenario} state={state} files={files} elapsed={elapsed} />
      </div>
    </section>
  );
}
