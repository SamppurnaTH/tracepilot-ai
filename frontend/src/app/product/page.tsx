import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { WorkflowOverview } from "@/components/WorkflowOverview";
import { Icon } from "@/components/icons";
import s from "@/components/app.module.css";
import { cx } from "@/lib/styles";
export const metadata: Metadata = { title: "Product overview · TracePilot AI" };
export default function Product() {
  return <AppShell><div className={s.pageHead}><div><p className={s.eyebrow}>PRODUCT OVERVIEW</p><h1 className={s.pageTitle}>A fix you can verify.</h1><p className={s.pageText}>From the first error to the final hand-off, every conclusion is backed by evidence.</p></div><Link className={cx(s.btn,s.btnPrimary)} href="/app/examples">Explore scenarios <Icon name="arrowRight" size={16} /></Link></div><div className={s.productOverview}><WorkflowOverview standalone /></div></AppShell>;
}
