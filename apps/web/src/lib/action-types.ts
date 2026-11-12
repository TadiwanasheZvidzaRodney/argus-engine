export type RiskLevel = "low" | "medium" | "high" | "critical";

export type ActionStatus =
  | "DRAFT"
  | "PLANNING"
  | "PLAN_READY"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "EXECUTING"
  | "VERIFYING"
  | "SUCCEEDED"
  | "PLAN_FAILED"
  | "REJECTED"
  | "EXPIRED"
  | "CANCELLED"
  | "FAILED"
  | "ROLLING_BACK"
  | "ROLLED_BACK"
  | "ROLLBACK_FAILED";

export interface CatalogItem {
  action_type: string;
  category: string;
  name: string;
  description: string;
  risk_level: RiskLevel;
  required_permissions: string[];
  plan_template: string;
  rollback_template: string;
  reversible: boolean;
  max_blast_radius: number;
  enabled: boolean;
  version: string;
}

export interface PlanView {
  id: string;
  plan_hash: string;
  graph_version: number;
  template_version: string;
  summary: string;
  risk: {
    level: RiskLevel;
    blast_radius: number;
    reversible: boolean;
    reasons: string[];
  };
  changes: Array<{
    resource: string;
    operation: string;
    attribute: string;
    before_hash: string;
    after_hash: string;
    description: string;
  }>;
  permissions: string[];
  diff: {
    affected_resources: string[];
    changed_attributes: Array<{
      resource: string;
      attribute: string;
      operation: string;
      before_hash: string;
      after_hash: string;
    }>;
  };
  rollback: {
    strategy: string;
    template: string;
    artifact: string;
    expires_at: string;
  };
  blast_radius: number;
  approved_hash: string | null;
  expires_at: string;
  created_at: string;
}

export interface ApprovalView {
  id: string;
  approver_id: string;
  approver_email: string;
  decision: "approved" | "rejected";
  comment: string | null;
  plan_hash: string;
  mfa_at: string | null;
  created_at: string;
}

export interface ExecutionView {
  id: string;
  status: string;
  error: string | null;
  rollback_status: string;
  verification: {
    status?: string;
    checked_resources?: number;
    checks?: Array<Record<string, unknown>>;
    rollback?: Record<string, unknown>;
  };
  started_at: string;
  completed_at: string | null;
}

export interface ActionDetail {
  id: string;
  action_type: string;
  status: ActionStatus;
  requester_id: string;
  targets: {
    source?: string | null;
    target?: string | null;
    resources?: string[];
  };
  parameters: Record<string, unknown>;
  constraints: {
    environment?: string;
    maintenance_window?: boolean;
    break_glass?: boolean;
    incident_id?: string | null;
  };
  justification: string;
  risk_level: RiskLevel;
  graph_version: number;
  plan: PlanView | null;
  approvals: ApprovalView[];
  executions: ExecutionView[];
  created_at: string;
  updated_at: string;
}

export interface ActionSummary {
  id: string;
  action_type: string;
  status: ActionStatus;
  requester_id: string;
  risk_level: RiskLevel;
  justification: string;
  plan_hash: string | null;
  summary: string | null;
  blast_radius: number | null;
  expires_at: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more?: boolean;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  uri: string;
  checksum: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface GuardrailRule {
  name: string;
  rule_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  version: string;
}

export interface KillSwitchState {
  tenant_enabled: boolean;
  global_enabled: boolean;
  reasons: string[];
}

export interface ParsedIntent {
  action_type: string | null;
  confidence: number;
  targets: Record<string, unknown>;
  parameters: Record<string, unknown>;
  constraints: Record<string, unknown>;
  rationale: string;
  rejected: boolean;
  rejection_reason: string | null;
}

export function statusTone(
  status: ActionStatus,
): "neutral" | "info" | "success" | "warning" | "danger" {
  switch (status) {
    case "SUCCEEDED":
      return "success";
    case "APPROVED":
      return "info";
    case "PENDING_APPROVAL":
    case "EXECUTING":
    case "VERIFYING":
    case "ROLLING_BACK":
      return "warning";
    case "FAILED":
    case "ROLLBACK_FAILED":
    case "REJECTED":
      return "danger";
    default:
      return "neutral";
  }
}

export function riskTone(level: RiskLevel): "neutral" | "info" | "success" | "warning" | "danger" {
  switch (level) {
    case "low":
      return "success";
    case "medium":
      return "warning";
    default:
      return "danger";
  }
}
