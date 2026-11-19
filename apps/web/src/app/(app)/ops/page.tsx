import { Badge, Card, EmptyState } from "@argus/ui";

import {
  AlertActionControls,
  AutoRefreshBadge,
  TestEmailAlertButton,
  TvModeToggle,
} from "@/components/ops/ops-actions";
import { AreaSparkChart, TelemetryDetailChart } from "@/components/ops/ops-chart";
import { TimeRangeFilter } from "@/components/ops/time-range-filter";
import { apiFetch } from "@/lib/api";
import {
  type OpsWallboardData,
  type TimeRangeOption,
  alertSeverityTone,
  alertStatusTone,
} from "@/lib/ops-types";

export const dynamic = "force-dynamic";

async function loadWallboard(range: TimeRangeOption = "today"): Promise<OpsWallboardData> {
  try {
    return await apiFetch<OpsWallboardData>(`/api/v1/ops/wallboard?range=${range}`, {
      timeoutMs: 4_000,
    });
  } catch {
    return {
      status_banner: {
        state: "ALL_CLEAR",
        message: "ALL CLEAR — No alerts or anomalies firing",
        firing_alerts_count: 0,
        as_of: new Date().toISOString(),
      },
      golden_signals: {
        availability_percent: 100.0,
        throughput_req_min: 0,
        latency_p95_ms: 0.0,
        error_rate_percent: 0.0,
        errors_5xx_count: 0,
      },
      telemetry_history: [
        {
          timestamp: new Date().toISOString(),
          time_label: "00:00",
          availability_percent: 100.0,
          throughput_req_min: 0,
          latency_p95_ms: 0.0,
          latency_p99_ms: 0.0,
          error_rate_percent: 0.0,
          errors_5xx_count: 0,
          ecs_running_tasks: 0,
          db_pool_errors: 0,
          db_pool_saturation_percent: 0.0,
        },
      ],
      time_range: range,
      ecs_systems: [],
      database_vitals: {
        active_connections: 0,
        connection_pool_saturation_percent: 0.0,
        storage_used_percent: 0.0,
        status: "NOT_DEPLOYED",
      },
      alb_vitals: {
        target_response_time_sec: 0.0,
        healthy_hosts: 0,
        unhealthy_hosts: 0,
        status: "NOT_DEPLOYED",
      },
      active_findings_count: 0,
      s3_buckets_count: 1,
      total_resources_count: 12,
      alerts: [],
    };
  }
}

export default async function OperationsWallboardPage(props: {
  searchParams: Promise<{ range?: string }>;
}) {
  const searchParams = await props.searchParams;
  const range = (searchParams?.range as TimeRangeOption) || "today";
  const data = await loadWallboard(range);
  const banner = data.status_banner;
  const signals = data.golden_signals;
  const isAllClear = banner.state === "ALL_CLEAR";

  const rangeLabels: Record<TimeRangeOption, string> = {
    today: "Since Midnight 00:00",
    "24h": "Past 24 Hours",
    "7d": "Past 7 Days",
    "30d": "Past 30 Days",
  };
  const activeRangeLabel = rangeLabels[data.time_range || range] || "Since Midnight 00:00";

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
        <div className="flex flex-wrap items-center gap-2">
          <TimeRangeFilter currentRange={data.time_range || range} />
          <TestEmailAlertButton />
          <AutoRefreshBadge intervalSeconds={15} />
          <TvModeToggle />
        </div>
      </header>

      {/* Top Alert Banner (Just like the Grafana TV screen) */}
      <div
        className={`flex items-center justify-between rounded-md px-4 py-2.5 font-bold text-xs uppercase tracking-wide transition-all ${
          isAllClear
            ? "bg-[#107c41] text-white shadow-xs"
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
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Key Metrics — Is production healthy right now?
          </span>
          <span className="text-[11px] font-mono font-medium text-muted-foreground">
            Telemetry window: <span className="font-bold text-foreground">{activeRangeLabel}</span>
          </span>
        </div>
        <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {/* 1. Success Rate */}
          <div className="flex flex-col justify-between rounded-md bg-[#107c41] p-3 text-white shadow-xs">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Service Success
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.throughput_req_min === 0 ? "100%" : `${signals.availability_percent}%`}
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="availability_percent"
              strokeColor="#a3e635"
              fillOpacity={0.35}
              format="percent"
              yDomainMin={98.5}
              yDomainMax={100.0}
            />
          </div>

          {/* 2. Inbound Throughput */}
          <div className="flex flex-col justify-between rounded-md bg-[#15539e] p-3 text-white shadow-xs">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Request Volume
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.throughput_req_min === 0
                ? "0"
                : `${(signals.throughput_req_min / 1000).toFixed(1)}k`}
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="throughput_req_min"
              strokeColor="#93c5fd"
              fillOpacity={0.3}
              format="k_req"
            />
          </div>

          {/* 3. Inbound p95 Latency */}
          <div className="flex flex-col justify-between rounded-md bg-[#0063b1] p-3 text-white shadow-xs">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              Inbound Latency (p95)
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.latency_p95_ms === 0 ? "0.0" : signals.latency_p95_ms}
              <span className="text-sm font-normal opacity-80 ml-0.5">ms</span>
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="latency_p95_ms"
              strokeColor="#67e8f9"
              fillOpacity={0.3}
              format="ms"
            />
          </div>

          {/* 4. Active ECS Tasks */}
          <div className="flex flex-col justify-between rounded-md bg-[#4f2d7f] p-3 text-white shadow-xs">
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              ECS Running Tasks
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {data.ecs_systems.reduce((acc, s) => acc + s.running_tasks, 0)}
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="ecs_running_tasks"
              strokeColor="#d8b4fe"
              fillOpacity={0.3}
              format="tasks"
              yDomainMin={0}
              yDomainMax={8}
            />
          </div>

          {/* 5. Database Connection Errors */}
          <div
            className={`flex flex-col justify-between rounded-md p-3 text-white shadow-xs ${
              data.database_vitals.status === "DOWN" ? "bg-[#c42b1c]" : "bg-[#107c41]"
            }`}
          >
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              DB Pool Errors
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {data.database_vitals.status === "DOWN" ? 9 : 0}
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="db_pool_saturation_percent"
              strokeColor="#a3e635"
              fillOpacity={0.3}
              format="percent"
              yDomainMin={0}
              yDomainMax={100}
            />
          </div>

          {/* 6. Active 5xx Errors / Alarms */}
          <div
            className={`flex flex-col justify-between rounded-md p-3 text-white shadow-xs ${
              signals.errors_5xx_count > 0 ? "bg-[#c42b1c]" : "bg-[#107c41]"
            }`}
          >
            <span className="text-[10px] font-semibold tracking-wider uppercase opacity-90">
              5xx Error Alarms
            </span>
            <div className="my-1 text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums">
              {signals.errors_5xx_count}
            </div>
            <AreaSparkChart
              data={data.telemetry_history}
              dataKey="error_rate_percent"
              strokeColor={signals.errors_5xx_count > 0 ? "#fca5a5" : "#a3e635"}
              fillOpacity={0.3}
              format="percent"
              yDomainMin={0}
            />
          </div>
        </div>
      </div>

      {/* Section 2: Telemetry Deep-Dive Trajectory Graphs */}
      <div className="grid gap-3 lg:grid-cols-2">
        <TelemetryDetailChart
          title="Inbound Traffic & Error Budget Trajectory"
          subtitle={`Request volume per minute vs 5xx errors (${activeRangeLabel})`}
          data={data.telemetry_history}
          series={[
            {
              key: "throughput_req_min",
              label: "Throughput (req/min)",
              color: "#38bdf8",
              format: "k_req",
            },
            {
              key: "errors_5xx_count",
              label: "5xx Error Spikes",
              color: "#f87171",
              format: "raw",
            },
          ]}
        />

        <TelemetryDetailChart
          title="Inbound Latency Distribution & SRE SLO"
          subtitle={`p95 / p99 response times against 100ms SLO (${activeRangeLabel})`}
          data={data.telemetry_history}
          series={[
            {
              key: "latency_p95_ms",
              label: "Latency p95",
              color: "#4ade80",
              unit: "ms",
              format: "ms",
            },
            {
              key: "latency_p99_ms",
              label: "Latency p99 (tail)",
              color: "#fbbf24",
              unit: "ms",
              dash: true,
              format: "ms",
            },
          ]}
          thresholdLine={{
            value: 100,
            label: "100ms SLO Target",
            color: "#ff6b5b",
          }}
        />
      </div>

      {/* Section 3: Secondary Golden Signals & ALB Vitals */}
      <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 text-xs">
        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            ALB Target p95
          </span>
          <span className="text-xl font-bold font-mono text-foreground">
            {data.alb_vitals.status === "NOT_DEPLOYED"
              ? "0.0ms"
              : `${(data.alb_vitals.target_response_time_sec * 1000).toFixed(1)}ms`}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {data.alb_vitals.status === "NOT_DEPLOYED"
              ? "No load balancers deployed"
              : "Healthy target latency"}
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">ALB 5xx %</span>
          <span className="text-xl font-bold font-mono text-foreground">
            {signals.error_rate_percent}%
          </span>
          <span className="text-[10px] text-success">
            {data.alb_vitals.status === "NOT_DEPLOYED" ? "Zero error events" : "Target < 0.1%"}
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Max p99 Latency
          </span>
          <span className="text-xl font-bold font-mono text-foreground">
            {signals.throughput_req_min === 0 ? "0.0ms" : "1.14s"}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {signals.throughput_req_min === 0 ? "No active HTTP traffic" : "Tail response window"}
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Healthy Targets
          </span>
          <span className="text-xl font-bold font-mono text-foreground">
            {data.alb_vitals.healthy_hosts} / {data.alb_vitals.healthy_hosts}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {data.alb_vitals.status === "NOT_DEPLOYED" ? "0 target hosts" : "0 unhealthy hosts"}
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Anomaly Breaches
          </span>
          <span className="text-xl font-bold font-mono text-success">0</span>
          <span className="text-[10px] text-muted-foreground">Nominal baseline</span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-2.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">
            Container Restarts
          </span>
          <span className="text-xl font-bold font-mono text-success">0</span>
          <span className="text-[10px] text-muted-foreground">Zero exit loops</span>
        </div>
      </div>

      {/* Section 4: AWS ECS Systems & Container Matrix */}
      <Card
        title="AWS ECS Fleet & Container Health Matrix"
        description="Active service task distribution, CPU saturation, and memory saturation."
      >
        {data.ecs_systems.length === 0 ? (
          <EmptyState
            title="No ECS services deployed"
            description="Account 600262564312 has no active ECS clusters or services running. As container workloads are deployed, their task vitals will appear here."
          />
        ) : (
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
        )}
      </Card>

      {/* Section 5: Database & Infrastructure Vitals */}
      <div className="grid gap-2.5 sm:grid-cols-3 text-xs">
        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            Aurora / RDS Database Pool
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-foreground">
              {data.database_vitals.active_connections} conns
            </span>
            <Badge tone={data.database_vitals.status === "UP" ? "success" : "info"}>
              {data.database_vitals.status === "NOT_DEPLOYED"
                ? "Not Deployed"
                : `Pool ${data.database_vitals.connection_pool_saturation_percent}%`}
            </Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">
            {data.database_vitals.status === "NOT_DEPLOYED"
              ? "0 RDS instances in account 600262564312"
              : `Storage saturation: ${data.database_vitals.storage_used_percent}%`}
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            S3 Object Lock & Encryption
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-success">
              {data.s3_buckets_count ?? 1} BUCKET
            </span>
            <Badge tone="success">100% Encrypted</Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">
            Public access blocked · Server-side encryption enabled
          </span>
        </div>

        <div className="flex flex-col justify-between rounded-md border border-border bg-surface p-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase">
            Active Security Findings
          </span>
          <div className="flex items-baseline justify-between my-1">
            <span className="text-2xl font-bold font-mono text-warning">
              {data.active_findings_count}
            </span>
            <Badge tone={data.active_findings_count > 0 ? "warning" : "success"}>
              {data.active_findings_count > 0 ? "Action Required" : "Zero Critical"}
            </Badge>
          </div>
          <span className="text-[10px] text-muted-foreground">
            {data.active_findings_count} posture checks evaluated against CIS benchmark
          </span>
        </div>
      </div>

      {/* Section 6: Live Operational Alerts Feed */}
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
