import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HistoryChart } from "@/components/security/history-chart";
import { type SecurityHistoryPoint, parseSecurityRange, securityTime } from "@/lib/security-types";

function point(hour: number, active: number | null): SecurityHistoryPoint {
  return {
    timestamp: `2026-11-18T${String(hour).padStart(2, "0")}:00:00+00:00`,
    bucket_start: `2026-11-18T${String(hour - 1).padStart(2, "0")}:00:00+00:00`,
    active,
    high: active,
    critical: active,
    medium: active,
    low: active,
    opened: active,
    resolved: active,
    transitions: active,
  };
}

describe("Security history", () => {
  it("does not turn missing history into zeroes", () => {
    render(
      <HistoryChart
        title="Unknown"
        points={[point(1, null)]}
        series={[{ key: "active", label: "Open", color: "#e05252" }]}
      />,
    );
    expect(screen.getByText("No recorded history")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("preserves genuine zeroes and offers keyboard-accessible inspection", () => {
    render(
      <HistoryChart
        title="Risk backlog"
        points={[point(1, 0), point(2, 3)]}
        series={[{ key: "active", label: "Open", color: "#e05252" }]}
      />,
    );
    expect(screen.getByRole("img", { name: "Risk backlog" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("slider", { name: "Inspect Risk backlog" }), {
      target: { value: "0" },
    });
    expect(screen.getByRole("status")).toHaveTextContent("Open: 0");
    expect(screen.getByRole("status")).toHaveTextContent("2026-11-18 01:00 UTC");
  });

  it("splits paths at missing samples without NaN or fabricated connections", () => {
    const { container } = render(
      <HistoryChart
        title="Gaps"
        points={[point(1, 2), point(2, null), point(3, 1)]}
        series={[{ key: "active", label: "Open", color: "#e05252" }]}
      />,
    );
    const paths = container.querySelectorAll("path[data-series=active]");
    expect(paths).toHaveLength(2);
    for (const path of paths) expect(path.getAttribute("d")).not.toMatch(/NaN|undefined|Infinity/);
  });

  it("validates ranges and formats times independently of local timezone", () => {
    expect(parseSecurityRange("7d")).toBe("7d");
    expect(parseSecurityRange("invalid")).toBe("today");
    expect(parseSecurityRange(["7d", "30d"])).toBe("today");
    expect(securityTime("2026-11-18T01:00:00Z")).toBe("2026-11-18 01:00 UTC");
  });
});
