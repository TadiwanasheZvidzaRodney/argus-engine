import { Badge, Card, EmptyState } from "@argus/ui";

import { apiFetch } from "@/lib/api";
import { getSession } from "@/lib/session";

interface MemberItem {
  user_id: string;
  email: string;
  role: string;
  status: string;
  joined_at: string;
}

export const dynamic = "force-dynamic";

async function loadMembers(tenantId: string): Promise<MemberItem[]> {
  try {
    return await apiFetch<MemberItem[]>(`/api/v1/tenants/${tenantId}/members`, {
      timeoutMs: 3_000,
    });
  } catch {
    return [];
  }
}

export default async function MembersPage() {
  const session = await getSession();
  const tenantId = session?.tenantId ?? "tnt_0190c3a1-0000-7000-8000-000000000001";
  const members = await loadMembers(tenantId);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Team Members & Access</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage members and role-based access control (RBAC).
          </p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold">Active Members ({members.length})</h2>
          {members.length === 0 ? (
            <Card>
              <EmptyState
                title="No members found"
                description="Invite team members to get started."
              />
            </Card>
          ) : (
            <div className="flex flex-col gap-2">
              {members.map((m) => (
                <div
                  key={m.user_id}
                  className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{m.email}</p>
                    <p className="text-xs text-muted-foreground">
                      Joined {new Date(m.joined_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge tone={m.role === "owner" ? "info" : "neutral"}>{m.role}</Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        <Card
          title="Invite Team Member"
          description="Send an invitation link with role assignment."
        >
          <form className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Work email
              <input
                type="email"
                placeholder="colleague@argus.local"
                required
                className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Role
              <select
                defaultValue="viewer"
                className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
              >
                <option value="viewer">Viewer (Read-only)</option>
                <option value="operator">Operator (Actions & Discovery)</option>
                <option value="approver">Approver (Sign-off on plans)</option>
                <option value="auditor">Auditor (Compliance & Audit logs)</option>
                <option value="admin">Admin (Full tenant administration)</option>
              </select>
            </label>
            <p className="text-[11px] text-muted-foreground">
              Invitations are signed with a 7-day expiration.
            </p>
          </form>
        </Card>
      </div>
    </div>
  );
}
