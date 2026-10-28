import Link from "next/link";
import { Icon, type IconName } from "./icons";
import { cx } from "@/lib/styles";
import s from "./app.module.css";

export function EmptyState({ icon = "search", title, text, href, action }: { icon?: IconName; title: string; text: string; href?: string; action?: string }) {
  return <div className={s.emptyState}><span className={cx(s.chip, s.iconViolet)}><Icon name={icon} size={23} /></span><h2>{title}</h2><p>{text}</p>{href && <Link href={href} className={cx(s.btn, s.btnPrimary)}>{action ?? "Get started"}<Icon name="arrowRight" size={15} /></Link>}</div>;
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return <div className={s.scenarioGrid} role="status" aria-label="Loading"><span className="sr-only">Loading content…</span>{Array.from({ length: count }, (_, i) => <div key={i} className={s.skeletonCard} aria-hidden="true"><div className={s.skeletonIcon} /><div className={s.skeletonLine} /><div className={s.skeletonLine} /><div className={s.skeletonShort} /></div>)}</div>;
}
