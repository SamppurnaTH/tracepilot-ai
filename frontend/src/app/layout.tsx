import type { Metadata } from "next";
import { Geist_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const sans = Plus_Jakarta_Sans({ variable: "--font-jakarta", subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const description =
  "A verification-first debugging agent: it turns an incident into a reproducing test, a patch your test suite confirms, and an independent model review, or tells you the fix isn't in the code. Built on Meta Muse Spark.";

export const metadata: Metadata = {
  metadataBase: new URL("https://tracepilot-ai.vercel.app"),
  title: "TracePilot AI: from errors to verified fixes",
  description,
  openGraph: { title: "TracePilot AI: from errors to verified fixes", description, url: "/", siteName: "TracePilot AI", type: "website" },
  twitter: { card: "summary_large_image", title: "TracePilot AI: from errors to verified fixes", description },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Font variables sit on <html> so the :root design tokens in globals.css can reference them.
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
