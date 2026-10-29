"use client";

import { useAuth } from "./AuthProvider";
import Link from "@/components/AreaLink";
import { Logo, Wordmark } from "./bits";
import s from "./footer.module.css";

export function Footer() {
  const { user } = useAuth();
  return (
    <footer className={s.footer}>
      <div className={s.top}>
        <div className={s.identity}><Link href="/" className={s.brand}><Logo size={28} /><Wordmark /></Link><p>From errors to verified fixes.<br />Built for engineers. Proven by tests.</p></div>
        <nav aria-label="Footer product"><span>Product</span><Link href="/app/product">How it works</Link><Link href="/app/examples">Example scenarios</Link>{user?.role !== "viewer" && <Link href="/app/investigate">New investigation</Link>}<Link href="/app/results">Benchmarks</Link></nav>
        <nav aria-label="Footer resources"><span>Resources</span><Link href="/docs">Documentation</Link><Link href="/evidence">Evidence & limitations</Link><Link href="/research">Research results</Link><a href="https://github.com/SamppurnaTH/tracepilot-ai" target="_blank" rel="noreferrer">GitHub ↗</a></nav>
      </div>
      <div className={s.bottom}><span>© {new Date().getFullYear()} TracePilot AI · MIT licensed</span><span>Meta Global AI Developer Hackathon</span><span className={s.note}>Investigate. Reproduce. Fix. Verify.</span></div>
    </footer>
  );
}
