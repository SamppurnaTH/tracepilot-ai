"use client";

import { useId, useState } from "react";
import s from "./app.module.css";

import { cx } from "@/lib/styles";
export { cx };

/**
 * The TracePilot AI mark (also public/brand/mark.svg): the letter A for AI, a flight path from error
 * to resolution, and a star for the verified fix. Gradient ids are unique per instance.
 */
export function Logo({ size = 34, className }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className ?? s.logo} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}r`} x1="30" y1="10" x2="50" y2="56" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#6366F1" />
          <stop offset="1" stopColor="#0EA5E9" />
        </linearGradient>
        <linearGradient id={`${id}l`} x1="14" y1="48" x2="30" y2="10" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#4F46E5" />
          <stop offset="1" stopColor="#7C83F7" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="4" y1="52" x2="50" y2="20" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8B5CF6" />
          <stop offset="0.55" stopColor="#6366F1" />
          <stop offset="1" stopColor="#38BDF8" />
        </linearGradient>
        <linearGradient id={`${id}t`} x1="44" y1="4" x2="60" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#C4B5FD" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      <path d="M30.5 13.5 L48 51" fill="none" stroke={`url(#${id}r)`} strokeWidth="13" strokeLinecap="round" />
      <path d="M29.5 13.5 L16.5 43" fill="none" stroke={`url(#${id}l)`} strokeWidth="12" strokeLinecap="round" />
      <path d="M2.5 50.5 C 16 46.5 35 37 51.5 19.5 C 42.5 39.5 24 55 9 57.5 C 4 58.3 1 54.5 2.5 50.5 Z" fill={`url(#${id}s)`} />
      <path d="M52 3 L54.3 10.7 L62 13 L54.3 15.3 L52 23 L49.7 15.3 L42 13 L49.7 10.7 Z" fill={`url(#${id}t)`} />
    </svg>
  );
}

/** "TracePilot AI" with the brand gradient on "AI". */
export function Wordmark() {
  return (
    <span className={s.wordmark}>
      TracePilot <span className={s.wordmarkAi}>AI</span>
    </span>
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
