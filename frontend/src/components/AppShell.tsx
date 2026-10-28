"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import s from "./app.module.css";
import { Logo, Wordmark, cx } from "./bits";
import { Icon, type IconName } from "./icons";

const LINKS: [string, string, IconName][] = [
  ["New investigation", "/investigate", "sparkle"],
  ["Example scenarios", "/examples", "list"],
  ["My runs", "/runs", "clock"],
  ["Comparison results", "/results", "chart"],
  ["Documentation", "/docs", "book"],
];

export const REPO_URL = "https://github.com/SamppurnaTH/tracepilot-ai";

export function AppShell({ live, children }: { live?: boolean | null; children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className={s.shell}>
      <aside className={s.sidebar}>
        <Link href="/" className={s.brand} aria-label="TracePilot AI home">
          <Logo />
          <span className={s.brandText}>
            <span className={s.brandName}>
              <Wordmark /> <span className={s.beta}>beta</span>
            </span>
            <span className={s.tagline}>AI Debug. Verify. Fix.</span>
          </span>
        </Link>
        <nav className={s.nav} aria-label="App">
          {LINKS.map(([label, href, icon]) => (
            <Link key={href} href={href} className={cx(s.navLink, path?.startsWith(href) && s.navOn)} aria-current={path?.startsWith(href) ? "page" : undefined}>
              <Icon name={icon} size={18} /> <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className={s.sideCard}>
          <span className={s.sideCardTitle}>Meta Global AI Developer Hackathon</span>
          <span className={s.sideMode}>
            <span className={cx(s.modeDot, live && s.modeDotLive)} aria-hidden="true" />
            {live === undefined || live === null ? "Checking for a backend" : live ? "Live backend connected" : "Replaying real recorded runs"}
          </span>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={s.navLink} style={{ padding: "4px 0" }}>
            <Icon name="github" size={15} /> GitHub
          </a>
        </div>
      </aside>
      <main className={s.content}>{children}</main>
    </div>
  );
}
