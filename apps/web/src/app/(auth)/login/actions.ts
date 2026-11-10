"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DEMO_SESSION, SESSION_COOKIE, encodeSession } from "@/lib/session";

const EIGHT_HOURS = 60 * 60 * 8;

export async function signIn(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  // Phase 0 stub: accept the demo identity so the shell is usable end to end.
  // Phase 1 swaps this for the OIDC authorization-code flow behind a BFF.
  if (!email.includes("@") || password.length < 8) {
    redirect("/login?error=invalid_credentials");
  }

  const jar = await cookies();
  jar.set(SESSION_COOKIE, encodeSession({ ...DEMO_SESSION, email }), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: EIGHT_HOURS,
  });
  redirect("/overview");
}

export async function signOut(): Promise<void> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  redirect("/login");
}
