import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">404</p>
      <h1 className="text-lg font-semibold">This view does not exist</h1>
      <Link className="text-sm text-accent underline underline-offset-4" href="/overview">
        Back to overview
      </Link>
    </main>
  );
}
