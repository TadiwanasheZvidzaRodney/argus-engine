import { Badge, Button, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

interface RegionStatus {
  region: string;
  enabled: boolean;
  discovery_status: string;
}

interface AccountItem {
  id: string;
  account_id: string;
  alias: string | null;
  status: string;
  read_role_arn: string;
  last_validated_at: string | null;
  regions: RegionStatus[];
}

export const dynamic = "force-dynamic";

async function loadAccounts(): Promise<AccountItem[]> {
  try {
    return await apiFetch<AccountItem[]>("/api/v1/aws-accounts", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

export default async function AccountsPage() {
  const accounts = await loadAccounts();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Connected AWS Accounts</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Cross-account roles assumed via AWS STS with ExternalId protection.
          </p>
        </div>
        <Link href="/aws-accounts/onboard">
          <Button>Connect Account</Button>
        </Link>
      </header>

      {accounts.length === 0 ? (
        <Card title="No accounts connected">
          <EmptyState
            title="Connect your first AWS account"
            description="Run our CloudFormation template in your management or workload account. No long-lived keys are stored."
            action={
              <Link href="/aws-accounts/onboard" className="mt-2">
                <Button size="sm">Start CloudFormation Onboarding</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4">
          {accounts.map((acc) => (
            <Card
              key={acc.id}
              title={
                <div className="flex items-center gap-2">
                  <span className="font-mono">{acc.account_id}</span>
                  {acc.alias && <span className="text-muted-foreground">({acc.alias})</span>}
                  <Badge tone={acc.status === "active" ? "success" : "warning"}>{acc.status}</Badge>
                </div>
              }
              description={`Role: ${acc.read_role_arn}`}
              actions={
                <span className="text-xs text-muted-foreground">
                  Validated:{" "}
                  {acc.last_validated_at
                    ? new Date(acc.last_validated_at).toLocaleString()
                    : "never"}
                </span>
              }
            >
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-xs font-medium text-muted-foreground">Enabled regions:</span>
                {acc.regions
                  .filter((r) => r.enabled)
                  .map((r) => (
                    <Badge key={r.region} tone="neutral">
                      {r.region}
                    </Badge>
                  ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
