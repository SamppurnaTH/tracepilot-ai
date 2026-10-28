"use client";

import { useState } from "react";
import s from "./ui.module.css";

export const cx = (...names: (string | false | undefined | null)[]) => names.filter(Boolean).join(" ");

/** A trace that ends in a check mark: evidence leading to a verified fix. */
export function Logo() {
  return (
    <svg className={s.logo} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="6" className={s.logoBg} />
      <path d="M5 15.5h3.2l2.3-7 3 10 2-5H19" className={s.logoTrace} />
      <circle cx="19" cy="13.5" r="1.6" className={s.logoDot} />
    </svg>
  );
}

const SEVERITY_CLASS = { critical: s.sevCritical, high: s.sevHigh, medium: s.sevMedium, low: s.sevLow };

export function Severity({ level, label }: { level: keyof typeof SEVERITY_CLASS; label?: string }) {
  return <span className={cx(s.tag, SEVERITY_CLASS[level])}>{label ?? level}</span>;
}

export function CopyButton({ text, label, className }: { text: string; label: string; className?: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("done");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 1800);
  };
  return (
    <button type="button" className={className ?? s.btn} onClick={copy}>
      {state === "done" ? "Copied" : state === "failed" ? "Copy failed" : label}
    </button>
  );
}
