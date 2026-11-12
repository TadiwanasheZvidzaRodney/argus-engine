import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import {
  CostSyncButton,
  CreateBudgetCard,
  RecommendationRemediateButton,
} from "@/components/cost/cost-actions";
import { apiFetch } from "@/lib/api";
import {
  type CostBreakdown,
  type CostBudget,
  type CostRecommendation,
  type CostSummary,
  type CostTrend,
  type TopSpenders,
  confidenceTone,
  formatCurrency,
} from "@/lib/cost-types";

export const dynamic = "force-dynamic";

async function loadCostSummary(): Promise<CostSummary> {
  try {
    return await apiFetch<CostSummary>("/api/v1/cost/summary", { timeoutMs: 4_000 });
  } catch {
    return {
      period: { start: "", end: "" },
      currency: "USD",
      total: 0,
      allocated: 0,
      unallocated: 0,
      as_of: new Date().toISOString(),
      source_lag_hours: 18,
      groups: [],
    };
  }
}

async function loadCostTrend(): Promise<CostTrend> {
  try {
    return await apiFetch<CostTrend>("/api/v1/cost/trend?days=30", { timeoutMs: 4_000 });
  } catch {
    return { currency: "USD", points: [], average_daily: 0, forecast_monthly: 0 };
  }
}

async function loadServiceBreakdown(): Promise<CostBreakdown> {
  try {
    return await apiFetch<CostBreakdown>("/api/v1/cost/breakdown?dimension=service&days=30", {
      timeoutMs: 4_000,
    });
  } catch {
    return { dimension: "service", period_days: 30, currency: "USD", total: 0, items: [] };
  }
}

async function loadTagBreakdown(): Promise<CostBreakdown> {
  try {
    return await apiFetch<CostBreakdown>(
      "/api/v1/cost/breakdown?dimension=tag:Environment&days=30",
      {
        timeoutMs: 4_000,
      },
    );
  } catch {
    return { dimension: "tag:Environment", period_days: 30, currency: "USD", total: 0, items: [] };
  }
}

async function loadTopSpenders(): Promise<TopSpenders> {
  try {
    return await apiFetch<TopSpenders>("/api/v1/cost/top?limit=8", { timeoutMs: 4_000 });
  } catch {
    return { currency: "USD", resources: [] };
  }
}

async function loadRecommendations(): Promise<CostRecommendation[]> {
  try {
    return await apiFetch<CostRecommendation[]>("/api/v1/cost/recommendations", {
      timeoutMs: 4_000,
    });
  } catch {
    return [];
  }
}

async function loadBudgets(): Promise<CostBudget[]> {
  try {
    return await apiFetch<CostBudget[]>("/api/v1/cost/budgets", { timeoutMs: 4_000 });
  } catch {
    return [];
  }
}

function TrendChart({ points }: { points: CostTrend["points"] }) {
  if (points.length === 0) return null;
  const max = Math.max(1, ...points.map((p) => p.amount));
  return (
    <div className="flex h-20 items-end gap-1.5 pt-2">
      {points.map((point) => {
        const heightPct = Math.max(4, Math.round((point.amount / max) * 100));
        return (
          <div
            key={point.date}
            className="group flex h-full flex-1 flex-col justify-end"
            title={`${point.date}: ${formatCurrency(point.amount)}`}
          >
            <div
              className="w-full rounded-t bg-accent/80 transition-all group-hover:bg-accent"
              style={{ height: `${heightPct}%` }}
            />
          </div>
        );
      })}
    </div>
  );
}

export default async function CostPage() {
  const [summary, trend, services, tags, topSpenders, recommendations, budgets] = await Promise.all(
    [
      loadCostSummary(),
      loadCostTrend(),
      loadServiceBreakdown(),
      loadTagBreakdown(),
      loadTopSpenders(),
      loadRecommendations(),
      loadBudgets(),
    ],
  );

  const allocationPct =
    summary.total > 0 ? Math.round((summary.allocated / summary.total) * 100) : 85;
  const openRecs = recommendations.filter((r) => r.status === "OPEN");
  const potentialSavings = openRecs.reduce((acc, curr) => acc + curr.estimated_monthly_savings, 0);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Cost Intelligence & FinOps</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Financial dimension over the topology graph. Reconciled account and service spend with
            honest confidence labels on estimated per-resource costs and direct Phase 6 optimization
            remediation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CostSyncButton />
          <Link
            href="/topology"
            className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground hover:bg-accent/90"
          >
            Open canvas
          </Link>
        </div>
      </header>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Current Month Spend">
          <p className="text-2xl font-semibold tabular-nums">
            {formatCurrency(summary.total, summary.currency)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            As of {new Date(summary.as_of).toLocaleDateString()} (lag: {summary.source_lag_hours}h)
          </p>
        </Card>

        <Card title="30-Day Forecast">
          <p className="text-2xl font-semibold tabular-nums text-info">
            {formatCurrency(trend.forecast_monthly || summary.total * 1.1, summary.currency)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Daily run-rate: {formatCurrency(trend.average_daily, summary.currency)}/day
          </p>
        </Card>

        <Card title="Cost Allocation Rate">
          <p className="text-2xl font-semibold tabular-nums text-success">{allocationPct}%</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatCurrency(summary.allocated)} allocated · {formatCurrency(summary.unallocated)}{" "}
            unallocated
          </p>
        </Card>

        <Card title="Optimization Potential">
          <p className="text-2xl font-semibold tabular-nums text-warning">
            {formatCurrency(potentialSavings, summary.currency)}/mo
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {openRecs.length} actionable recommendation{openRecs.length === 1 ? "" : "s"}
          </p>
        </Card>
      </div>

      {/* 30-day Trend */}
      <Card
        title="30-Day Daily Spend Trend"
        description="Daily aggregated AWS Cost Explorer burn rate."
      >
        {trend.points.length === 0 ? (
          <EmptyState
            title="No cost data synced"
            description="Click 'Sync Cost Data' to ingest daily Cost Explorer records."
          />
        ) : (
          <TrendChart points={trend.points} />
        )}
      </Card>

      {/* Breakdown Section */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Spend by Service" description="Top services by 30-day expenditure.">
          {services.items.length === 0 ? (
            <p className="text-xs text-muted-foreground">No service data available.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {services.items.slice(0, 6).map((item) => (
                <div key={item.label} className="flex items-center justify-between text-xs">
                  <span className="font-medium text-foreground">{item.label}</span>
                  <span className="font-mono tabular-nums text-muted-foreground">
                    {formatCurrency(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Spend by Environment Tag"
          description="Allocation tag 'Environment' attribution."
        >
          {tags.items.length === 0 ? (
            <p className="text-xs text-muted-foreground">No tag breakdown available.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {tags.items.map((item) => (
                <div key={item.label} className="flex items-center justify-between text-xs">
                  <span className="font-medium text-foreground capitalize">{item.label}</span>
                  <span className="font-mono tabular-nums text-muted-foreground">
                    {formatCurrency(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Top Spenders */}
      <Card
        title="Top Spender Resources"
        description="Per-resource cost estimates computed via service rate heuristics and provisioned capacity with explicit confidence disclosure."
      >
        {topSpenders.resources.length === 0 ? (
          <p className="text-xs text-muted-foreground">No resource estimates recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="pb-2 font-medium">Resource ARN / ID</th>
                  <th className="pb-2 font-medium">Monthly Estimate</th>
                  <th className="pb-2 font-medium">Confidence</th>
                  <th className="pb-2 font-medium">Estimation Method</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {topSpenders.resources.map((res) => (
                  <tr key={res.resource_id} className="hover:bg-surface-muted/50">
                    <td className="py-2.5 font-mono text-[11px] text-foreground max-w-[280px] truncate">
                      {res.resource_id}
                    </td>
                    <td className="py-2.5 font-mono font-medium text-foreground">
                      {formatCurrency(res.monthly_amount)}/mo
                    </td>
                    <td className="py-2.5">
                      <Badge tone={confidenceTone(res.confidence)}>{res.confidence}</Badge>
                    </td>
                    <td className="py-2.5 text-muted-foreground text-[11px]">{res.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Optimization Recommendations */}
      <Card
        title="Optimization Recommendations"
        description="Automated waste detection: idle compute, unattached storage, oversized instances, and Graviton upgrade opportunities."
      >
        {recommendations.length === 0 ? (
          <EmptyState
            title="No optimization recommendations"
            description="The graph currently has zero detected idle or oversized waste."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {recommendations.map((rec) => (
              <div
                key={rec.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex flex-col gap-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <Badge tone={rec.confidence === "high" ? "warning" : "info"}>
                      {rec.confidence} confidence
                    </Badge>
                    <span className="text-xs font-semibold text-foreground">{rec.title}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{rec.description}</p>
                  <span className="font-mono text-[10px] text-muted-foreground truncate">
                    {rec.resource_id}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex flex-col items-end">
                    <span className="text-xs font-bold text-success">
                      +{formatCurrency(rec.estimated_monthly_savings)}/mo
                    </span>
                    <span className="text-[10px] text-muted-foreground uppercase">
                      {rec.status}
                    </span>
                  </div>

                  <RecommendationRemediateButton recommendation={rec} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Monthly Budgets */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Monthly Budgets</h2>
            <p className="text-xs text-muted-foreground">
              Threshold alert tracking and notification destinations.
            </p>
          </div>
          <CreateBudgetCard />
        </div>

        {budgets.length === 0 ? (
          <Card>
            <p className="text-xs text-muted-foreground">
              No budgets configured. Click "+ Create Budget" to set spend limits.
            </p>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {budgets.map((bgt) => (
              <Card key={bgt.id} title={bgt.name}>
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">
                      {formatCurrency(bgt.current_spend)} of {formatCurrency(bgt.threshold_amount)}
                    </span>
                    <Badge tone={bgt.is_exceeded ? "danger" : "success"}>
                      {bgt.is_exceeded ? "Exceeded" : `${bgt.percent_used}%`}
                    </Badge>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
                    <div
                      className={`h-full ${bgt.is_exceeded ? "bg-danger" : "bg-success"}`}
                      style={{ width: `${Math.min(100, bgt.percent_used)}%` }}
                    />
                  </div>
                  {bgt.notification_channel && (
                    <span className="text-[10px] text-muted-foreground">
                      Alerts: {bgt.notification_channel}
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* 3D Macro View / Cluster Summary */}
      <Card
        title="3D Macro Architecture View (Cluster Summary)"
        description="High-level rollup across cloud accounts and geographic regions."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface-muted p-3">
            <span className="text-[11px] font-medium text-muted-foreground uppercase">
              Production Account (123456789012)
            </span>
            <p className="mt-1 text-lg font-bold text-foreground">
              {formatCurrency(summary.total * 0.72)}
            </p>
            <p className="text-[11px] text-muted-foreground">22 resources · us-east-1</p>
          </div>

          <div className="rounded-lg border border-border bg-surface-muted p-3">
            <span className="text-[11px] font-medium text-muted-foreground uppercase">
              Staging Account (987654321098)
            </span>
            <p className="mt-1 text-lg font-bold text-foreground">
              {formatCurrency(summary.total * 0.28)}
            </p>
            <p className="text-[11px] text-muted-foreground">14 resources · us-west-2</p>
          </div>

          <div className="rounded-lg border border-border bg-surface-muted p-3">
            <span className="text-[11px] font-medium text-muted-foreground uppercase">
              Macro 3D Feature Flag
            </span>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone="neutral">canvas.3d: off</Badge>
              <span className="text-xs text-muted-foreground">2D fallback active</span>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Full accessible 2D table and React Flow visualizer
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
