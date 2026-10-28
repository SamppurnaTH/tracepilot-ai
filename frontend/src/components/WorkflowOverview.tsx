import Link from "next/link";
import { Icon, type IconName } from "./icons";
import { cx } from "@/lib/styles";
import s from "@/app/landing.module.css";
import a from "./app.module.css";

const FLOW: [string, string, IconName, string][] = [
  ["1. Investigate", "Analyze logs, inspect code, and test hypotheses against real evidence.", "search", a.iconViolet],
  ["2. Reproduce", "Generate a test that fails on the original code and captures the incident.", "flask", a.iconBlue],
  ["3. Fix", "Create a targeted patch in an isolated copy of the project.", "code", a.iconGreen],
  ["4. Verify", "Run the tests and get an independent AI review of the proposed fix.", "shieldCheck", a.iconAmber],
  ["5. Hand-off", "Review the patch, test evidence, PR description, and detailed report.", "file", a.iconPink],
];
const FEATURES: [string, string, IconName, string][] = [
  ["Works on your code", "Python with pytest and Java with Maven. Start with a project, a public repository, or the CLI.", "code", a.iconPink],
  ["Knows when to stop", "Identifies external causes such as expired credentials and recommends an operational fix.", "minusCircle", a.iconAmber],
  ["Independent review", "A second model checks the evidence and patch to catch superficial fixes.", "shieldCheck", a.iconGreen],
  ["Secure sandbox", "Investigations run on a sandboxed copy, with existing tests kept read-only.", "box", a.iconBlue],
];

export function WorkflowOverview({ standalone = false }: { standalone?: boolean }) {
  return <>
    <section className={s.section} id="how" aria-labelledby="how-title">
      <div className={s.center}><span className={s.eyebrow}>EVIDENCE AT EVERY STEP</span><h2 id="how-title" className={s.h2}>How TracePilot AI Works</h2><p className={s.sub}>A verification-first AI agent for real-world software debugging.</p></div>
      <ol className={s.flow}>{FLOW.map(([title, text, icon, tone]) => <li key={title} className={s.flowStep}><span className={cx(s.flowIcon, tone)}><Icon name={icon} size={22} /></span><span className={s.flowTitle}>{title}</span><span className={s.flowText}>{text}</span></li>)}</ol>
    </section>
    <section className={s.section} id="product" aria-labelledby="product-title"><h2 id="product-title" className={s.h2}>Built for Real Engineering Work</h2><div className={s.features}>{FEATURES.map(([title, text, icon, tone]) => <article key={title} className={s.feature}><span className={cx(s.featureIcon, tone)}><Icon name={icon} size={20} /></span><h3 className={s.featureTitle}>{title}</h3><p className={s.featureText}>{text}</p></article>)}</div></section>
    {standalone && <div className={a.outcomePaths}><Link href="/run?id=checkout" className={a.outcomePath}><span className={cx(a.chip,a.iconGreen)}><Icon name="checkCircle" size={22} /></span><div><h3>When the fix is in the code</h3><p>A verified patch, reproducing tests, and an independent review.</p><span>Explore a verified result →</span></div></Link><Link href="/run?id=refunds" className={a.outcomePath}><span className={cx(a.chip,a.iconBlue)}><Icon name="bulb" size={22} /></span><div><h3>When the fix is elsewhere</h3><p>Evidence for the external cause and a clear operational recommendation.</p><span>Explore a no-code-change result →</span></div></Link></div>}
  </>;
}
