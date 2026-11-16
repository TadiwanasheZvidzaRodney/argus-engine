"use client";

import { Button, Card } from "@argus/ui";
import { useRouter } from "next/navigation";
import React, { useState } from "react";

import { apiFetch } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";

export interface TenantSettings {
  tenant_id: string;
  tenant_name: string;
  slug: string;
  plan: string;
  alert_email: string;
  alert_repeat_minutes: number;
  alert_slack_webhook: string | null;
  default_region: string;
  updated_at: string | null;
}

export function TenantSettingsForm({ initialSettings }: { initialSettings: TenantSettings }) {
  const router = useRouter();
  const [email, setEmail] = useState(initialSettings.alert_email);
  const [repeatMinutes, setRepeatMinutes] = useState(initialSettings.alert_repeat_minutes);
  const [slackWebhook, setSlackWebhook] = useState(initialSettings.alert_slack_webhook || "");
  const [defaultRegion, setDefaultRegion] = useState(initialSettings.default_region);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testSent, setTestSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);

    try {
      await apiFetch<TenantSettings>("/api/v1/settings/tenant", {
        method: "PUT",
        idempotencyKey: newIdempotencyKey("save-settings"),
        body: {
          alert_email: email,
          alert_repeat_minutes: repeatMinutes,
          alert_slack_webhook: slackWebhook || undefined,
          default_region: defaultRegion,
        },
      });
      setSaved(true);
      router.refresh();
      setTimeout(() => setSaved(false), 3000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to update tenant settings.");
    } finally {
      setBusy(false);
    }
  }

  const [testNotice, setTestNotice] = useState<string | null>(null);

  async function handleTestEmail() {
    setTesting(true);
    setTestSent(false);
    setTestNotice(null);
    setError(null);

    try {
      const res = await apiFetch<{ success: boolean; mode: string; detail: string }>(
        "/api/v1/ops/alerts/test-email",
        {
          method: "POST",
          idempotencyKey: newIdempotencyKey("test-mail"),
          body: {
            to_email: email,
            subject: "[TEST ALERT] Argus Notification Destination Verification",
            message: `Verification notification sent to ${email} from Argus Engine settings.`,
          },
        },
      );
      if (res.success) {
        setTestSent(true);
        if (res.mode === "mailpit") {
          setTestNotice("Captured in local Mailpit (view at http://localhost:8025).");
        } else {
          setTestNotice(`Delivered via SMTP to ${email}.`);
        }
      } else {
        setError(`Email delivery failed: ${res.detail}`);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to send test email.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card
      title="Alert Notification Preferences"
      description="Configure where operations, security, and FinOps alerts are dispatched."
    >
      <form onSubmit={handleSave} className="flex flex-col gap-4">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Notification Alert Email
          </label>
          <p className="mb-1 text-xs text-muted-foreground">
            All Sev-1/Sev-2 alerts and repeated action escalations will deliver to this address.
          </p>
          <div className="flex gap-2">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="h-9 flex-1 rounded-md border border-border bg-background px-3 text-xs text-foreground"
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              loading={testing}
              onClick={handleTestEmail}
            >
              {testSent ? "Test Sent ✓" : "Send Test Email"}
            </Button>
          </div>
          {testNotice && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-success">
              <span>{testNotice}</span>
              {testNotice.includes("Mailpit") && (
                <a
                  href="http://localhost:8025"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium underline underline-offset-4"
                >
                  Open Local Mailbox ↗
                </a>
              )}
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Repeated Alert Cadence
            </label>
            <p className="mb-1 text-xs text-muted-foreground">
              Interval before unaddressed alerts re-notify.
            </p>
            <select
              value={repeatMinutes}
              onChange={(e) => setRepeatMinutes(parseInt(e.target.value, 10))}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground"
            >
              <option value={15}>Every 15 minutes</option>
              <option value={30}>Every 30 minutes (Default)</option>
              <option value={60}>Every 1 hour</option>
              <option value={120}>Every 2 hours</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Default Cloud Region
            </label>
            <p className="mb-1 text-xs text-muted-foreground">
              Primary AWS region for telemetry and discovery.
            </p>
            <input
              type="text"
              value={defaultRegion}
              onChange={(e) => setDefaultRegion(e.target.value)}
              required
              className="h-9 w-full rounded-md border border-border bg-background px-3 text-xs text-foreground font-mono"
            />
          </div>
        </div>

        <div>
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Slack Webhook URL (Optional)
          </label>
          <input
            type="url"
            value={slackWebhook}
            onChange={(e) => setSlackWebhook(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className="mt-1 h-9 w-full rounded-md border border-border bg-background px-3 text-xs text-foreground"
          />
        </div>

        <div className="flex items-center justify-between border-t border-border/60 pt-3">
          {saved ? (
            <span className="text-xs font-medium text-success">Settings saved successfully ✓</span>
          ) : error ? (
            <span className="text-xs font-medium text-danger">{error}</span>
          ) : (
            <span />
          )}

          <Button type="submit" size="sm" variant="primary" loading={busy}>
            Save Preferences
          </Button>
        </div>
      </form>
    </Card>
  );
}
