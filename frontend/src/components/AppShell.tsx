"use client";

import Link from "next/link";
import { Footer } from "./Footer";
import { useState } from "react";
import { usePathname } from "next/navigation";
import s from "./app.module.css";
import { Logo, Wordmark, cx } from "./bits";
import { Icon, type IconName } from "./icons";

const LINKS: [string, string, IconName][] = [
  ["Product overview", "/product", "layers"],
  ["New investigation", "/investigate", "sparkle"],
  ["Example scenarios", "/examples", "list"],
  ["My runs", "/runs", "clock"],
  ["Comparison results", "/results", "chart"],
  ["Documentation", "/docs", "book"],
];

export const REPO_URL = "https://github.com/SamppurnaTH/tracepilot-ai";

export function AppShell({ live, children }: { live?: boolean | null; children: React.ReactNode }) {
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const currentPage = LINKS.find(([, href]) => path === href)?.[0] ?? (path === "/run" ? "Investigation" : path === "/admin" ? "Administration" : "Workspace");
  return (
    <div className={s.shell}>
      <a href="#main-content" className={s.skipLink}>Skip to content</a>
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
        <button className={s.mobileMenu} aria-expanded={menuOpen} aria-controls="app-navigation" onClick={() => setMenuOpen(!menuOpen)}><Icon name="list" size={18} />{menuOpen ? "Close menu" : "Menu"}</button>
        <nav id="app-navigation" className={cx(s.nav, menuOpen && s.navExpanded)} aria-label="App">
          {LINKS.map(([label, href, icon]) => (
            <Link key={href} href={href} onClick={() => setMenuOpen(false)} className={cx(s.navLink, path?.startsWith(href) && s.navOn)} aria-current={path?.startsWith(href) ? "page" : undefined}>
              <Icon name={icon} size={18} /> <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className={s.sideCard}>
          <span className={s.hackathonBrand}><span className={s.metaMark}>∞</span><span className={s.sideCardTitle}>Meta Global AI<br />Developer Hackathon</span></span>
          <span className={s.sideMode}>
            <span className={cx(s.modeDot, live && s.modeDotLive)} aria-hidden="true" />
            {live === undefined ? "Verification-first debugging" : live === null ? "Checking for a backend" : live ? "Live backend connected" : "Replaying real recorded runs"}
          </span>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={s.navLink} style={{ padding: "4px 0" }}>
            <Icon name="github" size={15} /> GitHub
          </a>
        </div>
      </aside>
      <div className={s.workspace}><div className={s.workspaceBar}><nav aria-label="Breadcrumb"><Link href="/">TracePilot AI</Link><span aria-hidden="true">/</span><span>{currentPage}</span></nav><Link href="/docs" className={s.helpLink}><Icon name="book" size={14} /> Help & docs</Link></div><main id="main-content" className={s.content}>{children}</main><div className={s.footerWrap}><Footer /></div></div>
    </div>
  );
}
