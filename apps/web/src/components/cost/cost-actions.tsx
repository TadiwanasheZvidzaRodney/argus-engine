"use client";

import { Button, Card } from "@argus/ui";
import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";
import type { CostRecommendation } from "@/lib/cost-types";

function newKey(prefix: string): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `${prefix}-${cryptoApi.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}`;
}

export function CostSyncButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSync() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/cost/sync", {
        method: "POST",
        idempotencyKey: newKey("cost-sync"),
        body: { days: 30 },
        timeoutMs: 30_000,
      });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sync failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" loading={busy} onClick={handleSync}>
        {busy ? "Syncing cost data…" : "Sync Cost Data"}
      </Button>
      {error && <span className="text-[11px] text-danger">{error}</span>}
    </div>
  );
}

export function RecommendationRemediateButton({
  recommendation,
}: {
  recommendation: CostRecommendation;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [actionId, setActionId] = useState(recommendation.remediation?.action_id);
  const [error, setError] = useState<string | null>(null);

  async function handleRemediate() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<{ action: { id: string } }>(
        `/api/v1/cost/recommendations/${recommendation.id}/remediate`,
        {
          method: "POST",
          idempotencyKey: newKey("rec-rem"),
          body: { constraints: { environment: "staging" } },
        },
      );
      setActionId(res.action.id);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create action.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAcknowledge() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/cost/recommendations/${recommendation.id}`, {
        method: "PATCH",
        idempotencyKey: newKey("rec-ack"),
        body: { status: "ACKNOWLEDGED" },
      });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to update.");
    } finally {
      setBusy(false);
    }
  }

  if (actionId) {
    return (
      <Link
        href={`/actions/${actionId}`}
        className="text-xs font-medium text-accent underline underline-offset-4"
      >
        View Action
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      {recommendation.status === "OPEN" && (
        <Button size="sm" variant="ghost" disabled={busy} onClick={handleAcknowledge}>
          Ack
        </Button>
      )}
      {recommendation.remediation && (
        <Button size="sm" variant="primary" loading={busy} onClick={handleRemediate}>
          Remediate
        </Button>
      )}
      {error && <span className="text-[10px] text-danger">{error}</span>}
    </div>
  );
}

export function CreateBudgetCard() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState("5000");
  const [channel, setChannel] = useState("slack:#finops-alerts");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/cost/budgets", {
        method: "POST",
        idempotencyKey: newKey("bgt-create"),
        body: {
          name,
          scope_type: "tenant",
          threshold_amount: parseFloat(threshold),
          period: "monthly",
          notification_channel: channel || undefined,
        },
      });
      setName("");
      setOpen(false);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create budget.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        + Create Budget
      </Button>
    );
  }

  return (
    <Card title="New Monthly Budget">
      <form onSubmit={handleCreate} className="flex flex-col gap-3">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Budget Name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="Production Spend Cap"
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Monthly Threshold (USD)
          </label>
          <input
            type="number"
            step="100"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            required
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Notification Channel
          </label>
          <input
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            placeholder="slack:#finops-alerts"
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
          />
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="submit" size="sm" variant="primary" loading={busy}>
            Save Budget
          </Button>
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </form>
    </Card>
  );
}
