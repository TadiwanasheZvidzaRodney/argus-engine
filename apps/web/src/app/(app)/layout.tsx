import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { getSession } from "@/lib/session";
import { signOut } from "@/app/(auth)/login/actions";

export default async function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const session = await getSession();
  if (!session) redirect("/login");
  return (
    <AppShell session={session} onSignOut={signOut}>
      {children}
    </AppShell>
  );
}
