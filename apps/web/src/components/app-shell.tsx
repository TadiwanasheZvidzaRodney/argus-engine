"use client";

import { Button, ThemeToggle, cn } from "@argus/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import type { Session } from "@/lib/session";

interface SubNavItem {
  href: string;
  label: string;
}

interface NavSection {
  id: string;
  label: string;
  icon: string;
  items: SubNavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    id: "overview",
    label: "Overview & Estate",
    icon: "📊",
    items: [
      { href: "/overview", label: "Overview" },
      { href: "/ops", label: "Operations Wallboard" },
      { href: "/resources", label: "Resources" },
      { href: "/aws-accounts", label: "AWS Accounts" },
    ],
  },
  {
    id: "topology",
    label: "Topology & Canvas",
    icon: "🌐",
    items: [
      { href: "/topology", label: "Topology" },
      { href: "/snapshots", label: "Snapshots" },
      { href: "/sync", label: "Sync Console" },
    ],
  },
  {
    id: "security",
    label: "Security & Posture",
    icon: "🛡️",
    items: [
      { href: "/security", label: "Security" },
      { href: "/findings", label: "Findings" },
    ],
  },
  {
    id: "actions",
    label: "Actions & GitOps",
    icon: "⚡",
    items: [
      { href: "/actions", label: "Actions" },
      { href: "/iac", label: "GitOps / IaC" },
      { href: "/actions/approvals", label: "Approvals" },
      { href: "/actions/guardrails", label: "Guardrails" },
    ],
  },
  {
    id: "cost",
    label: "Cost & FinOps",
    icon: "💰",
    items: [{ href: "/cost", label: "Cost" }],
  },
  {
    id: "governance",
    label: "Governance & Ops",
    icon: "📋",
    items: [
      { href: "/compliance", label: "Compliance & Ops" },
      { href: "/audit", label: "Audit Log" },
      { href: "/events", label: "Event Stream" },
      { href: "/settings", label: "Settings & Alerts" },
      { href: "/settings/members", label: "Team & Access" },
    ],
  },
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

  // All dropdown sections are closed by default
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});

  const toggleSection = (sectionId: string) => {
    setOpenSections((prev) => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }));
  };

  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[240px_1fr]">
      <aside className="flex flex-col border-b border-border bg-surface md:sticky md:top-0 md:h-dvh md:overflow-y-auto md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <Link href="/overview" className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-full bg-accent" />
            <span className="text-sm font-semibold tracking-tight">Argus Engine</span>
          </Link>
          <ThemeToggle />
        </div>

        <nav aria-label="Primary" className="flex flex-1 flex-col gap-2 px-2 pb-4">
          {NAV_SECTIONS.map((section) => {
            const isSectionActive = section.items.some(
              (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
            );
            const isOpen = Boolean(openSections[section.id]);

            return (
              <div key={section.id} className="flex flex-col">
                <button
                  type="button"
                  onClick={() => toggleSection(section.id)}
                  aria-expanded={isOpen}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs font-semibold tracking-wide transition-colors",
                    isSectionActive
                      ? "text-foreground font-bold"
                      : "text-muted-foreground hover:bg-surface-muted/60 hover:text-foreground",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-xs">{section.icon}</span>
                    <span>{section.label}</span>
                  </span>
                  <svg
                    className={cn(
                      "size-3 text-muted-foreground transition-transform duration-200",
                      isOpen && "rotate-90",
                    )}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="m9 18 6-6-6-6" />
                  </svg>
                </button>

                {isOpen && (
                  <div className="mt-0.5 ml-3 flex flex-col border-l border-border/60 pl-2">
                    {section.items.map((item) => {
                      const active =
                        pathname === item.href ||
                        (item.href !== "/actions" && pathname.startsWith(`${item.href}/`)) ||
                        (item.href === "/actions" && pathname === "/actions");

                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex items-center justify-between rounded-md px-2.5 py-1.5 text-xs transition-colors",
                            active
                              ? "bg-surface-muted font-medium text-foreground"
                              : "text-muted-foreground hover:bg-surface-muted/50 hover:text-foreground",
                          )}
                        >
                          <span>{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="mt-auto shrink-0 border-t border-border px-4 py-3">
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
