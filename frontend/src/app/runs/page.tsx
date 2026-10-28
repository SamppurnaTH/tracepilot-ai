"use client";

import { useAuth } from "@/components/AuthProvider";
import Link from "next/link";
import { useEffect, useState } from "react";
import s from "@/components/app.module.css";
import { EmptyState, SkeletonCards } from "@/components/ScreenState";
import { Icon } from "@/components/icons";
import { AppShell } from "@/components/AppShell";
import { cx } from "@/components/bits";
import { listSavedRuns, type SavedRun } from "@/lib/api";
import { fmtDate, kTokens, minutes, useData } from "@/lib/useData";

interface Row {
  key: string;
  title: string;
  status: string;
  tone: string;
  duration?: number | null;
  tokens?: number;
  date?: number;
  href: string;
  source: string;
}

function status(verified?: boolean | null, outcome?: string | null, raw?: string): [string, string] {
  if (outcome === "no_code_change") return ["No code change", s.sevPass];
  if (raw === "cancelled") return ["Stopped", s.sevLow];
  if (raw === "failed") return ["Failed", s.sevCritical];
  if (raw === "running") return ["Running", s.sevAccent];
  return verified ? ["Verified", s.sevPass] : ["Not verified", s.sevCritical];
}

export default function Runs() {
  const { user } = useAuth();
  const { index, live } = useData();
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const [page, setPage] = useState(1);
  const [savedError, setSavedError] = useState(false);
  useEffect(() => {
    if (live) listSavedRuns().then(setSaved).catch(() => setSavedError(true));
  }, [live]);

  const rows: Row[] = [
    ...saved.map((r) => {
      const [label, tone] = status(r.verified, r.outcome, r.status);
      const known = (index ?? []).find((e) => e.scenario.id === r.scenario)?.scenario.title;
      return { key: r.name, title: r.title || known || r.scenario, status: label, tone, duration: r.duration_s, tokens: r.tokens, date: r.started_at, href: `/app/run?saved=${encodeURIComponent(r.name)}`, source: "This backend" };
    }),
    ...(index ?? []).map((e) => {
      const [label, tone] = status(e.verified, e.outcome);
      return { key: e.scenario.id, title: e.scenario.title, status: label, tone, duration: e.duration_s, tokens: e.tokens, date: e.started_at, href: `/app/run?id=${e.scenario.id}`, source: "Recorded" };
    }),
  ];
  const shown = rows.filter((r) => r.title.toLowerCase().includes(query.toLowerCase()) && (filter === "All" || r.status === filter || r.source === filter));
  const totalPages = Math.max(1, Math.ceil(shown.length / 6));
  const currentPage = Math.min(page, totalPages);
  const paged = shown.slice((currentPage - 1) * 6, currentPage * 6);

  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>My investigations</h1>
          <p className={s.pageText}>
            {live ? "Runs saved by the connected backend, plus the published recordings." : "The published recordings. With a backend connected, your own runs appear here too."}
          </p>
        </div>
        {user?.role !== "viewer" && <Link href="/app/investigate" className={cx(s.btn, s.btnPrimary)}><Icon name="sparkle" size={16} /> New investigation</Link>}
      </div>
      <div className={s.statRow}>{[["Total investigations", rows.length], ["Verified fixes", rows.filter((r) => r.status === "Verified").length], ["No code change", rows.filter((r) => r.status === "No code change").length], ["Saved on backend", saved.length]].map(([label, value]) => <div key={label} className={s.stat}><span className={s.statLabel}>{label}</span><span className={s.statValue}>{index === null ? "—" : value}</span></div>)}</div>
      <div className={s.collectionToolbar}><div className={s.filters} role="group" aria-label="Filter investigations">{["All", "Verified", "No code change", "Recorded", "This backend"].map((value) => <button key={value} className={cx(s.filter, filter === value && s.filterOn)} aria-pressed={filter === value} onClick={() => { setFilter(value); setPage(1); }}>{value === "This backend" ? "My saved runs" : value}</button>)}</div><input className={s.search} type="search" placeholder="Search investigations…" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }} aria-label="Search runs" /></div>
      {savedError && <p className={s.errorText} role="alert">Saved backend runs could not be loaded. Recorded runs are still available.</p>}
      {index === null && <SkeletonCards count={2} />}
      {index !== null && shown.length === 0 && <EmptyState icon="clock" title="No investigations found" text="Try a different search or filter, or start a new investigation." href="/app/examples" action="Explore scenarios" />}
      {shown.length > 0 && <div className={s.tableWrap}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Investigation</th>
              <th scope="col">Status</th>
              <th scope="col">Time</th>
              <th scope="col">Tokens</th>
              <th scope="col">Date</th>
              <th scope="col">Source</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {index === null && (
              <tr>
                <td colSpan={7} className={s.muted}>
                  Loading…
                </td>
              </tr>
            )}
            {paged.map((r) => (
              <tr key={`${r.source}-${r.key}`}>
                <th scope="row" className={s.runName}>{r.title}</th>
                <td>
                  <span className={cx(s.tag, r.tone)}>{r.status}</span>
                </td>
                <td>{r.duration ? minutes(r.duration) : "—"}</td>
                <td>{r.tokens ? kTokens(r.tokens) : "—"}</td>
                <td>{fmtDate(r.date)}</td>
                <td className={s.muted}>{r.source}</td>
                <td>
                  <Link href={r.href} className={cx(s.btn, s.btnSm)}>
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>}
      {shown.length > 0 && <div className={s.pagination}><span>Showing {(currentPage - 1) * 6 + 1}–{Math.min(currentPage * 6, shown.length)} of {shown.length} investigations</span><div className={s.actions}><button className={cx(s.btn,s.btnSm)} disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Previous</button><span>Page {currentPage} of {totalPages}</span><button className={cx(s.btn,s.btnSm)} disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>}
    </AppShell>
  );
}
