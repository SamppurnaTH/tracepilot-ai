"use client";

import NextLink from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentProps } from "react";

/**
 * The signed-in workspace (/app/*) re-uses the public demo pages. Links written as /app/... stay in the
 * workspace there, and point at the public page (/examples, /run, ...) everywhere else.
 */
export function useAreaPath() {
  const inWorkspace = usePathname()?.startsWith("/app") ?? false;
  return (href: string) => (inWorkspace || !href.startsWith("/app") ? href : href.replace(/^\/app(?=[/?#]|$)/, "") || "/");
}

export default function Link({ href, ...rest }: ComponentProps<typeof NextLink>) {
  const area = useAreaPath();
  return <NextLink href={typeof href === "string" ? area(href) : href} {...rest} />;
}
