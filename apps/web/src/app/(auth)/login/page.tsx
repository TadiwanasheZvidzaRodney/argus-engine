import { Badge, Button, Card } from "@argus/ui";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getSession } from "@/lib/session";

import { signIn } from "./actions";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if (await getSession()) redirect("/overview");
  const { error } = await searchParams;

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-6">
      <div className="mb-6 flex items-center gap-2">
        <span aria-hidden className="size-2.5 rounded-full bg-accent" />
        <h1 className="text-base font-semibold tracking-tight">Argus Engine</h1>
        <Badge tone="warning">Phase 0</Badge>
      </div>

      <Card
        title="Sign in"
        description="Local stub authentication. SSO via OIDC arrives in Phase 1."
      >
        <form action={signIn} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            Work email
            <input
              name="email"
              type="email"
              required
              autoComplete="email"
              defaultValue="demo@argus.local"
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            Password
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              defaultValue="argus-demo"
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground"
            />
          </label>
          {error === "invalid_credentials" && (
            <p role="alert" className="text-xs text-danger">
              Enter a valid email and a password of at least 8 characters.
            </p>
          )}
          <Button type="submit" className="mt-1">
            Continue
          </Button>
        </form>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          Demo credentials are prefilled. Nothing is sent to an identity provider; the session is a
          signed-cookie placeholder for the real BFF flow.
        </p>
      </Card>
    </main>
  );
}
