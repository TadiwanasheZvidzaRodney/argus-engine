import { cookies } from "next/headers";

export const SESSION_COOKIE = "argus_session";

export interface Session {
  email: string;
  tenantId: string;
  tenantName: string;
  role: "argus-admin" | "argus-operator" | "argus-viewer";
  mode: "stub" | "oidc";
}

export const DEMO_SESSION: Session = {
  email: "demo@argus.local",
  tenantId: "tnt_0190c3a1-0000-7000-8000-000000000001",
  tenantName: "Demo tenant",
  role: "argus-admin",
  mode: "stub",
};

function decode(value: string): Session | null {
  try {
    const json = Buffer.from(value, "base64url").toString("utf8");
    const parsed = JSON.parse(json) as Partial<Session>;
    if (!parsed.email || !parsed.tenantId) return null;
    return {
      email: parsed.email,
      tenantId: parsed.tenantId,
      tenantName: parsed.tenantName ?? "Tenant",
      role: parsed.role ?? "argus-viewer",
      mode: parsed.mode ?? "stub",
    };
  } catch {
    return null;
  }
}

export function encodeSession(session: Session): string {
  return Buffer.from(JSON.stringify(session), "utf8").toString("base64url");
}

/**
 * Read the session from the httpOnly cookie.
 *
 * Phase 1 replaces this stub with the BFF callback that exchanges an OIDC code
 * and keeps tokens server-side; callers already treat this as async and opaque.
 */
export async function getSession(): Promise<Session | null> {
  const jar = await cookies();
  const raw = jar.get(SESSION_COOKIE)?.value;
  return raw ? decode(raw) : null;
}

export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) {
    throw new Error("requireSession called without a session; the route guard should redirect.");
  }
  return session;
}
