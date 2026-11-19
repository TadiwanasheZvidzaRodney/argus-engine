import type { BadgeTone } from "@argus/ui";

export interface StatusBanner {
  state: "ALL_CLEAR" | "ALERTS_FIRING";
  message: string;
  firing_alerts_count: number;
  as_of: string;
}

export interface GoldenSignals {
  availability_percent: number;
  throughput_req_min: number;
  latency_p95_ms: number;
  error_rate_percent: number;
  errors_5xx_count: number;
}

export interface EcsSystemItem {
  name: string;
  cluster: string;
  desired_tasks: number;
  running_tasks: number;
  cpu_percent: number;
  memory_percent: number;
  restarts_24h: number;
  status: "healthy" | "degraded";
}

export interface DatabaseVitals {
  active_connections: number;
  connection_pool_saturation_percent: number;
  storage_used_percent: number;
  status: "UP" | "DOWN" | "NOT_DEPLOYED";
}

export interface AlbVitals {
  target_response_time_sec: number;
  healthy_hosts: number;
  unhealthy_hosts: number;
  status: "UP" | "DOWN" | "NOT_DEPLOYED";
}

export interface OpsAlertItem {
  id: string;
  alert_key: string;
  severity: "critical" | "warning" | "info";
  title: string;
  description: string;
  source: string;
  resource_id: string | null;
  status: "FIRING" | "ACKNOWLEDGED" | "RESOLVED";
  requires_action: boolean;
  notification_count: number;
  notification_email: string;
  created_at: string;
  last_notified_at: string;
}

export type TimeRangeOption = "today" | "24h" | "7d" | "30d";

export interface TelemetryPoint {
  timestamp: string;
  time_label: string;
  availability_percent: number;
  throughput_req_min: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  error_rate_percent: number;
  errors_5xx_count: number;
  ecs_running_tasks: number;
  db_pool_errors: number;
  db_pool_saturation_percent: number;
}

export interface OpsWallboardData {
  status_banner: StatusBanner;
  golden_signals: GoldenSignals;
  telemetry_history: TelemetryPoint[];
  time_range: TimeRangeOption;
  ecs_systems: EcsSystemItem[];
  database_vitals: DatabaseVitals;
  alb_vitals: AlbVitals;
  active_findings_count: number;
  s3_buckets_count?: number;
  total_resources_count?: number;
  alerts: OpsAlertItem[];
}

export function alertSeverityTone(severity: string): BadgeTone {
  switch (severity) {
    case "critical":
      return "danger";
    case "warning":
      return "warning";
    default:
      return "info";
  }
}

export function alertStatusTone(status: string): BadgeTone {
  switch (status) {
    case "FIRING":
      return "danger";
    case "ACKNOWLEDGED":
      return "warning";
    case "RESOLVED":
      return "success";
    default:
      return "neutral";
  }
}
