"use client";

import { Button, Card } from "@argus/ui";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import type { ActionDetail } from "@/lib/action-types";

function key(action: string): string {
  return `${action}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    const details = (err.problem.errors ?? []).map((field) => field.detail);
    return details.length > 0 ? `${err.message} (${details.join("; ")})` : err.message;
  }
  return err instanceof Error ? err.message : "Request failed.";
}

export function ActionControls({ action }: { action: ActionDetail }) {
  const router = useRouter();
  const [comment, setComment] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const needsMfa = action.risk_level !== "low";
  const canApprove = action.status === "PENDING_APPROVAL";
  const canExecute = action.status === "APPROVED";
  const canRollback =
    action.status === "SUCCEEDED" ||
    action.status === "FAILED" ||
    action.status === "ROLLBACK_FAILED";
  const canCancel = !["EXECUTING", "VERIFYING", "SUCCEEDED"].includes(action.status);
  const canReplan = !["EXECUTING", "VERIFYING", "SUCCEEDED", "CANCELLED"].includes(action.status);

  async function run(label: string, path: string, body?: Record<string, unknown>) {
    setBusy(label);
    setError(null);
    try {
      await apiFetch(path, {
        method: "POST",
        body,
        idempotencyKey: key(label.toLowerCase()),
      });
      setComment("");
      setMfaCode("");
      router.refresh();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card
      title="Decision & execution"
      description="Approvals bind to the immutable plan hash. Re-planning invalidates them."
    >
      <div className="flex flex-col gap-4">
        {(canApprove || canRollback || canCancel || canReplan) && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Review comment
              <textarea
                rows={2}
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="Reason for approval or rejection"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            {needsMfa && canApprove && (
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Step-up MFA code
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, ""))}
                  placeholder="123456"
                  className="h-10 rounded-md border border-border bg-background px-3 font-mono text-sm text-foreground"
                />
              </label>
            )}
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-md border border-danger/30 bg-danger/10 p-3">
            <p className="text-xs font-medium text-danger">{error}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {canApprove && (
            <>
              <Button
                size="sm"
                loading={busy === "approve"}
                onClick={() =>
                  run("approve", `/api/v1/actions/${action.id}/approve`, {
                    comment: comment || null,
                    mfa_code: needsMfa ? mfaCode : null,
                  })
                }
              >
                Approve plan
              </Button>
              <Button
                size="sm"
                variant="danger"
                loading={busy === "reject"}
                onClick={() =>
                  run("reject", `/api/v1/actions/${action.id}/reject`, {
                    comment: comment || "Rejected during review.",
                  })
                }
              >
                Reject
              </Button>
            </>
          )}

          {canExecute && (
            <Button
              size="sm"
              loading={busy === "execute"}
              onClick={() => run("execute", `/api/v1/actions/${action.id}/execute`)}
            >
              Execute approved plan
            </Button>
          )}

          {canReplan && (
            <Button
              size="sm"
              variant="secondary"
              loading={busy === "replan"}
              onClick={() => run("replan", `/api/v1/actions/${action.id}/replan`)}
            >
              Re-plan
            </Button>
          )}

          {canCancel && (
            <Button
              size="sm"
              variant="secondary"
              loading={busy === "cancel"}
              onClick={() => run("cancel", `/api/v1/actions/${action.id}/cancel`)}
            >
              Cancel
            </Button>
          )}

          {canRollback && (
            <Button
              size="sm"
              variant="danger"
              loading={busy === "rollback"}
              onClick={() => run("rollback", `/api/v1/actions/${action.id}/rollback`)}
            >
              Roll back
            </Button>
          )}
        </div>

        <p className="text-[11px] text-muted-foreground">
          Approving records an immutable evidence object and an audit-chain entry. Execution is
          locked per resource and verified after apply.
        </p>
      </div>
    </Card>
  );
}
