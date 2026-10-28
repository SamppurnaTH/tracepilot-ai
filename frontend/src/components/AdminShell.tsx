"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Logo, Wordmark, cx } from "./bits";
import { Icon, type IconName } from "./icons";
import type { SessionUser } from "./AuthProvider";
import a from "./admin-shell.module.css";

export const ADMIN_ICONS: Record<string, IconName> = {
  Dashboard: "chart", Investigations: "search", "User management": "users", "Roles & permissions": "shieldCheck",
  "Workspace settings": "settings", "System health": "activity", "Audit logs": "logs",
};
export function initials(name: string) { return name.trim().split(/\s+/).slice(0,2).map((part) => part[0]).join("").toUpperCase(); }
export type SearchItem = { label: string; section: string; query?: string; detail?: string };
export function AdminShell({ children, live, sections, active, onSelect, user, searchItems = [], onSignOut, notifications = [] }: {
  children: React.ReactNode; live: boolean | null; sections: string[]; active: string; onSelect: (section: string, query?: string) => void;
  user: SessionUser | null; searchItems?: SearchItem[]; onSignOut: () => void; notifications?: { id: number; text: string }[];
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [dropdown, setDropdown] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); searchRef.current?.focus(); setSearchOpen(true); }
      if (event.key === "Escape") { setSearchOpen(false); setDropdown(""); setMenuOpen(false); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const found = [...sections.map((section) => ({ label: section, section, detail: "Administration" } as SearchItem)), ...searchItems].filter((item) => `${item.label} ${item.detail ?? ""}`.toLowerCase().includes(search.toLowerCase())).slice(0,8);
  const choose = (section: string, query?: string) => { onSelect(section, query); setSearchOpen(false); setSearch(""); setMenuOpen(false); setDropdown(""); };
  return <div className={a.shell}>
    <a href="#admin-content" className={a.skip}>Skip to administration</a>
    <aside className={a.sidebar}>
      <div className={a.brand}><Logo size={44} /><Wordmark /><span className={a.beta}>BETA</span></div>
      <button className={a.portalSelector} onClick={() => setDropdown(dropdown === "workspace" ? "" : "workspace")} aria-expanded={dropdown === "workspace"}><Icon name="shieldCheck" size={15} /> Admin Console <Icon name="chevronDown" size={13} /></button>
      {dropdown === "workspace" && <div className={a.portalMenu}>{user?.workspace_access ? <Link href="/app"><Icon name="external" size={15} /> Open TracePilot Workspace</Link> : <p>Workspace access must be granted by an administrator.</p>}</div>}
      <button className={a.mobileMenu} onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-controls="admin-navigation"><Icon name="list" />Admin menu</button>
      <nav id="admin-navigation" className={cx(a.navigation,menuOpen && a.navigationOpen)} aria-label="Admin Console">
        {sections.length ? sections.map((section) => <button key={section} className={cx(a.navButton,active === section && a.navActive)} aria-current={active === section ? "page" : undefined} onClick={() => choose(section)}><Icon name={ADMIN_ICONS[section]} size={21} /><span>{section}</span></button>) : <a href="#admin-sign-in" className={cx(a.navButton,a.navActive)}><Icon name="lock" size={20} />Administrator sign in</a>}
      </nav>
      <svg className={a.sidebarWave} viewBox="0 0 280 300" aria-hidden="true"><defs><linearGradient id="sidebar-wave" x2="1" y2="1"><stop stopColor="#722cff" stopOpacity=".55"/><stop offset="1" stopColor="#2469ff" stopOpacity=".05"/></linearGradient></defs><path d="M-80 160C60 400 150 30 340 35L360 90C150 50 70 390-80 215Z" fill="url(#sidebar-wave)"/><path d="M-70 140C50 380 150 0 330 10" stroke="#875aff" strokeOpacity=".22" fill="none"/></svg>
      <div className={a.sidebarCard}><div><span className={a.meta}>∞</span><span>Meta Global AI<br/>Developer Hackathon</span></div><p><i className={cx(a.dot,live && a.online)} />{live === null ? "Checking backend…" : live ? "Live backend connected" : "Backend unavailable"}</p><small><Icon name="lock" size={13} /> Restricted administration</small></div>
    </aside>
    <div className={a.workspace}>
      <header className={a.topbar}>
        <div className={a.searchWrap}><Icon name="search" size={18} /><input ref={searchRef} value={search} onFocus={() => setSearchOpen(true)} onChange={(event) => setSearch(event.target.value)} placeholder="Search investigations, team members, or settings…" aria-label="Search administration"/><kbd>Ctrl K</kbd>
          {searchOpen && <><button className={a.searchBackdrop} aria-label="Close search" onClick={() => setSearchOpen(false)} /><div className={a.searchResults}>{user ? found.length ? found.map((item,index) => <button key={`${item.label}-${index}`} onClick={() => choose(item.section,item.query)}><Icon name={ADMIN_ICONS[item.section]} size={17}/><span>{item.label}<small>{item.detail}</small></span></button>) : <p>No results. Try a team member, investigation, or setting.</p> : <p>Sign in to search administration.</p>}</div></>}
        </div>
        <div className={a.topActions}>
          <div className={a.dropdownWrap}><button className={a.helpButton} onClick={() => setDropdown(dropdown === "help" ? "" : "help")}><Icon name="bulb" size={18}/>Help & docs</button>{dropdown === "help" && <div className={a.dropdown}><strong>Administration help</strong><p>Manage access in User management. Workspace settings control the workspace identity.</p>{user && <button onClick={() => choose("System health")}><Icon name="activity" size={16}/>Check system health</button>}<p>Ctrl K opens search. Escape closes menus.</p></div>}</div>
          {user && <div className={a.dropdownWrap}><button className={a.iconButton} aria-label="Recent security events" onClick={() => setDropdown(dropdown === "alerts" ? "" : "alerts")}><Icon name="bell" size={20}/>{notifications.length > 0 && <i className={a.notificationDot}/>}</button>{dropdown === "alerts" && <div className={a.dropdown}><strong>Recent security events</strong>{notifications.length ? notifications.slice(0,4).map((item) => <p key={item.id}>{item.text}</p>) : <p>No security events available for this role.</p>}{sections.includes("Audit logs") && <button onClick={() => choose("Audit logs")}>View audit logs →</button>}</div>}</div>}
          <div className={a.dropdownWrap}><button className={a.profile} onClick={() => setDropdown(dropdown === "profile" ? "" : "profile")} aria-expanded={dropdown === "profile"}><span className={a.avatar}>{user ? initials(user.name) : "TP"}</span><span><strong>{user?.name ?? "Admin Console"}</strong><small>{user ? user.role === "admin" ? "Administrator" : user.role === "operator" ? "Operator" : "Viewer" : "Restricted access"}</small></span><Icon name="chevronDown" size={14}/></button>{dropdown === "profile" && <div className={a.dropdown}><strong>{user?.name ?? "Administration"}</strong>{user && <><p>{user.email}</p>{user.workspace_access && <Link href="/app"><Icon name="external" size={15}/>Open user workspace</Link>}<button onClick={onSignOut}><Icon name="logout" size={16}/>Sign out</button></>}</div>}</div>
        </div>
      </header>
      <main id="admin-content" className={a.content}>
        <nav className={a.breadcrumb} aria-label="Breadcrumb"><Icon name="home" size={17}/><span>›</span><span>TracePilot AI</span><span>›</span><strong>Administration</strong></nav>
        {children}
      </main>
      <footer className={a.footer}><span>TracePilot AI · Admin Console</span><span>Access governed by workspace roles</span></footer>
    </div>
  </div>;
}
