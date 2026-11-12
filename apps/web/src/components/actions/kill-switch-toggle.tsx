"use client";

import { Button } from "@argus/ui";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import type { KillSwitchState } from "@/lib/action-types";

export function KillSwitchToggle({ state }: { state: KillSwitchState }) {
  const router = useRouter();
  const [scope, setScope] = useState<"tenant" | "global">("tenant");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentlyEnabled = scope === "tenant" ? state.tenant_enabled : state.global_enabled;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/kill-switch", {
        method: "POST",
        idempotencyKey: `kill-switch-${Date.now()}`,
        body: {
          scope,
          enabled: !currentlyEnabled,
          reason: reason || (currentlyEnabled ? "writes restored" : "emergency stop"),
        },
      });
      setReason("");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Request failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Scope
          <select
            value={scope}
            onChange={(event) => setScope(event.target.value as "tenant" | "global")}
            className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          >
            <option value="tenant">This tenant</option>
            <option value="global">All tenants (global)</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Reason
          <input
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="INC-1234 · suspend writes during incident"
            className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={currentlyEnabled ? "secondary" : "danger"}
          loading={busy}
          onClick={toggle}
        >
          {currentlyEnabled ? "Restore writes" : "Stop all writes"}
        </Button>
        <span className="text-xs text-muted-foreground">
          {currentlyEnabled
            ? "Writes are currently stopped for this scope."
            : "Writes are currently enabled for this scope."}
        </span>
      </div>

      {state.reasons.length > 0 && (
        <ul className="list-inside list-disc text-[11px] text-danger">
          {state.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
