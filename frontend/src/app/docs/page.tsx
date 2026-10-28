"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import s from "@/components/app.module.css";
import { AppShell, REPO_URL } from "@/components/AppShell";
import { CopyButton, cx } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import { useData } from "@/lib/useData";

const SECTIONS: [string, string, IconName][] = [
  ["getting-started", "Getting started", "play"],
  ["cli", "CLI guide", "terminal"],
  ["projects", "Supported projects", "code"],
  ["architecture", "Architecture", "layers"],
  ["evaluation", "Evaluation results", "chart"],
  ["administration", "Administration", "shieldCheck"],
  ["faq", "FAQ", "bulb"],
];

const QUICKSTART: Record<string, string[]> = {
  "Python project": [
    "# Install (Python 3.11+, Docker recommended)",
    "git clone https://github.com/SamppurnaTH/tracepilot-ai && cd tracepilot-ai",
    "python -m venv .venv && .venv/Scripts/python -m pip install -r backend/requirements.txt",
    "cp .env.example .env   # add MODEL_API_KEY (and BASETEN_API_KEY for the reviewer)",
    "",
    "# Run an investigation",
    ".venv/Scripts/python tracepilot.py investigate --repo path/to/service --logs app.log \\",
    '  --screenshot bug.png --incident "Checkout returns 500 when the cart has no coupon"',
  ],
  "Java project": [
    "# Maven projects run in a cached JDK 17 image (Docker required)",
    ".venv/Scripts/python tracepilot.py investigate --repo path/to/spring-service --logs app.log \\",
    '  --tests "ShipControllerTest,UserServiceTest" --test-args "-Dspring.profiles.active=test" \\',
    '  --incident "Users can edit ships hours after posting; the rule is 10 minutes"',
  ],
  "Web app + API": [
    "# Backend (FastAPI) and the web app",
    ".venv/Scripts/uvicorn app.main:app --app-dir backend --port 8000",
    "cd frontend && npm install && npm run dev   # http://localhost:3000",
  ],
};

const OPTIONS: [string, string][] = [
  ["--repo PATH", "The service's folder (Python with pytest, or Java with Maven and JUnit 5)"],
  ['--incident "…" / --incident-file F', "What users are seeing, in plain words"],
  ["--logs FILE…", "Log files as evidence: JSON lines or plain text with tracebacks"],
  ["--screenshot IMG…", "Screenshots the model reads as evidence (PNG, JPEG, WebP, GIF)"],
  ["--tests A,B", "Java: test classes that define green, e.g. the list your CI runs"],
  ["--test-args \"-D…\"", "Java: extra test properties, e.g. a Spring profile"],
  ["--apply", "Apply the patch with git apply, only if it was verified"],
  ["--no-review", "Skip the Muse Spark Open second opinion"],
];

export default function Docs() {
  const { live } = useData();
  const [tab, setTab] = useState("Python project");
  const [active, setActive] = useState("getting-started");
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => { for (const entry of entries) { if (entry.isIntersecting) setActive(entry.target.id); } }, { rootMargin: "-10% 0px -65% 0px" });
    document.querySelectorAll("section[id]").forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);
  const code = QUICKSTART[tab].join("\n");
  return (
    <AppShell live={live}>
      <div className={s.pageHead}>
        <div>
          <h1 className={s.pageTitle}>Documentation</h1>
          <p className={s.pageText}>
            Run TracePilot on your own code. The full README is on <a href={REPO_URL}>GitHub</a>.
          </p>
        </div>
      </div>
      <div className={s.docs}>
        <nav className={s.docNav} aria-label="Documentation sections">
          {SECTIONS.map(([id, label, icon]) => (
            <a key={id} href={`#${id}`} className={cx(s.docLink, active === id && s.docLinkOn)} aria-current={active === id ? "location" : undefined} onClick={() => setActive(id)}>
              <Icon name={icon} size={16} /> {label}
            </a>
          ))}
        </nav>
        <div className={s.docBody}>
          <section id="getting-started" className={cx(s.panel, s.docSection)}>
            <h2>Quick start</h2>
            <p>TracePilot isn&apos;t published as a package yet; run it from the repository. It needs Python 3.11+, Docker (recommended) and a Meta Model API key.</p>
            <div className={s.terminal}>
              <div className={s.terminalHead}>
                <div className={s.terminalTabs} role="tablist" aria-label="Project type">
                  {Object.keys(QUICKSTART).map((t) => (
                    <button key={t} type="button" role="tab" aria-selected={tab === t} className={cx(s.terminalTab, tab === t && s.terminalTabOn)} onClick={() => setTab(t)}>
                      {t}
                    </button>
                  ))}
                </div>
                <CopyButton text={code.split("\n").filter((l) => !l.startsWith("#")).join("\n")} label="Copy" className={s.copySmall} />
              </div>
              <pre className={s.code}>
                {QUICKSTART[tab].map((line, i) => (
                  <span key={i} className={line.startsWith("#") ? s.comment : undefined}>
                    {line}
                    {"\n"}
                  </span>
                ))}
              </pre>
            </div>
            <p>
              The result is a hand-off folder, <code className={s.inlineCode}>tracepilot-out/&lt;time&gt;/</code>, with <code className={s.inlineCode}>fix.patch</code>,{" "}
              <code className={s.inlineCode}>pr.md</code>, <code className={s.inlineCode}>report.md</code> and <code className={s.inlineCode}>run.json</code>. Exit code 0 means
              verified (or no code change needed).
            </p>
          </section>

          <section id="cli" className={cx(s.panel, s.docSection)}>
            <h2>CLI guide</h2>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <tbody>
                  {OPTIONS.map(([flag, text]) => (
                    <tr key={flag}>
                      <th scope="row" className={s.mono}>
                        {flag}
                      </th>
                      <td style={{ whiteSpace: "normal" }}>{text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="projects" className={cx(s.panel, s.docSection)}>
            <h2>Supported projects</h2>
            <ul>
              <li>
                <strong>Python</strong> with pytest. Its <code className={s.inlineCode}>requirements.txt</code> is installed once into a cached sandbox image; FastAPI apps are
                detected so the agent can send requests.
              </li>
              <li>
                <strong>Java</strong> with Maven and JUnit 5 (Java 17). Dependencies are downloaded at image build time; tests that need a database, network or Docker are
                excluded and listed.
              </li>
              <li>Private repositories work the same as public ones: TracePilot reads a local folder. Code snippets, logs and test results are sent to the model providers.</li>
            </ul>
          </section>

          <section id="architecture" className={cx(s.panel, s.docSection)}>
            <h2>Architecture</h2>
            <div className={s.archBox}>
              {(
                [
                  ["Harness", "Owns the facts: evidence brief, hypotheses, verification by comparing tests before and after"],
                  ["Docker sandbox", "A copy of your code with no network, a read-only root and a non-root user"],
                  ["muse-spark-1.3", "The investigator: tool calls, reproducing tests, patches, screenshots (Meta Model API)"],
                  ["Muse Spark Open", "The independent reviewer on Baseten: sees the facts and the patch, not the transcript"],
                  ["Hand-off", "Patch, PR description, Markdown report and the full event log"],
                ] as [string, string][]
              ).map(([title, text]) => (
                <div key={title} className={s.archItem}>
                  <strong>{title}</strong>
                  <span>{text}</span>
                </div>
              ))}
            </div>
          </section>

          <section id="evaluation" className={cx(s.panel, s.docSection)}>
            <h2>Evaluation results</h2>
            <p>
              Same model, with and without TracePilot, judged by hidden tests: see <Link href="/results">comparison results</Link>. Raw data and scripts:{" "}
              <code className={s.inlineCode}>eval/</code>, <code className={s.inlineCode}>backend/scripts/compare.py</code> and{" "}
              <code className={s.inlineCode}>backend/scripts/eval.py</code>.
            </p>
          </section>

          <section id="administration" className={cx(s.panel, s.docSection)}>
            <h2>Administration</h2>
            <p>Set TRACEPILOT_ADMIN_EMAIL and TRACEPILOT_ADMIN_PASSWORD (at least 12 characters) in the backend environment before first sign-in. The first account is bootstrapped only when the account database is empty. There is no default password.</p>
            <p>Set NEXT_PUBLIC_API_URL to your backend URL before building the frontend. For local use: http://127.0.0.1:8000. Restart the backend and rebuild the frontend after configuring them, then open the <Link href="/admin">admin plane</Link>.</p>
            <p>Administrators create accounts and assign roles. Operators monitor and stop investigations. Viewers have read-only access. Suspending an account or changing its role revokes its sessions. Sessions expire after eight hours; reloading the page requires sign-in again.</p>
            <p>Accounts are stored in runs/admin.sqlite3; set TRACEPILOT_ADMIN_DB to use a persistent volume. Passwords use salted PBKDF2 hashing. Keep the database private and use HTTPS when deployed. These roles protect /api/admin endpoints; the public demo APIs retain their existing access policy. Password recovery and email invitations are not included.</p>
          </section>

          <section id="faq" className={cx(s.panel, s.docSection)}>
            <h2>FAQ</h2>
            <ul>
              <li>
                <strong>Does it change my files?</strong> No. It works on a copy; <code className={s.inlineCode}>--apply</code> uses git apply, and only for a verified patch.
              </li>
              <li>
                <strong>What does a run cost?</strong> Typically 40K–125K tokens, about $0.05–$0.15; a 260-file Spring Boot app took 341K (about $0.42).
              </li>
              <li>
                <strong>What if the bug isn&apos;t in the code?</strong> It reports where the fix belongs (configuration, data or an external service) and makes no patch.
              </li>
              <li>
                <strong>Which models?</strong> muse-spark-1.3 investigates; Muse Spark Open, an open-weight Meta model, reviews. Both can be swapped in{" "}
                <code className={s.inlineCode}>.env</code>.
              </li>
            </ul>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
