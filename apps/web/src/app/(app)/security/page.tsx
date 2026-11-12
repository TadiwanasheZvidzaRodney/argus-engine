import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { ScanControls } from "@/components/findings/scan-controls";
import { apiFetch } from "@/lib/api";
import {
  type AttackPathResponse,
  type SecuritySummary,
  severityRank,
  severityTone,
} from "@/lib/finding-types";

export const dynamic = "force-dynamic";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

function emptySummary(): SecuritySummary {
  return {
    total: 0,
    open_total: 0,
    by_severity: {},
    open_by_severity: {},
    by_status: {},
    by_account: {},
    by_region: {},
    by_rule: {},
    trend: [],
    top_risks: [],
  };
}

async function loadSummary(): Promise<SecuritySummary> {
  try {
    return await apiFetch<SecuritySummary>("/api/v1/security/summary", { timeoutMs: 4_000 });
  } catch {
    return emptySummary();
  }
}

async function loadAttackPaths(): Promise<AttackPathResponse | null> {
  try {
    return await apiFetch<AttackPathResponse>("/api/v1/security/attack-paths", {
      method: "POST",
      idempotencyKey: `dashboard-${Date.now().toString(36)}`,
      body: { source: "internet", max_depth: 8, limit: 10 },
      timeoutMs: 15_000,
    });
  } catch {
    return null;
  }
}

function Sparkline({ trend }: { trend: SecuritySummary["trend"] }) {
  if (trend.length === 0) return null;
  const max = Math.max(1, ...trend.map((point) => point.opened + point.resolved));
  return (
    <div className="flex h-16 items-end gap-1">
      {trend.map((point) => {
        const opened = Math.round((point.opened / max) * 100);
        const resolved = Math.round((point.resolved / max) * 100);
        return (
          <div
            key={point.date}
            className="group flex h-full flex-1 items-end gap-0.5"
            title={`${point.date}: ${point.opened} opened, ${point.resolved} resolved`}
          >
            <div
              className="w-full rounded-t bg-danger/70"
              style={{ height: `${Math.max(2, opened)}%` }}
            />
            <div
              className="w-full rounded-t bg-success/70"
              style={{ height: `${Math.max(2, resolved)}%` }}
            />
          </div>
        );
      })}
    </div>
  );
}

export default async function SecurityPage() {
  const [summary, attackPaths] = await Promise.all([loadSummary(), loadAttackPaths()]);
  const topRules = Object.entries(summary.by_rule)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Security posture</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Continuous security evaluation over the live graph. Findings deduplicate by rule and
            resource, and every risk path is derived from the same tenant-scoped graph the canvas
            renders.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <ScanControls />
          <div className="flex items-center gap-2">
            <Link
              href="/findings"
              className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-medium text-foreground hover:bg-surface-muted"
            >
              All findings
            </Link>
            <Link
              href="/topology"
              className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground hover:bg-accent/90"
            >
              Open canvas
            </Link>
          </div>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SEVERITIES.map((severity) => (
          <Card key={severity} title={severity.toUpperCase()}>
            <p className="text-2xl font-semibold tabular-nums">
              {summary.open_by_severity[severity] ?? 0}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Open · {summary.by_severity[severity] ?? 0} total
            </p>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card
          title="14-day finding trend"
          description="Opened findings in red, resolved findings in green."
        >
          {summary.trend.length === 0 ? (
            <EmptyState
              title="No trend data yet"
              description="Run a scan to populate finding history."
            />
          ) : (
            <Sparkline trend={summary.trend} />
          )}
        </Card>

        <Card title="Status breakdown">
          {Object.keys(summary.by_status).length === 0 ? (
            <p className="text-xs text-muted-foreground">No findings recorded.</p>
          ) : (
            <dl className="grid gap-2 text-xs">
              {Object.entries(summary.by_status)
                .sort((a, b) => b[1] - a[1])
                .map(([status, count]) => (
                  <div key={status} className="flex justify-between border-b border-border py-1">
                    <dt className="text-muted-foreground">{status}</dt>
                    <dd className="font-medium tabular-nums text-foreground">{count}</dd>
                  </div>
                ))}
            </dl>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Top risks"
          description="Highest severity open findings first."
          actions={
            <Link
              href="/findings"
              className="text-xs font-medium text-accent underline underline-offset-4"
            >
              View all
            </Link>
          }
        >
          {summary.top_risks.length === 0 ? (
            <EmptyState
              title="No open findings"
              description="The current graph passes every enabled security rule."
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {[...summary.top_risks]
                .sort(
                  (a, b) =>
                    severityRank(b.severity) - severityRank(a.severity) ||
                    a.first_seen.localeCompare(b.first_seen),
                )
                .slice(0, 6)
                .map((risk) => (
                  <li key={risk.id}>
                    <Link
                      href={`/findings/${risk.id}`}
                      className="flex flex-col gap-1 rounded-md border border-border px-3 py-2 hover:bg-surface-muted"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={severityTone(risk.severity)}>{risk.severity}</Badge>
                        <span className="text-xs font-medium text-foreground">{risk.title}</span>
                      </div>
                      <span className="truncate font-mono text-[10px] text-muted-foreground">
                        {risk.rule_id} · {risk.resource_id}
                      </span>
                    </Link>
                  </li>
                ))}
            </ul>
          )}
        </Card>

        <Card
          title="Internet attack paths"
          description="Ranked paths from an internet-exposed entry point to sensitive data."
        >
          {!attackPaths || attackPaths.paths.length === 0 ? (
            <EmptyState
              title="No reachable attack paths"
              description="No internet entry point currently reaches a sensitive data store."
            />
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span>{attackPaths.count} paths</span>
                <span>·</span>
                <span>{attackPaths.evaluated_nodes} nodes evaluated</span>
                {attackPaths.cached && <Badge tone="neutral">cached</Badge>}
                {attackPaths.truncated && <Badge tone="warning">truncated</Badge>}
              </div>
              <ul className="flex flex-col gap-2">
                {attackPaths.paths.slice(0, 5).map((path) => (
                  <li
                    key={path.hops.map((hop) => hop.node_id).join(">")}
                    className="flex flex-col gap-1 rounded-md border border-border px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={severityTone(path.severity)}>{path.severity}</Badge>
                      <span className="text-[11px] text-muted-foreground">score {path.score}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground">
                        {path.hops.length} hops
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                      {path.hops.map((hop, index) => (
                        <span key={`${hop.node_id}-${index}`} className="flex items-center gap-1">
                          <span className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-foreground">
                            {hop.type.split("::").pop()}:{hop.name}
                          </span>
                          {index < path.hops.length - 1 && <span>→</span>}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-muted-foreground">
                Generated {new Date(attackPaths.generated_at).toLocaleString()} from the live graph.
              </p>
            </div>
          )}
        </Card>
      </div>

      <Card title="Most frequent rules">
        {topRules.length === 0 ? (
          <p className="text-xs text-muted-foreground">No rule hits recorded.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-xs">
            {topRules.map(([ruleId, count]) => (
              <li key={ruleId} className="flex items-center justify-between gap-2">
                <Link
                  href={`/findings?rule_id=${encodeURIComponent(ruleId)}`}
                  className="font-mono text-accent underline underline-offset-4"
                >
                  {ruleId}
                </Link>
                <span className="tabular-nums text-muted-foreground">{count}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
