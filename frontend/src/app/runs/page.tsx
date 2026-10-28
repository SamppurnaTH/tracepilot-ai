"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import s from "@/components/app.module.css";
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
  const { index, live } = useData();
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (live) listSavedRuns().then(setSaved).catch(() => setSaved([]));
  }, [live]);

  const rows: Row[] = [
    ...saved.map((r) => {
      const [label, tone] = status(r.verified, r.outcome, r.status);
      const known = (index ?? []).find((e) => e.scenario.id === r.scenario)?.scenario.title;
      return { key: r.name, title: r.title || known || r.scenario, status: label, tone, duration: r.duration_s, tokens: r.tokens, date: r.started_at, href: `/run?saved=${encodeURIComponent(r.name)}`, source: "This backend" };
    }),
    ...(index ?? []).map((e) => {
      const [label, tone] = status(e.verified, e.outcome);
      return { key: e.scenario.id, title: e.scenario.title, status: label, tone, duration: e.duration_s, tokens: e.tokens, date: e.started_at, href: `/run?id=${e.scenario.id}`, source: "Recorded" };
    }),
  ];
  const shown = rows.filter((r) => r.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>My investigations</h1>
          <p className={s.pageText}>
            {live ? "Runs saved by the connected backend, plus the published recordings." : "The published recordings. With a backend connected, your own runs appear here too."}
          </p>
        </div>
        <input className={s.search} type="search" placeholder="Search runs…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search runs" />
      </div>
      <div className={s.tableWrap}>
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
            {shown.map((r) => (
              <tr key={`${r.source}-${r.key}`}>
                <th scope="row">{r.title}</th>
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
      </div>
    </AppShell>
  );
}
