import { Badge, Button, Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

interface ResourceItem {
  id: string;
  arn: string;
  type: string;
  name: string;
  account_id: string;
  region: string;
  state: string;
  tags: Record<string, string>;
}

interface ResourcePageResponse {
  items: ResourceItem[];
  has_more: boolean;
  next_cursor: string | null;
}

interface ResourceQuery {
  q?: string;
  type?: string;
  account_id?: string;
  region?: string;
  state?: string;
  group_by?: "type" | "account" | "region" | "state" | "none";
}

export const dynamic = "force-dynamic";

async function loadAllResources(): Promise<ResourceItem[]> {
  try {
    const res = await apiFetch<ResourcePageResponse>("/api/v1/resources?limit=200", {
      timeoutMs: 4_000,
    });
    return res.items;
  } catch {
    return [];
  }
}

function getServiceGlyph(type: string): string {
  if (type.includes("Instance")) return "EC2";
  if (type.includes("VPC")) return "VPC";
  if (type.includes("Subnet")) return "SBN";
  if (type.includes("Bucket")) return "S3";
  if (type.includes("DBInstance")) return "RDS";
  if (type.includes("Role")) return "IAM";
  if (type.includes("User")) return "USR";
  if (type.includes("LoadBalancer")) return "ALB";
  if (type.includes("SecurityGroup")) return "SG";
  if (type.includes("RouteTable")) return "RTB";
  if (type.includes("InternetGateway")) return "IGW";
  if (type.includes("Lambda")) return "LMB";
  return "AWS";
}

function stateTone(state: string) {
  const s = state.toLowerCase();
  if (s === "running" || s === "available" || s === "active") return "success";
  if (s === "pending" || s === "stopping" || s === "stopped") return "warning";
  if (s === "terminated" || s === "failed") return "danger";
  return "neutral";
}

function encodeResourceKey(idOrArn: string): string {
  return Buffer.from(idOrArn).toString("base64url").replace(/=/g, "");
}

function filterHref(current: ResourceQuery, updates: Partial<ResourceQuery>): string {
  const next = { ...current, ...updates };
  const params = new URLSearchParams();
  for (const [key, val] of Object.entries(next)) {
    if (val) params.set(key, val);
  }
  const qStr = params.toString();
  return qStr ? `/resources?${qStr}` : "/resources";
}

function prettyGroupName(groupKey: string, groupBy: string): string {
  if (groupBy === "type") {
    return groupKey.split("::").slice(1).join(" ") || groupKey;
  }
  if (groupBy === "account") {
    return groupKey === "000000000000" ? "Internet Sentinel" : `Account ${groupKey}`;
  }
  if (groupBy === "region") {
    return groupKey === "global" ? "Global / Multi-Region" : groupKey;
  }
  if (groupBy === "state") {
    return groupKey.toUpperCase();
  }
  return groupKey;
}

export default async function ResourcesPage({
  searchParams,
}: {
  searchParams: Promise<ResourceQuery>;
}) {
  const query = await searchParams;
  const rawResources = await loadAllResources();

  // Extract all available facets dynamically from current inventory
  const allAccounts = Array.from(new Set(rawResources.map((r) => r.account_id)))
    .filter((id) => id && id !== "000000000000")
    .sort();
  const allTypes = Array.from(new Set(rawResources.map((r) => r.type))).sort();
  const allRegions = Array.from(new Set(rawResources.map((r) => r.region))).sort();
  const allStates = Array.from(new Set(rawResources.map((r) => r.state))).sort();

  // Apply filters
  const searchTerm = query.q?.toLowerCase().trim();
  const filtered = rawResources.filter((r) => {
    if (query.account_id && r.account_id !== query.account_id) return false;
    if (query.type && r.type !== query.type) return false;
    if (query.region && r.region !== query.region) return false;
    if (query.state && r.state.toLowerCase() !== query.state.toLowerCase()) return false;
    if (searchTerm) {
      const matchName = r.name?.toLowerCase().includes(searchTerm);
      const matchArn = r.arn?.toLowerCase().includes(searchTerm);
      const matchId = r.id?.toLowerCase().includes(searchTerm);
      const matchType = r.type?.toLowerCase().includes(searchTerm);
      const matchTag = Object.entries(r.tags || {}).some(
        ([k, v]) => k.toLowerCase().includes(searchTerm) || v.toLowerCase().includes(searchTerm),
      );
      if (!matchName && !matchArn && !matchId && !matchType && !matchTag) return false;
    }
    return true;
  });

  const groupBy = query.group_by ?? "type";

  // Group resources
  const grouped: Record<string, ResourceItem[]> = {};
  if (groupBy === "none") {
    grouped["All Resources"] = filtered;
  } else {
    for (const r of filtered) {
      let key = r.type;
      if (groupBy === "account") key = r.account_id;
      if (groupBy === "region") key = r.region;
      if (groupBy === "state") key = r.state;
      const bucket = grouped[key] ?? [];
      bucket.push(r);
      grouped[key] = bucket;
    }
  }

  const groupKeys = Object.keys(grouped).sort();
  const hasActiveFilters = Boolean(
    query.q ||
    query.type ||
    query.region ||
    query.state ||
    (query.group_by && query.group_by !== "type"),
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Resource Inventory</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Grouped resource catalog across services, regions, and states with live topology
            linking.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/topology"
            className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground hover:bg-accent/90"
          >
            Open in canvas
          </Link>
        </div>
      </header>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Visible Resources">
          <p className="text-2xl font-semibold tabular-nums text-foreground">{filtered.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Of {rawResources.length} total resources.
          </p>
        </Card>
        <Card title="Service Types">
          <p className="text-2xl font-semibold tabular-nums text-foreground">{allTypes.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">Discovered AWS resource categories.</p>
        </Card>
        <Card title="Regions">
          <p className="text-2xl font-semibold tabular-nums text-foreground">{allRegions.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">Active cloud deployment zones.</p>
        </Card>
        <Card title="Healthy States">
          <p className="text-2xl font-semibold tabular-nums text-success">
            {filtered.filter((r) => stateTone(r.state) === "success").length}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Available or active resources.</p>
        </Card>
      </div>

      {/* Search and Filter Controls */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <form method="GET" className="flex flex-1 max-w-md gap-2">
            {query.account_id && <input type="hidden" name="account_id" value={query.account_id} />}
            {query.type && <input type="hidden" name="type" value={query.type} />}
            {query.region && <input type="hidden" name="region" value={query.region} />}
            {query.state && <input type="hidden" name="state" value={query.state} />}
            {query.group_by && <input type="hidden" name="group_by" value={query.group_by} />}
            <input
              name="q"
              type="search"
              defaultValue={query.q ?? ""}
              placeholder="Search by name, ARN, type, or tag..."
              className="h-9 flex-1 rounded-md border border-border bg-background px-3 text-xs text-foreground"
            />
            <Button type="submit" size="sm" variant="secondary">
              Search
            </Button>
            {hasActiveFilters && (
              <Link
                href="/resources"
                className="inline-flex h-9 items-center rounded-md border border-border px-2.5 text-xs text-muted-foreground hover:bg-surface-muted"
              >
                Reset filters
              </Link>
            )}
          </form>

          {/* Group By Selector */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="font-medium text-[11px] uppercase tracking-wider">Group by:</span>
            {(["type", "account", "region", "state", "none"] as const).map((mode) => {
              const active = groupBy === mode;
              return (
                <Link
                  key={mode}
                  href={filterHref(query, { group_by: mode })}
                  className={
                    active
                      ? "rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground"
                      : "rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-surface-muted"
                  }
                >
                  {mode === "type" ? "Service" : mode.charAt(0).toUpperCase() + mode.slice(1)}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Filter Pills: Accounts (if multiple accounts exist) */}
        {allAccounts.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border/60">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mr-1">
              Account:
            </span>
            <Link
              href={filterHref(query, { account_id: undefined })}
              className={
                !query.account_id
                  ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                  : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
              }
            >
              All
            </Link>
            {allAccounts.map((accId) => {
              const active = query.account_id === accId;
              return (
                <Link
                  key={accId}
                  href={filterHref(query, { account_id: active ? undefined : accId })}
                  className={
                    active
                      ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                      : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted font-mono"
                  }
                >
                  {accId}
                </Link>
              );
            })}
          </div>
        )}

        {/* Filter Pills: Service Type */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border/60">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mr-1">
            Service:
          </span>
          <Link
            href={filterHref(query, { type: undefined })}
            className={
              !query.type
                ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
            }
          >
            All
          </Link>
          {allTypes.map((t) => {
            const active = query.type === t;
            const shortName = t.split("::").pop() || t;
            return (
              <Link
                key={t}
                href={filterHref(query, { type: active ? undefined : t })}
                className={
                  active
                    ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                    : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
                }
              >
                {shortName}
              </Link>
            );
          })}
        </div>

        {/* Filter Pills: Region & State */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/60">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mr-1">
              Region:
            </span>
            <Link
              href={filterHref(query, { region: undefined })}
              className={
                !query.region
                  ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                  : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
              }
            >
              All
            </Link>
            {allRegions.map((reg) => {
              const active = query.region === reg;
              return (
                <Link
                  key={reg}
                  href={filterHref(query, { region: active ? undefined : reg })}
                  className={
                    active
                      ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                      : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
                  }
                >
                  {reg}
                </Link>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mr-1">
              State:
            </span>
            <Link
              href={filterHref(query, { state: undefined })}
              className={
                !query.state
                  ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                  : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
              }
            >
              All
            </Link>
            {allStates.map((st) => {
              const active = query.state === st;
              return (
                <Link
                  key={st}
                  href={filterHref(query, { state: active ? undefined : st })}
                  className={
                    active
                      ? "rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-foreground"
                      : "rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:bg-surface-muted"
                  }
                >
                  {st}
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      {/* Grouped Resource Inventory Results */}
      {filtered.length === 0 ? (
        <Card>
          <EmptyState
            title="No resources match the active filters"
            description="Adjust your search keywords or clear the service and region filter pills."
            action={
              hasActiveFilters ? (
                <Link href="/resources" className="mt-2 inline-block">
                  <Button size="sm" variant="secondary">
                    Clear all filters
                  </Button>
                </Link>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          {groupKeys.map((groupKey) => {
            const items = grouped[groupKey] || [];
            return (
              <section key={groupKey} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 border-b border-border pb-1.5">
                  <h2 className="text-sm font-semibold text-foreground">
                    {prettyGroupName(groupKey, groupBy)}
                  </h2>
                  <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
                    {items.length}
                  </span>
                </div>

                <div className="grid gap-2">
                  {items.map((res) => {
                    const encodedId = encodeResourceKey(res.arn || res.id);
                    const tagKeys = Object.keys(res.tags || {});
                    return (
                      <Link
                        key={res.id}
                        href={`/resources/${encodedId}`}
                        className="group flex flex-col gap-1.5 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent hover:bg-surface-muted/40"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="flex size-5 items-center justify-center rounded bg-surface-muted text-[10px] font-bold text-accent">
                              {getServiceGlyph(res.type)}
                            </span>
                            <span className="font-semibold text-sm text-foreground group-hover:text-accent">
                              {res.name || res.arn.split("/").pop()}
                            </span>
                            <Badge tone="neutral">{res.type.split("::").pop()}</Badge>
                            <Badge tone={stateTone(res.state)}>{res.state}</Badge>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            <span className="font-mono">{res.region}</span>
                            <span>·</span>
                            <span className="font-mono">{res.account_id}</span>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="truncate font-mono text-xs text-muted-foreground max-w-2xl">
                            {res.arn || res.id}
                          </p>
                          {tagKeys.length > 0 && (
                            <div className="flex items-center gap-1">
                              {tagKeys.slice(0, 3).map((k) => (
                                <span
                                  key={k}
                                  className="rounded border border-border/80 bg-surface px-1.5 py-0.2 text-[10px] text-muted-foreground"
                                >
                                  {k}={res.tags[k]}
                                </span>
                              ))}
                              {tagKeys.length > 3 && (
                                <span className="text-[10px] text-muted-foreground">
                                  +{tagKeys.length - 3} more
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
