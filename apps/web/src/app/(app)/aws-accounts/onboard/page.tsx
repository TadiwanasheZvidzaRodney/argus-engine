"use client";

import { Button, Card } from "@argus/ui";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiFetch } from "@/lib/api";

interface OnboardingResult {
  account_id: string;
  external_id: string;
  cloudformation_url: string;
  parameters: Record<string, string>;
}

export default function OnboardWizardPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [accountId, setAccountId] = useState("");
  const [alias, setAlias] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onboardData, setOnboardData] = useState<OnboardingResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationSuccess, setValidationSuccess] = useState(false);

  async function handleStartOnboarding(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const idempotencyKey = `onboard-${accountId}-${Date.now()}`;
      const result = await apiFetch<OnboardingResult>("/api/v1/aws-accounts/onboarding", {
        method: "POST",
        body: { account_id: accountId, alias: alias || undefined },
        idempotencyKey,
      });
      setOnboardData(result);
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to initiate onboarding.");
    } finally {
      setLoading(false);
    }
  }

  async function handleValidate() {
    if (!onboardData) return;
    setError(null);
    setValidating(true);

    try {
      const idempotencyKey = `validate-${onboardData.account_id}-${Date.now()}`;
      await apiFetch(`/api/v1/aws-accounts/${onboardData.account_id}/validate`, {
        method: "POST",
        idempotencyKey,
      });
      setValidationSuccess(true);
      setTimeout(() => {
        router.push("/aws-accounts");
        router.refresh();
      }, 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Validation failed. Ensure stack is created.");
    } finally {
      setValidating(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <header>
        <Link href="/aws-accounts" className="text-xs text-accent underline underline-offset-4">
          ← Back to accounts
        </Link>
        <h1 className="mt-2 text-xl font-semibold tracking-tight">Onboard AWS Account</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Step-by-step cross-account IAM role setup via AWS CloudFormation.
        </p>
      </header>

      {step === 1 ? (
        <Card
          title="Step 1: Enter AWS Account Details"
          description="We will issue a dedicated ExternalId and prefilled CloudFormation template."
        >
          <form onSubmit={handleStartOnboarding} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              12-digit AWS Account ID
              <input
                type="text"
                required
                maxLength={12}
                pattern="^[0-9]{12}$"
                placeholder="123456789012"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value.trim())}
                className="h-10 rounded-md border border-border bg-background px-3 font-mono text-sm text-foreground"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Account Alias (optional)
              <input
                type="text"
                placeholder="e.g. production-core"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
              />
            </label>

            {error && (
              <p role="alert" className="text-xs text-danger">
                {error}
              </p>
            )}

            <Button type="submit" loading={loading} className="mt-2">
              Generate CloudFormation Link
            </Button>
          </form>
        </Card>
      ) : (
        <Card
          title="Step 2: Deploy CloudFormation Stack"
          description="Launch the stack in your AWS console and verify role assumption."
        >
          <div className="flex flex-col gap-4">
            <div className="rounded-md border border-border bg-surface-muted p-3">
              <p className="text-xs font-semibold text-foreground">Generated External ID:</p>
              <code className="mt-1 block break-all font-mono text-xs text-accent">
                {onboardData?.external_id}
              </code>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Protects cross-account access against the Confused Deputy problem.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <a
                href={onboardData?.cloudformation_url}
                target="_blank"
                rel="noreferrer"
                className="w-full"
              >
                <Button className="w-full">Launch CloudFormation Stack ↗</Button>
              </a>
              <p className="text-[11px] text-muted-foreground">
                Opens the AWS Console with prefilled parameters. Check the IAM acknowledgment box
                and click &quot;Create stack&quot;.
              </p>
            </div>

            <hr className="border-border" />

            <div className="flex flex-col gap-2">
              <h2 className="text-xs font-semibold text-foreground">Verify Connection</h2>
              <p className="text-xs text-muted-foreground">
                Once the CloudFormation stack reaches CREATE_COMPLETE, click validate below.
              </p>

              {error && (
                <p role="alert" className="text-xs text-danger">
                  {error}
                </p>
              )}

              {validationSuccess ? (
                <div className="rounded-md border border-success/30 bg-success/10 p-3 text-xs text-success">
                  ✓ Account connection validated successfully! Redirecting…
                </div>
              ) : (
                <Button
                  onClick={handleValidate}
                  loading={validating}
                  variant="secondary"
                  className="mt-1"
                >
                  Validate Role Assumption
                </Button>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
