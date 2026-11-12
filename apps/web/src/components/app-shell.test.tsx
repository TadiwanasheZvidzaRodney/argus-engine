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

  it("marks the active route", () => {
    render(
      <AppShell session={DEMO_SESSION} onSignOut={async () => {}}>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  });

  it("links implemented phases including topology, security, actions, cost, and compliance", () => {
    render(
      <AppShell session={DEMO_SESSION} onSignOut={async () => {}}>
        <p>content</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "Topology" })).toHaveAttribute("href", "/topology");
    expect(screen.getByRole("link", { name: "Security" })).toHaveAttribute("href", "/security");
    expect(screen.getByRole("link", { name: "Findings" })).toHaveAttribute("href", "/findings");
    expect(screen.getByRole("link", { name: "Actions" })).toHaveAttribute("href", "/actions");
    expect(screen.getByRole("link", { name: "Cost" })).toHaveAttribute("href", "/cost");
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
