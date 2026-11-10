import { Badge, Card, EmptyState } from "@argus/ui";
import type { ServiceMeta } from "@argus/contracts";

import { apiFetch } from "@/lib/api";

async function loadMeta(): Promise<ServiceMeta | null> {
  try {
    return await apiFetch<ServiceMeta>("/api/v1/meta", { timeoutMs: 2_000 });
  } catch {
    return null;
  }
}

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const meta = await loadMeta();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            The execution spine is live; AWS discovery starts in Phase 2.
          </p>
        </div>
        <Badge tone={meta ? "success" : "warning"}>
          {meta ? `api ${meta.version}${meta.env ? ` · ${meta.env}` : ""}` : "api unreachable"}
        </Badge>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card title="Connected accounts">
          <p className="text-2xl font-semibold tabular-nums">0</p>
          <p className="mt-1 text-xs text-muted-foreground">Onboarding lands in Phase 1.</p>
        </Card>
        <Card title="Resources">
          <p className="text-2xl font-semibold tabular-nums">—</p>
          <p className="mt-1 text-xs text-muted-foreground">Discovery lands in Phase 2.</p>
        </Card>
        <Card title="Open findings">
          <p className="text-2xl font-semibold tabular-nums">—</p>
          <p className="mt-1 text-xs text-muted-foreground">Security rules land in Phase 7.</p>
        </Card>
        <Card title="Graph freshness">
          <p className="text-2xl font-semibold tabular-nums">n/a</p>
          <p className="mt-1 text-xs text-muted-foreground">Real-time sync lands in Phase 3.</p>
        </Card>
      </div>

      <Card title="Get started" description="What this build can already do.">
        <EmptyState
          title="No AWS account connected yet"
          description="Phase 0 proves the platform spine: contracts, idempotent writes, structured logs, traces, migrations, and deployment. Connect an account in Phase 1 to see your estate here."
        />
      </Card>

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
