import { Badge, Card } from "@argus/ui";
import Link from "next/link";

import { FindingActions } from "@/components/findings/finding-actions";
import { apiFetch } from "@/lib/api";
import { type FindingDetail, findingStatusTone, severityTone } from "@/lib/finding-types";

export const dynamic = "force-dynamic";

async function loadFinding(id: string): Promise<FindingDetail | null> {
  try {
    return await apiFetch<FindingDetail>(`/api/v1/findings/${encodeURIComponent(id)}`, {
      timeoutMs: 4_000,
    });
  } catch {
    return null;
  }
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default async function FindingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const finding = await loadFinding(id);

  if (!finding) {
    return (
      <div className="flex flex-col gap-6">
        <Link
          href="/findings"
          className="w-fit text-xs font-medium text-accent underline underline-offset-4"
        >
          ← Back to findings
        </Link>
        <Card title="Finding not available">
          <p className="text-sm text-muted-foreground">
            This finding could not be loaded. It may have been removed, or the API may be
            unreachable.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link
          href="/findings"
          className="w-fit text-xs font-medium text-accent underline underline-offset-4"
        >
          ← Back to findings
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
          <Badge tone={findingStatusTone(finding.status)}>{finding.status}</Badge>
          <h1 className="text-xl font-semibold tracking-tight">{finding.title}</h1>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">{finding.description}</p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="font-mono">{finding.rule_id}</span>
          <span>v{finding.rule_version}</span>
          <span>·</span>
          <span className="truncate font-mono">{finding.resource_id}</span>
          {finding.account_id && (
            <>
              <span>·</span>
              <span>{finding.account_id}</span>
            </>
          )}
          {finding.region && (
            <>
              <span>·</span>
              <span>{finding.region}</span>
            </>
          )}
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Evidence">
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                <span>
                  Resource type{" "}
                  <span className="font-mono text-foreground">{finding.resource_type}</span>
                </span>
                <span>
                  Finding key{" "}
                  <span className="font-mono text-foreground">{finding.finding_key}</span>
                </span>
                <span>
                  Evidence hash{" "}
                  <span className="font-mono text-foreground">
                    {finding.evidence_hash.slice(0, 16)}…
                  </span>
                </span>
              </div>
              <pre className="max-h-80 overflow-auto rounded-md border border-border bg-surface-muted p-3 font-mono text-[11px] text-foreground">
                {JSON.stringify(finding.evidence, null, 2)}
              </pre>
            </div>
          </Card>

          <Card title="Timeline" description="Every state transition is recorded for audit.">
            {finding.events.length === 0 ? (
              <p className="text-xs text-muted-foreground">No lifecycle events recorded yet.</p>
            ) : (
              <ol className="flex flex-col gap-3">
                {finding.events.map((event) => (
                  <li key={event.id} className="border-l-2 border-border pl-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-medium text-foreground">{event.event_type}</span>
                      {event.from_status && (
                        <span className="text-muted-foreground">
                          {event.from_status} → {event.to_status ?? "—"}
                        </span>
                      )}
                      <span className="ml-auto text-muted-foreground">
                        {formatTimestamp(event.created_at)}
                      </span>
                    </div>
                    {event.comment && (
                      <p className="mt-1 text-xs text-muted-foreground">{event.comment}</p>
                    )}
                    {event.actor_id && (
                      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                        by {event.actor_id}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card title="Details">
            <dl className="grid gap-2 text-xs">
              <div className="flex justify-between border-b border-border py-1">
                <dt className="text-muted-foreground">First seen</dt>
                <dd className="text-foreground">{formatTimestamp(finding.first_seen)}</dd>
              </div>
              <div className="flex justify-between border-b border-border py-1">
                <dt className="text-muted-foreground">Last seen</dt>
                <dd className="text-foreground">{formatTimestamp(finding.last_seen)}</dd>
              </div>
              <div className="flex justify-between border-b border-border py-1">
                <dt className="text-muted-foreground">Resolved at</dt>
                <dd className="text-foreground">{formatTimestamp(finding.resolved_at)}</dd>
              </div>
              <div className="flex justify-between border-b border-border py-1">
                <dt className="text-muted-foreground">Assignee</dt>
                <dd className="truncate font-mono text-foreground">
                  {finding.assignee_id ?? "Unassigned"}
                </dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-muted-foreground">Risk accepted until</dt>
                <dd className="text-foreground">{formatTimestamp(finding.risk_accepted_until)}</dd>
              </div>
            </dl>
          </Card>

          {finding.suppression && (
            <Card title="Suppression">
              <dl className="grid gap-2 text-xs">
                <div className="flex justify-between border-b border-border py-1">
                  <dt className="text-muted-foreground">Owner</dt>
                  <dd className="truncate font-mono">{finding.suppression.owner_id}</dd>
                </div>
                <div className="flex justify-between border-b border-border py-1">
                  <dt className="text-muted-foreground">Expires</dt>
                  <dd>{formatTimestamp(finding.suppression.expires_at)}</dd>
                </div>
                <div className="py-1">
                  <dt className="text-muted-foreground">Reason</dt>
                  <dd className="mt-1 text-foreground">{finding.suppression.reason}</dd>
                </div>
              </dl>
            </Card>
          )}

          {finding.remediation && (
            <Card title="Remediation">
              <div className="flex flex-col gap-2 text-xs">
                <code className="font-mono text-foreground">{finding.remediation.action_type}</code>
                {finding.remediation.action_id ? (
                  <Link
                    href={`/actions/${finding.remediation.action_id}`}
                    className="w-fit text-accent underline underline-offset-4"
                  >
                    View action {finding.remediation.action_id.slice(0, 12)}…
                  </Link>
                ) : (
                  <p className="text-muted-foreground">
                    No action has been created from this finding yet.
                  </p>
                )}
              </div>
            </Card>
          )}

          <FindingActions finding={finding} />
        </div>
      </div>
    </div>
  );
}
