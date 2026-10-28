"use client";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/ScreenState";
import s from "@/components/app.module.css";
export default function Error({ reset }: { reset: () => void }) { return <AppShell><EmptyState icon="minusCircle" title="Something interrupted this page" text="Please try loading it again. Your saved investigations are still available." href="/runs" action="View my runs" /><div className={s.actions}><button className={s.btn} onClick={reset}>Try again</button></div></AppShell>; }
