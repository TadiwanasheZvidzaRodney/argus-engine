"use client";

import { Button, Card } from "@argus/ui";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";
import type { DegradedModeState, DisasterRecoveryReport } from "@/lib/compliance-types";

function newKey(prefix: string): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `${prefix}-${cryptoApi.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}`;
}

export function CollectEvidenceButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCollect() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/compliance/collect", {
        method: "POST",
        idempotencyKey: newKey("cmp-collect"),
        timeoutMs: 30_000,
      });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evidence collection failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="primary" loading={busy} onClick={handleCollect}>
        {busy ? "Sealing Evidence…" : "Collect & Seal Evidence"}
      </Button>
      {error && <span className="text-[11px] text-danger">{error}</span>}
    </div>
  );
}

export function ExportAuditPackageButton() {
  const [busy, setBusy] = useState(false);
  const [signature, setSignature] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<{ package_signature: string; manifest: unknown }>(
        "/api/v1/compliance/export?framework=SOC2",
        { timeoutMs: 10_000 },
      );
      setSignature(res.package_signature);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="secondary" loading={busy} onClick={handleExport}>
        Export Audit Package
      </Button>
      {signature && (
        <span className="font-mono text-[10px] text-success truncate max-w-xs">
          Signed: {signature.slice(0, 24)}…
        </span>
      )}
      {error && <span className="text-[11px] text-danger">{error}</span>}
    </div>
  );
}

export function DegradedModeControls({ initialMode }: { initialMode: DegradedModeState }) {
  const router = useRouter();
  const [mode, setMode] = useState(initialMode);
  const [busy, setBusy] = useState(false);

  async function toggleFlag(key: keyof DegradedModeState) {
    setBusy(true);
    const nextState = {
      ...mode,
      [key]: !mode[key],
      scope: "tenant",
    };
    try {
      const updated = await apiFetch<DegradedModeState>("/api/v1/admin/degraded", {
        method: "POST",
        idempotencyKey: newKey("deg-toggle"),
        body: nextState,
      });
      setMode(updated);
      router.refresh();
    } catch {
      // Keep previous state on failure
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Degraded Operational Modes"
      description="Fail-safe circuit breakers to survive incidents and throttles."
    >
      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          variant={mode.read_only ? "danger" : "secondary"}
          disabled={busy}
          onClick={() => toggleFlag("read_only")}
        >
          {mode.read_only ? "Read-Only: Active" : "Read-Only Mode"}
        </Button>
        <Button
          size="sm"
          variant={mode.live_paused ? "danger" : "secondary"}
          disabled={busy}
          onClick={() => toggleFlag("live_paused")}
        >
          {mode.live_paused ? "Live Stream: Paused" : "Pause Live Stream"}
        </Button>
        <Button
          size="sm"
          variant={mode.telemetry_paused ? "danger" : "secondary"}
          disabled={busy}
          onClick={() => toggleFlag("telemetry_paused")}
        >
          {mode.telemetry_paused ? "Telemetry: Off" : "Pause Telemetry"}
        </Button>
        <Button
          size="sm"
          variant={mode.actions_disabled ? "danger" : "secondary"}
          disabled={busy}
          onClick={() => toggleFlag("actions_disabled")}
        >
          {mode.actions_disabled ? "Actions: Disabled" : "Disable Actions"}
        </Button>
      </div>
    </Card>
  );
}

export function RunDrDrillButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<DisasterRecoveryReport | null>(null);

  async function handleDrill() {
    setBusy(true);
    try {
      const res = await apiFetch<DisasterRecoveryReport>("/api/v1/admin/dr-drill", {
        method: "POST",
        idempotencyKey: newKey("dr-drill"),
        timeoutMs: 15_000,
      });
      setReport(res);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" variant="secondary" loading={busy} onClick={handleDrill}>
        Simulate Multi-Region DR Drill
      </Button>
      {report && (
        <p className="text-[11px] text-success">
          Drill {report.drill_id}: {report.overall_status} (RTO: {report.rto_achieved_minutes}m,
          RPO: {report.rpo_achieved_minutes}m)
        </p>
      )}
    </div>
  );
}
