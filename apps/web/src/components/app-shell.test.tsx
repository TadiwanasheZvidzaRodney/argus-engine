import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { DEMO_SESSION } from "@/lib/session";

const usePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathname(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("AppShell", () => {
  beforeEach(() => {
    usePathname.mockReturnValue("/overview");
  });

  it("renders closed dropdowns by default and opens subtabs on click", async () => {
    const user = userEvent.setup();
    render(
      <AppShell session={DEMO_SESSION} onSignOut={async () => {}}>
        <p>content</p>
      </AppShell>,
    );

    // Closed by default
    expect(screen.queryByRole("link", { name: "Topology" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Overview" })).toBeNull();

    // Clicking section reveals its sub-links
    await user.click(screen.getByRole("button", { name: /Overview & Estate/i }));
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: /Topology & Canvas/i }));
    expect(screen.getByRole("link", { name: "Topology" })).toHaveAttribute("href", "/topology");

    await user.click(screen.getByRole("button", { name: /Security & Posture/i }));
    expect(screen.getByRole("link", { name: "Security" })).toHaveAttribute("href", "/security");
    expect(screen.getByRole("link", { name: "Findings" })).toHaveAttribute("href", "/findings");

    await user.click(screen.getByRole("button", { name: /Actions & GitOps/i }));
    expect(screen.getByRole("link", { name: "Actions" })).toHaveAttribute("href", "/actions");
    expect(screen.getByRole("link", { name: "GitOps / IaC" })).toHaveAttribute("href", "/iac");

    await user.click(screen.getByRole("button", { name: /Cost & FinOps/i }));
    expect(screen.getByRole("link", { name: "Cost" })).toHaveAttribute("href", "/cost");

    await user.click(screen.getByRole("button", { name: /Governance & Ops/i }));
    expect(screen.getByRole("link", { name: "Compliance & Ops" })).toHaveAttribute(
      "href",
      "/compliance",
    );
  });

  it("shows the tenant and the signed-in identity", () => {
    render(
      <AppShell session={DEMO_SESSION} onSignOut={async () => {}}>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByLabelText("Tenant")).toBeDisabled();
    expect(screen.getByText(DEMO_SESSION.email)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("renders children", () => {
    render(
      <AppShell session={DEMO_SESSION} onSignOut={async () => {}}>
        <p>canvas placeholder</p>
      </AppShell>,
    );
    expect(screen.getByText("canvas placeholder")).toBeInTheDocument();
  });
});
