"use client";

import { useState } from "react";
import Link from "@/components/AreaLink";
import { EmptyState, SkeletonCards } from "@/components/ScreenState";
import { downloadText } from "@/lib/report";
import s from "@/components/app.module.css";
import { AppShell } from "@/components/AppShell";
import { cx } from "@/components/bits";
import { Icon } from "@/components/icons";
import { kTokens, minutes, useData } from "@/lib/useData";
import evidence from "../../../public/evidence.json";

const CASE_LABEL: Record<string, [string, string]> = {
  orders: ["Orders: 500 + data exposure", "Python"],
  notes: ["Notes: search errors (SQL injection)", "Python"],
  billing: ["Billing: disputed cent + pagination", "Python"],
  inventory: ["Inventory: green CI, phantom stock", "Python"],
  refunds: ["Refunds: expired API key (no code bug)", "Python"],
  checkout: ["Checkout: screenshot-only evidence", "Python"],
  shipping: ["Shipping: Friday orders promised Saturday", "Python"],
  shipspace: ["ShipSpace: Spring Boot edit window", "Java"],
};

function Bars({ title, sub, a, b, fmt }: { title: string; sub: string; a: number; b: number; fmt: (n: number) => string }) {
  const max = Math.max(a, b) || 1;
  const cols: [number, string, string][] = [
    [a, "TracePilot", s.barPrimary],
    [b, "Plain agent", s.barMuted],
  ];
  return (
    <div className={s.chart}>
      <p className={s.chartTitle}>{title}</p>
      <p className={s.chartSub}>{sub}</p>
      <div className={s.bars} role="img" aria-label={`${title}: TracePilot ${fmt(a)}, plain agent ${fmt(b)}`}>
        {cols.map(([v, label, cls]) => (
          <div key={label} className={s.barCol}>
            <span className={s.barValue}>{fmt(v)}</span>
            <span className={s.barTrack}>
              <span className={cx(s.bar, cls)} style={{ height: `${(v / max) * 100}%` }} />
            </span>
            <span className={s.barLabel}>{label}</span>
          </div>
        ))}
      </div>
      <section className={s.panel} aria-label="Evidence and uncertainty">
        <h2 className={s.panelTitle}>Evidence, with limits</h2>
        <p className={s.pageText}>13 runs per system across 7 authored incidents. These results do not establish a statistically significant success advantage. Both model roles use Meta models in separate contexts; shared blind spots remain possible.</p>
        <div className={s.tableWrap}><table className={s.table}><thead><tr><th>Measurement</th><th>Observed</th><th>Descriptive 95% interval</th></tr></thead><tbody>{([
          ["TracePilot correct outcomes", evidence.systems.tracepilot],
          ["Plain agent correct outcomes", evidence.systems.plain],
          ["Unsafe patches approved", evidence.reviewer.unsafe_approval],
          ["Correct patches not approved", evidence.reviewer.correct_patch_nonapproval],
        ] as const).map(([label, rate]) => <tr key={label}><td>{label}</td><td>{rate.count}/{rate.total}</td><td>{rate.wilson_95?.map((n) => `${(n * 100).toFixed(1)}%`).join("–")}</td></tr>)}</tbody></table></div>
        <p className={s.footnote}>Wilson intervals describe this small repeated-case set. “Concerns” counts as nonapproval, not rejection. These original fixtures were project-authored. The separate completed research extension adds external-source tests, brief ablations and a Meta-version comparison; its null and negative results are reported separately.</p>
        <div className={s.actions}><Link href="/evidence" className={s.btn}>Judge evidence & limitations</Link><a href="/evidence.json" className={s.btn} download>Download statistics & source hashes</a></div>
      </section>
    </div>
  );
}

export default function Results() {
  const { comparison, evaluation, live, comparisonLoading } = useData();
  const [language, setLanguage] = useState("All");
  const tp = comparison?.systems.tracepilot;
  const plain = comparison?.systems.plain;
  const gamed = evaluation?.reviewer.gamed;
  const reference = evaluation?.reviewer.reference;
  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>TracePilot vs a plain AI agent</h1>
          <p className={s.pageText}>
            Original service pilot: same model (muse-spark-1.3), sandbox and basic tools. Code cases use hidden acceptance tests; Refunds scores an external-cause diagnosis with no application patch.
          </p>
        </div>
        <button className={s.btn} disabled={!comparison} onClick={() => downloadText("tracepilot-benchmark.json", JSON.stringify(comparison, null, 2))}><Icon name="download" size={15} /> Export benchmark</button>
      </div>
      {!tp || !plain ? (
        comparisonLoading ? <SkeletonCards /> : <EmptyState icon="chart" title="Benchmark unavailable" text="Benchmark data could not be loaded. Refresh the page to try again." />
      ) : (
        <>
          <section className={s.panel} aria-labelledby="bench-title">
            <h2 id="bench-title" className={s.panelTitle}>
              Benchmark results ({tp.runs} runs each)
            </h2>
            <div className={s.charts}>
              <Bars title="Correct outcomes" sub="Includes no-code-change diagnoses" a={tp.correct / tp.runs} b={plain.correct / plain.runs} fmt={(n) => `${(n * 100).toFixed(n === 1 ? 0 : 1)}%`} />
              <Bars title="Average tokens" sub="Lower is better" a={tp.avg_tokens} b={plain.avg_tokens} fmt={kTokens} />
              <Bars title="Average time" sub="Lower is better" a={tp.avg_duration_s} b={plain.avg_duration_s} fmt={minutes} />
              <Bars title="Reproducing test files" sub="Proof that ships with the fix" a={tp.new_tests} b={plain.new_tests} fmt={String} />
            </div>
          </section>

          <section className={s.panel} aria-labelledby="detail-title">
            <h2 id="detail-title" className={s.panelTitle}>
              Detailed results
            </h2>
            <div className={s.filters} role="group" aria-label="Benchmark language">{["All", "Python", "Java"].map((value) => <button key={value} className={cx(s.filter, language === value && s.filterOn)} aria-pressed={language === value} onClick={() => setLanguage(value)}>{value}</button>)}</div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Incident</th>
                    <th scope="col">Language</th>
                    <th scope="col">TracePilot: correct</th>
                    <th scope="col">Time</th>
                    <th scope="col">Tokens</th>
                    <th scope="col">Plain agent: correct</th>
                    <th scope="col">Time</th>
                    <th scope="col">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(comparison!.cases).filter(([id]) => language === "All" || (CASE_LABEL[id]?.[1] ?? "Python") === language).map(([id, c]) => {
                    const [label, lang] = CASE_LABEL[id] ?? [id, "Python"];
                    const cell = (x?: { runs: number; correct: number; avg_tokens: number; avg_duration_s: number }) =>
                      x
                        ? [
                            <span key="ok" className={cx(s.cellOk, x.correct === x.runs ? s.good : s.bad)}>
                              <Icon name={x.correct === x.runs ? "checkCircle" : "minusCircle"} size={16} /> {x.correct}/{x.runs}
                            </span>,
                            minutes(x.avg_duration_s),
                            kTokens(x.avg_tokens),
                          ]
                        : ["—", "—", "—"];
                    return (
                      <tr key={id}>
                        <th scope="row"><Link className={s.tableLink} href={`/app/run?id=${id}`}>{label}</Link></th>
                        <td>{lang}</td>
                        {cell(c.tracepilot).map((v, i) => (
                          <td key={`t${i}`}>{v}</td>
                        ))}
                        {cell(c.plain).map((v, i) => (
                          <td key={`p${i}`}>{v}</td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className={s.footnote}>
              Correct outcome means passing the case acceptance criteria; Refunds scores diagnosis without an application patch, not verified provider recovery. Tokens include the reviewer for TracePilot; mixed-provider totals are not measured dollar cost. The plain agent&apos;s one miss changed code during an incident caused by an expired API key; raw runs are in{" "}
              <code className={s.inlineCode}>eval/comparison.json</code>.
            </p>
          </section>

          {gamed && reference && (
            <section className={s.panel} aria-labelledby="review-title">
              <h2 id="review-title" className={s.panelTitle}>
                Second-opinion benchmark
              </h2>
              <p className={s.pageText}>Muse Spark Open reviews patches that pass every visible test. Only the reference fixes actually fix the cause.</p>
              <div className={s.statRow}>
                <div className={s.stat}>
                  <span className={s.statValue}>
                    {gamed.correct}/{gamed.cases}
                  </span>
                  <span className={s.statLabel}>test-gaming patches rejected</span>
                </div>
                <div className={s.stat}>
                  <span className={s.statValue}>
                    {reference.correct}/{reference.cases}
                  </span>
                  <span className={s.statLabel}>correct patches approved</span>
                </div>
                <div className={s.stat}>
                  <span className={s.statValue}>~{kTokens(gamed.avg_tokens)}</span>
                  <span className={s.statLabel}>tokens per review</span>
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </AppShell>
  );
}
