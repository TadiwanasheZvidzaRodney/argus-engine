import { Card } from "@argus/ui";
import Link from "next/link";

import {
  type TenantSettings,
  TenantSettingsForm,
} from "@/components/settings/tenant-settings-form";
import { apiFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadTenantSettings(): Promise<TenantSettings> {
  try {
    return await apiFetch<TenantSettings>("/api/v1/settings/tenant", { timeoutMs: 4_000 });
  } catch {
    return {
      tenant_id: "tnt_0190c3a1-0000-7000-8000-000000000001",
      tenant_name: "Argus Demo Tenant",
      slug: "demo-tenant",
      plan: "enterprise",
      alert_email: "devops@zimworx.com",
      alert_repeat_minutes: 30,
      alert_slack_webhook: null,
      default_region: "us-west-2",
      updated_at: null,
    };
  }
}

export default async function SettingsPage() {
  const settings = await loadTenantSettings();

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Settings & Alerts</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Configure operational alert destinations, escalation intervals, and tenant profile.
          </p>
        </div>
        <Link
          href="/settings/members"
          className="inline-flex h-8 items-center rounded-md border border-border bg-surface px-3 text-xs font-medium text-foreground hover:bg-surface-muted"
        >
          Manage Team & Roles →
        </Link>
      </header>

      {/* Main Settings Form */}
      <TenantSettingsForm initialSettings={settings} />

      {/* Tenant Metadata Card */}
      <Card title="Tenant Profile">
        <dl className="grid gap-2 text-xs">
          <div className="flex justify-between border-b border-border py-1.5">
            <dt className="text-muted-foreground">Tenant Identifier</dt>
            <dd className="font-mono text-foreground">{settings.tenant_id}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-1.5">
            <dt className="text-muted-foreground">Tenant Name</dt>
            <dd className="font-medium text-foreground">{settings.tenant_name}</dd>
          </div>
          <div className="flex justify-between border-b border-border py-1.5">
            <dt className="text-muted-foreground">URL Slug</dt>
            <dd className="font-mono text-foreground">{settings.slug}</dd>
          </div>
          <div className="flex justify-between py-1.5">
            <dt className="text-muted-foreground">Plan Tier</dt>
            <dd className="font-semibold text-accent uppercase tracking-wider">{settings.plan}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
