import type { BadgeTone } from "@argus/ui";

export type Severity = "critical" | "high" | "medium" | "low";
export type FindingStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "RISK_ACCEPTED" | "SUPPRESSED";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface FindingSummary {
  id: string;
  rule_id: string;
  rule_version: string;
  severity: Severity;
  status: FindingStatus;
  title: string;
  resource_id: string;
  resource_type: string;
  account_id: string | null;
  region: string | null;
  finding_key: string;
  assignee_id: string | null;
  remediation_action: string | null;
  remediation_action_id: string | null;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  created_at: string;
}

export interface FindingEvent {
  id: string;
  event_type: string;
  actor_id: string | null;
  from_status: string | null;
  to_status: string | null;
  comment: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface FindingDetail extends FindingSummary {
  description: string;
  evidence: Record<string, unknown>;
  evidence_hash: string;
  risk_accepted_until: string | null;
  events: FindingEvent[];
  suppression: {
    id: string;
    owner_id: string;
    reason: string;
    expires_at: string;
    created_at: string;
  } | null;
  remediation: { action_type: string; action_id: string | null } | null;
}

export interface SecuritySummary {
  total: number;
  open_total: number;
  by_severity: Record<string, number>;
  open_by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_account: Record<string, number>;
  by_region: Record<string, number>;
  by_rule: Record<string, number>;
  trend: Array<{ date: string; opened: number; resolved: number }>;
  top_risks: Array<{
    id: string;
    rule_id: string;
    severity: Severity;
    status: FindingStatus;
    title: string;
    resource_id: string;
    first_seen: string;
  }>;
}

export interface AttackPathHop {
  node_id: string;
  name: string;
  type: string;
  edge_type: string;
  why: string;
  evidence: Record<string, unknown>;
}

export interface AttackPath {
  hops: AttackPathHop[];
  severity: Severity;
  score: number;
  evidence: Record<string, unknown>;
}

export interface AttackPathResponse {
  source: string;
  paths: AttackPath[];
  count: number;
  truncated: boolean;
  evaluated_nodes: number;
  generated_at: string;
  cached: boolean;
}

export interface SecurityOverlay {
  resources: Record<
    string,
    {
      resource_id: string;
      max_severity: Severity;
      open_count: number;
      rule_ids: string[];
      statuses: FindingStatus[];
    }
  >;
  counts: { resources_with_findings: number; findings: number };
}

export function severityTone(severity: Severity): BadgeTone {
  switch (severity) {
    case "critical":
      return "danger";
    case "high":
      return "warning";
    case "medium":
      return "info";
    default:
      return "neutral";
  }
}

export function findingStatusTone(status: FindingStatus): BadgeTone {
  switch (status) {
    case "OPEN":
      return "danger";
    case "ACKNOWLEDGED":
      return "warning";
    case "RISK_ACCEPTED":
      return "info";
    case "SUPPRESSED":
      return "neutral";
    case "RESOLVED":
      return "success";
  }
}

export function severityRank(severity: Severity): number {
  return { critical: 4, high: 3, medium: 2, low: 1 }[severity];
}
