import type { Metadata } from "next";
import { WorkspaceGate } from "@/components/WorkspaceGate";
export const metadata: Metadata = { title: { default: "TracePilot Workspace", template: "%s · TracePilot Workspace" }, robots: { index: false, follow: false } };
export default function Layout({ children }: { children: React.ReactNode }) { return <WorkspaceGate>{children}</WorkspaceGate>; }
