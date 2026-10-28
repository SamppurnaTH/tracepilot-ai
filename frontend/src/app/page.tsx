"use client";

import Link from "@/components/AreaLink";
import s from "./landing.module.css";
import a from "@/components/app.module.css";
import { Footer } from "@/components/Footer";
import { Logo, Wordmark } from "@/components/bits";
import { Icon, type IconName } from "@/components/icons";
import { WorkflowOverview } from "@/components/WorkflowOverview";
import { estimateCost } from "@/lib/run";
import { kTokens, minutes, useData } from "@/lib/useData";

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
              <Link href="/app/product">Product</Link>
              <Link href="/app/product#how">How it works</Link>
              <Link href="/app/examples">Examples</Link>
              <Link href="/app/results">Results</Link>
              <Link href="/docs">Docs</Link>
              <Link href="/app/examples" className={s.cta}>
                Run live demo
              </Link>
            </div>
          </nav>
          <div className={s.heroGrid}>
            <div>
              <h1 className={s.title}>
                From Errors to <span className={s.gradient}>Verified Fixes</span>
              </h1>
              <p className={s.lede}>
                TracePilot AI automatically investigates application issues, finds the root cause, generates a fix, verifies it with tests, and tells you exactly what to do.
              </p>
              <div className={s.heroActions}>
                <Link href="/app/run?id=checkout&replay=1" className={s.cta}>
                  Watch demo <Icon name="arrowRight" size={16} />
                </Link>
                <Link href="/app/examples" className={s.ghost}>
                  View example scenarios
                </Link>
              </div>
            </div>
            <div className={s.stage} aria-hidden="true">
              <div className={s.orbit} />
              <div className={s.codeWindow}>
                <div className={s.windowDots}><i /><i /><i /><span>checkout / validator.py</span></div>
                <pre><span>def</span> validate_checkout(cart):{"\n"}  coupon = cart.get(<b>&quot;coupon&quot;</b>){"\n"}  <span>if</span> coupon is not None:{"\n"}    apply_coupon(coupon){"\n\n"}  <span>return</span> checkout(cart)</pre>
                <div className={s.codeStatus}>● Reproducing test generated</div>
              </div>
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
              <div className={s.testWindow}><span>VERIFICATION</span><code>✓ Reproduction test</code><code>✓ Regression suite</code><code>✓ Independent AI review</code><strong>All checks passed <Icon name="checkCircle" size={15} /></strong></div>
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
        <WorkflowOverview />

        <div className={s.band}>
          <div>
            <p className={s.bandTitle}>{index ? `${index.length} real investigations to replay` : "Real investigations to replay"}</p>
            <p className={s.bandText}>Watch each step, or compare TracePilot with a plain agent on the same model.</p>
          </div>
          <div className={a.actions}>
            <Link href="/app/examples" className={s.cta}>
              Explore scenarios <Icon name="arrowRight" size={16} />
            </Link>
            <Link href="/app/results" className={s.ghost}>
              See the comparison
            </Link>
          </div>
        </div>

        <Footer />
      </div>
    </div>
  );
}
