/** Sends signed-out visitors to /login. (Next 16 "proxy" convention — the
 *  former `middleware.ts` name is deprecated.)
 *
 *  UX only. The pages carry no data — every fetch is client-side — so the gate
 *  that actually protects anything is Caddy's forward_auth in front of the
 *  backends (see Caddyfile.snippet). Accordingly this checks only that a session
 *  cookie is *present*: validating the signature here would mean shipping
 *  JWT_SECRET_KEY into the edge runtime to re-decide what the edge already
 *  decides. The refresh cookie is the one to look at — the access cookie lapses
 *  after 30 minutes while the session is still alive.
 */
import { NextResponse, type NextRequest } from "next/server"

const PUBLIC_ROUTES = ["/login", "/reset-password"]

export function proxy(request: NextRequest) {
  const { pathname, search, basePath } = request.nextUrl

  if (PUBLIC_ROUTES.some(p => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next()
  }
  if (request.cookies.has("refresh_token_cookie")) return NextResponse.next()

  const url = request.nextUrl.clone()
  url.pathname = "/login"
  // basePath is stripped from `pathname`, but the post-login navigation is a
  // plain location.assign, so put it back.
  url.search = `?next=${encodeURIComponent(basePath + pathname + search)}`
  return NextResponse.redirect(url)
}

export const config = {
  // Pages only. Static files are excluded by extension so a signed-out /login
  // can still load its own styling and sprites.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|svg|jpe?g|gif|webp|ico|css|js|woff2?)$).*)"],
}
