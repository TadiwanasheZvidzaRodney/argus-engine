import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { type ActionSummary, riskTone } from "@/lib/action-types";

export const dynamic = "force-dynamic";

async function loadInbox(): Promise<ActionSummary[]> {
  try {
    return await apiFetch<ActionSummary[]>("/api/v1/actions/inbox", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

export default async function ApprovalsPage() {
  const inbox = await loadInbox();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link href="/actions" className="text-xs text-accent underline underline-offset-4">
          ← Back to actions
        </Link>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Approval inbox</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Plans awaiting a decision from someone other than the requester. Medium risk and above
            require step-up MFA; high and critical risk require two distinct approvers.
          </p>
        </div>
      </header>

      {inbox.length === 0 ? (
        <Card>
          <EmptyState
            title="Nothing awaiting approval"
            description="New action requests from other members of your tenant will appear here."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {inbox.map((action) => (
            <Link
              key={action.id}
              href={`/actions/${action.id}`}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:bg-surface-muted"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold text-foreground">{action.id}</span>
                <Badge tone="neutral">{action.action_type}</Badge>
                <Badge tone={riskTone(action.risk_level)}>{action.risk_level} risk</Badge>
                {action.blast_radius !== null && (
                  <Badge tone="info">blast radius {action.blast_radius}</Badge>
                )}
                <span className="ml-auto text-xs text-muted-foreground">
                  {new Date(action.created_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-foreground">{action.summary ?? action.justification}</p>
              <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                <span>
                  requester <span className="font-mono">{action.requester_id}</span>
                </span>
                {action.expires_at && (
                  <span>expires {new Date(action.expires_at).toLocaleString()}</span>
                )}
                {action.plan_hash && <span className="font-mono">plan {action.plan_hash}</span>}
              </div>
            </Link>
          ))}
        </div>
      )}

      <Card title="Approval policy">
        <div className="grid gap-3 text-xs text-muted-foreground sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="font-medium text-foreground">Low</p>
            <p>1 approval · self-approval allowed · no MFA · 30 min window.</p>
          </div>
          <div>
            <p className="font-medium text-foreground">Medium</p>
            <p>1 non-requester approval · MFA · 60 min window.</p>
          </div>
          <div>
            <p className="font-medium text-foreground">High</p>
            <p>2 non-requester approvals · MFA · 240 min window.</p>
          </div>
          <div>
            <p className="font-medium text-foreground">Critical</p>
            <p>2 non-requesters · break-glass incident · MFA · 60 min window.</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
