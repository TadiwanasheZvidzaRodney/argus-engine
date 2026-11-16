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
