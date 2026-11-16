import { Badge, Card, EmptyState } from "@argus/ui";

import {
  ConnectRepoCard,
  ScanDriftButton,
  SynthesizeDriftPrButton,
} from "@/components/iac/iac-actions";
import { apiFetch } from "@/lib/api";
import {
  type GitRepository,
  type IacDriftRecord,
  type IacPullRequest,
  driftSeverityTone,
  prStatusTone,
} from "@/lib/iac-types";

export const dynamic = "force-dynamic";

async function loadRepositories(): Promise<GitRepository[]> {
  try {
    return await apiFetch<GitRepository[]>("/api/v1/iac/repositories", { timeoutMs: 4_000 });
  } catch {
    return [];
  }
}

async function loadDrift(): Promise<IacDriftRecord[]> {
  try {
    return await apiFetch<IacDriftRecord[]>("/api/v1/iac/drift", { timeoutMs: 4_000 });
  } catch {
    return [];
  }
}

async function loadPullRequests(): Promise<IacPullRequest[]> {
  try {
    return await apiFetch<IacPullRequest[]>("/api/v1/iac/prs", { timeoutMs: 4_000 });
  } catch {
    return [];
  }
}

export default async function IacPage() {
  const [repositories, driftRecords, pullRequests] = await Promise.all([
    loadRepositories(),
    loadDrift(),
    loadPullRequests(),
  ]);

  const activeDrift = driftRecords.filter((d) => d.status === "DRIFTED");
  const openPrs = pullRequests.filter((p) => p.status === "OPEN");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            GitOps Bridge & IaC Drift Remediation
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Eliminate ClickOps drift between live cloud infrastructure and checked-in
            Terraform/OpenTofu code. Every approved action compiles an exact unified HCL diff and
            opens an automated Pull Request.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ScanDriftButton />
          <ConnectRepoCard />
        </div>
      </header>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Connected Repos">
          <p className="text-2xl font-semibold tabular-nums text-foreground">
            {repositories.length}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">GitHub & GitLab IaC sources.</p>
        </Card>

        <Card title="Active Drift Items">
          <p
            className={`text-2xl font-semibold tabular-nums ${
              activeDrift.length > 0 ? "text-warning" : "text-success"
            }`}
          >
            {activeDrift.length}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {activeDrift.length === 0
              ? "Infrastructure in sync with code"
              : "Manual ClickOps detected"}
          </p>
        </Card>

        <Card title="Generated Pull Requests">
          <p className="text-2xl font-semibold tabular-nums text-info">{pullRequests.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">{openPrs.length} currently open.</p>
        </Card>

        <Card title="GitOps Policy">
          <div className="mt-1 flex items-center gap-1.5">
            <Badge tone="success">NO-DRIFT ACTIVE</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Actions synthesize HCL patches automatically.
          </p>
        </Card>
      </div>

      {/* Connected Git Repositories */}
      <Card
        title="Connected IaC Repositories"
        description="Repositories holding Terraform / OpenTofu root modules."
      >
        {repositories.length === 0 ? (
          <EmptyState
            title="No Git repositories connected yet"
            description="Click '+ Connect IaC Repository' above to link your GitHub or GitLab repository."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {repositories.map((repo) => (
              <div
                key={repo.id}
                className="flex items-center justify-between rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex items-center gap-3">
                  <Badge tone="info">{repo.provider}</Badge>
                  <span className="font-mono text-xs font-semibold text-foreground">
                    {repo.repo_url}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    branch: <strong>{repo.default_branch}</strong> · path:{" "}
                    <strong>{repo.iac_path}</strong>
                  </span>
                </div>
                <Badge tone="success">{repo.status}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Detected ClickOps Drift */}
      <Card
        title="Detected ClickOps Drift"
        description="Live cloud configuration modifications made outside Terraform."
      >
        {activeDrift.length === 0 ? (
          <EmptyState
            title="Zero IaC Drift Detected"
            description="Your live cloud infrastructure strictly matches your checked-in Terraform baseline."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {activeDrift.map((drift) => (
              <div
                key={drift.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex flex-col gap-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <Badge tone={driftSeverityTone(drift.drift_details.severity)}>
                      {drift.drift_details.drift_type}
                    </Badge>
                    <span className="font-mono text-xs font-bold text-foreground">
                      {drift.iac_file_path} :: {drift.iac_block_type}.{drift.iac_block_name}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{drift.drift_details.message}</p>
                  <span className="font-mono text-[10px] text-muted-foreground truncate">
                    Target: {drift.resource_id}
                  </span>
                </div>

                <SynthesizeDriftPrButton drift={drift} />
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Generated GitOps Pull Requests */}
      <Card
        title="Synthesized GitOps Pull Requests"
        description="Automated HCL diffs compiled and opened against customer Git repositories."
      >
        {pullRequests.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No pull requests generated yet. Remediating a finding or drift item will compile an HCL
            patch and open a PR.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {pullRequests.map((pr) => (
              <div
                key={pr.id}
                className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone={prStatusTone(pr.status)}>{pr.status}</Badge>
                    <a
                      href={pr.pr_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-xs text-foreground hover:text-accent underline underline-offset-4"
                    >
                      PR #{pr.pr_number}: {pr.title} ↗
                    </a>
                  </div>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    branch: {pr.branch_name}
                  </span>
                </div>

                <div className="rounded-md border border-border bg-surface-muted p-2 font-mono text-[11px] overflow-x-auto text-foreground">
                  <pre className="max-h-40 overflow-y-auto">{pr.hcl_diff}</pre>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
