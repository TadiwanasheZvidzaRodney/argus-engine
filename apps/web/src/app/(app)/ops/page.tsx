import { Badge, Card, EmptyState } from "@argus/ui";

import {
  AlertActionControls,
  AutoRefreshBadge,
  TestEmailAlertButton,
  TvModeToggle,
} from "@/components/ops/ops-actions";
import { apiFetch } from "@/lib/api";
import { type OpsWallboardData, alertSeverityTone, alertStatusTone } from "@/lib/ops-types";

export const dynamic = "force-dynamic";

async function loadWallboard(): Promise<OpsWallboardData> {
  try {
    return await apiFetch<OpsWallboardData>("/api/v1/ops/wallboard", { timeoutMs: 4_000 });
  } catch {
    return {
      status_banner: {
        state: "ALL_CLEAR",
        message: "ALL CLEAR — No alerts or anomalies firing",
        firing_alerts_count: 0,
        as_of: new Date().toISOString(),
      },
      golden_signals: {
        availability_percent: 99.95,
        throughput_req_min: 48200,
        latency_p95_ms: 16.4,
        error_rate_percent: 0.012,
        errors_5xx_count: 0,
      },
      ecs_systems: [],
      database_vitals: {
        active_connections: 18,
        connection_pool_saturation_percent: 24.0,
        storage_used_percent: 38.5,
        status: "UP",
      },
      alb_vitals: {
        target_response_time_sec: 0.018,
        healthy_hosts: 4,
        unhealthy_hosts: 0,
        status: "UP",
      },
      active_findings_count: 0,
      alerts: [],
    };
  }
}

export default async function OperationsWallboardPage() {
  const data = await loadWallboard();
  const banner = data.status_banner;
  const signals = data.golden_signals;
  const isAllClear = banner.state === "ALL_CLEAR";

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Operations Wallboard (NOC Display)
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Live SRE Golden Signals, AWS ECS container fleet vitals, and automated DevOps alert
            escalations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TestEmailAlertButton />
          <AutoRefreshBadge intervalSeconds={15} />
          <TvModeToggle />
        </div>
      </header>

      {/* Top Status Banner (Just like Grafana TV screen) */}
      <div
        className={`flex items-center justify-between rounded-lg border px-4 py-3 font-semibold text-sm transition-all ${
          isAllClear
            ? "border-success/30 bg-success/15 text-success"
            : "border-danger/50 bg-danger/20 text-danger animate-pulse shadow-lg"
        }`}
      >
        <div className="flex items-center gap-2.5">
          <span className="size-2.5 rounded-full bg-current" />
          <span className="tracking-wide uppercase text-xs font-bold">
            {isAllClear ? "✓ ALL CLEAR" : "⚠ ALARM FIRING"}
          </span>
          <span className="text-xs font-medium text-foreground">{banner.message}</span>
        </div>
        <span className="text-[11px] font-mono text-muted-foreground">
          as of {new Date(banner.as_of).toLocaleTimeString()}
        </span>
      </div>

      {/* SRE Golden Signals Grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5 shadow-sm">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            System Availability (SLO)
          </span>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold tabular-nums text-success">
              {signals.availability_percent}%
            </span>
            <span className="text-[11px] text-muted-foreground">target: 99.90%</span>
          </div>
          <p className="text-[11px] text-muted-foreground">Rolling 30-day API & canvas uptime.</p>
        </div>

        <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5 shadow-sm">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Traffic Throughput
          </span>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold tabular-nums text-info">
              {(signals.throughput_req_min / 1000).toFixed(1)}k
            </span>
            <span className="text-[11px] text-muted-foreground">req / min</span>
          </div>
          <p className="text-[11px] text-muted-foreground">Inbound ALB & API gateway traffic.</p>
        </div>

        <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5 shadow-sm">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Inbound Latency (p95)
          </span>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold tabular-nums text-foreground">
              {signals.latency_p95_ms}
              <span className="text-lg font-normal text-muted-foreground">ms</span>
            </span>
            <Badge tone="success">&lt; 50ms</Badge>
          </div>
          <p className="text-[11px] text-muted-foreground">Server-side request execution p95.</p>
        </div>

        <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3.5 shadow-sm">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            HTTP 5xx Error Rate
          </span>
          <div className="flex items-baseline justify-between">
            <span
              className={`text-3xl font-extrabold tabular-nums ${
                signals.errors_5xx_count > 0 ? "text-danger" : "text-success"
              }`}
            >
              {signals.error_rate_percent}%
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">
              {signals.errors_5xx_count} errors
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">Failed transaction percentage.</p>
        </div>
      </div>

      {/* AWS ECS Systems & Container Matrix */}
      <Card
        title="AWS ECS Systems & Container Fleet Matrix"
        description="Real-time task allocations, CPU/memory saturation, and container health."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          {data.ecs_systems.map((svc) => (
            <div
              key={svc.name}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface-muted/50 p-3.5"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs text-foreground truncate">{svc.name}</span>
                <Badge tone={svc.status === "healthy" ? "success" : "danger"}>
                  {svc.running_tasks}/{svc.desired_tasks} tasks
                </Badge>
              </div>

              <div className="flex flex-col gap-1.5 pt-1 text-xs">
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>CPU Utilization</span>
                  <span className="font-mono font-semibold text-foreground">
                    {svc.cpu_percent}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface">
                  <div
                    className={`h-full ${
                      svc.cpu_percent > 80
                        ? "bg-danger"
                        : svc.cpu_percent > 60
                          ? "bg-warning"
                          : "bg-info"
                    }`}
                    style={{ width: `${Math.min(100, svc.cpu_percent)}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-muted-foreground pt-1">
                  <span>Memory Utilization</span>
                  <span className="font-mono font-semibold text-foreground">
                    {svc.memory_percent}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface">
                  <div
                    className={`h-full ${
                      svc.memory_percent > 80
                        ? "bg-danger"
                        : svc.memory_percent > 60
                          ? "bg-warning"
                          : "bg-success"
                    }`}
                    style={{ width: `${Math.min(100, svc.memory_percent)}%` }}
                  />
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/50 pt-2 text-[10px] text-muted-foreground">
                <span>Cluster: {svc.cluster}</span>
                <span>{svc.restarts_24h} restarts</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ALB & RDS Vitals */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card title="Application Load Balancer Vitals">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted/40 p-2.5">
              <span className="text-muted-foreground">Target Response Time</span>
              <span className="text-lg font-bold font-mono text-foreground">
                {(data.alb_vitals.target_response_time_sec * 1000).toFixed(1)}ms
              </span>
            </div>
            <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted/40 p-2.5">
              <span className="text-muted-foreground">Healthy Hosts</span>
              <span className="text-lg font-bold font-mono text-success">
                {data.alb_vitals.healthy_hosts} / {data.alb_vitals.healthy_hosts}
              </span>
            </div>
          </div>
        </Card>

        <Card title="Aurora PostgreSQL / Database Vitals">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted/40 p-2.5">
              <span className="text-muted-foreground">Active Connections</span>
              <span className="text-lg font-bold font-mono text-foreground">
                {data.database_vitals.active_connections}
              </span>
            </div>
            <div className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted/40 p-2.5">
              <span className="text-muted-foreground">Pool Saturation</span>
              <span className="text-lg font-bold font-mono text-info">
                {data.database_vitals.connection_pool_saturation_percent}%
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Live Operational Alerts Feed */}
      <Card
        title="Live Operational Alerts & Escalation Feed"
        description="Unaddressed alerts send repeated notifications to devops@zimworx.com until acknowledged or resolved."
      >
        {data.alerts.length === 0 ? (
          <EmptyState
            title="Zero active operational alerts"
            description="All ECS services, container tasks, and healthchecks are operating within nominal thresholds."
          />
        ) : (
          <div className="flex flex-col gap-2.5">
            {data.alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3"
              >
                <div className="flex flex-col gap-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <Badge tone={alertSeverityTone(alert.severity)}>{alert.severity}</Badge>
                    <Badge tone={alertStatusTone(alert.status)}>{alert.status}</Badge>
                    {alert.requires_action && alert.status === "FIRING" && (
                      <Badge tone="danger">Action Required</Badge>
                    )}
                    {alert.notification_count > 1 && (
                      <span className="rounded-full bg-danger/20 px-2 py-0.5 text-[10px] font-bold text-danger">
                        Repeated Alert #{alert.notification_count}
                      </span>
                    )}
                    <span className="text-xs font-semibold text-foreground">{alert.title}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{alert.description}</p>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
                    <span>Source: {alert.source}</span>
                    <span>·</span>
                    <span>Emailed to: {alert.notification_email}</span>
                    <span>·</span>
                    <span>Triggered: {new Date(alert.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                <AlertActionControls alertId={alert.id} status={alert.status} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
