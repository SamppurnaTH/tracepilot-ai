"use client";

import Link from "next/link";
import s from "./landing.module.css";
import a from "@/components/app.module.css";
import { REPO_URL } from "@/components/AppShell";
import { Logo, Wordmark, cx } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import { estimateCost } from "@/lib/run";
import { kTokens, minutes, useData } from "@/lib/useData";

const FLOW: [string, string, IconName, string][] = [
  ["1. Investigate", "Reads logs, code and screenshots; tests hypotheses with real requests", "search", a.iconViolet],
  ["2. Reproduce", "Writes a test that fails on the current code, or uses one that already does", "flask", a.iconBlue],
  ["3. Fix", "Patches a sandboxed copy; existing tests stay read-only", "code", a.iconGreen],
  ["4. Verify", "Your test suite decides, then an independent model reviews the patch", "shieldCheck", a.iconAmber],
  ["5. Hand-off", "Patch, PR description and a full report, ready to review", "file", a.iconPink],
];

const FEATURES: [string, string, IconName, string][] = [
  ["Works on your code", "Python with pytest and Java with Maven. Upload a project, point at a repo, or use the CLI.", "code", a.iconViolet],
  ["Knows when to stop", "When the cause is outside the code, like an expired API key, it says so instead of patching.", "minusCircle", a.iconAmber],
  ["Independent review", "Muse Spark Open, an open-weight Meta model, rejects patches that only game the tests.", "eye", a.iconGreen],
  ["Secure sandbox", "Docker with no network, a read-only root and a non-root user. Your files are never touched.", "shieldCheck", a.iconBlue],
];

export default function Landing() {
  const { comparison, index } = useData();
  const tp = comparison?.systems.tracepilot;
  const plain = comparison?.systems.plain;
  const stats: [IconName, string, string][] = tp && plain
    ? [
        ["checkCircle", `${Math.round((tp.correct / tp.runs) * 100)}%`, `${tp.correct}/${tp.runs} incidents fixed (hidden tests)`],
        ["layers", `${Math.round((1 - tp.avg_tokens / plain.avg_tokens) * 100)}%`, `fewer tokens (avg ${kTokens(tp.avg_tokens)} vs ${kTokens(plain.avg_tokens)})`],
        ["bolt", `${Math.round((1 - tp.avg_duration_s / plain.avg_duration_s) * 100)}%`, `less time (avg ${minutes(tp.avg_duration_s)} vs ${minutes(plain.avg_duration_s)})`],
        ["receipt", estimateCost(tp.avg_tokens), "average cost per investigation (est.)"],
      ]
    : [];
  return (
    <div className={s.page}>
      <header className={s.hero}>
        <div className={s.inner}>
          <nav className={s.nav} aria-label="Main">
            <Link href="/" className={s.brand}>
              <Logo size={38} />
              <span className={s.brandText}>
                <span>
                  <Wordmark /> <span className={s.beta}>beta</span>
                </span>
                <span className={s.tagline}>AI Debug. Verify. Fix.</span>
              </span>
            </Link>
            <div className={s.links}>
              <a href="#product">Product</a>
              <a href="#how">How it works</a>
              <Link href="/examples">Examples</Link>
              <Link href="/results">Results</Link>
              <Link href="/docs">Docs</Link>
              <Link href="/examples" className={s.cta}>
                Run live demo
              </Link>
            </div>
          </nav>
          <div className={s.heroGrid}>
            <div>
              <h1 className={s.title}>
                From errors to <span className={s.gradient}>verified fixes</span>
              </h1>
              <p className={s.lede}>
                TracePilot AI investigates a failing service, writes a test that reproduces the bug, fixes it, proves the fix with your tests and an independent model,
                and tells you exactly what to do. When the cause isn&apos;t in the code, it says so instead of patching.
              </p>
              <div className={s.heroActions}>
                <Link href="/examples" className={s.cta}>
                  Run live demo <Icon name="arrowRight" size={16} />
                </Link>
                <Link href="/examples" className={s.ghost}>
                  View example scenarios
                </Link>
              </div>
            </div>
            <div className={s.stage} aria-hidden="true">
              <div className={s.stack}>
                {(["Investigate", "Reproduce", "Fix", "Verify", "Hand-off"] as const).map((label, i) => (
                  <div key={label} className={s.layer}>
                    <span className={s.layerIcon}>
                      <Icon name={(["search", "flask", "code", "shieldCheck", "file"] as IconName[])[i]} size={20} />
                    </span>
                    {label}
                  </div>
                ))}
              </div>
              <span className={s.check}>
                <Icon name="check" size={30} />
              </span>
            </div>
          </div>
          {stats.length > 0 && (
            <div className={s.stats} aria-label="Results from the latest benchmark">
              {stats.map(([icon, value, label]) => (
                <div key={label} className={s.stat}>
                  <span className={s.statIcon}>
                    <Icon name={icon} size={20} />
                  </span>
                  <span>
                    <span className={s.statValue}>{value}</span>
                    <span className={s.statLabel}>{label}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className={s.inner}>
        <section className={s.section} id="how" aria-labelledby="how-title">
          <div className={s.center}>
            <h2 id="how-title" className={s.h2}>
              How TracePilot AI works
            </h2>
            <p className={s.sub}>A verification-first AI agent for real-world debugging, built on Meta Muse Spark.</p>
          </div>
          <ol className={s.flow}>
            {FLOW.map(([title, text, icon, tone]) => (
              <li key={title} className={s.flowStep}>
                <span className={cx(s.flowIcon, tone)}>
                  <Icon name={icon} size={22} />
                </span>
                <span className={s.flowTitle}>{title}</span>
                <span className={s.flowText}>{text}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className={s.section} id="product" aria-labelledby="product-title">
          <h2 id="product-title" className={s.h2}>
            Built for real engineering work
          </h2>
          <div className={s.features}>
            {FEATURES.map(([title, text, icon, tone]) => (
              <article key={title} className={s.feature}>
                <span className={cx(s.featureIcon, tone)}>
                  <Icon name={icon} size={20} />
                </span>
                <h3 className={s.featureTitle}>{title}</h3>
                <p className={s.featureText}>{text}</p>
              </article>
            ))}
          </div>
        </section>

        <div className={s.band}>
          <div>
            <p className={s.bandTitle}>{index ? `${index.length} real investigations to replay` : "Real investigations to replay"}</p>
            <p className={s.bandText}>Watch each step, or compare TracePilot with a plain agent on the same model.</p>
          </div>
          <div className={a.actions}>
            <Link href="/examples" className={s.cta}>
              Explore scenarios <Icon name="arrowRight" size={16} />
            </Link>
            <Link href="/results" className={s.ghost}>
              See the comparison
            </Link>
          </div>
        </div>

        <footer className={s.footer}>
          <span>TracePilot AI · Meta Global AI Developer Hackathon · MIT licensed</span>
          <span>
            Investigator: muse-spark-1.3 · Reviewer: Muse Spark Open ·{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </span>
        </footer>
      </div>
    </div>
  );
}
