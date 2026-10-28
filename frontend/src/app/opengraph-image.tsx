import { ImageResponse } from "next/og";
import evalSummary from "../../public/eval.json";
import { estimateCost } from "@/lib/run";

// The link-preview card for X, Discord and Slack. Numbers come from the published evaluation.
export const alt = "TracePilot AI: the AI debugger that proves its fix";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const INK = "#e8eaed";
const MUTED = "#a4acb8";
const BORDER = "#2a3038";
const GOOD = "#3ecf8e";

export default function OpengraphImage() {
  const { agent, agent_total: runs, reviewer } = evalSummary;
  const rows = Object.values(agent);
  const avgTokens = rows.reduce((a, r) => a + r.avg_tokens * r.runs, 0) / Math.max(1, runs.runs);
  const stats = [
    [`${runs.verified}/${runs.runs}`, "runs verified by tests"],
    [`${reviewer.gamed.correct}/${reviewer.gamed.cases}`, "test-gaming patches caught"],
    [estimateCost(avgTokens), "average per investigation"],
  ];
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#0b0d10", color: INK }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <svg width="56" height="56" viewBox="0 0 24 24">
              <rect width="24" height="24" rx="6" fill={INK} />
              <path d="M5 15.5h3.2l2.3-7 3 10 2-5H19" fill="none" stroke="#0b0d10" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="19" cy="13.5" r="1.6" fill={GOOD} />
            </svg>
            <span style={{ fontSize: 40 }}>TracePilot AI</span>
          </div>
          <span style={{ fontSize: 26, color: MUTED }}>Built on Meta Muse Spark</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <span style={{ fontSize: 80, letterSpacing: -2, lineHeight: 1.05 }}>The AI debugger that proves its fix.</span>
          <span style={{ fontSize: 30, color: MUTED }}>Root cause, a failing test, a patch, and an open-weight second opinion.</span>
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          {stats.map(([value, label]) => (
            <div key={label} style={{ display: "flex", flexDirection: "column", padding: "16px 28px", border: `2px solid ${BORDER}`, borderRadius: 14 }}>
              <span style={{ fontSize: 44, color: GOOD }}>{value}</span>
              <span style={{ fontSize: 22, color: MUTED }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
