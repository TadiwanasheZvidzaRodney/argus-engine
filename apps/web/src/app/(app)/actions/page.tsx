import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import {
  type ActionStatus,
  type ActionSummary,
  type Page,
  riskTone,
  statusTone,
} from "@/lib/action-types";

export const dynamic = "force-dynamic";

const FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "All" },
  { value: "PENDING_APPROVAL", label: "Pending approval" },
  { value: "APPROVED", label: "Approved" },
  { value: "SUCCEEDED", label: "Succeeded" },
  { value: "FAILED", label: "Failed" },
];

async function loadActions(status: string | undefined): Promise<Page<ActionSummary>> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  try {
    return await apiFetch<Page<ActionSummary>>(`/api/v1/actions${query}`, { timeoutMs: 3_000 });
  } catch {
    return { items: [], next_cursor: null, has_more: false };
  }
}

export default async function ActionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const page = await loadActions(status);
  const pending = page.items.filter((item) => item.status === "PENDING_APPROVAL").length;
  const succeeded = page.items.filter((item) => item.status === "SUCCEEDED").length;
  const failed = page.items.filter((item) => item.status === "FAILED").length;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Actions & Safe Mutations</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every change is a typed intent, a deterministic plan, an explicit approval, and a
            verified execution with rollback and audit.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/actions/approvals"
            className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-medium text-foreground hover:bg-surface-muted"
          >
            Approval inbox
          </Link>
          <Link
            href="/actions/guardrails"
            className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-medium text-foreground hover:bg-surface-muted"
          >
            Guardrails
          </Link>
          <Link
            href="/actions/new"
            className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground hover:bg-accent/90"
          >
            Request action
          </Link>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Visible actions">
          <p className="text-2xl font-semibold tabular-nums">{page.items.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">Current filter, newest first.</p>
        </Card>
        <Card title="Pending approval">
          <p className="text-2xl font-semibold tabular-nums text-warning">{pending}</p>
          <p className="mt-1 text-xs text-muted-foreground">Awaiting four-eyes review.</p>
        </Card>
        <Card title="Succeeded">
          <p className="text-2xl font-semibold tabular-nums text-success">{succeeded}</p>
          <p className="mt-1 text-xs text-muted-foreground">Verified post-conditions.</p>
        </Card>
        <Card title="Failed">
          <p className="text-2xl font-semibold tabular-nums text-danger">{failed}</p>
          <p className="mt-1 text-xs text-muted-foreground">Rolled back or awaiting rollback.</p>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((filter) => {
          const active = (status ?? "") === filter.value;
          const href = filter.value
            ? `/actions?status=${encodeURIComponent(filter.value)}`
            : "/actions";
          return (
            <Link
              key={filter.value || "all"}
              href={href}
              className={
                active
                  ? "rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground"
                  : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-surface-muted"
              }
            >
              {filter.label}
            </Link>
          );
        })}
      </div>

      {page.items.length === 0 ? (
        <Card>
          <EmptyState
            title="No actions match this view"
            description="Request a change from the canvas or the action composer; it will appear here with a deterministic plan."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {page.items.map((action) => (
            <Link
              key={action.id}
              href={`/actions/${action.id}`}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:bg-surface-muted"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold text-foreground">{action.id}</span>
                <Badge tone="neutral">{action.action_type}</Badge>
                <Badge tone={riskTone(action.risk_level)}>{action.risk_level} risk</Badge>
                <Badge tone={statusTone(action.status as ActionStatus)}>{action.status}</Badge>
                {action.blast_radius !== null && (
                  <Badge tone="info">blast radius {action.blast_radius}</Badge>
                )}
                <span className="ml-auto text-xs text-muted-foreground">
                  {new Date(action.created_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-foreground">{action.summary ?? action.justification}</p>
              {action.plan_hash && (
                <p className="truncate font-mono text-[10px] text-muted-foreground">
                  plan {action.plan_hash}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}

      {page.has_more && (
        <p className="text-xs text-muted-foreground">
          More actions exist than fit on this page. Use the API cursor to page further.
        </p>
      )}
    </div>
  );
}
