import { Badge, Button, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

interface SyncShard {
  id: string;
  service: string;
  region: string;
  status: string;
  items_discovered: number;
  items_upserted: number;
}

interface SyncJobItem {
  id: string;
  account_id: string;
  type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  resource_count: number;
  shards: SyncShard[];
}

interface TopologySummary {
  tenant_id: string;
  nodes: number;
  edges: number;
}

interface AccountItem {
  id: string;
  account_id: string;
  alias: string | null;
  status: string;
}

export const dynamic = "force-dynamic";

async function loadData() {
  const [jobs, summary, accounts] = await Promise.all([
    apiFetch<SyncJobItem[]>("/api/v1/sync-jobs", { timeoutMs: 3_000 }).catch(() => []),
    apiFetch<TopologySummary>("/api/v1/topology/summary", { timeoutMs: 3_000 }).catch(() => null),
    apiFetch<AccountItem[]>("/api/v1/aws-accounts", { timeoutMs: 3_000 }).catch(() => []),
  ]);
  return { jobs, summary, accounts };
}

export default async function SyncConsolePage() {
  const { jobs, summary, accounts } = await loadData();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Discovery & Sync Console</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Inventory ingestion pipeline hydrating Neo4j from AWS Resource Explorer and direct APIs.
          </p>
        </div>
      </header>

      {/* Graph Volume Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card title="Graph Nodes (Neo4j)">
          <p className="text-2xl font-semibold tabular-nums">{summary?.nodes ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">Active resources across all regions.</p>
        </Card>
        <Card title="Graph Relationships">
          <p className="text-2xl font-semibold tabular-nums">{summary?.edges ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Resolved topological edges (CONTAINS, ROUTES_TO, ATTACHED_TO, etc.)
          </p>
        </Card>
        <Card title="Connected Accounts">
          <p className="text-2xl font-semibold tabular-nums">{accounts.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">Validated AWS accounts in registry.</p>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Sync Jobs Table */}
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold">Sync History ({jobs.length})</h2>
          {jobs.length === 0 ? (
            <Card>
              <EmptyState
                title="No sync jobs executed"
                description="Trigger your first discovery backfill to populate the graph."
              />
            </Card>
          ) : (
            <div className="flex flex-col gap-2">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="flex flex-col gap-2 rounded-lg border border-border bg-surface px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-foreground">
                        {job.account_id}
                      </span>
                      <Badge tone={job.status === "succeeded" ? "success" : "warning"}>
                        {job.status}
                      </Badge>
                      <Badge tone="neutral">{job.type}</Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {job.completed_at
                        ? new Date(job.completed_at).toLocaleString()
                        : "in progress"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Discovered: <strong>{job.resource_count}</strong> resources across{" "}
                      <strong>{job.shards.length}</strong> shards
                    </span>
                    <Link
                      href={`/aws-accounts`}
                      className="text-xs text-accent underline underline-offset-4"
                    >
                      View account
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Trigger Backfill Card */}
        <Card
          title="Trigger Discovery Backfill"
          description="Fan-out parallel sync workers across all enabled regions."
        >
          {accounts.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No AWS accounts connected.{" "}
              <Link
                href="/aws-accounts/onboard"
                className="text-accent underline underline-offset-4"
              >
                Onboard an account
              </Link>{" "}
              first.
            </p>
          ) : (
            <form className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Target AWS Account
                <select
                  defaultValue={accounts[0]?.account_id}
                  className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
                >
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.account_id}>
                      {acc.account_id} {acc.alias ? `(${acc.alias})` : ""}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Sync Type
                <select
                  defaultValue="backfill"
                  className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
                >
                  <option value="backfill">Full Backfill (Re-index all)</option>
                  <option value="reconciliation">Reconciliation (Diff & Tombstone)</option>
                </select>
              </label>

              <Button type="button" size="sm" className="mt-2">
                Start Backfill Job
              </Button>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
