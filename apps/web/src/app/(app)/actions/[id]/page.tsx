import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { ActionControls } from "@/components/actions/action-controls";
import { apiFetch } from "@/lib/api";
import { type ActionDetail, type EvidenceItem, riskTone, statusTone } from "@/lib/action-types";

export const dynamic = "force-dynamic";

async function loadAction(id: string): Promise<ActionDetail | null> {
  try {
    return await apiFetch<ActionDetail>(`/api/v1/actions/${id}`, { timeoutMs: 3_000 });
  } catch {
    return null;
  }
}

async function loadEvidence(id: string): Promise<EvidenceItem[]> {
  try {
    return await apiFetch<EvidenceItem[]>(`/api/v1/actions/${id}/evidence`, {
      timeoutMs: 3_000,
    });
  } catch {
    return [];
  }
}

async function loadExplanation(id: string): Promise<string | null> {
  try {
    const result = await apiFetch<{ explanation: string }>(`/api/v1/actions/${id}/explanation`, {
      timeoutMs: 3_000,
    });
    return result.explanation;
  } catch {
    return null;
  }
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-md border border-border bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default async function ActionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [action, evidence, explanation] = await Promise.all([
    loadAction(id),
    loadEvidence(id),
    loadExplanation(id),
  ]);

  if (!action) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <Link href="/actions" className="text-xs text-accent underline underline-offset-4">
            ← Back to actions
          </Link>
          <h1 className="mt-2 text-xl font-semibold tracking-tight">Action not found</h1>
        </header>
        <Card>
          <EmptyState
            title="This action could not be loaded"
            description="It may not exist, may belong to another tenant, or the API may be unavailable."
          />
        </Card>
      </div>
    );
  }

  const plan = action.plan;
  const targets = [
    action.targets.source ? `source: ${action.targets.source}` : null,
    action.targets.target ? `target: ${action.targets.target}` : null,
    ...(action.targets.resources ?? []),
  ].filter((value): value is string => Boolean(value));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link href="/actions" className="text-xs text-accent underline underline-offset-4">
          ← Back to actions
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-mono text-lg font-semibold tracking-tight">{action.id}</h1>
          <Badge tone="neutral">{action.action_type}</Badge>
          <Badge tone={riskTone(action.risk_level)}>{action.risk_level} risk</Badge>
          <Badge tone={statusTone(action.status)}>{action.status}</Badge>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">{action.justification}</p>
        <p className="text-xs text-muted-foreground">
          Requested {new Date(action.created_at).toLocaleString()} · graph version{" "}
          {action.graph_version} · requester{" "}
          <span className="font-mono">{action.requester_id}</span>
        </p>
      </header>

      <ActionControls action={action} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Intent" description="Typed targets and parameters captured at request time.">
          <div className="flex flex-col gap-3">
            <div>
              <h3 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                Targets ({targets.length})
              </h3>
              <ul className="mt-1 flex flex-col gap-1">
                {targets.length === 0 ? (
                  <li className="text-xs text-muted-foreground">No targets recorded.</li>
                ) : (
                  targets.map((target) => (
                    <li key={target} className="break-all font-mono text-xs text-foreground">
                      {target}
                    </li>
                  ))
                )}
              </ul>
            </div>
            <div>
              <h3 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                Parameters
              </h3>
              <div className="mt-1">
                <JsonBlock value={action.parameters} />
              </div>
            </div>
            <div>
              <h3 className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                Constraints
              </h3>
              <div className="mt-1">
                <JsonBlock value={action.constraints} />
              </div>
            </div>
          </div>
        </Card>

        <Card
          title="Plan"
          description="Immutable, deterministic output compiled from the versioned catalog template."
        >
          {!plan ? (
            <p className="text-xs text-muted-foreground">No plan has been compiled yet.</p>
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-foreground">{plan.summary}</p>
              {explanation && (
                <p className="rounded-md border border-info/30 bg-info/10 p-2 text-xs text-info">
                  {explanation}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={riskTone(plan.risk.level)}>{plan.risk.level} risk</Badge>
                <Badge tone="info">blast radius {plan.blast_radius}</Badge>
                <Badge tone={plan.risk.reversible ? "success" : "danger"}>
                  {plan.risk.reversible ? "reversible" : "irreversible"}
                </Badge>
                <Badge tone="neutral">template {plan.template_version}</Badge>
              </div>
              {plan.risk.reasons.length > 0 && (
                <ul className="list-inside list-disc text-xs text-muted-foreground">
                  {plan.risk.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
              <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-[11px] tracking-wider text-muted-foreground uppercase">
                    Plan hash
                  </dt>
                  <dd className="break-all font-mono text-[11px] text-foreground">
                    {plan.plan_hash}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] tracking-wider text-muted-foreground uppercase">
                    Approved hash
                  </dt>
                  <dd className="break-all font-mono text-[11px] text-foreground">
                    {plan.approved_hash ?? "not approved"}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] tracking-wider text-muted-foreground uppercase">
                    Expires
                  </dt>
                  <dd className="text-foreground">{new Date(plan.expires_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-[11px] tracking-wider text-muted-foreground uppercase">
                    Rollback
                  </dt>
                  <dd className="text-foreground">
                    {plan.rollback.strategy} · {plan.rollback.template}
                  </dd>
                </div>
              </dl>
            </div>
          )}
        </Card>
      </div>

      {plan && (
        <Card title={`Planned changes (${plan.changes.length})`}>
          <div className="flex flex-col gap-2">
            {plan.changes.map((change) => (
              <div
                key={`${change.resource}-${change.attribute}`}
                className="rounded-md border border-border bg-background px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{change.operation}</Badge>
                  <span className="font-mono text-xs font-semibold text-foreground">
                    {change.attribute}
                  </span>
                  <span className="break-all font-mono text-[11px] text-muted-foreground">
                    {change.resource}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{change.description}</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {change.before_hash.slice(0, 12)} → {change.after_hash.slice(0, 12)}
                </p>
              </div>
            ))}
            <div>
              <h3 className="mt-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                Required permissions
              </h3>
              <ul className="mt-1 flex flex-wrap gap-1">
                {plan.permissions.map((permission) => (
                  <li
                    key={permission}
                    className="rounded border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                  >
                    {permission}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Approvals (${action.approvals.length})`}>
          {action.approvals.length === 0 ? (
            <p className="text-xs text-muted-foreground">No decisions recorded yet.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {action.approvals.map((approval) => (
                <div
                  key={approval.id}
                  className="rounded-md border border-border bg-background px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={approval.decision === "approved" ? "success" : "danger"}>
                      {approval.decision}
                    </Badge>
                    <span className="text-xs font-medium text-foreground">
                      {approval.approver_email}
                    </span>
                    {approval.mfa_at && <Badge tone="info">MFA</Badge>}
                    <span className="ml-auto text-[11px] text-muted-foreground">
                      {new Date(approval.created_at).toLocaleString()}
                    </span>
                  </div>
                  {approval.comment && (
                    <p className="mt-1 text-xs text-muted-foreground">{approval.comment}</p>
                  )}
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    plan {approval.plan_hash}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title={`Executions (${action.executions.length})`}>
          {action.executions.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Nothing has executed. Approval and execution are separate steps.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {action.executions.map((execution) => (
                <div
                  key={execution.id}
                  className="rounded-md border border-border bg-background px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      tone={
                        execution.status === "SUCCEEDED"
                          ? "success"
                          : execution.status === "FAILED"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {execution.status}
                    </Badge>
                    <Badge tone="neutral">rollback: {execution.rollback_status}</Badge>
                    <span className="ml-auto text-[11px] text-muted-foreground">
                      {new Date(execution.started_at).toLocaleString()}
                    </span>
                  </div>
                  {execution.error && <p className="mt-1 text-xs text-danger">{execution.error}</p>}
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    verification: {execution.verification.status ?? "unknown"} ·{" "}
                    {execution.verification.checked_resources ?? 0} resources
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card
        title={`Evidence (${evidence.length})`}
        description="Immutable artifacts referenced by S3 URI and SHA-256 checksum."
      >
        {evidence.length === 0 ? (
          <p className="text-xs text-muted-foreground">No evidence recorded.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {evidence.map((item) => (
              <div
                key={item.id}
                className="rounded-md border border-border bg-background px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="info">{item.kind}</Badge>
                  <span className="break-all font-mono text-[11px] text-foreground">
                    {item.uri}
                  </span>
                  <span className="ml-auto text-[11px] text-muted-foreground">
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                  sha256 {item.checksum}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
