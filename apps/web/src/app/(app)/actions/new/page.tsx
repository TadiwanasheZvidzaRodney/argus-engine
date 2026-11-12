import { Card, EmptyState } from "@argus/ui";
import Link from "next/link";

import { ActionComposer } from "@/components/actions/action-composer";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/action-types";

export const dynamic = "force-dynamic";

async function loadCatalog(): Promise<CatalogItem[]> {
  try {
    return await apiFetch<CatalogItem[]>("/api/v1/actions/catalog", { timeoutMs: 3_000 });
  } catch {
    return [];
  }
}

export default async function NewActionPage() {
  const catalog = (await loadCatalog()).filter((item) => item.enabled);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/actions" className="text-xs text-accent underline underline-offset-4">
          ← Back to actions
        </Link>
        <h1 className="mt-2 text-xl font-semibold tracking-tight">Request an action</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Compile a deterministic, reviewable plan. Nothing executes until the plan is approved.
        </p>
      </header>

      {catalog.length === 0 ? (
        <Card>
          <EmptyState
            title="Action catalog unavailable"
            description="The API did not return any enabled actions. Check that the API and scheduler are running and the Phase 6 migration is applied."
          />
        </Card>
      ) : (
        <ActionComposer catalog={catalog} />
      )}
    </div>
  );
}
