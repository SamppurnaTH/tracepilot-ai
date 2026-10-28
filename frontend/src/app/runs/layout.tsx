import type { Metadata } from "next";

export const metadata: Metadata = { title: "My runs · TracePilot AI" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
