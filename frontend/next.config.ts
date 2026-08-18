import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone build: `next build` emits a self-contained server bundle to
  // .next/standalone (with its own server.js). Prod deploy only needs:
  //   .next/standalone/  +  .next/static/  +  public/
  // No node_modules, no `next start` CLI. See start-prod.ps1 for how the
  // root launcher boots it via `node .next/standalone/server.js`.
  output: "standalone",
  // Served under a path prefix, not at the origin root: a single public port
  // (frp) can front this app alongside others, so the root is not ours to take.
  // basePath is baked in at build time — Next
  // rewrites its own asset and <Link> URLs with it — so it cannot be toggled per
  // launch; the app lives here in standalone mode too.
  //
  // It is `/vndb` — the Flask API sits at `/vndbserve` (see lib/constants.ts),
  // so the two prefixes cannot collide.
  basePath: "/vndb",
  images: {
    // Skip Next.js's server-side image optimizer. Both image-source modes
    // already deliver appropriately-sized images — imgserve caches them and
    // VNDB serves pre-generated '.t' thumbnails — so the optimizer is
    // redundant. It also cannot serve "direct" mode: the optimizer fetches the
    // upstream image server-side, and t.vndb.org trips its private-IP (SSRF)
    // guard whenever the host resolves DNS through a fake-IP proxy. Keep this
    // on, or "direct" image source breaks.
    unoptimized: true,
  },
  // Dev-only proxy: in prod Caddy intercepts /vndbserve, /imgserve, /userserve
  // before they reach Next.js (see Caddyfile.snippet), so these rewrites are a
  // no-op in prod. In dev (`next dev` with no Caddy), the browser hits Next.js
  // directly on :5010 and these rewrites forward to the Flask ports.
  //
  // Every source sets `basePath: false`. Next otherwise prefixes a rewrite's
  // source with basePath, which would make these match /vndb/vndbserve/*
  // — but lib/constants.ts sends the backends absolute, unprefixed paths
  // (`/vndbserve`, `/imgserve`, …), matching the top-level routes Caddy serves them on
  // in prod. Without `basePath: false` the sources would never match in dev and
  // every backend call would 404.
  async rewrites() {
    return [
      {
        source: "/vndbserve/:path*",
        destination: `${process.env.VNDBSERVE_BASE_URL || "http://localhost:5000"}/:path*`,
        basePath: false,
      },
      {
        source: "/imgserve/:path*",
        destination: `${process.env.IMGSERVE_BASE_URL || "http://localhost:5001"}/:path*`,
        basePath: false,
      },
      {
        source: "/userserve/:path*",
        destination: `${process.env.USERSERVE_BASE_URL || "http://localhost:5002"}/:path*`,
        basePath: false,
      },
      {
        source: "/transserve/:path*",
        destination: `${process.env.TRANSSERVE_BASE_URL || "http://localhost:5003"}/:path*`,
        basePath: false,
      },
      {
        source: "/musicserve/:path*",
        destination: `${process.env.MUSICSERVE_BASE_URL || "http://localhost:5004"}/:path*`,
        basePath: false,
      },
    ]
  }
};

export default nextConfig;
