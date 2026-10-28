import type { Metadata } from "next";
export const metadata: Metadata = { title: "Admin Console · TracePilot AI", robots: { index: false, follow: false } };
export default function Layout({ children }: { children: React.ReactNode }) { return children; }
