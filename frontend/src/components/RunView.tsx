"use client";

import { useEffect, useRef } from "react";
import s from "./ui.module.css";
import {
  formatTally,
  shortTest,
  type Hypothesis,
  type Issue,
  type Outcome,
  type RunState,
  type ScenarioSummary,
  type TimelineItem,
  type Verification,
} from "@/lib/run";

const cx = (...names: (string | false | undefined)[]) => names.filter(Boolean).join(" ");

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function StatusBadge({ state, mode }: { state: RunState; mode: "live" | "replay" }) {
  if (state.phase === "failed") return <span className={cx(s.status, s.statusBad)}>Failed</span>;
  if (state.phase === "done") {
    const ok = state.verification?.verified;
    return <span className={cx(s.status, ok ? s.statusGood : s.statusBad)}>{ok ? "Fix verified" : "Not verified"}</span>;
  }
  const label = state.phase === "starting" ? "Starting sandbox" : state.phase === "fix" ? "Fixing" : state.phase === "report" ? "Reporting" : "Investigating";
  return (
    <span className={cx(s.status, s.statusRunning)}>
      <span className={s.pulse} aria-hidden="true" />
      {mode === "replay" ? `Replay: ${label}` : label}
    </span>
  );
}

function Stats({ state }: { state: RunState }) {
  const usage = state.report?.usage;
  const tokens = usage ? usage.input_tokens + usage.output_tokens : undefined;
  const confirmed = state.hypotheses.filter((h) => h.status === "confirmed").length;
  const items = [
    ["Elapsed", formatClock(state.report?.duration_s ?? state.elapsed)],
    ["Hypotheses", `${confirmed}/${state.hypotheses.length} confirmed`],
    ["Tool calls", String(usage?.tool_calls ?? state.toolCalls)],
    ["Tokens", tokens ? `${Math.round(tokens / 1000)}K` : "…"],
    ["Model", state.model ?? "…"],
    ["Sandbox", state.isolation ?? "…"],
  ];
  return (
    <div className={s.stats}>
      {items.map(([label, value]) => (
        <div key={label} className={s.stat}>
          <span className={s.statLabel}>{label}</span>
          <span className={s.statValue}>{value}</span>
        </div>
      ))}
    </div>
  );
}

function Timeline({ items }: { items: TimelineItem[] }) {
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    // Follow the newest entry inside the log only; never scroll the page itself.
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  const markClass = { good: s.markGood, bad: s.markBad, signal: s.markSignal, neutral: undefined };
  return (
    <section className={s.panel} aria-labelledby="log-title">
      <div className={s.panelHead}>
        <h2 id="log-title" className={s.panelTitle}>Flight log</h2>
        <span className={s.panelMeta}>{items.filter((i) => i.kind === "tool").length} checks run</span>
      </div>
      <ol ref={list} className={s.timeline}>
        {items.length === 0 && <li className={cx(s.entry, s.empty)}>Waiting for the sandbox…</li>}
        {items.map((item) =>
          item.kind === "phase" ? (
            <li key={item.seq} className={s.phaseRow}>
              {item.title}
            </li>
          ) : (
            <li key={item.seq} className={cx(s.entry, item.kind === "tool" && s.entryTool)}>
              <span className={s.entryTime}>{formatClock(item.t)}</span>
              <span className={cx(s.entryMark, item.tone && markClass[item.tone])} aria-hidden="true" />
              <span className={s.entryText}>
                <span className={s.entryTitle}>{item.title}</span>
                {item.detail && <span className={s.entryDetail}> · {item.detail}</span>}
              </span>
            </li>
          ),
        )}
      </ol>
    </section>
  );
}

function HypothesisCard({ h }: { h: Hypothesis }) {
  const tone = { open: [s.hypOpen, s.pillOpen], confirmed: [s.hypConfirmed, s.pillConfirmed], rejected: [s.hypRejected, s.pillRejected] }[h.status];
  return (
    <article className={cx(s.hypothesis, tone[0])}>
      <div className={s.hypTop}>
        <span className={s.hypId}>{h.id}</span>
        <span className={cx(s.pill, tone[1])}>{h.status}</span>
      </div>
      <p className={s.hypClaim}>{h.claim}</p>
      {h.symptom && <p className={s.hypMeta}>Explains: {h.symptom}</p>}
      {h.status === "open" && h.next_check && <p className={s.hypMeta}>Next check: {h.next_check}</p>}
      {h.evidence.length > 0 && (
        <ul className={s.evidence}>
          {h.evidence.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function Hypotheses({ list }: { list: Hypothesis[] }) {
  return (
    <section className={s.panel} aria-labelledby="hyp-title">
      <div className={s.panelHead}>
        <h2 id="hyp-title" className={s.panelTitle}>Hypotheses</h2>
        <span className={s.panelMeta}>Each one needs evidence to be confirmed</span>
      </div>
      <div className={s.panelBody}>
        {list.length === 0 ? (
          <p className={s.empty}>The agent registers each suspected cause here before testing it.</p>
        ) : (
          <div className={s.hypotheses}>
            {list.map((h) => (
              <HypothesisCard key={h.id} h={h} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function Cells({ tests }: { tests?: Record<string, Outcome> }) {
  const outcomes = Object.entries(tests ?? {}).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className={s.cells} aria-hidden="true">
      {outcomes.map(([id, o]) => (
        <span key={id} className={cx(s.cell, o === "passed" ? s.cellPass : s.cellFail)} />
      ))}
    </div>
  );
}

function VerificationPanel({ baseline, v }: { baseline?: Record<string, Outcome>; v?: Verification }) {
  const before = baseline ? Object.values(baseline).filter((o) => o === "passed").length : 0;
  const total = baseline ? Object.keys(baseline).length : 0;
  const rows: [string, string, string][] = v
    ? [
        ...v.fixed.map((t): [string, string, string] => [t, "fixed", s.tagFixed]),
        ...v.regressions.map((t): [string, string, string] => [t, "broke", s.tagBroken]),
        ...v.still_failing.map((t): [string, string, string] => [t, "failing", s.tagStill]),
      ]
    : [];
  return (
    <section className={s.panel} aria-labelledby="verify-title">
      <div className={s.panelHead}>
        <h2 id="verify-title" className={s.panelTitle}>Verification</h2>
        <span className={s.panelMeta}>Decided by the test suite, not the model</span>
      </div>
      <div className={s.panelBody}>
        {!baseline ? (
          <p className={s.empty}>The harness runs the app&apos;s tests before any change.</p>
        ) : (
          <>
            <div className={s.gauge}>
              <div className={s.gaugeSide}>
                <span className={s.gaugeLabel}>Before</span>
                <span className={s.gaugeValue}>
                  {before}/{total}
                </span>
                <Cells tests={baseline} />
              </div>
              <span className={s.arrow} aria-hidden="true">→</span>
              <div className={s.gaugeSide}>
                <span className={s.gaugeLabel}>After fix</span>
                <span className={s.gaugeValue}>{v ? formatTally(v.after).replace(" passing", "") : "…"}</span>
                {v?.tests ? <Cells tests={v.tests} /> : <div className={s.cells} />}
              </div>
            </div>
            {rows.length > 0 && (
              <ul className={s.tests}>
                {rows.map(([id, label, cls]) => (
                  <li key={id + label} className={s.test}>
                    <span className={cx(s.testTag, cls)}>{label}</span>
                    <span className="mono">{shortTest(id)}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function DiffPanel({ diff }: { diff: string }) {
  if (!diff) return null;
  const lines = diff.replace(/\n$/, "").split("\n");
  return (
    <section className={s.panel} aria-labelledby="diff-title">
      <div className={s.panelHead}>
        <h2 id="diff-title" className={s.panelTitle}>Patch</h2>
        <span className={s.panelMeta}>Applied to the sandbox copy only</span>
      </div>
      <pre className={s.diff}>
        {lines.map((line, i) => {
          const cls = line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@") ? s.diffHunk : line.startsWith("+") ? s.diffAdd : line.startsWith("-") ? s.diffDel : undefined;
          return (
            <code key={i} className={cx(s.diffLine, cls)}>
              {line || " "}
            </code>
          );
        })}
      </pre>
    </section>
  );
}

function IssueCard({ issue }: { issue: Issue }) {
  const sev = { critical: s.sevCritical, high: s.sevHigh, medium: s.sevMedium, low: s.sevLow }[issue.severity];
  return (
    <article className={s.issue}>
      <div className={s.issueTop}>
        <span className={cx(s.pill, sev)}>{issue.severity}</span>
        <span className={s.category}>{issue.category}</span>
        {issue.hypothesis_ids.length > 0 && <span className={s.category}>· {issue.hypothesis_ids.join(", ")}</span>}
      </div>
      <p className={s.issueTitle}>{issue.title}</p>
      <p className={s.issueRow}>
        <strong>Root cause:</strong> {issue.root_cause}
      </p>
      <p className={s.issueRow}>
        <strong>Fix:</strong> {issue.fix}
      </p>
    </article>
  );
}

function Findings({ state }: { state: RunState }) {
  const findings = state.report?.findings;
  if (!findings) return null;
  return (
    <section className={s.panel} aria-labelledby="findings-title">
      <div className={s.panelHead}>
        <h2 id="findings-title" className={s.panelTitle}>Findings</h2>
        <span className={s.panelMeta}>{findings.issues.length} issues</span>
      </div>
      <div className={s.panelBody}>
        <p className={s.summary}>{findings.summary}</p>
        <div className={s.issues}>
          {findings.issues.map((issue, i) => (
            <IssueCard key={i} issue={issue} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function RunView({
  scenario,
  state,
  mode,
  onBack,
  replayControls,
}: {
  scenario: ScenarioSummary;
  state: RunState;
  mode: "live" | "replay";
  onBack: () => void;
  replayControls?: React.ReactNode;
}) {
  return (
    <>
      <header className={s.runHeader}>
        <div className={s.runHeaderRow}>
          <div>
            <p className={s.service}>{scenario.service}</p>
            <h1 className={s.runTitle}>{scenario.title}</h1>
          </div>
          <StatusBadge state={state} mode={mode} />
        </div>
        <p className={s.ticket}>{scenario.incident}</p>
        <div className={s.replayBar}>
          <button type="button" className={s.button} onClick={onBack}>
            ← All scenarios
          </button>
          {replayControls}
        </div>
        {state.error && <p className={s.errorText}>{state.error}</p>}
        <Stats state={state} />
      </header>
      <div className={s.grid}>
        <Timeline items={state.timeline} />
        <div className={s.stack}>
          <Hypotheses list={state.hypotheses} />
          <VerificationPanel baseline={state.baseline} v={state.verification} />
          <DiffPanel diff={state.diff} />
          <Findings state={state} />
        </div>
      </div>
    </>
  );
}
