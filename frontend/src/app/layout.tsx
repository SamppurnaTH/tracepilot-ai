import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const sans = Geist({ variable: "--font-geist", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TracePilot AI: root cause, patch and proof for every incident",
  description:
    "An AI agent that investigates software incidents in a sandbox, patches the code, and proves the fix with your tests and an independent model review. Built on Meta Muse Spark.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Font variables sit on <html> so the :root design tokens in globals.css can reference them.
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
