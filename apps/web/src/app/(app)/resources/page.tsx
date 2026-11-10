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

export const dynamic = "force-dynamic";

async function loadResources(searchQuery?: string): Promise<ResourceItem[]> {
  try {
    if (searchQuery) {
      const res = await apiFetch<{ items: ResourceItem[] }>(
        `/api/v1/topology/search?q=${encodeURIComponent(searchQuery)}&limit=50`,
        { timeoutMs: 3_000 },
      );
      return res.items;
    }
    const res = await apiFetch<ResourcePageResponse>("/api/v1/resources?limit=50", {
      timeoutMs: 3_000,
    });
    return res.items;
  } catch {
    return [];
  }
}

export default async function ResourcesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const resources = await loadResources(q);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Resource Inventory</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Multi-dimensional topology search over names, ARNs, types, and tags.
          </p>
        </div>
      </header>

      {/* Search Bar */}
      <form method="GET" className="flex max-w-lg gap-2">
        <input
          name="q"
          type="search"
          defaultValue={q ?? ""}
          placeholder="Search by name, ARN, or type (e.g. vpc, payments, instance)..."
          className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm text-foreground"
        />
        <Button type="submit" size="sm">
          Search
        </Button>
      </form>

      {resources.length === 0 ? (
        <Card>
          <EmptyState
            title="No resources found"
            description={
              q
                ? `No resources match search query "${q}".`
                : "Run a discovery sync to ingest your AWS resources."
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {resources.map((res) => {
            const encodedId = Buffer.from(res.arn || res.id)
              .toString("base64url")
              .replace(/=/g, "");
            return (
              <Link
                key={res.id}
                href={`/resources/${encodedId}`}
                className="group flex flex-col gap-1 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground group-hover:text-accent">
                      {res.name || res.arn.split("/").pop()}
                    </span>
                    <Badge tone="neutral">{res.type.split("::").pop()}</Badge>
                    <Badge
                      tone={
                        res.state === "running" || res.state === "available" ? "success" : "neutral"
                      }
                    >
                      {res.state}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{res.region}</span>
                </div>
                <p className="truncate font-mono text-xs text-muted-foreground">{res.arn}</p>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
