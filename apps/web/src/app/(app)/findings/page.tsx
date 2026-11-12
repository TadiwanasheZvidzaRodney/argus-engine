import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import {
  type FindingSummary,
  findingStatusTone,
  type Page,
  severityTone,
} from "@/lib/finding-types";

export const dynamic = "force-dynamic";

const SEVERITY_FILTERS = ["", "critical", "high", "medium", "low"];
const STATUS_FILTERS = ["", "OPEN", "ACKNOWLEDGED", "SUPPRESSED", "RISK_ACCEPTED", "RESOLVED"];

interface FindingQuery {
  severity?: string;
  status?: string;
  account_id?: string;
  rule_id?: string;
}

async function loadFindings(query: FindingQuery): Promise<Page<FindingSummary>> {
  const params = new URLSearchParams();
  if (query.severity) params.set("severity", query.severity);
  if (query.status) params.set("status", query.status);
  if (query.account_id) params.set("account_id", query.account_id);
  if (query.rule_id) params.set("rule_id", query.rule_id);
  params.set("limit", "100");
  try {
    return await apiFetch<Page<FindingSummary>>(`/api/v1/findings?${params.toString()}`, {
      timeoutMs: 4_000,
    });
  } catch {
    return { items: [], next_cursor: null, has_more: false };
  }
}

function filterHref(key: string, value: string, current: FindingQuery): string {
  const params = new URLSearchParams();
  const next = { ...current, [key]: value || undefined };
  for (const [name, entry] of Object.entries(next)) {
    if (entry) params.set(name, entry);
  }
  const query = params.toString();
  return query ? `/findings?${query}` : "/findings";
}

export default async function FindingsPage({
  searchParams,
}: {
  searchParams: Promise<FindingQuery>;
}) {
  const query = await searchParams;
  const page = await loadFindings(query);
  const critical = page.items.filter(
    (finding) => finding.severity === "critical" && finding.status !== "RESOLVED",
  ).length;
  const open = page.items.filter(
    (finding) => finding.status === "OPEN" || finding.status === "ACKNOWLEDGED",
  ).length;
  const suppressed = page.items.filter((finding) => finding.status === "SUPPRESSED").length;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Security Findings</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Continuous posture checks over the live graph. Findings deduplicate by rule and
            resource, reopen when evidence changes, and hand off directly to approved actions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/security"
            className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-medium text-foreground hover:bg-surface-muted"
          >
            Security dashboard
          </Link>
          <Link
            href="/topology"
            className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground hover:bg-accent/90"
          >
            Open canvas
          </Link>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Visible findings">
          <p className="text-2xl font-semibold tabular-nums">{page.items.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">Current filter.</p>
        </Card>
        <Card title="Critical">
          <p className="text-2xl font-semibold tabular-nums text-danger">{critical}</p>
          <p className="mt-1 text-xs text-muted-foreground">Unresolved critical findings.</p>
        </Card>
        <Card title="Open / acknowledged">
          <p className="text-2xl font-semibold tabular-nums text-warning">{open}</p>
          <p className="mt-1 text-xs text-muted-foreground">Awaiting triage or fix.</p>
        </Card>
        <Card title="Suppressed">
          <p className="text-2xl font-semibold tabular-nums">{suppressed}</p>
          <p className="mt-1 text-xs text-muted-foreground">Time-bounded with an owner.</p>
        </Card>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Severity
          </span>
          {SEVERITY_FILTERS.map((severity) => {
            const active = (query.severity ?? "") === severity;
            return (
              <Link
                key={severity || "all"}
                href={filterHref("severity", severity, query)}
                className={
                  active
                    ? "rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground"
                    : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-surface-muted"
                }
              >
                {severity || "All"}
              </Link>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Status
          </span>
          {STATUS_FILTERS.map((status) => {
            const active = (query.status ?? "") === status;
            return (
              <Link
                key={status || "all"}
                href={filterHref("status", status, query)}
                className={
                  active
                    ? "rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground"
                    : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-surface-muted"
                }
              >
                {status || "All"}
              </Link>
            );
          })}
        </div>
      </div>

      {page.items.length === 0 ? (
        <Card>
          <EmptyState
            title="No findings match this view"
            description="Run a security scan from the dashboard, or adjust the severity and status filters."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {page.items.map((finding) => (
            <Link
              key={finding.id}
              href={`/findings/${finding.id}`}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:bg-surface-muted"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
                <Badge tone={findingStatusTone(finding.status)}>{finding.status}</Badge>
                <span className="text-sm font-medium text-foreground">{finding.title}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {new Date(finding.first_seen).toLocaleString()}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="font-mono">{finding.rule_id}</span>
                <span>·</span>
                <span className="truncate font-mono">{finding.resource_id}</span>
                {finding.account_id && (
                  <>
                    <span>·</span>
                    <span>{finding.account_id}</span>
                  </>
                )}
                {finding.region && (
                  <>
                    <span>·</span>
                    <span>{finding.region}</span>
                  </>
                )}
                {finding.remediation_action && <Badge tone="info">remediation ready</Badge>}
              </div>
            </Link>
          ))}
        </div>
      )}

      {page.has_more && (
        <p className="text-xs text-muted-foreground">
          More findings exist than fit on this page. Narrow the filters to see a focused set.
        </p>
      )}
    </div>
  );
}
