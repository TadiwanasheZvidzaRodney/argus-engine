"use client";

import { Button } from "@argus/ui";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(JSON.stringify({ event: "web.error_boundary", digest: error.digest }));
  }, [error]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-lg font-semibold">Something went wrong</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        The page failed to render. If the problem persists, quote reference{" "}
        <code className="font-mono text-xs">{error.digest ?? "unknown"}</code> to support.
      </p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
