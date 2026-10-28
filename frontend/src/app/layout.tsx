import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const sans = Geist({ variable: "--font-geist", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const description =
  "An AI agent that investigates software incidents in a sandbox, writes the failing test, patches the code, and proves the fix with your tests and an independent model review. Built on Meta Muse Spark.";

export const metadata: Metadata = {
  metadataBase: new URL("https://tracepilot-ai.vercel.app"),
  title: "TracePilot AI: root cause, patch and proof for every incident",
  description,
  openGraph: { title: "TracePilot AI: the AI debugger that proves its fix", description, url: "/", siteName: "TracePilot AI", type: "website" },
  twitter: { card: "summary_large_image", title: "TracePilot AI: the AI debugger that proves its fix", description },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Font variables sit on <html> so the :root design tokens in globals.css can reference them.
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
