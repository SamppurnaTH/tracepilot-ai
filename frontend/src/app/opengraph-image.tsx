import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import comparison from "../../public/comparison.json";
import evalSummary from "../../public/eval.json";
import { estimateCost } from "@/lib/run";

// The link-preview card for X, Discord and Slack, in the brand colours. Numbers come from the published results.
export const alt = "TracePilot AI: from errors to verified fixes";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const INK = "#EEF0FB";
const MUTED = "#A3A9D6";
const BORDER = "#26305C";

export default function OpengraphImage() {
  const mark = `data:image/svg+xml;base64,${readFileSync(join(process.cwd(), "public/brand/mark.svg")).toString("base64")}`;
  const tp = comparison.systems.tracepilot;
  const plain = comparison.systems.plain;
  const gamed = evalSummary.reviewer.gamed;
  const stats = [
    [`${tp.correct}/${tp.runs}`, "incidents fixed (hidden tests)"],
    [`${gamed.correct}/${gamed.cases}`, "test-gaming patches caught"],
    [`${Math.round((1 - tp.avg_tokens / plain.avg_tokens) * 100)}% fewer`, `tokens · about ${estimateCost(tp.avg_tokens)} a run`],
  ];
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 68,
          color: INK,
          background: "radial-gradient(circle at 82% 22%, #2A2470 0%, #0B1020 55%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- rendered by next/og, not the browser */}
            <img src={mark} width={84} height={84} alt="" />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", fontSize: 46, fontWeight: 700, letterSpacing: -1 }}>
                TracePilot<span style={{ color: "#818CF8", marginLeft: 12 }}>AI</span>
              </div>
              <span style={{ fontSize: 18, letterSpacing: 6, color: MUTED }}>AI DEBUG. VERIFY. FIX.</span>
            </div>
          </div>
          <span style={{ fontSize: 24, color: MUTED }}>Built on Meta Muse Spark</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", fontSize: 78, fontWeight: 700, letterSpacing: -2, lineHeight: 1.05 }}>
            From errors to<span style={{ color: "#8B9CFF", marginLeft: 22 }}>verified fixes.</span>
          </div>
          <span style={{ fontSize: 28, color: MUTED }}>A reproducing test, a patch your tests confirm, an open-weight review.</span>
        </div>
        <div style={{ display: "flex", gap: 18 }}>
          {stats.map(([value, label]) => (
            <div key={label} style={{ display: "flex", flexDirection: "column", padding: "14px 26px", border: `2px solid ${BORDER}`, borderRadius: 16, background: "rgba(99,102,241,0.08)" }}>
              <span style={{ fontSize: 40, fontWeight: 700, color: "#7DD3FC" }}>{value}</span>
              <span style={{ fontSize: 21, color: MUTED }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
