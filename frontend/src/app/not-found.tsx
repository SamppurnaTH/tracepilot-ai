import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/ScreenState";
export default function NotFound() { return <AppShell><EmptyState icon="search" title="This page took a wrong turn" text="The page may have moved. Head back to the examples to start an investigation." href="/examples" action="Explore scenarios" /></AppShell>; }
