"use client";

import { Badge, Button, ThemeToggle, cn } from "@argus/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import type { Session } from "@/lib/session";

interface NavItem {
  href: string;
  label: string;
  phase?: string;
}

const NAV: NavItem[] = [
  { href: "/overview", label: "Overview" },
  { href: "/resources", label: "Resources" },
  { href: "/aws-accounts", label: "AWS Accounts" },
  { href: "/sync", label: "Sync Console" },
  { href: "/events", label: "Event Stream" },
  { href: "/snapshots", label: "Snapshots" },
  { href: "/settings/members", label: "Team & Access" },
  { href: "/audit", label: "Audit Log" },
  { href: "/topology", label: "Topology" },
  { href: "/security", label: "Security" },
  { href: "/findings", label: "Findings" },
  { href: "/actions", label: "Actions" },
  { href: "/cost", label: "Cost" },
  { href: "/compliance", label: "Compliance & Ops" },
];

export function AppShell({
  session,
  children,
  onSignOut,
}: {
  session: Session;
  children: ReactNode;
  onSignOut: () => Promise<void>;
}) {
  const pathname = usePathname();

  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[240px_1fr]">
      <aside className="flex flex-col border-b border-border bg-surface md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <Link href="/overview" className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-full bg-accent" />
            <span className="text-sm font-semibold tracking-tight">Argus Engine</span>
          </Link>
          <ThemeToggle />
        </div>

        <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 px-2 pb-4">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            if (item.phase) {
              return (
                <span
                  key={item.href}
                  aria-disabled="true"
                  className="flex cursor-not-allowed items-center justify-between rounded-md px-3 py-2 text-sm text-muted-foreground/60"
                >
                  {item.label}
                  <Badge tone="neutral">{item.phase}</Badge>
                </span>
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-surface-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-surface-muted hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border px-4 py-3">
          <label className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
            Tenant
          </label>
          <select
            aria-label="Tenant"
            defaultValue={session.tenantId}
            disabled
            className="mt-1 w-full rounded-md border border-border bg-surface-muted px-2 py-1.5 text-sm disabled:opacity-80"
          >
            <option value={session.tenantId}>{session.tenantName}</option>
          </select>
          <p className="mt-2 truncate text-[11px] text-muted-foreground">{session.email}</p>
          <form action={onSignOut} className="mt-2">
            <Button type="submit" variant="ghost" size="sm" className="w-full justify-start">
              Sign out
            </Button>
          </form>
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 md:px-8">{children}</main>
    </div>
  );
}
