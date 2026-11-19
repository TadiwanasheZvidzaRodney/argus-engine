import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SecurityPage from "@/app/(app)/security/page";
import { apiFetch } from "@/lib/api";
import type { SecurityDashboardData } from "@/lib/security-types";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("@/components/findings/scan-controls", () => ({
  ScanControls: () => <button>Run security scan</button>,
}));
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    scroll: _scroll,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    scroll?: boolean;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const timestamp = "2026-11-18T14:30:00+00:00";
function data(): SecurityDashboardData {
  return {
    total: 1,
    open_total: 1,
    by_severity: { high: 1 },
    open_by_severity: { high: 1 },
    by_status: { OPEN: 1 },
    by_account: {},
    by_region: {},
    by_rule: { "iam-old-access-key": 1 },
    trend: [],
    top_risks: [],
    generated_at: timestamp,
    source: "Stored records.",
    time_range: "7d",
    window_start: "2026-11-11T14:30:00+00:00",
    window_end: timestamp,
    timezone: "UTC",
    observed_since: timestamp,
    history_partial: false,
    trend_history: [
      {
        timestamp,
        bucket_start: "2026-11-17T14:30:00+00:00",
        opened: 1,
        resolved: 0,
        active: 1,
        critical: 0,
        high: 1,
        medium: 0,
        low: 0,
        transitions: 1,
      },
    ],
    posture: {
      score: 92,
      grade: "A",
      last_finding_observed_at: timestamp,
      stale: false,
      graph_available: true,
      resources_observed: 1,
      score_method: "A heuristic, not certification.",
      domains: [
        {
          id: "iam",
          label: "IAM & access hygiene",
          score: 92,
          resources_observed: 1,
          open_findings: 1,
          status: "recorded_findings",
        },
      ],
    },
    attack_paths: {
      count: 1,
      cached: false,
      truncated: false,
      source: "internet",
      evaluated_nodes: 3,
      generated_at: timestamp,
      paths: [
        {
          score: 80,
          severity: "high",
          evidence: {},
          hops: [
            {
              node_id: "arn:aws:s3:::test-bucket",
              name: "test-bucket",
              type: "AWS::S3::Bucket",
              edge_type: "PUBLIC_POLICY",
              why: "Public policy",
              evidence: {},
            },
          ],
        },
      ],
    },
  };
}

describe("Security dashboard page", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("loads selected history and renders charts, score and real canvas deep links", async () => {
    vi.mocked(apiFetch).mockResolvedValue(data());
    render(await SecurityPage({ searchParams: Promise.resolve({ range: "7d" }) }));
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/security/summary?range=7d", expect.anything());
    expect(screen.getByRole("link", { name: "7 Days" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "92");
    expect(screen.getByRole("img", { name: "Open risk backlog" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open attack chain in canvas/ })).toHaveAttribute(
      "href",
      "/topology?root=arn%3Aaws%3As3%3A%3A%3Atest-bucket",
    );
  });

  it("does not claim healthy zero findings or grade A on API failure", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error("offline"));
    render(await SecurityPage({ searchParams: Promise.resolve({ range: "invalid" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("Security data unavailable");
    expect(screen.getByRole("meter")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText("Grade A")).not.toBeInTheDocument();
    expect(screen.getByText("Attack path analysis unavailable")).toBeInTheDocument();
  });

  it("labels stale findings and graph outages independently", async () => {
    const summary = data();
    summary.posture.stale = true;
    summary.posture.graph_available = false;
    summary.posture.score = null;
    summary.posture.grade = null;
    summary.attack_paths = null;
    vi.mocked(apiFetch).mockResolvedValue(summary);
    render(await SecurityPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(/Finding evidence is older than 24 hours/)).toBeInTheDocument();
    expect(screen.getByText(/Graph unavailable:/)).toBeInTheDocument();
    expect(screen.queryByText(/No paths found/)).not.toBeInTheDocument();
  });
});
