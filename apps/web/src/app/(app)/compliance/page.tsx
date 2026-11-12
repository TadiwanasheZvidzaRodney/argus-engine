import { Badge, Card, EmptyState } from "@argus/ui";

import {
  CollectEvidenceButton,
  DegradedModeControls,
  ExportAuditPackageButton,
  RunDrDrillButton,
} from "@/components/compliance/compliance-actions";
import { apiFetch } from "@/lib/api";
import {
  type ComplianceControl,
  type ComplianceFramework,
  type DisasterRecoveryReport,
  type SystemStatusReport,
  type UsageMeteringRecord,
  complianceStatusTone,
} from "@/lib/compliance-types";

export const dynamic = "force-dynamic";

async function loadFrameworks(): Promise<ComplianceFramework[]> {
  try {
    return await apiFetch<ComplianceFramework[]>("/api/v1/compliance/frameworks", {
      timeoutMs: 4_000,
    });
  } catch {
    return [];
  }
}

async function loadControls(): Promise<ComplianceControl[]> {
  try {
    return await apiFetch<ComplianceControl[]>("/api/v1/compliance/controls?framework=SOC2", {
      timeoutMs: 4_000,
    });
  } catch {
    return [];
  }
}

async function loadSystemStatus(): Promise<SystemStatusReport> {
  try {
    return await apiFetch<SystemStatusReport>("/api/v1/admin/status", { timeoutMs: 4_000 });
  } catch {
    return {
      overall_status: "OPERATIONAL",
      degraded_mode: {
        read_only: false,
        live_paused: false,
        telemetry_paused: false,
        actions_disabled: false,
        maintenance_message: null,
        is_degraded: false,
        updated_at: null,
      },
      slos: [],
      dependencies: [],
    };
  }
}

async function loadMetering(): Promise<UsageMeteringRecord[]> {
  try {
    return await apiFetch<UsageMeteringRecord[]>("/api/v1/admin/metering", { timeoutMs: 4_000 });
  } catch {
    return [];
  }
}

async function loadDrReport(): Promise<DisasterRecoveryReport | null> {
  try {
    return await apiFetch<DisasterRecoveryReport>("/api/v1/admin/dr-drill", {
      method: "POST",
      timeoutMs: 5_000,
    });
  } catch {
    return null;
  }
}

export default async function CompliancePage() {
  const [frameworks, controls, statusReport, meteringHistory, drReport] = await Promise.all([
    loadFrameworks(),
    loadControls(),
    loadSystemStatus(),
    loadMetering(),
    loadDrReport(),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Compliance, Evidence Locker & Operations
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Continuous compliance readiness across SOC 2, CIS AWS Foundations, and NIST 800-53 with
            cryptographically sealed evidence records, production SLOs, degraded mode controls, and
            DR verification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ExportAuditPackageButton />
          <CollectEvidenceButton />
        </div>
      </header>

      {/* Framework Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {frameworks.map((fw) => (
          <Card key={fw.framework} title={fw.framework}>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-2xl font-bold tabular-nums">
                  {fw.compliance_score_percent}%
                </span>
                <Badge tone={complianceStatusTone(fw.status)}>{fw.status}</Badge>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className={`h-full ${fw.status === "COMPLIANT" ? "bg-success" : "bg-warning"}`}
                  style={{ width: `${fw.compliance_score_percent}%` }}
                />
              </div>
              <p className="text-[11px] text-muted-foreground">
                {fw.passed_controls} of {fw.total_controls} controls passing
              </p>
            </div>
          </Card>
        ))}
      </div>

      {/* SRE Status & SLO Attainment */}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card
          title="Service Level Objectives (SLOs) & Error Budgets"
          description="30-day rolling evaluation against GA reliability commitments."
          actions={
            <Badge tone={complianceStatusTone(statusReport.overall_status)}>
              {statusReport.overall_status}
            </Badge>
          }
        >
          {statusReport.slos.length === 0 ? (
            <EmptyState
              title="SLO metrics initializing"
              description="Collecting telemetry samples."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="pb-2 font-medium">Objective (SLO)</th>
                    <th className="pb-2 font-medium">Target</th>
                    <th className="pb-2 font-medium">Current (30d)</th>
                    <th className="pb-2 font-medium">Budget Burn</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {statusReport.slos.map((slo) => (
                    <tr key={slo.slo_name} className="hover:bg-surface-muted/50">
                      <td className="py-2.5 font-medium text-foreground">{slo.slo_name}</td>
                      <td className="py-2.5 font-mono text-muted-foreground">
                        {slo.target_percent}%
                      </td>
                      <td className="py-2.5 font-mono font-semibold text-foreground">
                        {slo.current_percent}%
                      </td>
                      <td className="py-2.5 font-mono text-muted-foreground">
                        {slo.error_budget_burn_percent}%
                      </td>
                      <td className="py-2.5">
                        <Badge tone={complianceStatusTone(slo.status)}>{slo.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Core Dependencies" description="Live cluster and provider health.">
          <div className="flex flex-col gap-2">
            {statusReport.dependencies.map((dep) => (
              <div
                key={dep.name}
                className="flex items-center justify-between text-xs py-1 border-b border-border/50"
              >
                <span className="text-foreground">{dep.name}</span>
                <Badge tone={dep.status === "UP" ? "success" : "danger"}>{dep.status}</Badge>
              </div>
            ))}
            <div className="pt-2">
              <RunDrDrillButton />
            </div>
          </div>
        </Card>
      </div>

      {/* Degraded Modes Circuit Breakers */}
      <DegradedModeControls initialMode={statusReport.degraded_mode} />

      {/* SOC 2 Evidence Locker Table */}
      <Card
        title="SOC 2 Type II Evidence Locker"
        description="Immutable cryptographic records linking controls directly to security rule evaluations and change approvals."
      >
        {controls.length === 0 ? (
          <EmptyState
            title="No controls loaded"
            description="Controls are being initialized from the catalog."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="pb-2 font-medium">Control ID</th>
                  <th className="pb-2 font-medium">Domain & Title</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Cryptographic Evidence Hash</th>
                  <th className="pb-2 font-medium">Collected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {controls.map((ctrl) => (
                  <tr key={ctrl.control_id} className="hover:bg-surface-muted/50">
                    <td className="py-2.5 font-mono font-bold text-foreground">
                      {ctrl.control_id}
                    </td>
                    <td className="py-2.5">
                      <div className="flex flex-col">
                        <span className="font-semibold text-foreground">{ctrl.title}</span>
                        <span className="text-[11px] text-muted-foreground">{ctrl.domain}</span>
                      </div>
                    </td>
                    <td className="py-2.5">
                      <Badge tone={complianceStatusTone(ctrl.status)}>{ctrl.status}</Badge>
                    </td>
                    <td className="py-2.5 font-mono text-[11px] text-muted-foreground">
                      {ctrl.evidence_hash ? (
                        <span title={ctrl.evidence_hash}>
                          sha256:{ctrl.evidence_hash.slice(0, 16)}…
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2.5 text-muted-foreground text-[11px]">
                      {ctrl.collected_at
                        ? new Date(ctrl.collected_at).toLocaleDateString()
                        : "Pending"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Multi-Region Disaster Recovery (DR) Verification */}
      {drReport && (
        <Card
          title="Multi-Region Disaster Recovery (DR) Verification"
          description={`Simulated failover drill (${drReport.drill_id}) between Primary (${drReport.primary_region}) and Secondary (${drReport.recovery_region}).`}
          actions={<Badge tone="success">{drReport.overall_status}</Badge>}
        >
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-4 text-xs">
              <span className="text-muted-foreground">
                Target RTO: <strong className="text-foreground">&lt; 1 hour</strong> (Achieved:{" "}
                <strong className="text-success">{drReport.rto_achieved_minutes}m</strong>)
              </span>
              <span className="text-muted-foreground">
                Target RPO: <strong className="text-foreground">&lt; 15 minutes</strong> (Achieved:{" "}
                <strong className="text-success">{drReport.rpo_achieved_minutes}m</strong>)
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="pb-1.5 font-medium">Component</th>
                    <th className="pb-1.5 font-medium">Metric</th>
                    <th className="pb-1.5 font-medium">Target</th>
                    <th className="pb-1.5 font-medium">Measured</th>
                    <th className="pb-1.5 font-medium">Status</th>
                    <th className="pb-1.5 font-medium">Verification Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {drReport.checks.map((chk) => (
                    <tr key={chk.component}>
                      <td className="py-2 font-medium text-foreground">{chk.component}</td>
                      <td className="py-2 font-mono text-muted-foreground">{chk.metric}</td>
                      <td className="py-2 text-muted-foreground">{chk.target}</td>
                      <td className="py-2 font-mono font-medium text-foreground">{chk.measured}</td>
                      <td className="py-2">
                        <Badge tone={complianceStatusTone(chk.status)}>{chk.status}</Badge>
                      </td>
                      <td className="py-2 text-[11px] text-muted-foreground">{chk.details}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}

      {/* Usage Metering & Commercial Economics */}
      <Card
        title="Tenant Usage Metering & Unit Economics"
        description="Daily consumption across resources, real-time events, metric queries, and planned actions."
      >
        {meteringHistory.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No consumption records logged yet. Normal graph activity will record daily usage.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Resources</th>
                  <th className="pb-2 font-medium">Events Ingested</th>
                  <th className="pb-2 font-medium">Metric Requests</th>
                  <th className="pb-2 font-medium">Actions Executed</th>
                  <th className="pb-2 font-medium">Est. Marginal Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {meteringHistory.map((m) => (
                  <tr key={m.period_date} className="hover:bg-surface-muted/50">
                    <td className="py-2 font-mono text-foreground">{m.period_date}</td>
                    <td className="py-2 font-mono">{m.resources_count}</td>
                    <td className="py-2 font-mono">{m.events_ingested}</td>
                    <td className="py-2 font-mono">{m.metric_requests}</td>
                    <td className="py-2 font-mono">{m.actions_executed}</td>
                    <td className="py-2 font-mono font-medium text-foreground">
                      ${m.estimated_cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
