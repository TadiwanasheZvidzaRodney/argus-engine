import { Badge, Card, EmptyState } from "@argus/ui";

import { apiFetch } from "@/lib/api";

interface AuditItem {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  prev_hash: string | null;
  hash: string;
  created_at: string;
}

interface AuditPageResponse {
  items: AuditItem[];
  has_more: boolean;
  next_cursor: string | null;
}

interface ChainVerification {
  total_records: number;
  chain_valid: boolean;
  message: string;
}

export const dynamic = "force-dynamic";

async function loadAudit(): Promise<AuditItem[]> {
  try {
    const res = await apiFetch<AuditPageResponse>("/api/v1/audit-events?limit=25", {
      timeoutMs: 3_000,
    });
    return res.items;
  } catch {
    return [];
  }
}

async function verifyChain(): Promise<ChainVerification | null> {
  try {
    return await apiFetch<ChainVerification>("/api/v1/audit-events/verify", {
      method: "POST",
      idempotencyKey: `verify-${Date.now()}`,
      timeoutMs: 3_000,
    });
  } catch {
    return null;
  }
}

export default async function AuditPage() {
  const events = await loadAudit();
  const verification = await verifyChain();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Audit Trail</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Append-only, cryptographic hash-chained operational and security log.
          </p>
        </div>
        {verification && (
          <Badge tone={verification.chain_valid ? "success" : "danger"}>
            {verification.chain_valid ? "✓ Hash Chain Verified" : "✗ Chain Discrepancy"}
          </Badge>
        )}
      </header>

      {events.length === 0 ? (
        <Card title="No audit events">
          <EmptyState title="Audit log empty" description="Operational events will appear here." />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {events.map((evt) => (
            <div
              key={evt.id}
              className="flex flex-col gap-1 rounded-lg border border-border bg-surface px-4 py-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-accent">{evt.action}</span>
                  <Badge tone="neutral">{evt.actor_type}</Badge>
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(evt.created_at).toLocaleString()}
                </span>
              </div>

              <div className="mt-1 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                {evt.actor_id && <span>Actor: {evt.actor_id}</span>}
                {evt.resource_type && (
                  <span>
                    Resource: {evt.resource_type} ({evt.resource_id ?? "—"})
                  </span>
                )}
              </div>

              <div className="mt-1 border-t border-border pt-1">
                <p className="truncate font-mono text-[10px] text-muted-foreground">
                  SHA-256: {evt.hash}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
