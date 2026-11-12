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
  await expect(page.getByText("No AWS account connected yet")).toBeVisible();
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

  await page.getByRole("link", { name: "Security" }).click();
  await expect(page).toHaveURL(/\/security/);
  await expect(page.getByRole("heading", { name: "Security posture" })).toBeVisible();

  await page.getByRole("link", { name: "Findings", exact: true }).click();
  await expect(page).toHaveURL(/\/findings/);
  await expect(page.getByRole("heading", { name: "Security Findings" })).toBeVisible();

  await page.getByRole("link", { name: "Cost", exact: true }).click();
  await expect(page).toHaveURL(/\/cost/);
  await expect(page.getByRole("heading", { name: "Cost Intelligence & FinOps" })).toBeVisible();

  await page.getByRole("link", { name: "Compliance & Ops", exact: true }).click();
  await expect(page).toHaveURL(/\/compliance/);
  await expect(
    page.getByRole("heading", { name: "Compliance, Evidence Locker & Operations" }),
  ).toBeVisible();
});
