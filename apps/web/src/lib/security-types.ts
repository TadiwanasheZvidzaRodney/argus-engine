import type { AttackPathResponse, SecuritySummary, Severity } from "@/lib/finding-types";

export const SECURITY_RANGES = [
  { value: "today", label: "Today (00:00 UTC)" },
  { value: "24h", label: "Last 24h" },
  { value: "7d", label: "7 Days" },
  { value: "14d", label: "14 Days" },
  { value: "30d", label: "30 Days" },
] as const;

export type SecurityRange = (typeof SECURITY_RANGES)[number]["value"];
export type HistoryMetric = Severity | "opened" | "resolved" | "active" | "transitions";

export type SecurityHistoryPoint = {
  timestamp: string;
  bucket_start: string;
} & Record<HistoryMetric, number | null>;

export interface SecurityDashboardData extends SecuritySummary {
  generated_at: string;
  source: string;
  time_range: SecurityRange;
  window_start: string;
  window_end: string;
  timezone: "UTC";
  observed_since: string | null;
  history_partial: boolean;
  trend_history: SecurityHistoryPoint[];
  attack_paths: AttackPathResponse | null;
  posture: {
    score: number | null;
    grade: string | null;
    last_finding_observed_at: string | null;
    stale: boolean;
    graph_available: boolean;
    resources_observed: number | null;
    score_method: string;
    domains: Array<{
      id: string;
      label: string;
      score: number | null;
      resources_observed: number | null;
      open_findings: number;
      status: "recorded_findings" | "coverage_unverified";
    }>;
  };
}

export function parseSecurityRange(range: string | string[] | undefined): SecurityRange {
  return SECURITY_RANGES.find((option) => option.value === range)?.value ?? "today";
}

export function securityTime(iso: string): string {
  // Identical on the server and client; never rely on the host timezone/locale.
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}
