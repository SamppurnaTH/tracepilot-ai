"use client";

import Link, { useAreaPath } from "@/components/AreaLink";
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
  const [fileError, setFileError] = useState("");
  const selectFiles = (selected: File[]) => {
    const limit = multiple ? 5_000_000 : 50_000_000;
    const valid = selected.every((file) => accept.split(",").some((type) => type.startsWith(".") ? file.name.toLowerCase().endsWith(type) : file.type === type) && file.size <= limit);
    if (!valid) { setFileError(`Choose a supported file type, up to ${multiple ? 5 : 50} MB per file.`); return; }
    setFileError(""); onChange(selected.slice(0, multiple ? 10 : 1));
  };
  return (
    <div className={s.field}>
      <span className={s.label}>{label}</span>
      <div
        className={cx(s.drop, multiple && s.dropCompact, over && s.dropOn, files.length > 0 && s.dropSelected)}
        role="button"
        aria-label={`Choose ${label.toLowerCase()}`}
        tabIndex={0}
        onClick={() => ref.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ref.current?.click(); } }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          selectFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <Icon name={files.length ? "checkCircle" : "file"} size={22} />
        {!multiple && <strong className={s.dropTitle}>Upload your project</strong>}
        <span className={s.hint}>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""} selected` : hint}</span>
        <span className={cx(s.btn, s.btnSm)}>Choose {multiple ? "files" : "a file"}</span>
        <input ref={ref} type="file" accept={accept} multiple={multiple} hidden onChange={(e) => { selectFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      </div>
      {fileError && <p className={s.errorText} role="alert">{fileError}</p>}
      {files.length > 0 && (
        <ul className={s.files}>
          {files.map((f) => (
            <li key={f.name}>
              <span>{f.name} · {(f.size / 1024).toFixed(0)} KB</span><button type="button" aria-label={`Remove ${f.name}`} onClick={() => onChange(files.filter((file) => file !== f))}>Remove</button>
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
  const area = useAreaPath();
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
      router.push(area(`/app/run?id=${example}&replay=1`));
      return;
    }
    setBusy(true);
    try {
      if (source === "example") {
        router.push(area(`/app/run?live=${await startLiveRun(example)}`));
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
      router.push(area(`/app/run?live=${run.id}`));
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

      <div className={s.setupSteps} aria-label="Investigation setup"><span><b>1</b> Connect your code</span><span><b>2</b> Describe the incident</span><span><b>3</b> Investigate & verify</span></div>
      <section className={s.panel} aria-label="New investigation">
        <div className={s.tabs} role="tablist" aria-label="Project source">
          {(
            [
              ["upload", "Upload project"],
              ["repo", "Git repository"],
              ["example", "Use example"],
            ] as [Source, string][]
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" id={`source-tab-${id}`} aria-controls="source-panel" aria-selected={source === id} className={cx(s.tab, source === id && s.tabOn)} onClick={() => setSource(id)}>
              {label}
            </button>
          ))}
        </div>

        <div className={s.formGrid} role="tabpanel" id="source-panel" aria-labelledby={`source-tab-${source}`}>
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
            {source !== "example" && <div className={s.setupNote}><Icon name="shieldCheck" size={18} /><div><strong>Your project stays yours.</strong><p>Investigations work on a sandboxed copy. Review the evidence and patch before applying a change.</p><Link href="/docs#projects">Supported projects →</Link></div></div>}
            {source === "example" && <div className={s.setupNote}><Icon name="play" size={20} /><div><strong>No setup required</strong><p>Select a real incident to follow the complete debugging workflow.</p></div></div>}
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
                <span className={s.hint}>{incident.length}/4,000 characters · At least 10 characters</span>
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

        {error && <p className={s.errorText} role="alert">{error}</p>}
        <div className={s.formActions}><p className={s.hint}>{source === "example" ? "Real incidents. Reproducing tests. Verifiable outcomes." : ready ? "Ready to investigate. Your original files stay unchanged." : "Connect a project and describe the incident to continue."}</p><div className={s.actions}>
          <button type="button" className={cx(s.btn, s.btnPrimary, s.btnLg)} onClick={start} disabled={busy || !ready || (source !== "example" && !live)}>
            {busy ? "Starting…" : source === "example" && !live ? "Watch the recorded run" : "Start investigation"} <Icon name="arrowRight" size={16} />
          </button>
          {source !== "example" && !live && <span className={s.hint}>Needs a TracePilot backend.</span>}
        </div></div>
      </section>
    </AppShell>
  );
}
