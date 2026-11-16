import type { BadgeTone } from "@argus/ui";

export interface GitRepository {
  id: string;
  provider: string;
  repo_url: string;
  default_branch: string;
  iac_path: string;
  status: string;
  created_at: string;
}

export interface IacDriftRecord {
  id: string;
  resource_id: string;
  resource_type: string;
  iac_file_path: string;
  iac_block_type: string;
  iac_block_name: string;
  drift_details: {
    drift_type: string;
    severity: "critical" | "high" | "medium" | "low";
    message: string;
    live_value: unknown;
    expected_iac_value: unknown;
  };
  status: "DRIFTED" | "IN_SYNC" | "RECONCILED";
  detected_at: string;
}

export interface IacPullRequest {
  id: string;
  action_id: string | null;
  repo_id: string;
  pr_url: string;
  pr_number: number;
  title: string;
  branch_name: string;
  hcl_diff: string;
  status: "OPEN" | "MERGED" | "CLOSED";
  created_at: string;
}

export function driftSeverityTone(severity: string): BadgeTone {
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

export function prStatusTone(status: string): BadgeTone {
  switch (status) {
    case "MERGED":
      return "success";
    case "OPEN":
      return "info";
    case "CLOSED":
    default:
      return "neutral";
  }
}
