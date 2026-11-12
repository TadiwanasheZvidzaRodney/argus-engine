"use client";

import { Badge, Button, Card } from "@argus/ui";
import Link from "next/link";
import React, { useState } from "react";

import { confidenceTone, formatCurrency } from "@/lib/cost-types";
import { severityTone } from "@/lib/finding-types";
import type { TopologyNode } from "@/lib/graph-types";

export interface InspectorDrawerProps {
  node: TopologyNode | null;
  onClose: () => void;
  onSelectNode?: (nodeId: string) => void;
}

type Tab = "attributes" | "security" | "metrics" | "cost";

function MetricChart({
  points,
  unit,
}: {
  points: Array<{ timestamp: number; value: number }>;
  unit: string;
}) {
  if (points.length === 0) return null;
  const values = points.map((point) => point.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const width = 320;
  const height = 72;
  const path = points
    .map((point, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((point.value - min) / span) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="flex flex-col gap-1">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-20 w-full text-info" aria-hidden>
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>
          min {Math.round(min)} {unit === "Percent" ? "%" : unit}
        </span>
        <span>
          max {Math.round(max)} {unit === "Percent" ? "%" : unit}
        </span>
      </div>
    </div>
  );
}

export function InspectorDrawer({ node, onClose }: InspectorDrawerProps) {
  const [tab, setTab] = useState<Tab>("attributes");
  if (!node) return null;

  const security = node.security;
  const telemetry = node.telemetry;
  const cost = node.cost;

  return (
    <aside
      aria-label="Resource Inspector"
      className="absolute top-0 right-0 z-20 flex h-full w-96 flex-col border-l border-border bg-surface shadow-xl"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 truncate">
          <Badge tone="info">{node.type.split("::").pop()}</Badge>
          <span className="truncate text-xs font-semibold text-foreground">
            {node.name || node.id}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close inspector">
          ✕
        </Button>
      </header>

      <div className="flex border-b border-border" role="tablist">
        {(["attributes", "security", "metrics", "cost"] as Tab[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={`flex-1 px-2 py-2 text-xs font-medium capitalize transition-colors ${
              tab === value
                ? "border-b-2 border-accent text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {value}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        {tab === "attributes" && (
          <>
            <Card title="Attributes">
              <dl className="grid gap-2 text-xs">
                <div className="flex justify-between py-1 border-b border-border">
                  <dt className="text-muted-foreground">State</dt>
                  <dd className="font-medium text-foreground">{node.state}</dd>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <dt className="text-muted-foreground">Account ID</dt>
                  <dd className="font-mono">{node.account_id}</dd>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <dt className="text-muted-foreground">Region</dt>
                  <dd className="font-mono">{node.region}</dd>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <dt className="text-muted-foreground">Version</dt>
                  <dd className="font-mono">{node.version}</dd>
                </div>
                {node.parent_id && (
                  <div className="flex justify-between py-1">
                    <dt className="text-muted-foreground">Parent</dt>
                    <dd className="font-mono truncate max-w-[160px]">{node.parent_id}</dd>
                  </div>
                )}
              </dl>
            </Card>

            <Card title="Tags">
              {!node.tags || Object.keys(node.tags).length === 0 ? (
                <p className="text-xs text-muted-foreground">No tags configured.</p>
              ) : (
                <dl className="grid gap-1.5 text-xs">
                  {Object.entries(node.tags).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-border/50 py-1">
                      <dt className="font-medium text-foreground">{k}</dt>
                      <dd className="font-mono text-muted-foreground">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Card>

            <Card title="Properties">
              <pre className="max-h-60 overflow-auto rounded bg-surface-muted p-2 font-mono text-[10px] text-foreground">
                {JSON.stringify(node.properties || {}, null, 2)}
              </pre>
            </Card>
          </>
        )}

        {tab === "security" && (
          <Card title="Security posture">
            {!security || security.open_count === 0 ? (
              <p className="text-xs text-muted-foreground">No open findings for this resource.</p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Badge tone={severityTone(security.max_severity)}>{security.max_severity}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {security.open_count} open finding{security.open_count === 1 ? "" : "s"}
                  </span>
                </div>
                <ul className="flex flex-col gap-1">
                  {security.rule_ids.map((ruleId) => (
                    <li key={ruleId} className="font-mono text-[11px] text-foreground">
                      {ruleId}
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/findings?resource_id=${encodeURIComponent(node.id)}`}
                  className="w-fit text-xs font-medium text-accent underline underline-offset-4"
                >
                  Open findings for this resource
                </Link>
              </div>
            )}
          </Card>
        )}

        {tab === "metrics" && (
          <Card title={telemetry ? telemetry.metric : "Metrics"}>
            {!telemetry ? (
              <p className="text-xs text-muted-foreground">
                Metrics are not enabled. Toggle the Metrics layer in the canvas toolbar.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{telemetry.resolution}s resolution</span>
                  <span className="font-mono text-foreground">{telemetry.unit}</span>
                </div>
                <MetricChart points={telemetry.points} unit={telemetry.unit} />
                {telemetry.anomalies.length > 0 ? (
                  <ul className="flex flex-col gap-1">
                    {telemetry.anomalies.map((anomaly, index) => (
                      <li key={`${anomaly.kind}-${index}`} className="text-[11px] text-warning">
                        {anomaly.message}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[11px] text-muted-foreground">
                    No threshold or statistical anomalies in the current window.
                  </p>
                )}
              </div>
            )}
          </Card>
        )}

        {tab === "cost" && (
          <Card title="Resource Cost & Attribution">
            {!cost ? (
              <p className="text-xs text-muted-foreground">
                Cost attribution layer is not enabled. Toggle the Cost layer in the toolbar or visit
                the FinOps dashboard.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Estimated Monthly Run-Rate</span>
                  <span className="text-sm font-bold font-mono text-foreground">
                    {formatCurrency(cost.monthly_amount, cost.currency)}/mo
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Confidence:</span>
                  <Badge tone={confidenceTone(cost.confidence)}>{cost.confidence}</Badge>
                </div>
                <div className="rounded-md border border-border bg-surface-muted p-2.5">
                  <span className="text-[11px] font-medium text-foreground block mb-1">
                    Estimation Method
                  </span>
                  <p className="text-[11px] text-muted-foreground">{cost.method}</p>
                </div>
                <Link
                  href="/cost"
                  className="w-fit text-xs font-medium text-accent underline underline-offset-4"
                >
                  View full FinOps dashboard & recommendations →
                </Link>
              </div>
            )}
          </Card>
        )}
      </div>

      <footer className="border-t border-border px-4 py-2 text-[10px] text-muted-foreground truncate font-mono">
        ARN: {node.id}
      </footer>
    </aside>
  );
}
