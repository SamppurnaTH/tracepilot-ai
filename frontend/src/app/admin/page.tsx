"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { cx } from "@/components/bits";
import { Icon } from "@/components/icons";
import { API_URL, type RunSummary } from "@/lib/api";
import { fmtDate, useData } from "@/lib/useData";
import s from "@/components/app.module.css";
import a from "./admin.module.css";

type Role = "admin" | "operator" | "viewer";
type User = { id: string; name: string; email: string; role: Role; active: boolean };
type Overview = { user: User; active: number; max_concurrent: number; daily_limit: number; uploads_need_key: boolean; require_docker: boolean; runs: RunSummary[] };
const ROLES: Role[] = ["admin", "operator", "viewer"];

export default function Admin() {
  const { index, live } = useData();
  // Keep bearer credentials in memory only. Reloading requires a fresh sign-in.
  const [token, setToken] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tab, setTab] = useState("Overview");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [updated, setUpdated] = useState("");
  const request = useCallback(async <T,>(path: string, method = "GET", body?: unknown, bearer = token): Promise<T> => {
    if (!API_URL) throw new Error("Configure NEXT_PUBLIC_API_URL and rebuild the frontend to connect an admin backend.");
    const response = await fetch(`${API_URL}/api/admin${path}`, { method, headers: { "Content-Type": "application/json", ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(10000) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && bearer) { setToken(""); setOverview(null); setUsers([]); }
      throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (HTTP ${response.status})`);
    }
    return data;
  }, [token]);

  const refresh = useCallback(async () => {
    const next = await request<Overview>("/overview");
    setOverview(next);
    if (next.user.role === "admin") setUsers(await request<User[]>("/users"));
    else setUsers([]);
    setUpdated(new Date().toLocaleTimeString());
  }, [request]);

  useEffect(() => {
    if (!token) return;
    refresh().catch((err) => setError(err.message));
    const interval = setInterval(() => refresh().catch((err) => setError(err.message)), 30000);
    return () => clearInterval(interval);
  }, [token, refresh]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  const visibleUsers = users.filter((user) => `${user.name} ${user.email}`.toLowerCase().includes(query.toLowerCase()));

  return <AppShell live={live}>
    <div className={s.pageHead}><div><p className={a.eyebrow}>WORKSPACE ADMINISTRATION</p><h1 className={s.pageTitle}>Admin plane</h1><p className={s.pageText}>Monitor investigations, manage your team, and control workspace access.</p></div>
      {overview && <div className={s.actions}><span className={cx(s.tag, s.sevAccent)}>{overview.user.name} · {overview.user.role}</span><button className={s.btn} disabled={busy} onClick={() => action(refresh)}>Refresh</button><button className={s.btn} disabled={busy} onClick={() => action(async () => { await request("/logout", "POST"); setToken(""); setOverview(null); setUsers([]); })}>Sign out</button></div>}
    </div>
    {error && <p className={s.errorText} role="alert">{error}</p>}
    {notice && <p className={s.notice} role="status">{notice}</p>}
    {!overview ? <div className={a.loginGrid}>
      <section className={cx(s.panel, a.login)}><span className={cx(s.chip, s.iconViolet)}><Icon name="shieldCheck" size={23} /></span><h2 className={s.panelTitle}>Sign in to administration</h2><p className={s.pageText}>Use an account created by your workspace administrator.</p>
        <form className={a.form} onSubmit={(event) => { event.preventDefault(); action(async () => { const data = await request<{ token: string }>("/login", "POST", { email, password }); setToken(data.token); setPassword(""); setTab("Overview"); }); }}>
          <label className={s.field}><span className={s.label}>Email address</span><input className={s.input} type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>
          <label className={s.field}><span className={s.label}>Password</span><input className={s.input} type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <button className={cx(s.btn, s.btnPrimary, s.btnLg)} disabled={busy || !API_URL}>{busy ? "Signing in…" : "Sign in"}<Icon name="arrowRight" size={16} /></button>
        </form>
        {!API_URL && <p className={s.hint}>This frontend has no admin API configured. <Link href="/docs#administration">Connect your backend</Link> to sign in.</p>}
      </section>
      <section className={cx(s.panel, a.access)}><h2 className={s.panelTitle}>The right access for every role</h2>{[["Administrator", "Create accounts, assign roles, suspend access, and manage operations."], ["Operator", "Monitor workspace activity and stop running investigations."], ["Viewer", "Read operational status and investigation activity."]].map(([title, text]) => <div className={a.role} key={title}><span className={cx(s.chip, s.iconBlue)}><Icon name="shieldCheck" size={18} /></span><div><h3>{title}</h3><p>{text}</p></div></div>)}<p className={s.footnote}>Access is checked by the server. Admin sessions expire after eight hours. These roles govern the admin plane; public demo endpoints retain their existing access policy.</p></section>
    </div> : <>
      <div className={s.tabs} role="tablist" aria-label="Administration views">{["Overview", "Investigations", ...(overview.user.role === "admin" ? ["Users & roles"] : [])].map((label) => <button role="tab" id={`admin-tab-${label.replaceAll(" ", "-")}`} aria-controls="admin-panel" aria-selected={tab === label} className={cx(s.tab, tab === label && s.tabOn)} key={label} onClick={() => setTab(label)}>{label}</button>)}</div>
      <div role="tabpanel" id="admin-panel" aria-labelledby={`admin-tab-${tab.replaceAll(" ", "-")}`} className={a.tabPanel}>
      {tab === "Overview" && <>
        <div className={s.statRow}>{[["Active investigations", `${overview.active} / ${overview.max_concurrent}`], ["Session investigations", overview.runs.length], ["Published scenarios", index?.length ?? "—"], ["Team accounts", overview.user.role === "admin" ? users.length : "Restricted"]].map(([label, value]) => <div className={s.stat} key={label}><span className={s.statLabel}>{label}</span><span className={s.statValue}>{value}</span></div>)}</div>
        <section className={s.panel}><h2 className={s.panelTitle}>Runtime & access policy</h2><dl className={a.settings}>{[["Backend", API_URL], ["Upload access key", overview.uploads_need_key ? "Required" : "Not configured"], ["Docker enforcement", overview.require_docker ? "Required" : "Optional"], ["Daily investigation limit", overview.daily_limit || "Unlimited"], ["Session expiry", "8 hours"], ["Last refreshed", updated]].map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><p className={s.footnote}>Runtime policies are configured on the server. <Link href="/docs#administration">Administration guide →</Link></p></section>
      </>}
      {tab === "Investigations" && <section className={s.panel}><div className={s.pageHead}><h2 className={s.panelTitle}>Backend investigations</h2><Link href="/runs" className={s.btn}>Browse saved runs</Link></div><div className={s.tableWrap}><table className={s.table}><thead><tr><th>Investigation</th><th>Status</th><th>Started</th><th>Actions</th></tr></thead><tbody>{overview.runs.map((run) => <tr key={run.id}><td>{run.title || run.scenario}</td><td><span className={cx(s.tag, run.status === "failed" ? s.sevCritical : s.sevPass)}>{run.status}</span></td><td>{fmtDate(run.started_at)}</td><td><div className={s.actions}><Link className={cx(s.btn, s.btnSm)} href={`/run?live=${encodeURIComponent(run.id)}`}>View</Link>{run.status === "running" && overview.user.role !== "viewer" && <button className={cx(s.btn, s.btnSm, s.btnDanger)} disabled={busy} onClick={() => action(async () => { await request(`/runs/${encodeURIComponent(run.id)}/cancel`, "POST"); setNotice("Stop requested. The investigation will stop before its next model call."); await refresh(); })}>Stop</button>}</div></td></tr>)}{!overview.runs.length && <tr><td colSpan={4}>No investigations in this backend session.</td></tr>}</tbody></table></div></section>}
      {tab === "Users & roles" && overview.user.role === "admin" && <>
        <div className={a.roleCards}>{[["admin", "Administrator", "Manage accounts, assign roles, and operate investigations."], ["operator", "Operator", "Monitor activity and stop running investigations."], ["viewer", "Viewer", "Read workspace health and investigation activity."]].map(([value, title, text]) => <section key={value} className={s.panel}><span className={cx(s.chip,s.iconViolet)}><Icon name="shieldCheck" size={20} /></span><h2 className={s.panelTitle}>{title}</h2><p className={s.pageText}>{text}</p><span className={s.footnote}>{users.filter((user) => user.role === value && user.active).length} active members</span></section>)}</div>
        <section className={s.panel}><div className={s.pageHead}><h2 className={s.panelTitle}>Team members</h2><input type="search" className={s.search} aria-label="Search users" placeholder="Search team…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className={s.tableWrap}><table className={s.table}><thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Access</th></tr></thead><tbody>{visibleUsers.map((user) => <tr key={user.id}><td><strong>{user.name}</strong><br /><span className={s.muted}>{user.email}</span></td><td><select aria-label={`Role for ${user.email}`} className={s.select} value={user.role} disabled={busy || user.id === overview.user.id} onChange={(event) => action(async () => { await request(`/users/${user.id}`, "PATCH", { role: event.target.value, active: Boolean(user.active) }); await refresh(); setNotice("Role updated. Existing sessions for this member were revoked."); })}>{ROLES.map((value) => <option key={value} value={value}>{value}</option>)}</select></td><td><span className={cx(s.tag, user.active ? s.sevPass : s.sevLow)}>{user.active ? "Active" : "Suspended"}</span></td><td><button className={cx(s.btn, s.btnSm)} disabled={busy || user.id === overview.user.id} onClick={() => action(async () => { await request(`/users/${user.id}`, "PATCH", { role: user.role, active: !user.active }); await refresh(); setNotice(user.active ? "Account suspended and sessions revoked." : "Account reactivated."); })}>{user.active ? "Suspend" : "Reactivate"}</button></td></tr>)}{visibleUsers.length === 0 && <tr><td colSpan={4}>No members match your search.</td></tr>}</tbody></table></div><p className={s.footnote}>You cannot change your own access here. The server preserves at least one active administrator.</p></section>
        <section className={s.panel}><h2 className={s.panelTitle}>Add a team member</h2><form className={a.create} onSubmit={(event) => { event.preventDefault(); action(async () => { await request("/users", "POST", { name, email: newEmail, password: newPassword, role }); setName(""); setNewEmail(""); setNewPassword(""); await refresh(); setNotice("Account created. Share credentials with the member through your secure channel."); }); }}><label className={s.field}><span className={s.label}>Name</span><input className={s.input} required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label><label className={s.field}><span className={s.label}>Email</span><input className={s.input} type="email" required maxLength={254} value={newEmail} onChange={(event) => setNewEmail(event.target.value)} /></label><label className={s.field}><span className={s.label}>Initial password</span><input className={s.input} type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><span className={s.hint}>At least 12 characters.</span></label><label className={s.field}><span className={s.label}>Role</span><select className={s.select} value={role} onChange={(event) => setRole(event.target.value as Role)}>{ROLES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><button className={cx(s.btn, s.btnPrimary)} disabled={busy}>Create account</button></form></section>
      </>}
      </div>
    </>}
  </AppShell>;
}
