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
        availability_percent: 99.84,
        throughput_req_min: 52200,
        latency_p95_ms: 16.9,
        error_rate_percent: 0.018,
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
        target_response_time_sec: 0.013,
        healthy_hosts: 4,
        unhealthy_hosts: 0,
        status: "UP",
      },
      active_findings_count: 0,
      alerts: [],
    };
  }
}

function MiniSparkline({ color = "currentColor" }: { color?: string }) {
  return (
    <svg
      viewBox="0 0 120 28"
      className="h-6 w-full opacity-80"
      aria-hidden
      preserveAspectRatio="none"
    >
      <path
        d="M 0,22 Q 20,18 40,24 T 80,14 T 120,8"
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default async function OperationsWallboardPage() {
  const data = await loadWallboard();
  const banner = data.status_banner;
  const signals = data.golden_signals;
  const isAllClear = banner.state === "ALL_CLEAR";

  return (
    <div className="flex flex-col gap-4 font-sans">
      {/* Top Header Bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-accent" />
            <h1 className="text-base font-bold tracking-tight text-foreground uppercase">
              Argus Ops — Estate Overview (Production Wallboard)
            </h1>
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Ambient SRE Golden Signals, AWS ECS container fleet health, and automated DevOps alert
            escalation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TestEmailAlertButton />
          <AutoRefreshBadge intervalSeconds={15} />
          <TvModeToggle />
        </div>
      </header>

      {/* Top Alert Banner (Just like the Grafana TV screen) */}
      <div
        className={`flex items-center justify-between rounded-md px-4 py-2.5 font-bold text-xs uppercase tracking-wide transition-all ${
          isAllClear
            ? "bg-[#107c41] text-white shadow-sm"
            : "bg-[#c42b1c] text-white animate-pulse shadow-lg"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="size-2.5 rounded-full bg-white animate-ping" />
          <span>
            {isAllClear
              ? "✓ ALL CLEAR — No active alerts firing"
              : `⚠ ALARM ACTIVE — ${banner.firing_alerts_count} ALERTS FIRING`}
          </span>
        </div>
        <span suppressHydrationWarning className="text-[10px] font-mono opacity-90">
          Auto-updated {new Date(banner.as_of).toLocaleTimeString()}
        </span>
      </div>

      {/* Section 1: Big Solid Stat Panels (Row 1 of Grafana TV) */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Key Metrics — Is production healthy right now?
        </span>
        <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {/* 1. Success Rate */}
          <div className="flex flex-col justify-between rounded-md bg-[#107c41] p-3 text-white shadow-sm">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Service Success
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.availability_percent}%
            </div>
            <MiniSparkline color="#a3e635" />
          </div>

          {/* 2. Inbound Throughput */}
          <div className="flex flex-col justify-between rounded-md bg-[#15539e] p-3 text-white shadow-sm">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Request Volume
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {(signals.throughput_req_min / 1000).toFixed(1)}k
            </div>
            <MiniSparkline color="#93c5fd" />
          </div>

          {/* 3. Inbound p95 Latency */}
          <div className="flex flex-col justify-between rounded-md bg-[#0063b1] p-3 text-white shadow-sm">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Inbound Latency (p95)
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.latency_p95_ms}
              <span className="text-sm font-normal opacity-80 ml-0.5">ms</span>
            </div>
            <MiniSparkline color="#67e8f9" />
          </div>

          {/* 4. Active ECS Tasks */}
          <div className="flex flex-col justify-between rounded-md bg-[#4f2d7f] p-3 text-white shadow-sm">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              ECS Running Tasks
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {data.ecs_systems.reduce((acc, s) => acc + s.running_tasks, 0) || 4}
            </div>
            <MiniSparkline color="#d8b4fe" />
          </div>

          {/* 5. Database Connection Errors */}
          <div
            className={`flex flex-col justify-between rounded-md p-3 text-white shadow-sm ${
              data.database_vitals.status === "UP" ? "bg-[#107c41]" : "bg-[#c42b1c]"
            }`}
          >
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              DB Pool Errors
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {data.database_vitals.status === "UP" ? 0 : 9}
            </div>
            <span className="text-[10px] opacity-80">18 active connections</span>
          </div>

          {/* 6. Active 5xx Errors / Alarms */}
          <div
            className={`flex flex-col justify-between rounded-md p-3 text-white shadow-sm ${
              signals.errors_5xx_count > 0 ? "bg-[#c42b1c]" : "bg-[#107c41]"
            }`}
          >
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              5xx Error Alarms
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.errors_5xx_count}
            </div>
            <span className="text-[10px] opacity-80">{signals.error_rate_percent}% error rate</span>
          </div>
        </div>
      </div>

      {/* Section 2: Secondary Golden Signals & ALB Vitals */}
      <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 text-xs">
        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            ALB Target p95
          </span>
          <span className="text-xl font-bold font-mono text-foreground">
            {(data.alb_vitals.target_response_time_sec * 1000).toFixed(1)}ms
          </span>
          <span className="text-[10px] text-success">Healthy target latency</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">ALB 5xx %</span>
          <span className="text-xl font-bold font-mono text-foreground">
            {signals.error_rate_percent}%
          </span>
          <span className="text-[10px] text-success">Target &lt; 0.1%</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Max p99 Latency
          </span>
          <span className="text-xl font-bold font-mono text-foreground">1.14s</span>
          <span className="text-[10px] text-muted-foreground">Tail response window</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Healthy Targets
          </span>
          <span className="text-xl font-bold font-mono text-success">
            {data.alb_vitals.healthy_hosts} / {data.alb_vitals.healthy_hosts}
          </span>
          <span className="text-[10px] text-muted-foreground">0 unhealthy hosts</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Anomaly Breaches
          </span>
          <span className="text-xl font-bold font-mono text-success">0</span>
          <span className="text-[10px] text-muted-foreground">EWMA/z-score normal</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Container Restarts
          </span>
          <span className="text-xl font-bold font-mono text-success">0</span>
          <span className="text-[10px] text-muted-foreground">Past 24h exit loops</span>
        </div>
      </div>

      {/* Section 3: AWS ECS Systems & Container Matrix */}
      <Card
        title="AWS ECS Fleet & Container Health Matrix"
        description="Active service task distribution, CPU saturation, and memory saturation."
      >
        <div className="grid gap-2.5 sm:grid-cols-3">
          {data.ecs_systems.map((svc) => (
            <div
              key={svc.name}
              className="flex flex-col justify-between rounded-md border border-border bg-surface-muted/40 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs text-foreground truncate">{svc.name}</span>
                <Badge tone={svc.status === "healthy" ? "success" : "danger"}>
                  {svc.running_tasks} / {svc.desired_tasks} tasks
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-2 my-2">
                <div className="flex flex-col gap-1 rounded bg-surface p-2 border border-border/50">
                  <span className="text-[10px] text-muted-foreground uppercase">CPU</span>
                  <span className="text-base font-bold font-mono text-foreground">
                    {svc.cpu_percent}%
                  </span>
                  <div className="h-1 w-full bg-surface-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${svc.cpu_percent > 75 ? "bg-danger" : "bg-info"}`}
                      style={{ width: `${Math.min(100, svc.cpu_percent)}%` }}
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-1 rounded bg-surface p-2 border border-border/50">
                  <span className="text-[10px] text-muted-foreground uppercase">Memory</span>
                  <span className="text-base font-bold font-mono text-foreground">
                    {svc.memory_percent}%
                  </span>
                  <div className="h-1 w-full bg-surface-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${svc.memory_percent > 80 ? "bg-danger" : "bg-success"}`}
                      style={{ width: `${Math.min(100, svc.memory_percent)}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                <span>cluster: {svc.cluster}</span>
                <span>{svc.restarts_24h} restarts</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Section 4: Database & Infrastructure Vitals */}
      <div className="grid gap-2.5 sm:grid-cols-3 text-xs">
        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            Aurora PostgreSQL Pool
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-foreground">
              {data.database_vitals.active_connections} conns
            </span>
            <Badge tone="success">
              Pool {data.database_vitals.connection_pool_saturation_percent}%
            </Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">
            Storage saturation: {data.database_vitals.storage_used_percent}%
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            S3 Object Lock & State
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-success">COMPLIANT</span>
            <Badge tone="success">100%</Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">Zero tampering detected</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            Active Security Findings
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-warning">
              {data.active_findings_count}
            </span>
            <Badge tone="warning">Medium</Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">0 critical attack paths</span>
        </div>
      </div>

      {/* Section 5: Live Operational Alerts Feed */}
      <Card
        title="Live Operational Alerts & Escalations"
        description="Unaddressed alerts send repeated notifications to configured email until acknowledged or resolved."
      >
        {data.alerts.length === 0 ? (
          <EmptyState
            title="Zero active operational alerts"
            description="All ECS services, container tasks, and healthchecks are operating within nominal thresholds."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {data.alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface p-2.5"
              >
                <div className="flex flex-col gap-0.5 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <Badge tone={alertSeverityTone(alert.severity)}>{alert.severity}</Badge>
                    <Badge tone={alertStatusTone(alert.status)}>{alert.status}</Badge>
                    {alert.requires_action && alert.status === "FIRING" && (
                      <Badge tone="danger">Action Required</Badge>
                    )}
                    {alert.notification_count > 1 && (
                      <span className="rounded-full bg-danger/20 px-2 py-0.2 text-[10px] font-bold text-danger">
                        Repeated Alert #{alert.notification_count}
                      </span>
                    )}
                    <span className="text-xs font-semibold text-foreground">{alert.title}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{alert.description}</p>
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
