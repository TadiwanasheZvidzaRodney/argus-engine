"use client";

import { Button, Card } from "@argus/ui";
import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";
import type { FindingDetail } from "@/lib/finding-types";

function newKey(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `fnd-${cryptoApi.randomUUID()}`;
  return `fnd-${Date.now().toString(36)}`;
}

export function FindingActions({ finding }: { finding: FindingDetail }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("Compensating control documented in the risk register.");
  const [actionId, setActionId] = useState(finding.remediation_action_id);

  async function transition(status: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch<FindingDetail>(`/api/v1/findings/${finding.id}`, {
        method: "PATCH",
        idempotencyKey: newKey(),
        body: { status, comment: comment || undefined, ...extra },
      });
      setComment("");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The finding could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  async function remediate() {
    setBusy(true);
    setError(null);
    try {
      const result = await apiFetch<{ action: { id: string } }>(
        `/api/v1/findings/${finding.id}/remediation`,
        {
          method: "POST",
          idempotencyKey: newKey(),
          body: { constraints: { environment: "staging" } },
        },
      );
      setActionId(result.action.id);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The remediation action could not be created.",
      );
    } finally {
      setBusy(false);
    }
  }

  const suppressed = finding.status === "SUPPRESSED";
  const terminal = finding.status === "RESOLVED";

  return (
    <Card title="Triage & remediation">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || finding.status === "ACKNOWLEDGED"}
            onClick={() => transition("ACKNOWLEDGED")}
          >
            Acknowledge
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => transition("RESOLVED")}
          >
            Resolve
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || terminal}
            onClick={() => transition("OPEN")}
          >
            Reopen
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() =>
              transition("RISK_ACCEPTED", {
                risk_accepted_until: new Date(Date.now() + 30 * 86_400_000).toISOString(),
                comment: comment || "Risk accepted for 30 days.",
              })
            }
          >
            Accept risk (30d)
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-label="Suppression reason"
            className="h-9 rounded-md border border-border bg-background px-3 text-xs text-foreground"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || !reason || suppressed}
            onClick={() =>
              transition("SUPPRESSED", {
                suppression_reason: reason,
                suppression_expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
              })
            }
          >
            Suppress 7 days
          </Button>
        </div>

        <div>
          <label
            htmlFor="finding-comment"
            className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
          >
            Comment / justification
          </label>
          <textarea
            id="finding-comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={2}
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground"
            placeholder="Why is this finding being changed?"
          />
        </div>

        {finding.remediation_action ? (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface-muted px-3 py-2">
            <span className="text-xs text-muted-foreground">Remediation</span>
            <code className="font-mono text-xs text-foreground">{finding.remediation_action}</code>
            {actionId ? (
              <Link
                href={`/actions/${actionId}`}
                className="ml-auto text-xs font-medium text-accent underline underline-offset-4"
              >
                View action
              </Link>
            ) : (
              <Button
                size="sm"
                variant="primary"
                className="ml-auto"
                disabled={busy || terminal || suppressed}
                onClick={remediate}
              >
                Create action
              </Button>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            This rule does not have an automated Phase 6 remediation. Resolve it manually or with a
            custom action.
          </p>
        )}

        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
    </Card>
  );
}
