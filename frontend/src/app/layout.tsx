import type { Metadata } from "next";
import { Chakra_Petch, IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const chakra = Chakra_Petch({ variable: "--font-chakra", subsets: ["latin"], weight: ["500", "600", "700"] });
const plex = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin"], weight: ["400", "500", "600"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "TracePilot AI",
  description: "An agent that investigates software failures, tests its hypotheses, and proves its fixes in a sandbox. Built on Meta's Muse Spark models.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Font variables sit on <html> so the :root design tokens in globals.css can reference them.
    <html lang="en" className={`${chakra.variable} ${plex.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  );
}
