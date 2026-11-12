import type { BadgeTone } from "@argus/ui";

export type CostConfidence = "exact" | "allocated" | "estimated" | "unknown";

export interface CostPeriod {
  start: string;
  end: string;
}

export interface CostGroup {
  dimension: string;
  value: string;
  amount: number;
}

export interface CostSummary {
  period: CostPeriod;
  currency: string;
  total: number;
  allocated: number;
  unallocated: number;
  as_of: string;
  source_lag_hours: number;
  groups: CostGroup[];
}

export interface CostBreakdownItem {
  label: string;
  amount: number;
}

export interface CostBreakdown {
  dimension: string;
  period_days: number;
  currency: string;
  total: number;
  items: CostBreakdownItem[];
}

export interface CostTrendPoint {
  date: string;
  amount: number;
}

export interface CostTrend {
  currency: string;
  points: CostTrendPoint[];
  average_daily: number;
  forecast_monthly: number;
}

export interface ResourceCost {
  resource_id: string;
  monthly_amount: number;
  currency: string;
  confidence: CostConfidence;
  method: string;
  as_of?: string;
}

export interface TopSpenders {
  currency: string;
  resources: ResourceCost[];
}

export interface CostRecommendation {
  id: string;
  rule: string;
  resource_id: string;
  resource_type: string;
  title: string;
  description: string;
  confidence: "high" | "medium" | "low";
  evidence: Record<string, unknown>;
  estimated_monthly_savings: number;
  currency: string;
  status: "OPEN" | "ACKNOWLEDGED" | "DISMISSED" | "REMEDIATED";
  remediation: {
    action_type: string;
    action_id: string | null;
  } | null;
  first_seen: string;
  last_seen: string;
}

export interface CostBudget {
  id: string;
  name: string;
  scope_type: string;
  scope_value: string | null;
  threshold_amount: number;
  period: string;
  current_spend: number;
  percent_used: number;
  is_exceeded: boolean;
  notification_channel: string | null;
  enabled: boolean;
}

export function confidenceTone(confidence: CostConfidence): BadgeTone {
  switch (confidence) {
    case "exact":
      return "success";
    case "allocated":
      return "info";
    case "estimated":
      return "warning";
    case "unknown":
    default:
      return "neutral";
  }
}

export function formatCurrency(amount: number, currency: string = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
