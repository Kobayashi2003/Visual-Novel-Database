/** Application-wide constants: backend routes, UI defaults, and the entity-type registry. */


/* ─── Backend routes ───────────────────────────────────────────────────────── */
// The backend services sit behind path-prefix routes. In prod, Caddy intercepts
// these prefixes and proxies directly to the matching Flask backend (see
// Caddyfile's `handle_path /vndbserve/*` etc.). In dev, Next.js' rewrites in
// next.config.ts forward them to the same Flask ports. Either way, the
// browser only ever talks to a single origin.

export const VNDBSERVE_BASE_URL = "/vndbserve"
export const IMGSERVE_BASE_URL = "/imgserve"
export const USERSERVE_BASE_URL = "/userserve"
export const TRANSSERVE_BASE_URL = "/transserve"
export const MUSICSERVE_BASE_URL = "/musicserve"


/* ─── UI defaults ──────────────────────────────────────────────────────────── */

// Default page size for paginated lists / grids.
export const PAGE_LIMIT = 24


/* ─── Collection-type registry ─────────────────────────────────────────────── */
// Single source of truth that maps a high-level type name to the VNDB
// single-letter route prefix and a human-readable label. Adding a new entity
// type means appending a row here.

export const COLLECTION_TYPES = [
  { type: 'vn',        route: 'v', label: 'Visual Novel' },
  { type: 'release',   route: 'r', label: 'Release'      },
  { type: 'character', route: 'c', label: 'Character'    },
  { type: 'producer',  route: 'p', label: 'Producer'     },
  { type: 'staff',     route: 's', label: 'Staff'        },
  { type: 'tag',       route: 'g', label: 'Tag'          },
  { type: 'trait',     route: 'i', label: 'Trait'        },
] as const

export type CollectionTypeItem = typeof COLLECTION_TYPES[number]

// Lookup table form of `COLLECTION_TYPES` for O(1) access by type name.
export const COLLECTION_TYPE_MAP: Record<string, CollectionTypeItem> =
  Object.fromEntries(COLLECTION_TYPES.map(c => [c.type, c]))

// Reverse lookup: single-letter VNDB route prefix (`"v"`) → high-level type
// name (`"vn"`). Used where only the route letter is in hand (e.g. the search
// panel maps its `v`/`c`/… type onto the userserve collection endpoints).
export const ROUTE_TO_TYPE: Record<string, string> =
  Object.fromEntries(COLLECTION_TYPES.map(c => [c.route, c.type]))
