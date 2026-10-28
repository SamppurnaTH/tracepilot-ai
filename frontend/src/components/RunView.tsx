"use client";

import { useEffect, useRef } from "react";
import s from "./ui.module.css";
import { CopyButton, Severity, cx } from "./bits";
import { downloadText, markdownReport, prDescription, publicTicket } from "@/lib/report";
import {
  STAGES,
  formatTally,
  shortTest,
  type Hypothesis,
  type Issue,
  type Outcome,
  type RunState,
  type ScenarioSummary,
  type SecondOpinion,
  type Stage,
  type TimelineItem,
  type Verification,
} from "@/lib/run";

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

const kTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}K` : String(n));
const passing = (tally?: Record<string, number>) => formatTally(tally).replace(" passing", "");

const STAGE_LABEL: Record<Stage, string> = {
  sandbox: "Sandbox",
  investigate: "Investigate",
  fix: "Patch",
  verify: "Verify",
  review: "Second opinion",
  report: "Report",
};

const REVIEW: Record<SecondOpinion["verdict"], [string, string]> = {
  approve: ["Approved", s.goodText],
  concerns: ["Concerns", s.warnText],
  reject: ["Rejected", s.badText],
  unavailable: ["Unavailable", s.muted],
};

function StatusBadge({ state }: { state: RunState }) {
  if (state.phase === "failed") return <span className={cx(s.badge, s.badgeBad)}>Failed</span>;
  if (state.phase === "done") {
    const ok = state.verification?.verified;
    return <span className={cx(s.badge, ok ? s.badgeGood : s.badgeBad)}>{ok ? "Fix verified" : "Not verified"}</span>;
  }
  return (
    <span className={cx(s.badge, s.badgeRunning)}>
      <span className={s.pulse} aria-hidden="true" />
      Running
    </span>
  );
}

function Stepper({ state }: { state: RunState }) {
  const done = state.phase === "done";
  const furthest = Math.max(-1, ...state.reached.map((r) => STAGES.indexOf(r)));
  return (
    <ol className={s.stepper} aria-label="Progress">
      {STAGES.map((stage, i) => {
        const reached = state.reached.includes(stage);
        const status = done ? (reached ? "done" : "skipped") : i < furthest ? "done" : i === furthest ? "current" : "pending";
        return (
          <li key={stage} className={cx(s.stage, s[`stage_${status}`])} aria-current={status === "current" ? "step" : undefined}>
            <span className={s.stageMark} aria-hidden="true">
              {status === "done" ? "✓" : status === "skipped" ? "–" : i + 1}
            </span>
            <span className={s.stageLabel}>{STAGE_LABEL[stage]}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Outcome({ scenario, state }: { scenario: ScenarioSummary; state: RunState }) {
  const r = state.report;
  const v = state.verification;
  const confirmed = state.hypotheses.filter((h) => h.status === "confirmed").length;
  const tokens = r ? r.usage.input_tokens + r.usage.output_tokens : undefined;
  const review = state.secondOpinion;

  if (!r) {
    const last = [...state.timeline].reverse().find((item) => item.kind !== "phase");
    return (
      <section className={cx(s.card, s.outcome)} aria-live="polite">
        <div className={s.outcomeHead}>
          <span className={cx(s.outcomeIcon, s.outcomeIconRunning)} aria-hidden="true">
            <span className={s.pulse} />
          </span>
          <div className={s.outcomeText}>
            <h2 className={s.outcomeTitle}>{state.phase === "failed" ? "Investigation failed" : "Investigating…"}</h2>
            <p className={s.muted}>{state.error ?? (last ? `${last.title}${last.detail ? `: ${last.detail}` : ""}` : "Starting the sandbox")}</p>
          </div>
        </div>
        <dl className={s.kpis}>
          <Kpi label="Elapsed" value={formatClock(state.elapsed)} />
          <Kpi label="Hypotheses" value={`${confirmed} of ${state.hypotheses.length} confirmed`} />
          <Kpi label="Checks run" value={String(state.toolCalls)} />
          <Kpi label="Tests before" value={state.baseline ? passing(tallyOf(state.baseline)) : "…"} />
        </dl>
      </section>
    );
  }

  const ok = v?.verified;
  const slug = scenario.id;
  return (
    <section className={cx(s.card, s.outcome)}>
      <div className={s.outcomeHead}>
        <span className={cx(s.outcomeIcon, ok ? s.outcomeIconGood : s.outcomeIconBad)} aria-hidden="true">
          {ok ? "✓" : "!"}
        </span>
        <div className={s.outcomeText}>
          <h2 className={s.outcomeTitle}>{ok ? "Fixed and verified" : "Not verified"}</h2>
          <p className={s.outcomeSummary}>{r.findings.summary}</p>
        </div>
      </div>
      <dl className={s.kpis}>
        <Kpi label="Tests" value={v ? `${passing(v.before)} → ${passing(v.after)}` : "—"} tone={ok ? s.goodText : s.badText} />
        <Kpi label="Root causes" value={`${confirmed} confirmed`} />
        <Kpi label="Second opinion" value={review ? REVIEW[review.verdict][0] : "—"} tone={review ? REVIEW[review.verdict][1] : undefined} />
        <Kpi label="Time" value={formatClock(r.duration_s)} />
        <Kpi label="Tokens" value={tokens ? kTokens(tokens) : "—"} />
        <Kpi label="Model calls" value={String(r.usage.model_calls)} />
      </dl>
      <div className={s.outcomeActions}>
        {state.diff && <CopyButton text={state.diff} label="Copy patch" className={cx(s.btn, s.btnPrimary)} />}
        <CopyButton text={prDescription(scenario, state)} label="Copy PR description" />
        <button type="button" className={s.btn} onClick={() => downloadText(`tracepilot-${slug}-report.md`, markdownReport(scenario, state))}>
          Download report
        </button>
      </div>
    </section>
  );
}

function tallyOf(tests: Record<string, Outcome>): Record<string, number> {
  const t: Record<string, number> = {};
  Object.values(tests).forEach((o) => (t[o] = (t[o] ?? 0) + 1));
  return t;
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className={s.kpi}>
      <dt>{label}</dt>
      <dd className={tone}>{value}</dd>
    </div>
  );
}

function Panel({ title, meta, children, flush }: { title: string; meta?: React.ReactNode; children: React.ReactNode; flush?: boolean }) {
  const id = `panel-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section className={s.card} aria-labelledby={id}>
      <header className={s.cardHead}>
        <h2 id={id} className={s.cardTitle}>
          {title}
        </h2>
        {meta && <span className={s.cardMeta}>{meta}</span>}
      </header>
      <div className={flush ? undefined : s.cardBody}>{children}</div>
    </section>
  );
}

function Findings({ state }: { state: RunState }) {
  const issues = state.report?.findings.issues ?? [];
  if (!issues.length) return null;
  return (
    <Panel title="Root causes" meta={`${issues.length} found`}>
      <div className={s.issues}>
        {issues.map((issue, i) => (
          <IssueCard key={i} issue={issue} hypotheses={state.hypotheses} />
        ))}
      </div>
    </Panel>
  );
}

function IssueCard({ issue, hypotheses }: { issue: Issue; hypotheses: Hypothesis[] }) {
  const evidence = issue.evidence.length ? issue.evidence : hypotheses.filter((h) => issue.hypothesis_ids.includes(h.id)).flatMap((h) => h.evidence);
  return (
    <article className={s.issue}>
      <div className={s.tagRow}>
        <Severity level={issue.severity} />
        <span className={s.tagPlain}>{issue.category}</span>
        {issue.hypothesis_ids.length > 0 && <span className={s.tagPlain}>{issue.hypothesis_ids.join(", ")}</span>}
      </div>
      <h3 className={s.issueTitle}>{issue.title}</h3>
      <p className={s.issueText}>{issue.root_cause}</p>
      {evidence.length > 0 && (
        <details className={s.disclosure}>
          <summary>Evidence ({evidence.length})</summary>
          <ul className={s.evidence}>
            {evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      )}
      <p className={s.issueFix}>
        <span>Fix</span> {issue.fix}
      </p>
    </article>
  );
}

function Hypotheses({ list }: { list: Hypothesis[] }) {
  const status = { open: [s.hypOpen, "Testing"], confirmed: [s.hypConfirmed, "Confirmed"], rejected: [s.hypRejected, "Rejected"] } as const;
  return (
    <Panel title="Hypotheses" meta="Each needs cited evidence to be confirmed">
      {list.length === 0 ? (
        <p className={s.muted}>Suspected causes appear here before the agent tests them.</p>
      ) : (
        <ul className={s.hypotheses}>
          {list.map((h) => (
            <li key={h.id} className={s.hypothesis}>
              <span className={s.hypId}>{h.id}</span>
              <div className={s.hypBody}>
                <p className={s.hypClaim}>{h.claim}</p>
                {h.status === "open" ? (
                  h.next_check && <p className={s.hypMeta}>Next check: {h.next_check}</p>
                ) : (
                  h.reason && <p className={s.hypMeta}>{h.reason}</p>
                )}
              </div>
              <span className={cx(s.tag, status[h.status][0])}>{status[h.status][1]}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DiffView({ diff }: { diff: string }) {
  if (!diff) return null;
  const lines = diff.replace(/\n$/, "").split("\n");
  const added = lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
  const removed = lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
  return (
    <Panel
      title="Patch"
      flush
      meta={
        <>
          <span className={s.goodText}>+{added}</span> <span className={s.badText}>−{removed}</span> · sandbox copy only
        </>
      }
    >
      <pre className={s.diff}>
        {lines.map((line, i) => {
          const cls = line.startsWith("+++") || line.startsWith("---") ? s.diffFile : line.startsWith("@@") ? s.diffHunk : line.startsWith("+") ? s.diffAdd : line.startsWith("-") ? s.diffDel : undefined;
          return (
            <code key={i} className={cx(s.diffLine, cls)}>
              {line || " "}
            </code>
          );
        })}
      </pre>
    </Panel>
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
  const rows: [string, string, string][] = v
    ? [
        ...v.fixed.map((t): [string, string, string] => [t, "Fixed", s.sevPass]),
        ...v.regressions.map((t): [string, string, string] => [t, "Broke", s.sevCritical]),
        ...v.still_failing.map((t): [string, string, string] => [t, "Failing", s.sevMedium]),
      ]
    : [];
  return (
    <Panel title="Verification" meta="Decided by the test suite, not the model">
      {!baseline ? (
        <p className={s.muted}>The harness runs the service&apos;s tests before any change.</p>
      ) : (
        <>
          <div className={s.gauge}>
            <div className={s.gaugeSide}>
              <span className={s.gaugeLabel}>Before</span>
              <span className={s.gaugeValue}>{passing(tallyOf(baseline))}</span>
              <Cells tests={baseline} />
            </div>
            <span className={s.gaugeArrow} aria-hidden="true">
              →
            </span>
            <div className={s.gaugeSide}>
              <span className={s.gaugeLabel}>After patch</span>
              <span className={s.gaugeValue}>{v ? passing(v.after) : "…"}</span>
              {v?.tests ? <Cells tests={v.tests} /> : <div className={s.cells} />}
            </div>
          </div>
          {rows.length > 0 && (
            <ul className={s.testRows}>
              {rows.map(([id, label, cls]) => (
                <li key={id + label}>
                  <span className={cx(s.tag, cls)}>{label}</span>
                  <span className={s.testName}>{shortTest(id)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Panel>
  );
}

function SecondOpinionPanel({ opinion }: { opinion?: SecondOpinion }) {
  if (!opinion) return null;
  const [label, tone] = REVIEW[opinion.verdict] ?? [opinion.verdict, s.muted];
  const assessment = { supported: s.sevPass, weak: s.sevMedium, unsupported: s.sevCritical };
  return (
    <Panel
      title="Second opinion"
      meta={
        <>
          {opinion.model ?? "Independent reviewer"}
          {opinion.tokens ? ` · ${kTokens(opinion.tokens)} tokens` : ""}
        </>
      }
    >
      <div className={s.review}>
        <p className={s.reviewVerdict}>
          <span className={tone}>{label}</span>
          {opinion.confidence && <span className={s.muted}> · {opinion.confidence} confidence · saw none of the investigation</span>}
        </p>
        <p className={s.issueText}>{opinion.verdict === "unavailable" ? opinion.error : opinion.summary}</p>
        {opinion.hypotheses && opinion.hypotheses.length > 0 && (
          <ul className={s.testRows}>
            {opinion.hypotheses.map((h) => (
              <li key={h.id}>
                <span className={cx(s.tag, assessment[h.assessment])}>{h.assessment}</span>
                <span>
                  <span className={s.hypId}>{h.id}</span> {h.note}
                </span>
              </li>
            ))}
          </ul>
        )}
        {opinion.risks && opinion.risks.length > 0 && (
          <ul className={s.evidence}>
            {opinion.risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

function Activity({ items }: { items: TimelineItem[] }) {
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    // Follow the newest entry inside the log only; never scroll the page itself.
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  const tone = { good: s.dotGood, bad: s.dotBad, signal: s.dotAccent, neutral: undefined };
  return (
    <Panel title="Activity" meta={`${items.filter((i) => i.kind === "tool").length} checks`} flush>
      <ol ref={list} className={s.activity}>
        {items.length === 0 && <li className={s.activityEmpty}>Waiting for the sandbox…</li>}
        {items.map((item) =>
          item.kind === "phase" ? (
            <li key={item.seq} className={s.activityPhase}>
              {item.title}
            </li>
          ) : (
            <li key={item.seq} className={s.activityItem}>
              <span className={cx(s.activityDot, item.tone && tone[item.tone])} aria-hidden="true" />
              <span className={s.activityText}>
                <span className={item.kind === "tool" ? s.activityTool : s.activityTitle}>{item.title}</span>
                {item.detail && <span className={s.activityDetail}>{item.detail}</span>}
              </span>
              <span className={s.activityTime}>{formatClock(item.t)}</span>
            </li>
          ),
        )}
      </ol>
    </Panel>
  );
}

function TokenSpend({ state }: { state: RunState }) {
  const usage = state.report?.usage;
  const phases = Object.entries(usage?.by_phase ?? {});
  if (!usage || !phases.length) return null;
  const review = state.secondOpinion?.tokens ?? 0;
  const rows: [string, number][] = [...phases, ...(review ? [["review (open model)", review] as [string, number]] : [])];
  const max = Math.max(...rows.map(([, n]) => n));
  const total = rows.reduce((a, [, n]) => a + n, 0);
  return (
    <Panel title="Token spend" meta={`${kTokens(total)} total`}>
      <ul className={s.spend}>
        {rows.map(([phase, n]) => (
          <li key={phase}>
            <span className={s.spendLabel}>{phase}</span>
            <span className={s.spendBar}>
              <span style={{ width: `${Math.max(4, (n / max) * 100)}%` }} />
            </span>
            <span className={s.spendValue}>{kTokens(n)}</span>
          </li>
        ))}
      </ul>
      {usage.cached_tokens ? <p className={s.footnote}>{kTokens(usage.cached_tokens)} input tokens served from the provider&apos;s cache.</p> : null}
    </Panel>
  );
}

export function RunView({
  scenario,
  state,
  mode,
  onBack,
  controls,
}: {
  scenario: ScenarioSummary;
  state: RunState;
  mode: "live" | "replay";
  onBack: () => void;
  controls?: React.ReactNode;
}) {
  const done = state.phase === "done";
  return (
    <div className={s.run}>
      <div className={s.runBar}>
        <button type="button" className={s.backLink} onClick={onBack}>
          ← All incidents
        </button>
        <div className={s.runBarRight}>
          <span className={s.muted}>{mode === "replay" ? "Recorded run" : "Live run"}</span>
          {controls}
        </div>
      </div>

      <header className={s.runHead}>
        <div className={s.runHeadTop}>
          <div className={s.runHeadText}>
            <span className={s.service}>{scenario.service}</span>
            <h1 className={s.runTitle}>{scenario.title}</h1>
          </div>
          <StatusBadge state={state} />
        </div>
        <details className={s.ticket}>
          <summary>Incident ticket</summary>
          <p>{publicTicket(scenario.incident)}</p>
        </details>
      </header>

      <Stepper state={state} />
      <Outcome scenario={scenario} state={state} />

      <div className={s.runGrid}>
        <div className={s.runMain}>
          {done && <Findings state={state} />}
          <Hypotheses list={state.hypotheses} />
          <VerificationPanel baseline={state.baseline} v={state.verification} />
          <SecondOpinionPanel opinion={state.secondOpinion} />
          <DiffView diff={state.diff} />
        </div>
        <aside className={s.runAside}>
          <Activity items={state.timeline} />
          <TokenSpend state={state} />
        </aside>
      </div>
    </div>
  );
}
