"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth, type SessionUser } from "./AuthProvider";
import { Logo, Wordmark, cx } from "./bits";
import { EmptyState } from "./ScreenState";
import s from "./app.module.css";
import a from "./workspace-gate.module.css";

export function WorkspaceGate({ children }: { children: React.ReactNode }) {
  const { token, user, request, setIdentity, setWorkspace } = useAuth();
  const path = usePathname();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!token) return;
    request<{ user: SessionUser; workspace: { name: string; description: string } }>("/api/workspace/me").then((data) => { setWorkspace(data.workspace); setIdentity(token,data.user); }).catch((err) => setError(err.message));
  },[token,request,setIdentity,setWorkspace]);
  if (user && user.workspace_access && !(path === "/app/investigate" && user.role === "viewer")) return children;
  return <div className={a.page}><header><Link href="/" className={a.brand}><Logo /><Wordmark /></Link><span>TracePilot Workspace</span></header><main className={a.main}>
    {user ? <><EmptyState icon="shieldCheck" title={user.workspace_access ? "This workspace is read-only" : "Workspace access is not enabled"} text={user.workspace_access ? "Your viewer role can review investigations and reports. An operator or administrator can start an investigation." : "An administrator must enable user workspace access for this account."} href={user.workspace_access ? "/app" : "/admin"} action={user.workspace_access ? "Open workspace" : "Back to Admin Console"} /></> : <section className={cx(s.panel,a.card)}><span className={a.eyebrow}>TRACEPILOT WORKSPACE</span><h1>Welcome back.</h1><p>Sign in to investigate, verify, and review your team’s fixes.</p><form onSubmit={async (event) => { event.preventDefault(); setBusy(true); setError(""); try { const data = await request<{ token: string; user: SessionUser }>("/api/admin/login", "POST", { email, password }); setIdentity(data.token, data.user); setPassword(""); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } }}><label className={s.field}><span className={s.label}>Email address</span><input className={s.input} type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label className={s.field}><span className={s.label}>Password</span><input className={s.input} type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <p className={s.errorText} role="alert">{error}</p>}<button className={cx(s.btn,s.btnPrimary,s.btnLg)} disabled={busy}>{busy ? "Signing in…" : "Open workspace →"}</button></form><p className={s.hint}>Access is managed by your administrator. Sessions last up to eight hours and end when this page is reloaded.</p></section>}
  </main></div>;
}
