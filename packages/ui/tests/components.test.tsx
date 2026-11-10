import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Badge, Button, Card, EmptyState } from "../src/index";

describe("Button", () => {
  it("renders its label and handles clicks", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Approve plan</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Approve plan" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("is disabled and busy while loading", () => {
    render(<Button loading>Saving</Button>);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("defaults to type=button so forms do not submit accidentally", () => {
    render(<Button>Action</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});

describe("Badge", () => {
  it("exposes its text", () => {
    render(<Badge tone="danger">critical</Badge>);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });
});

describe("Card", () => {
  it("renders header and body", () => {
    render(
      <Card title="Findings" description="Open security findings" actions={<Badge>3</Badge>}>
        body
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Findings" })).toBeInTheDocument();
    expect(screen.getByText("Open security findings")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("is announced politely", () => {
    render(<EmptyState title="No accounts connected" description="Connect an AWS account." />);
    expect(screen.getByRole("status")).toHaveTextContent("No accounts connected");
  });
});
