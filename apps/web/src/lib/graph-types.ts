import type { Severity } from "./finding-types";

export interface NodeSecurityOverlay {
  resource_id: string;
  max_severity: Severity;
  open_count: number;
  rule_ids: string[];
  statuses: string[];
}

export interface NodeMetricPoint {
  timestamp: number;
  value: number;
}

export interface NodeTelemetry {
  resource_id: string;
  metric: string;
  unit: string;
  resolution: number;
  points: NodeMetricPoint[];
  anomalies: Array<{
    kind: string;
    severity: string;
    message: string;
    value: number;
    threshold: number | null;
    z_score: number | null;
  }>;
}

export interface NodeCost {
  monthly_amount: number;
  currency: string;
  confidence: "exact" | "allocated" | "estimated" | "unknown";
  method: string;
}

export interface TopologyNode {
  id: string;
  type: string;
  name: string;
  account_id: string;
  region: string;
  state: string;
  parent_id?: string | null;
  tags?: Record<string, string>;
  version: number;
  properties?: Record<string, unknown>;
  isPulsing?: boolean;
  security?: NodeSecurityOverlay;
  telemetry?: NodeTelemetry;
  cost?: NodeCost;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  properties?: Record<string, unknown>;
}

export interface TopologyGroup {
  id: string;
  type: string;
  name: string;
  parent_id?: string | null;
  child_count: number;
}

export interface TopologySlice {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  groups: TopologyGroup[];
  counts: {
    nodes: number;
    edges: number;
    truncated?: boolean;
  };
  as_of: string;
  seq: number;
}
