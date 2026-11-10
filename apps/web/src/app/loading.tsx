export default function Loading() {
  return (
    <div role="status" aria-live="polite" className="flex min-h-dvh items-center justify-center">
      <span className="text-sm text-muted-foreground">Loading Argus…</span>
    </div>
  );
}
