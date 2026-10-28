"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import s from "@/components/app.module.css";
import { AppShell } from "@/components/AppShell";
import { cx } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import { startLiveRun, type RecordingIndexEntry } from "@/lib/api";
import { publicTicket } from "@/lib/report";
import { kTokens, minutes, useData } from "@/lib/useData";

const ICONS: Record<string, [IconName, string]> = {
  orders: ["cart", s.iconViolet],
  notes: ["note", s.iconBlue],
  billing: ["receipt", s.iconGreen],
  inventory: ["box", s.iconPink],
  refunds: ["card", s.iconAmber],
  checkout: ["image", s.iconBlue],
  shipping: ["clock", s.iconGreen],
  shipspace: ["layers", s.iconViolet],
};

const FILTERS: [string, (e: RecordingIndexEntry) => boolean][] = [
  ["All", () => true],
  ["Python", (e) => (e.scenario.language ?? "python") === "python"],
  ["Java", (e) => e.scenario.language === "java"],
  ["Bug fix", (e) => e.verified],
  ["No code change", (e) => e.outcome === "no_code_change"],
  ["Screenshot", (e) => Boolean(e.scenario.screenshots?.length)],
];

export default function Examples() {
  const { index, live } = useData();
  const [filter, setFilter] = useState("All");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const test = FILTERS.find(([name]) => name === filter)![1];

  const runLive = async (id: string) => {
    setError(null);
    try {
      const runId = await startLiveRun(id);
      router.push(`/run?live=${runId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>Try an example scenario</h1>
          <p className={s.pageText}>
            Every card is a real, unedited investigation. View it step by step, or{live ? " run it live on the connected backend." : " run it live once a backend is connected."}
          </p>
        </div>
        <Link href="/investigate" className={cx(s.btn, s.btnPrimary)}>
          <Icon name="sparkle" size={16} /> New investigation
        </Link>
      </div>
      <div className={s.filters} role="group" aria-label="Filter scenarios">
        {FILTERS.map(([name]) => (
          <button key={name} type="button" className={cx(s.filter, filter === name && s.filterOn)} aria-pressed={filter === name} onClick={() => setFilter(name)}>
            {name}
          </button>
        ))}
      </div>
      {error && <p className={s.errorText}>{error}</p>}
      <div className={s.scenarioGrid}>
        {index === null && <p className={s.muted}>Loading scenarios…</p>}
        {index?.filter(test).map((e) => {
          const [icon, tone] = ICONS[e.scenario.id] ?? ["file", s.iconViolet];
          const [service, ...rest] = e.scenario.title.split(":");
          const result = e.outcome === "no_code_change" ? ["No code change needed", s.sevPass] : e.verified ? ["Fix verified", s.sevPass] : ["Not verified", s.sevCritical];
          const lang = e.scenario.language === "java" ? "Java" : "Python";
          return (
            <article key={e.scenario.id} className={s.scenarioCard}>
              <span className={cx(s.chip, tone)}>
                <Icon name={icon} size={20} />
              </span>
              <div className={s.scenarioBody}>
                <div className={s.scenarioTop}>
                  <h2 className={s.scenarioTitle}>{service}</h2>
                  <span className={cx(s.tag, s.sevAccent)}>{lang}</span>
                </div>
                <p className={s.scenarioText}>{rest.join(":").trim() || publicTicket(e.scenario.incident).split("\n")[0]}</p>
                <div className={s.scenarioMeta}>
                  <span className={cx(s.tag, result[1])}>{result[0]}</span>
                  {e.scenario.screenshots?.length ? <span className={cx(s.tag, s.iconBlue)}>Screenshot</span> : null}
                  <span>{minutes(e.duration_s)}</span>
                  {e.tokens ? <span>{kTokens(e.tokens)} tokens</span> : null}
                </div>
                <div className={s.scenarioActions}>
                  <button
                    type="button"
                    className={cx(s.btn, s.btnSm, s.btnPrimary)}
                    disabled={!live || !e.scenario.live}
                    title={!e.scenario.live ? "A benchmark run on an external project: replay only" : live ? undefined : "Needs a TracePilot backend"}
                    onClick={() => runLive(e.scenario.id)}
                  >
                    <Icon name="bolt" size={13} /> Run live
                  </button>
                  <Link href={`/run?id=${e.scenario.id}&replay=1`} className={cx(s.btn, s.btnSm, !live && s.btnPrimary)}>
                    <Icon name="play" size={13} /> Watch run
                  </Link>
                  <Link href={`/run?id=${e.scenario.id}`} className={cx(s.btn, s.btnSm)}>
                    View details
                  </Link>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {live === false && (
        <p className={s.footnote}>
          This hosted demo replays recorded runs. To run investigations live, start the backend (see the{" "}
          <Link href="/docs#getting-started">getting started guide</Link>) and open this page from it.
        </p>
      )}
    </AppShell>
  );
}
