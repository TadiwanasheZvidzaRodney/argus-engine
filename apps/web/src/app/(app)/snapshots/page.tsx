import { Badge, Button, Card, EmptyState } from "@argus/ui";

import { apiFetch } from "@/lib/api";

interface SnapshotItem {
  id: string;
  scope: string;
  node_count: number;
  edge_count: number;
  checksum: string;
  status: string;
  created_at: string;
}

export const dynamic = "force-dynamic";

async function loadSnapshots(): Promise<SnapshotItem[]> {
  try {
    return await apiFetch<SnapshotItem[]>("/api/v1/topology/snapshots", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

export default async function SnapshotsPage() {
  const snapshots = await loadSnapshots();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Graph Snapshots & Diffs</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Daily columnar graph backups with SHA-256 manifests and diff computation.
          </p>
        </div>
        <Button size="sm">Create Daily Snapshot</Button>
      </header>

      {snapshots.length === 0 ? (
        <Card>
          <EmptyState
            title="No snapshots recorded"
            description="Snapshots are created daily or on-demand before major infrastructure changes."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {snapshots.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-foreground">{s.id}</span>
                  <Badge tone={s.status === "completed" ? "success" : "warning"}>{s.status}</Badge>
                  <Badge tone="neutral">{s.scope}</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Contains: <strong>{s.node_count}</strong> nodes, <strong>{s.edge_count}</strong>{" "}
                  edges
                </p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  Checksum: {s.checksum}
                </p>
              </div>

              <span className="text-xs text-muted-foreground">
                {new Date(s.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
