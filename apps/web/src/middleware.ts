import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/session";

/**
 * Fast path guard: redirect unauthenticated requests before any rendering.
 *
 * This only checks cookie presence. The authenticated layout still verifies the
 * session payload, and Phase 1 replaces the cookie with the BFF's server-side
 * session store so nothing sensitive is client-visible.
 */
const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (isPublic || request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }

  const signIn = request.nextUrl.clone();
  signIn.pathname = "/login";
  signIn.search = "";
  return NextResponse.redirect(signIn);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|webp|ico)$).*)"],
};
