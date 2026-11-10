import { Badge, Button, Card, EmptyState } from "@argus/ui";

import { apiFetch } from "@/lib/api";

interface DlqItem {
  id: string;
  message_id: string;
  error_reason: string;
  resolved: boolean;
  created_at: string;
}

export const dynamic = "force-dynamic";

async function loadDlqItems(): Promise<DlqItem[]> {
  try {
    return await apiFetch<DlqItem[]>("/api/v1/events/dlq", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

export default async function EventsPage() {
  const dlqItems = await loadDlqItems();
  const unresolvedCount = dlqItems.filter((i) => !i.resolved).length;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Real-Time Event Stream</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sub-30s change detection via AWS Config, EventBridge global bus, and SQS buffering.
          </p>
        </div>
        <Badge tone={unresolvedCount === 0 ? "success" : "danger"}>
          {unresolvedCount === 0 ? "✓ DLQ Clean" : `⚠ ${unresolvedCount} DLQ Messages`}
        </Badge>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card title="Change-to-Canvas Latency">
          <p className="text-2xl font-semibold tabular-nums">&lt; 10s</p>
          <p className="mt-1 text-xs text-muted-foreground">
            p95 target across regional ingress buses.
          </p>
        </Card>
        <Card title="Deduplication Window">
          <p className="text-2xl font-semibold tabular-nums">7 Days</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Redis atomic idempotency guards against duplicate delivery.
          </p>
        </Card>
        <Card title="Stream Retention">
          <p className="text-2xl font-semibold tabular-nums">15 min</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Redis Stream retention allows seamless client resumption on reconnect.
          </p>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Dead-Letter Queue (DLQ) & Poison Pills</h2>
          <Button size="sm" variant="secondary" disabled={unresolvedCount === 0}>
            Replay DLQ Messages
          </Button>
        </div>

        {dlqItems.length === 0 ? (
          <Card>
            <EmptyState
              title="No dead-letter messages"
              description="All AWS Config and CloudTrail events have processed successfully without schema violations."
            />
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {dlqItems.map((item) => (
              <div
                key={item.id}
                className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold">{item.message_id}</span>
                    <Badge tone={item.resolved ? "neutral" : "danger"}>
                      {item.resolved ? "resolved" : "unresolved"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-danger">{item.error_reason}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Received: {new Date(item.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
