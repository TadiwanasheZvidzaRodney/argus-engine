"use client";

import { Button } from "@argus/ui";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";

interface ScanResponse {
  scan_id: string;
  rules_evaluated: number;
  hits: number;
  created: number;
  updated: number;
  reopened: number;
  resolved: number;
  suppressed: number;
}

function newKey(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `scan-${cryptoApi.randomUUID()}`;
  return `scan-${Date.now().toString(36)}`;
}

export function ScanControls() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runScan() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch<ScanResponse>("/api/v1/security/scan", {
        method: "POST",
        idempotencyKey: newKey(),
        body: { materialize: true },
        timeoutMs: 30_000,
      });
      setResult(response);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The scan could not be started.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button size="sm" loading={busy} onClick={runScan}>
        {busy ? "Scanning…" : "Run security scan"}
      </Button>
      {result && (
        <p className="text-[11px] text-muted-foreground">
          {result.rules_evaluated} rules · {result.created} new · {result.updated} updated ·{" "}
          {result.resolved} resolved
        </p>
      )}
      {error && <p className="max-w-xs text-right text-[11px] text-danger">{error}</p>}
    </div>
  );
}
