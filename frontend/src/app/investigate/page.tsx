"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import s from "@/components/app.module.css";
import { AppShell } from "@/components/AppShell";
import { cx } from "@/components/bits";
import { Icon } from "@/components/icons";
import { startCustomRun, startLiveRun, uploadsNeedKey } from "@/lib/api";
import { useData } from "@/lib/useData";

type Source = "upload" | "repo" | "example";

// The access key is kept for this browser tab only, so judges type it once.
const KEY_STORE = "tracepilot-access-key";
const readKey = () => {
  try {
    return sessionStorage.getItem(KEY_STORE) ?? "";
  } catch {
    return "";
  }
};

function FilePick({ label, hint, accept, multiple, files, onChange }: { label: string; hint: string; accept: string; multiple?: boolean; files: File[]; onChange: (f: File[]) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div className={s.field}>
      <span className={s.label}>{label}</span>
      <div
        className={cx(s.drop, over && s.dropOn)}
        role="button"
        tabIndex={0}
        onClick={() => ref.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && ref.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          onChange(Array.from(e.dataTransfer.files).slice(0, multiple ? 10 : 1));
        }}
      >
        <Icon name="download" size={22} />
        <span className={s.hint}>{hint}</span>
        <span className={cx(s.btn, s.btnSm)}>Choose {multiple ? "files" : "a file"}</span>
        <input ref={ref} type="file" accept={accept} multiple={multiple} hidden onChange={(e) => onChange(Array.from(e.target.files ?? []))} />
      </div>
      {files.length > 0 && (
        <ul className={s.files}>
          {files.map((f) => (
            <li key={f.name}>
              {f.name} · {(f.size / 1024).toFixed(0)} KB
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Investigate() {
  const { index, live } = useData();
  const router = useRouter();
  const [source, setSource] = useState<Source>("upload");
  const [project, setProject] = useState<File[]>([]);
  const [repo, setRepo] = useState("");
  const [example, setExample] = useState("checkout");
  const [incident, setIncident] = useState("");
  const [logs, setLogs] = useState<File[]>([]);
  const [shots, setShots] = useState<File[]>([]);
  const [tests, setTests] = useState("");
  const [testArgs, setTestArgs] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needKey, setNeedKey] = useState(false);
  const [accessKey, setAccessKey] = useState("");
  useEffect(() => setAccessKey(readKey()), []);
  useEffect(() => {
    if (live) uploadsNeedKey().then(setNeedKey);
  }, [live]);
  const examples = (index ?? []).filter((e) => e.scenario.live);

  const ready =
    source === "example"
      ? Boolean(example)
      : incident.trim().length >= 10 && (source === "upload" ? project.length === 1 : /^https:\/\//.test(repo.trim())) && (!needKey || Boolean(accessKey.trim()));

  const start = async () => {
    setError(null);
    if (source === "example" && !live) {
      router.push(`/run?id=${example}`);
      return;
    }
    setBusy(true);
    try {
      if (source === "example") {
        router.push(`/run?live=${await startLiveRun(example)}`);
        return;
      }
      const form = new FormData();
      form.append("incident", incident.trim());
      if (source === "upload") form.append("project", project[0]);
      else form.append("repo_url", repo.trim());
      logs.forEach((f) => form.append("logs", f));
      shots.forEach((f) => form.append("screenshots", f));
      if (tests.trim()) form.append("tests", tests.trim());
      if (testArgs.trim()) form.append("test_args", testArgs.trim());
      try {
        sessionStorage.setItem(KEY_STORE, accessKey.trim());
      } catch {}
      const run = await startCustomRun(form, accessKey.trim() || undefined);
      router.push(`/run?live=${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>Start a new investigation</h1>
          <p className={s.pageText}>Provide your code, any logs or screenshots, and a short description of what users are seeing.</p>
        </div>
      </div>

      {live === false && (
        <div className={cx(s.notice, s.noticeWarn)}>
          <Icon name="bulb" size={18} />
          <span>
            This hosted demo has no backend, so it can&apos;t run new investigations. Run TracePilot locally (<Link href="/docs#getting-started">getting started</Link>
            ) or use the CLI on your project. You can still pick an example below to watch its recorded run.
          </span>
        </div>
      )}

      <section className={s.panel} aria-label="New investigation">
        <div className={s.tabs} role="tablist" aria-label="Project source">
          {(
            [
              ["upload", "Upload project"],
              ["repo", "Git repository"],
              ["example", "Use example"],
            ] as [Source, string][]
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={source === id} className={cx(s.tab, source === id && s.tabOn)} onClick={() => setSource(id)}>
              {label}
            </button>
          ))}
        </div>

        <div className={s.formGrid}>
          <div className={s.field}>
            {source === "upload" && (
              <FilePick
                label="Project (ZIP)"
                hint="Python with pytest, or Java with Maven. Up to 50 MB, 5,000 files."
                accept=".zip,application/zip"
                files={project}
                onChange={setProject}
              />
            )}
            {source === "repo" && (
              <label className={s.field}>
                <span className={s.label}>Public repository URL</span>
                <input className={s.input} type="url" placeholder="https://github.com/owner/service" value={repo} onChange={(e) => setRepo(e.target.value)} />
                <span className={s.hint}>GitHub, GitLab or Bitbucket over HTTPS. Shallow-cloned into the sandbox; never pushed to.</span>
              </label>
            )}
            {source === "example" && (
              <label className={s.field}>
                <span className={s.label}>Example scenario</span>
                <select className={s.select} value={example} onChange={(e) => setExample(e.target.value)}>
                  {examples.map((e) => (
                    <option key={e.scenario.id} value={e.scenario.id}>
                      {e.scenario.title}
                    </option>
                  ))}
                </select>
                <span className={s.hint}>{live ? "Runs live on the connected backend." : "Opens the recorded run."}</span>
              </label>
            )}
          </div>

          {source !== "example" && (
            <div className={s.field} style={{ gap: 16 }}>
              <label className={s.field}>
                <span className={s.label}>Incident description</span>
                <textarea
                  className={s.textarea}
                  placeholder="What are users seeing? e.g. Checkout returns 500 when the cart has no coupon."
                  value={incident}
                  onChange={(e) => setIncident(e.target.value)}
                  maxLength={4000}
                />
              </label>
              <FilePick label="Logs (optional)" hint="JSON lines or plain text: .log, .txt, .json" accept=".log,.txt,.json,.jsonl" multiple files={logs} onChange={setLogs} />
              <FilePick label="Screenshots (optional)" hint="PNG, JPEG, WebP or GIF; the model reads them as evidence" accept="image/png,image/jpeg,image/webp,image/gif" multiple files={shots} onChange={setShots} />
              {needKey && (
                <label className={s.field}>
                  <span className={s.label}>Access key</span>
                  <input className={s.input} type="password" autoComplete="off" value={accessKey} onChange={(e) => setAccessKey(e.target.value)} />
                  <span className={s.hint}>
                    Investigating your own code on this hosted backend needs a key, shared with the hackathon judges. The example scenarios run without one, or run TracePilot
                    on your machine (<Link href="/docs#getting-started">getting started</Link>).
                  </span>
                </label>
              )}
              <details className={s.details}>
                <summary>Advanced options (Java)</summary>
                <div className={s.field} style={{ gap: 12 }}>
                  <label className={s.field}>
                    <span className={s.label}>Test classes that define green</span>
                    <input className={s.input} placeholder="ShipControllerTest,UserServiceTest (default: all)" value={tests} onChange={(e) => setTests(e.target.value)} />
                  </label>
                  <label className={s.field}>
                    <span className={s.label}>Extra test properties</span>
                    <input className={s.input} placeholder="-Dspring.profiles.active=test" value={testArgs} onChange={(e) => setTestArgs(e.target.value)} />
                  </label>
                </div>
              </details>
            </div>
          )}
        </div>

        {error && <p className={s.errorText}>{error}</p>}
        <div className={s.actions}>
          <button type="button" className={cx(s.btn, s.btnPrimary, s.btnLg)} onClick={start} disabled={busy || !ready || (source !== "example" && !live)}>
            {busy ? "Starting…" : source === "example" && !live ? "Watch the recorded run" : "Start investigation"} <Icon name="arrowRight" size={16} />
          </button>
          {source !== "example" && !live && <span className={s.hint}>Needs a TracePilot backend.</span>}
        </div>
      </section>
    </AppShell>
  );
}
