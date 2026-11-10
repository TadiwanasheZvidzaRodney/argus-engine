import { Badge, Button, Card, EmptyState } from "@argus/ui";
import type { ServiceMeta } from "@argus/contracts";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

interface TopologySummary {
  tenant_id: string;
  nodes: number;
  edges: number;
}

interface AccountItem {
  id: string;
  account_id: string;
}

export const dynamic = "force-dynamic";

async function loadData() {
  const [meta, summary, accounts] = await Promise.all([
    apiFetch<ServiceMeta>("/api/v1/meta", { timeoutMs: 2_000 }).catch(() => null),
    apiFetch<TopologySummary>("/api/v1/topology/summary", { timeoutMs: 2_000 }).catch(() => null),
    apiFetch<AccountItem[]>("/api/v1/aws-accounts", { timeoutMs: 2_000 }).catch(() => []),
  ]);
  return { meta, summary, accounts };
}

export default async function OverviewPage() {
  const { meta, summary, accounts } = await loadData();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Real-time multi-tenant AWS topology graph and execution engine.
          </p>
        </div>
        <Badge tone={meta ? "success" : "warning"}>
          {meta ? `api ${meta.version}${meta.env ? ` · ${meta.env}` : ""}` : "api unreachable"}
        </Badge>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card title="Connected accounts">
          <p className="text-2xl font-semibold tabular-nums">{accounts.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {accounts.length > 0 ? "Accounts in registry" : "No accounts connected yet."}
          </p>
        </Card>
        <Card title="Graph Resources">
          <p className="text-2xl font-semibold tabular-nums">{summary?.nodes ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">Ingested into Neo4j graph.</p>
        </Card>
        <Card title="Relationships">
          <p className="text-2xl font-semibold tabular-nums">{summary?.edges ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">Topological edges resolved.</p>
        </Card>
        <Card title="Open findings">
          <p className="text-2xl font-semibold tabular-nums">—</p>
          <p className="mt-1 text-xs text-muted-foreground">Security engine lands in Phase 7.</p>
        </Card>
      </div>

      {accounts.length === 0 ? (
        <Card title="Get started" description="Connect your AWS estate.">
          <EmptyState
            title="No AWS account connected yet"
            description="Run our CloudFormation template in your management or workload account to discover your topology in Neo4j."
            action={
              <Link href="/aws-accounts/onboard" className="mt-2">
                <Button size="sm">Connect AWS Account</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <Card title="Active Topology" description="Summary of current tenant graph state.">
          <div className="flex flex-col gap-2">
            <p className="text-sm text-foreground">
              Your topology graph contains <strong>{summary?.nodes ?? 0} resources</strong> and{" "}
              <strong>{summary?.edges ?? 0} relationships</strong>.
            </p>
            <div className="flex items-center gap-3 pt-2">
              <Link href="/sync">
                <Button size="sm" variant="secondary">
                  View Sync Console →
                </Button>
              </Link>
              <Link href="/aws-accounts">
                <Button size="sm" variant="ghost">
                  Manage Accounts
                </Button>
              </Link>
            </div>
          </div>
        </Card>
      )}

      <Card title="Platform status">
        <dl className="grid gap-3 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">API service</dt>
            <dd className="mt-0.5 font-mono">{meta?.service ?? "not reachable"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Commit</dt>
            <dd className="mt-0.5 font-mono">{meta?.commit ?? "unknown"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Capabilities</dt>
            <dd className="mt-0.5 font-mono">{meta?.capabilities.join(", ") ?? "—"}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
