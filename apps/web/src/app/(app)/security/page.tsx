import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { ScanControls } from "@/components/findings/scan-controls";
import { HistoryChart } from "@/components/security/history-chart";
import { apiFetch } from "@/lib/api";
import { severityTone } from "@/lib/finding-types";
import {
  SECURITY_RANGES,
  type SecurityDashboardData,
  parseSecurityRange,
  securityTime,
} from "@/lib/security-types";

export const dynamic = "force-dynamic";

const SEVERITIES = [
  {
    key: "critical",
    label: "Critical findings",
    color: "#991b1b",
    line: "#fecaca",
    hint: "Prioritize immediate investigation",
  },
  {
    key: "high",
    label: "High severity",
    color: "#92400e",
    line: "#fde68a",
    hint: "Prioritize remediation",
  },
  {
    key: "medium",
    label: "Medium severity",
    color: "#854d0e",
    line: "#fef08a",
    hint: "Review policy & configuration",
  },
  {
    key: "low",
    label: "Low severity",
    color: "#1e40af",
    line: "#bfdbfe",
    hint: "Review hardening opportunities",
  },
] as const;

export default async function SecurityPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string | string[] }>;
}) {
  const range = parseSecurityRange((await searchParams).range);
  const data = await apiFetch<SecurityDashboardData>(`/api/v1/security/summary?range=${range}`, {
    timeoutMs: 15_000,
  }).catch(() => null);
  const posture = data?.posture;
  const paths = data?.attack_paths;
  const history = data?.trend_history ?? [];
  const score = posture?.score;
  const topRules = Object.entries(data?.by_rule ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const urgent = (data?.open_by_severity.critical ?? 0) + (data?.open_by_severity.high ?? 0);
  const domainHints: Record<string, string> = {
    iam: "IAM users, roles, access keys and trust policies.",
    storage: "S3, EBS and RDS configuration findings.",
    network: "Security group ingress and public API configuration.",
    governance: "Discovered CloudTrail trails and GuardDuty detectors.",
  };

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <p className="mb-1 text-[10px] font-bold uppercase tracking-[.2em] text-accent">
            Security & posture / Intelligence
          </p>
          <h1 className="text-xl font-bold tracking-tight">Security posture</h1>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
            Recorded risks, remediation progress and graph-derived attack chains. No simulated
            history.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <ScanControls />
          <div className="flex gap-3 text-xs">
            <Link className="font-medium text-accent underline underline-offset-4" href="/findings">
              All findings
            </Link>
            <Link className="font-medium text-accent underline underline-offset-4" href="/topology">
              Open canvas
            </Link>
          </div>
        </div>
      </header>

      <nav
        aria-label="Security history range"
        className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-surface p-1.5"
      >
        {SECURITY_RANGES.map((option) => (
          <Link
            key={option.value}
            href={`/security?range=${option.value}`}
            scroll={false}
            aria-current={range === option.value ? "page" : undefined}
            className={`rounded-md px-3 py-2 text-xs font-semibold ${range === option.value ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-surface-muted"}`}
          >
            {option.label}
          </Link>
        ))}
        <span className="ml-auto px-2 text-[10px] text-muted-foreground">
          History filter · current risk cards stay current · UTC
        </span>
      </nav>

      {!data ? (
        <div role="alert" className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
          Security data unavailable. No health or score can be inferred. Retry this page or check
          API connectivity.
        </div>
      ) : (
        <div
          role="status"
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-xs ${urgent ? "border-danger/30 bg-danger/10" : "border-border bg-surface"}`}
        >
          <strong>
            {urgent
              ? `${urgent} critical / high findings require review`
              : "No critical / high findings recorded — coverage is not a guarantee of safety"}
          </strong>
          <span className="font-mono text-[10px] text-muted-foreground">
            Report built {securityTime(data.generated_at)}
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <Card
          title="Argus posture indicator"
          description="A prioritization heuristic, not a compliance grade."
        >
          <div className="flex items-center gap-5 py-3">
            <div
              role="meter"
              aria-label="Argus posture indicator"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={score ?? undefined}
              aria-valuetext={score == null ? "Unavailable" : `${score} out of 100`}
              className="flex size-28 shrink-0 items-center justify-center rounded-full border-[9px] border-accent/30 bg-accent/5"
            >
              <span className="text-3xl font-extrabold tabular-nums">{score ?? "—"}</span>
            </div>
            <div>
              <p className="text-lg font-bold">
                {posture?.grade ? `Grade ${posture.grade}` : "Coverage unverified"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {score == null
                  ? "Scan evidence and graph context are required."
                  : "Weighted open findings + returned internet attack paths."}
              </p>
            </div>
          </div>
          <details className="mt-2 text-[11px] text-muted-foreground">
            <summary className="cursor-pointer font-semibold">How this score is calculated</summary>
            <p className="mt-2">
              {posture?.score_method ?? "Score unavailable while the API is unreachable."}
            </p>
          </details>
        </Card>
        <Card
          title="Evidence & coverage"
          description="Stored observations, not a fresh AWS inventory verification."
        >
          <dl className="grid gap-4 py-2 sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Resources in graph slice</dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums">
                {posture?.resources_observed ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Open / acknowledged</dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums">{data?.open_total ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Internet paths returned</dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums">
                {paths ? `${paths.count}${paths.truncated ? "+" : ""}` : "—"}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">
            Latest finding observation:{" "}
            {posture?.last_finding_observed_at
              ? securityTime(posture.last_finding_observed_at)
              : "Not recorded"}
            . This is not the timestamp of the last successful scan.
          </p>
          {posture?.stale && (
            <p role="alert" className="mt-2 text-xs font-semibold text-warning">
              Finding evidence is older than 24 hours. Rescan after refreshing inventory.
            </p>
          )}
          {data && !posture?.graph_available && (
            <p role="alert" className="mt-2 text-xs text-warning">
              Graph unavailable: domain coverage, attack paths and overall score cannot be verified.
            </p>
          )}
        </Card>
      </div>

      <section aria-label="Finding severity" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {SEVERITIES.map((severity) => (
          <article
            key={severity.key}
            className="min-w-0 rounded-lg p-4 text-white shadow-sm"
            style={{ background: severity.color }}
          >
            <Link
              href={`/findings?severity=${severity.key}`}
              className="text-[11px] font-bold uppercase tracking-wider underline-offset-4 hover:underline"
            >
              {severity.label}
            </Link>
            <p className="mt-2 text-4xl font-extrabold tabular-nums">
              {data ? (data.open_by_severity[severity.key] ?? 0) : "—"}
            </p>
            <p className="mt-1 text-[10px] opacity-85">{severity.hint}</p>
            <HistoryChart
              title={`${severity.label} history`}
              points={history}
              series={[{ key: severity.key, label: severity.label, color: severity.line }]}
              compact
            />
            <p className="text-[10px] opacity-80">Open backlog · current severity classification</p>
          </article>
        ))}
      </section>

      <section aria-label="Security domains">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Security domains · CIS-aligned topics, not CIS certification
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(
            posture?.domains ??
            Object.entries(domainHints).map(([id]) => ({
              id,
              label: (
                {
                  iam: "IAM & access hygiene",
                  storage: "Storage & encryption",
                  network: "Network boundary",
                  governance: "Logging & governance",
                } as Record<string, string>
              )[id],
              score: null,
              resources_observed: null,
              open_findings: null,
            }))
          ).map((domain) => (
            <Card key={domain.id} title={domain.label}>
              <p className="text-2xl font-bold tabular-nums">
                {domain.score == null ? "—" : `${domain.score}/100`}
              </p>
              <div className="my-3 h-1.5 overflow-hidden rounded bg-surface-muted" aria-hidden>
                {domain.score !== null && (
                  <div className="h-full bg-accent" style={{ width: `${domain.score}%` }} />
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {domain.resources_observed ?? "—"} resources observed ·{" "}
                {domain.open_findings ?? "—"} open findings
              </p>
              <p className="mt-2 text-[11px] text-muted-foreground">{domainHints[domain.id]}</p>
              <p className="mt-2 text-[10px] font-semibold text-warning">
                {domain.score == null
                  ? "Coverage unverified — no passing controls inferred"
                  : "Indicator based on recorded findings only"}
              </p>
            </Card>
          ))}
        </div>
      </section>

      <section aria-label="Security history" className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Finding inflow & resolution"
          description="Recorded entries into the open backlog versus resolutions, per bucket."
        >
          <HistoryChart
            title="Finding inflow & resolution"
            points={history}
            series={[
              { key: "opened", label: "Opened / reopened", color: "#e05252" },
              { key: "resolved", label: "Resolved", color: "#1e9e69" },
            ]}
          />
        </Card>
        <Card
          title="Open risk backlog"
          description="Open + acknowledged findings at bucket end; current severity classifications."
        >
          <HistoryChart
            title="Open risk backlog"
            points={history}
            series={[
              { key: "critical", label: "Critical", color: "#e05252" },
              { key: "high", label: "High", color: "#c57912" },
              { key: "medium", label: "Medium", color: "#8b64d9" },
              { key: "low", label: "Low", color: "#3388d6" },
            ]}
          />
        </Card>
      </section>
      <p className="-mt-2 text-[11px] text-muted-foreground">
        {data
          ? `Window: ${securityTime(data.window_start)} → ${securityTime(data.window_end)}. `
          : ""}
        Blank intervals mean no observation history. Accepted / suppressed risks are excluded from
        the open backlog, not proven fixed.
        {data?.history_partial &&
          " Some legacy findings lack complete lifecycle logs; their history is partial."}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Priority remediation queue"
          description="Current open findings, ranked by severity."
        >
          {!data ? (
            <EmptyState
              title="Findings unavailable"
              description="Unable to load stored findings."
            />
          ) : data.top_risks.length === 0 ? (
            <EmptyState
              title="No open findings recorded"
              description="This does not establish scan coverage or guarantee a secure account."
            />
          ) : (
            <ul className="flex flex-col gap-2">
              {data.top_risks.slice(0, 6).map((risk) => (
                <li key={risk.id}>
                  <Link
                    href={`/findings/${risk.id}`}
                    className="flex flex-col gap-2 rounded-md border border-border p-3 hover:bg-surface-muted"
                  >
                    <span className="flex items-center gap-2">
                      <Badge tone={severityTone(risk.severity)}>{risk.severity}</Badge>
                      <span className="text-xs font-semibold">{risk.title}</span>
                    </span>
                    <span className="truncate font-mono text-[10px] text-muted-foreground">
                      {risk.rule_id} · {risk.resource_id}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card
          title="Internet attack chains"
          description="Current graph-derived paths, not historical exposure measurements."
        >
          {!paths ? (
            <EmptyState
              title="Attack path analysis unavailable"
              description="Cannot infer reachability without graph context."
            />
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-[11px] text-muted-foreground">
                {paths.count} paths returned · {paths.evaluated_nodes} nodes evaluated{" "}
                {paths.truncated && <Badge tone="warning">Bounded / truncated</Badge>}
              </p>
              {paths.paths.length === 0 ? (
                <EmptyState
                  title="No paths found in the available graph"
                  description="Missing resources or relationships can hide reachable paths."
                />
              ) : (
                <ul className="flex flex-col gap-3">
                  {paths.paths.slice(0, 5).map((path) => (
                    <li
                      key={path.hops.map((hop) => hop.node_id).join(">")}
                      className="rounded-md border border-border p-3"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <Badge tone={severityTone(path.severity)}>{path.severity}</Badge>
                        <span className="text-[10px] text-muted-foreground">
                          Path risk {path.score} · {path.hops.length} hops
                        </span>
                      </div>
                      <ol className="flex flex-wrap items-center gap-1.5 text-[10px]">
                        {path.hops.map((hop, index) => (
                          <li key={`${hop.node_id}-${index}`} className="flex items-center gap-1.5">
                            {index > 0 && <span aria-hidden>→</span>}
                            <Link
                              href={`/topology?root=${encodeURIComponent(hop.node_id)}`}
                              title={hop.why}
                              className="max-w-52 truncate rounded border border-border bg-surface-muted px-2 py-1 font-mono hover:border-accent"
                            >
                              {hop.type.split("::").pop()}: {hop.name}
                            </Link>
                          </li>
                        ))}
                      </ol>
                      <Link
                        href={`/topology?root=${encodeURIComponent(path.hops.find((hop) => hop.type !== "AWS::Internet::Endpoint")?.node_id ?? "")}`}
                        className="mt-3 inline-block text-[11px] font-semibold text-accent underline underline-offset-4"
                      >
                        Open attack chain in canvas →
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[10px] text-muted-foreground">
                Computed {securityTime(paths.generated_at)}. Graph inventory freshness is not
                verified by this timestamp.
              </p>
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Finding lifecycle status">
          {!data ? (
            <p className="text-xs text-muted-foreground">Unavailable</p>
          ) : Object.keys(data.by_status).length === 0 ? (
            <p className="text-xs text-muted-foreground">No records.</p>
          ) : (
            <dl className="flex flex-col gap-3">
              {Object.entries(data.by_status).map(([status, count]) => (
                <div key={status} className="text-xs">
                  <div className="mb-1 flex justify-between">
                    <dt>{status}</dt>
                    <dd className="font-mono">{count}</dd>
                  </div>
                  <div className="h-1 rounded bg-surface-muted" aria-hidden>
                    <div
                      className="h-full rounded bg-accent"
                      style={{ width: `${(count / Math.max(1, data.total)) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </dl>
          )}
        </Card>
        <Card
          title="Most frequent rules"
          description="All recorded findings, including resolved findings."
        >
          {topRules.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {data ? "No rule hits recorded." : "Unavailable"}
            </p>
          ) : (
            <ul className="flex flex-col gap-3 text-xs">
              {topRules.map(([rule, count]) => (
                <li key={rule} className="flex justify-between gap-2">
                  <Link
                    href={`/findings?rule_id=${encodeURIComponent(rule)}`}
                    className="font-mono text-accent underline underline-offset-4"
                  >
                    {rule}
                  </Link>
                  <span className="font-mono">{count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <p className="text-[10px] text-muted-foreground">
        {data?.source ?? "Security API unavailable."} History filters do not rerun scans or verify
        AWS credentials.
      </p>
    </div>
  );
}
