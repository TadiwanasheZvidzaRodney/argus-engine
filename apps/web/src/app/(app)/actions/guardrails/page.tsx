import { Badge, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { KillSwitchToggle } from "@/components/actions/kill-switch-toggle";
import { apiFetch } from "@/lib/api";
import type { GuardrailRule, KillSwitchState } from "@/lib/action-types";

export const dynamic = "force-dynamic";

async function loadRules(): Promise<GuardrailRule[]> {
  try {
    return await apiFetch<GuardrailRule[]>("/api/v1/guardrails", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

async function loadKillSwitch(): Promise<KillSwitchState> {
  try {
    return await apiFetch<KillSwitchState>("/api/v1/kill-switch", { timeoutMs: 3_000 });
  } catch {
    return { tenant_enabled: false, global_enabled: false, reasons: [] };
  }
}

export default async function GuardrailsPage() {
  const [rules, killSwitch] = await Promise.all([loadRules(), loadKillSwitch()]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link href="/actions" className="text-xs text-accent underline underline-offset-4">
          ← Back to actions
        </Link>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Guardrails & kill switch</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Server-enforced policy evaluated before any plan is stored. The kill switch blocks new
            requests and executions immediately.
          </p>
        </div>
      </header>

      <Card
        title="Kill switch"
        description="An emergency stop for all mutation writes. Global scope affects every tenant."
      >
        <KillSwitchToggle state={killSwitch} />
      </Card>

      {rules.length === 0 ? (
        <Card>
          <EmptyState
            title="No effective guardrail rules"
            description="Default rules apply until the tenant overrides them through the API."
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {rules.map((rule) => (
            <Card
              key={rule.name}
              title={rule.name}
              actions={
                <Badge tone={rule.enabled ? "success" : "neutral"}>
                  {rule.enabled ? "enabled" : "disabled"}
                </Badge>
              }
            >
              <p className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                {rule.rule_type} · v{rule.version}
              </p>
              <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-border bg-background p-2 font-mono text-[11px] text-muted-foreground">
                {JSON.stringify(rule.config, null, 2)}
              </pre>
            </Card>
          ))}
        </div>
      )}

      <Card title="How guardrails are evaluated">
        <ul className="list-inside list-disc text-xs text-muted-foreground">
          <li>Protected and deny-listed resources are rejected before planning.</li>
          <li>Account and region allow-lists constrain every ARN target.</li>
          <li>Blast-radius and resource-count limits cap the scope of a single plan.</li>
          <li>Wildcard IAM actions are refused unless the tenant explicitly allows them.</li>
          <li>Change windows and production break-glass rules apply per environment.</li>
          <li>Per-tenant hourly quotas are enforced at request time.</li>
        </ul>
      </Card>
    </div>
  );
}
