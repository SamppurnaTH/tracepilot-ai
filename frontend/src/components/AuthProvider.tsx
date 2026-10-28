"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { API_URL, apiFetch, setApiToken } from "@/lib/api";

export type UserRole = "admin" | "operator" | "viewer";
export type SessionUser = { id: string; name: string; email: string; role: UserRole; active: boolean; workspace_access: boolean; permissions: string[] };
const Context = createContext<{
  workspace: { name: string; description: string }; setWorkspace: (workspace: { name: string; description: string }) => void;
  token: string; user: SessionUser | null; setIdentity: (token: string, user: SessionUser | null) => void;
  request: <T>(path: string, method?: string, body?: unknown) => Promise<T>;
} | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [workspace, setWorkspace] = useState({ name: "TracePilot Workspace", description: "Verification-first AI debugging" });
  const [token, setToken] = useState("");
  const [user, setUser] = useState<SessionUser | null>(null);
  const setIdentity = useCallback((nextToken: string, nextUser: SessionUser | null) => {
    setApiToken(nextToken); setToken(nextToken); setUser(nextUser);
  }, []);
  const request = useCallback(async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
    if (!API_URL) throw new Error("No backend is configured. Connect a backend to sign in.");
    const response = await apiFetch(`${API_URL}${path}`, { method, headers: { "Content-Type": "application/json" }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(20000) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && token) setIdentity("", null);
      throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (HTTP ${response.status})`);
    }
    return data;
  }, [token, setIdentity]);
  return <Context.Provider value={{ token, user, setIdentity, request, workspace, setWorkspace }}>{children}</Context.Provider>;
}

export function useAuth() {
  const auth = useContext(Context);
  if (!auth) throw new Error("Authentication provider is missing");
  return auth;
}
