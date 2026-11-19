import { expect, test } from "@playwright/test";

test("unauthenticated visitors are sent to sign-in", async ({ page }) => {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Argus Engine" })).toBeVisible();
});

test("the stub sign-in lands on the overview", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});

test("signed-in users get a not-found view for unknown routes", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);

  await page.goto("/does-not-exist");
  await expect(page.getByRole("heading", { name: "This view does not exist" })).toBeVisible();
});

test("signed-in users can navigate to security, findings, cost, and compliance", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);

  // Expand Overview & Estate section to access Operations Wallboard
  await page.getByRole("button", { name: /Overview & Estate/i }).click();
  await page.getByRole("link", { name: "Operations Wallboard", exact: true }).click();
  await expect(page).toHaveURL(/\/ops/);
  await expect(page.getByRole("heading", { name: /Argus Ops — Estate Overview/i })).toBeVisible();

  // Expand Security & Posture section
  await page.getByRole("button", { name: /Security & Posture/i }).click();
  await page.getByRole("link", { name: "Security" }).click();
  await expect(page).toHaveURL(/\/security/);
  await expect(page.getByRole("heading", { name: "Security posture" })).toBeVisible();

  await page.getByRole("link", { name: "Findings", exact: true }).click();
  await expect(page).toHaveURL(/\/findings/);
  await expect(page.getByRole("heading", { name: "Security Findings" })).toBeVisible();

  // Expand Cost section
  await page.getByRole("button", { name: /Cost & FinOps/i }).click();
  await page.getByRole("link", { name: "Cost", exact: true }).click();
  await expect(page).toHaveURL(/\/cost/);
  await expect(page.getByRole("heading", { name: "Cost Intelligence & FinOps" })).toBeVisible();

  // Expand Actions & GitOps section
  await page.getByRole("button", { name: /Actions & GitOps/i }).click();
  await page.getByRole("link", { name: "GitOps / IaC", exact: true }).click();
  await expect(page).toHaveURL(/\/iac/);
  await expect(
    page.getByRole("heading", { name: "GitOps Bridge & IaC Drift Remediation" }),
  ).toBeVisible();

  // Expand Topology section
  await page.getByRole("button", { name: /Topology & Canvas/i }).click();
  await page.getByRole("link", { name: "Topology", exact: true }).click();
  await expect(page).toHaveURL(/\/topology/);
  await expect(page.getByText("Fit View", { exact: true })).toBeVisible();
});

test("kiosk mode hides sidebar and expands wallboard to 100% width", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);

  await page.goto("/ops");
  await expect(page).toHaveURL(/\/ops/);

  const aside = page.locator("aside");
  await expect(aside).toBeVisible();

  // Click TV Kiosk Mode
  await page.getByRole("button", { name: /TV Kiosk Mode/i }).click();
  await expect(aside).toBeHidden();
  await expect(page.locator("html")).toHaveAttribute("data-kiosk", "true");

  // Exit Kiosk Mode
  await page.getByRole("button", { name: /Exit Kiosk/i }).click();
  await expect(aside).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-kiosk");
});

test("ops wallboard renders time-series graphs and switches range filters", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);

  await page.goto("/ops");
  await expect(page).toHaveURL(/\/ops/);

  // Time range filter is visible
  const filterGroup = page.getByRole("group", { name: "Time range selector" });
  await expect(filterGroup).toBeVisible();
  await expect(page.getByText("Today (Since 00:00)")).toBeVisible();

  // Metric tiles have SVG graph paths
  const svgPaths = page.locator("svg path");
  await expect(svgPaths.first()).toBeVisible();

  // Deep-dive graphs are rendered
  await expect(page.getByText("Inbound Traffic & Error Budget Trajectory")).toBeVisible();
  await expect(page.getByText("Inbound Latency Distribution & SRE SLO")).toBeVisible();

  // Switch to Last 7 Days
  await page.getByRole("button", { name: "7 Days" }).click();
  await expect(page).toHaveURL(/range=7d/);
  await expect(page.getByText("Past 7 Days").first()).toBeVisible();

  // Switch to Last 30 Days
  await page.getByRole("button", { name: "30 Days" }).click();
  await expect(page).toHaveURL(/range=30d/);
  await expect(page.getByText("Past 30 Days").first()).toBeVisible();
});

test("security posture exposes evidence, domains and persistent UTC history ranges", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/overview/);
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "Security posture", exact: true })).toBeVisible();
  await expect(page.getByRole("meter", { name: "Argus posture indicator" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Security domains" })).toBeVisible();
  const ranges = page.getByRole("navigation", { name: "Security history range" });
  await expect(ranges.getByRole("link", { name: "Today (00:00 UTC)" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  for (const [name, range] of [
    ["Last 24h", "24h"],
    ["7 Days", "7d"],
    ["30 Days", "30d"],
  ]) {
    await ranges.getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`range=${range}`));
    await expect(ranges.getByRole("link", { name, exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
  }
  await page.reload();
  await expect(ranges.getByRole("link", { name: "30 Days" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "Finding inflow & resolution" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open risk backlog" })).toBeVisible();
  expect(errors).toEqual([]);
});
