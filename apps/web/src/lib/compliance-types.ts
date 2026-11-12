import type { BadgeTone } from "@argus/ui";

export interface ComplianceFramework {
  framework: string;
  total_controls: number;
  passed_controls: number;
  failed_controls: number;
  compliance_score_percent: number;
  status: "COMPLIANT" | "DEFICIENCIES_DETECTED";
}

export interface ComplianceControl {
  id: string;
  framework: string;
  control_id: string;
  title: string;
  description: string;
  domain: string;
  severity: "critical" | "high" | "medium" | "low";
  automated: boolean;
  rule_mappings: string[];
  status: "PASS" | "FAIL" | "WARN" | "NOT_EVALUATED";
  evidence_hash: string | null;
  collected_at: string | null;
}

export interface SystemSlo {
  slo_name: string;
  target_percent: number;
  current_percent: number;
  error_budget_burn_percent: number;
  status: "healthy" | "warning" | "critical";
  window_days: number;
  updated_at: string | null;
}

export interface DegradedModeState {
  read_only: boolean;
  live_paused: boolean;
  telemetry_paused: boolean;
  actions_disabled: boolean;
  maintenance_message: string | null;
  is_degraded: boolean;
  updated_at: string | null;
}

export interface SystemStatusReport {
  overall_status: "OPERATIONAL" | "DEGRADED";
  degraded_mode: DegradedModeState;
  slos: SystemSlo[];
  dependencies: Array<{ name: string; status: "UP" | "DOWN" }>;
}

export interface UsageMeteringRecord {
  period_date: string;
  resources_count: number;
  events_ingested: number;
  metric_requests: number;
  actions_planned: number;
  actions_executed: number;
  storage_bytes: number;
  estimated_cost_usd: number;
}

export interface DrCheck {
  component: string;
  metric: string;
  target: string;
  measured: string;
  status: "PASS" | "FAIL";
  details: string;
}

export interface DisasterRecoveryReport {
  drill_id: string;
  timestamp: string;
  primary_region: string;
  recovery_region: string;
  overall_status: "SUCCESS" | "FAIL";
  rto_achieved_minutes: number;
  rpo_achieved_minutes: number;
  checks: DrCheck[];
}

export function complianceStatusTone(status: string): BadgeTone {
  switch (status) {
    case "PASS":
    case "COMPLIANT":
    case "OPERATIONAL":
    case "SUCCESS":
    case "healthy":
      return "success";
    case "WARN":
    case "warning":
      return "warning";
    case "FAIL":
    case "DEFICIENCIES_DETECTED":
    case "critical":
    case "DEGRADED":
      return "danger";
    default:
      return "neutral";
  }
}
