"use client";

import { Button, Card } from "@argus/ui";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";
import type { IacDriftRecord } from "@/lib/iac-types";

function newKey(prefix: string): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `${prefix}-${cryptoApi.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}`;
}

export function ScanDriftButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleScan() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/iac/drift/scan", {
        method: "POST",
        idempotencyKey: newKey("drift-scan"),
        timeoutMs: 15_000,
      });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Drift scan failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="secondary" loading={busy} onClick={handleScan}>
        Scan IaC Drift
      </Button>
      {error && <span className="text-[11px] text-danger">{error}</span>}
    </div>
  );
}

export function ConnectRepoCard() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [iacPath, setIacPath] = useState("terraform/");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/api/v1/iac/repositories", {
        method: "POST",
        idempotencyKey: newKey("repo-connect"),
        body: {
          provider: "github",
          repo_url: repoUrl,
          default_branch: branch,
          iac_path: iacPath,
        },
      });
      setRepoUrl("");
      setOpen(false);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to connect repository.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        + Connect IaC Repository
      </Button>
    );
  }

  return (
    <Card title="Connect Git Repository (GitHub / GitLab)">
      <form onSubmit={handleConnect} className="flex flex-col gap-3">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Repository URL
          </label>
          <input
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
            placeholder="https://github.com/my-org/aws-infrastructure-live"
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Default Branch
            </label>
            <input
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              IaC Root Path
            </label>
            <input
              value={iacPath}
              onChange={(e) => setIacPath(e.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="submit" size="sm" variant="primary" loading={busy}>
            Connect Repository
          </Button>
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </form>
    </Card>
  );
}

export function SynthesizeDriftPrButton({ drift }: { drift: IacDriftRecord }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSynthesize() {
    setBusy(true);
    setError(null);
    let actionType = "network.restrict_security_group_ingress";
    if (drift.drift_details.drift_type === "MODIFIED_INSTANCE_TYPE") {
      actionType = "optimization.resize_instance";
    } else if (drift.drift_details.drift_type === "MISSING_TAGS") {
      actionType = "tagging.apply";
    }

    try {
      const res = await apiFetch<{ pr_url: string }>("/api/v1/iac/prs", {
        method: "POST",
        idempotencyKey: newKey("synth-pr"),
        body: {
          action_type: actionType,
          target_resource_id: drift.resource_id,
          parameters: {
            port: 22,
            cidr: "0.0.0.0/0",
            tags: { Environment: "production", ManagedBy: "terraform" },
          },
        },
      });
      setPrUrl(res.pr_url);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to open PR.");
    } finally {
      setBusy(false);
    }
  }

  if (prUrl) {
    return (
      <a
        href={prUrl}
        target="_blank"
        rel="noreferrer"
        className="text-xs font-semibold text-accent underline underline-offset-4"
      >
        View GitHub PR ↗
      </a>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <Button size="sm" variant="primary" loading={busy} onClick={handleSynthesize}>
        Open GitOps PR
      </Button>
      {error && <span className="text-[10px] text-danger">{error}</span>}
    </div>
  );
}
