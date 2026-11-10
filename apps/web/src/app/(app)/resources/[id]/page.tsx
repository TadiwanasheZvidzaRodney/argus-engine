import { Badge, Card } from "@argus/ui";
import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";

interface ResourceDetail {
  id: string;
  arn: string;
  type: string;
  name: string;
  account_id: string;
  region: string;
  state: string;
  tags: Record<string, string>;
  version: number;
  parent_id: string | null;
  properties: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface RelationshipItem {
  source: string;
  target: string;
  type: string;
  direction: string;
  other_type: string | null;
  other_name: string | null;
}

export const dynamic = "force-dynamic";

async function loadDetail(encodedId: string): Promise<ResourceDetail | null> {
  try {
    return await apiFetch<ResourceDetail>(`/api/v1/resources/${encodedId}`, { timeoutMs: 3_000 });
  } catch {
    return null;
  }
}

async function loadRelationships(encodedId: string): Promise<RelationshipItem[]> {
  try {
    return await apiFetch<RelationshipItem[]>(`/api/v1/resources/${encodedId}/relationships`, {
      timeoutMs: 3_000,
    });
  } catch {
    return [];
  }
}

export default async function ResourceInspectorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [detail, relationships] = await Promise.all([loadDetail(id), loadRelationships(id)]);

  if (!detail) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/resources" className="text-xs text-accent underline underline-offset-4">
          ← Back to inventory
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{detail.name || detail.type}</h1>
              <Badge tone="neutral">{detail.type.split("::").pop()}</Badge>
              <Badge
                tone={
                  detail.state === "running" || detail.state === "available" ? "success" : "neutral"
                }
              >
                {detail.state}
              </Badge>
            </div>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{detail.arn}</p>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Core Attributes */}
        <Card title="Resource Metadata">
          <dl className="grid gap-2 text-xs">
            <div className="flex justify-between py-1 border-b border-border">
              <dt className="text-muted-foreground">Account ID</dt>
              <dd className="font-mono">{detail.account_id}</dd>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <dt className="text-muted-foreground">Region</dt>
              <dd className="font-mono">{detail.region}</dd>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <dt className="text-muted-foreground">Version</dt>
              <dd className="font-mono">{detail.version}</dd>
            </div>
            {detail.parent_id && (
              <div className="flex justify-between py-1 border-b border-border">
                <dt className="text-muted-foreground">Parent Container</dt>
                <dd className="font-mono truncate max-w-xs">{detail.parent_id}</dd>
              </div>
            )}
            <div className="flex justify-between py-1">
              <dt className="text-muted-foreground">Last Updated</dt>
              <dd>{new Date(detail.updated_at).toLocaleString()}</dd>
            </div>
          </dl>
        </Card>

        {/* Tags */}
        <Card title="Tags">
          {Object.keys(detail.tags).length === 0 ? (
            <p className="text-xs text-muted-foreground">No tags configured on this resource.</p>
          ) : (
            <dl className="grid gap-2 text-xs">
              {Object.entries(detail.tags).map(([k, v]) => (
                <div key={k} className="flex justify-between py-1 border-b border-border">
                  <dt className="font-medium text-foreground">{k}</dt>
                  <dd className="font-mono text-muted-foreground">{v}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
      </div>

      {/* Relationships */}
      <Card title={`Direct Relationships (${relationships.length})`}>
        {relationships.length === 0 ? (
          <p className="text-xs text-muted-foreground">No direct relationships discovered.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {relationships.map((r, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-md border border-border bg-surface-muted px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2">
                  <Badge tone={r.direction === "outgoing" ? "info" : "neutral"}>
                    {r.direction === "outgoing" ? "→ Outgoing" : "← Incoming"}
                  </Badge>
                  <span className="font-mono font-semibold text-accent">{r.type}</span>
                  <span className="text-foreground">
                    {r.other_name ||
                      (r.direction === "outgoing" ? r.target : r.source).split("/").pop()}
                  </span>
                  {r.other_type && <Badge tone="neutral">{r.other_type.split("::").pop()}</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Configuration Properties */}
      <Card title="Raw Configuration Properties">
        <pre className="max-h-96 overflow-auto rounded bg-surface-muted p-3 font-mono text-[11px] text-foreground">
          {JSON.stringify(detail.properties, null, 2)}
        </pre>
      </Card>
    </div>
  );
}
