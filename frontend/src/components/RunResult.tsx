"use client";

import { useState } from "react";
import s from "./app.module.css";
import { CopyButton, cx } from "./bits";
import { DiffBlock, Evidence, ReproTests, Review, RootCauses, Terminal, TestResults, isTestPath, splitDiff } from "./Console";
import { Icon, type IconName } from "./icons";
import { downloadText, markdownReport, prDescription } from "@/lib/report";
import { estimateCost, formatTally, type RunState, type ScenarioSummary } from "@/lib/run";
import { minutes } from "@/lib/useData";

const VERDICT: Record<string, string> = { approve: "Approved", concerns: "Concerns raised", reject: "Rejected", unavailable: "Unavailable" };

/** A finished investigation: the outcome first, then each piece of evidence in its own tab. */
export function RunResult({ scenario, state, startedAt }: { scenario: ScenarioSummary; state: RunState; startedAt?: number }) {
  const r = state.report!;
  const noCode = r.outcome === "no_code_change";
  const v = state.verification;
  const ok = noCode || Boolean(v?.verified);
  const files = splitDiff(state.diff || "");
  const code = files.filter((f) => !isTestPath(f.path));
  const tests = files.filter((f) => f.isNew && isTestPath(f.path));
  const tokens = r.usage.input_tokens + r.usage.output_tokens;
  const issue = r.findings.issues[0];
  const tabs = noCode
    ? ["Summary", "Root cause", "Evidence", "Recommendation", "Activity log"]
    : ["Summary", "Root cause", "Patch", "Tests", "AI review", "Evidence", "Activity log"];
  const [tab, setTab] = useState("Summary");
  const [exporting, setExporting] = useState(false);

  const facts: [IconName, string, string, string][] = [
    ["search", "Root cause", issue?.root_cause ?? state.hypotheses.find((h) => h.status === "confirmed")?.claim ?? "—", s.iconViolet],
    noCode
      ? ["minusCircle", "Code changes", "None, on purpose: the fix belongs outside the code", s.iconGreen]
      : ["file", "Files changed", code.length ? `${code.length} file${code.length > 1 ? "s" : ""} modified${tests.length ? `, ${tests.length} test file${tests.length > 1 ? "s" : ""} added` : ""}` : "None", s.iconBlue],
    ["flask", "Tests", noCode ? "No test needed" : v ? `${formatTally(v.before)} → ${formatTally(v.after)}` : "—", s.iconPink],
    ["eye", "Second opinion", state.secondOpinion ? `${VERDICT[state.secondOpinion.verdict]} (${state.secondOpinion.model})` : noCode ? "Not needed" : "—", s.iconGreen],
    ["clock", "Execution time", minutes(r.duration_s), s.iconAmber],
    ["layers", "Tokens used", `${tokens.toLocaleString()} · est. ${estimateCost(tokens)}`, s.iconViolet],
  ];

  const handoff = (
    <div className={s.handoff}>
      <p className={s.handoffLabel}>READY FOR HAND-OFF</p><div className={s.actions}>
      <button type="button" className={cx(s.btn, s.btnPrimary)} onClick={() => downloadText(`tracepilot-${scenario.id}-report.md`, markdownReport(scenario, state))}>
        <Icon name="download" size={16} /> Download report
      </button>
      {!noCode && <CopyButton text={prDescription(scenario, state)} label="Copy PR description" className={s.btn} />}
      {state.diff && <CopyButton text={state.diff} label="Copy patch" className={s.btn} />}
      <button className={s.btn} disabled={exporting} onClick={() => { setExporting(true); window.print(); setExporting(false); }}><Icon name="file" size={14} /> Print / Save PDF</button>
      </div><p className={s.hint}>Report exports as Markdown. Use the print dialog to save a PDF.</p>
    </div>
  );

  return (
    <section className={cx(s.panel, s.resultPanel)} aria-labelledby="result-title">
      <div className={s.runHead}>
        <div className={s.runTitle}>
          <span className={cx(s.chip, ok ? s.iconGreen : s.iconMuted)}>
            <Icon name={ok ? "checkCircle" : "minusCircle"} size={22} />
          </span>
          <h2 id="result-title" className={s.panelTitle}>
            Investigation complete
          </h2>
          <span className={cx(s.tag, ok ? s.sevPass : s.sevCritical)}>{noCode ? "No code change needed" : ok ? "Verified fix" : "Not verified"}</span>
        </div>
      </div>
      <div className={s.resultMetrics}><span><Icon name="clock" size={14} /> {minutes(r.duration_s)}</span><span><Icon name="layers" size={14} /> {tokens.toLocaleString()} tokens</span><span><Icon name="file" size={14} /> {code.length} code files changed</span><span><Icon name="shieldCheck" size={14} /> {noCode ? "External root cause" : state.secondOpinion ? VERDICT[state.secondOpinion.verdict] : "Review unavailable"}</span></div>
      <div className={s.tabs} role="tablist" aria-label="Result views">
        {tabs.map((t) => (
          <button key={t} type="button" role="tab" id={`result-tab-${t.replaceAll(" ", "-")}`} aria-controls="result-panel" aria-selected={tab === t} className={cx(s.tab, tab === t && s.tabOn)} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="result-panel" aria-labelledby={`result-tab-${tab.replaceAll(" ", "-")}`}>
        {tab === "Summary" && (
          <div className={s.resultGrid}>
            <div className={s.field} style={{ gap: 12 }}>
              <div className={cx(s.verdict, noCode ? s.verdictInfo : ok ? s.verdictGood : s.verdictBad)}>
                <span className={s.verdictIcon} style={{ background: noCode ? "#2570ff" : ok ? "var(--good)" : "var(--bad)" }}>
                  <Icon name={noCode ? "bulb" : ok ? "check" : "minusCircle"} size={22} />
                </span>
                <div>
                  <p className={s.verdictTitle}>{noCode ? "No code change needed" : ok ? "Fix verified" : "Not verified"}</p>
                  <p className={s.factValue}>
                    {noCode ? "The cause is real, but its fix belongs outside this code." : ok ? "The issue is fixed and proven by tests." : "The tests did not confirm the fix."}
                  </p>
                </div>
              </div>
              <ul className={s.facts}>
                {facts.map(([icon, label, value, tone]) => (
                  <li key={label} className={s.fact}>
                    <span className={cx(s.factIcon, tone)}>
                      <Icon name={icon} size={16} />
                    </span>
                    <span>
                      <span className={s.factLabel}>{label}</span>
                      <br />
                      <span className={s.factValue}>{value}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className={s.field} style={{ gap: 14 }}>
              <p className={s.factValue}>{r.findings.summary}</p>
              {noCode ? (
                <>
                  <span className={s.label}>Evidence</span>
                  <pre className={s.logLines}>{state.brief ?? "—"}</pre>
                  <span className={s.label}>Recommended action</span>
                  <ol className={s.steps}>
                    {r.findings.issues.map((i, n) => (
                      <li key={n}>{i.fix}</li>
                    ))}
                  </ol>
                </>
              ) : (
                <>
                  <div className={s.pageHead}><span className={s.label}>Patch preview</span><button className={cx(s.btn,s.btnSm)} onClick={() => setTab("Patch")}>View full patch <Icon name="arrowRight" size={13} /></button></div>
                  {code.length ? (
                    <div className={s.light}>
                      <DiffBlock files={code.slice(0, 1)} />
                    </div>
                  ) : (
                    <p className={s.muted}>No code was changed.</p>
                  )}
                </>
              )}
              {handoff}
            </div>
          </div>
        )}
        <div className={s.light}>
          {tab === "Root cause" && <RootCauses state={state} />}
          {tab === "Patch" && (code.length ? <DiffBlock files={code} /> : <p className={s.muted}>No code was changed.</p>)}
          {tab === "Tests" && (
            <>
              <ReproTests state={state} files={files} />
              <TestResults state={state} />
            </>
          )}
          {tab === "AI review" && <Review state={state} />}
          {tab === "Evidence" && <Evidence scenario={scenario} state={state} />}
          {tab === "Recommendation" && (
            <>
              <ol className={s.steps}>
                {r.findings.issues.map((i, n) => (
                  <li key={n}>
                    <strong>{i.title}.</strong> {i.fix}
                  </li>
                ))}
              </ol>
              {handoff}
            </>
          )}
          {tab === "Activity log" && <Terminal items={state.timeline} startedAt={startedAt} />}
        </div>
      </div>
    </section>
  );
}
