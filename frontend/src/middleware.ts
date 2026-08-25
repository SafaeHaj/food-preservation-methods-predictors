import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "shelf_life_session";

/**
 * Routing-level session gate.
 *
 * This only checks that a session cookie is *present* — it deliberately does
 * not verify the JWT, because the signing secret lives in the backend and
 * should not be duplicated here. Real enforcement is the 401 that FastAPI
 * returns on every protected endpoint; this middleware exists so signed-out
 * visitors get sent to /login instead of loading an app shell that would then
 * fail every data call.
 *
 * Cookies ignore port, so the cookie the API sets on localhost:8010 is visible
 * to the Next.js server on localhost:3000. If the two are ever deployed to
 * different hosts, the API must set an explicit parent Domain for this to keep
 * working.
 */
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  if (pathname.startsWith("/app")) {
    if (!hasSession) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      // Preserve where they were heading so login can return them there.
      url.search = `?next=${encodeURIComponent(pathname + search)}`;
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // Already signed in? Skip the auth screens.
  if ((pathname === "/login" || pathname === "/signup") && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/app";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*", "/login", "/signup"],
};
