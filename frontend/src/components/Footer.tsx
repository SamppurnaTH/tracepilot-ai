import Link from "next/link";
import { Logo, Wordmark } from "./bits";
import s from "./footer.module.css";

export function Footer() {
  return (
    <footer className={s.footer}>
      <div className={s.top}>
        <div className={s.identity}><Link href="/" className={s.brand}><Logo size={28} /><Wordmark /></Link><p>From errors to verified fixes.<br />Built for engineers. Proven by tests.</p></div>
        <nav aria-label="Footer product"><span>Product</span><Link href="/product">How it works</Link><Link href="/examples">Example scenarios</Link><Link href="/investigate">New investigation</Link><Link href="/results">Benchmarks</Link></nav>
        <nav aria-label="Footer resources"><span>Resources</span><Link href="/docs">Documentation</Link><a href="https://github.com/SamppurnaTH/tracepilot-ai" target="_blank" rel="noreferrer">GitHub ↗</a></nav>
      </div>
      <div className={s.bottom}><span>© {new Date().getFullYear()} TracePilot AI · MIT licensed</span><span>Meta Global AI Developer Hackathon</span><span className={s.note}>Investigate. Reproduce. Fix. Verify.</span></div>
    </footer>
  );
}
