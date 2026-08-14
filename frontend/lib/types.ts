/** Shared TypeScript types for VNDB entities, query shapes, and user data. */


export type SexualLevel = "safe" | "suggestive" | "explicit"
export type ViolenceLevel = "tame" | "violent" | "brutal"

// Where the browser loads VNDB images from: "imgserve" routes them through
// our caching proxy; "direct" requests them straight from t.vndb.org.
export type ImageSource = "imgserve" | "direct"

// How the VN detail page renders its Characters section: "grid" is the default
// thumbnail grid; "slider" shows one dense info card at a time with left/right
// navigation.
export type VNCharacterLayout = "grid" | "slider"


/* ─── Pagination & query parameters ────────────────────────────────────────── */

export interface PaginationParams {
  page?: number
  limit?: number
  sort?: string
  reverse?: boolean
  count?: boolean
}

export interface PaginatedResponse<T> {
  results: T[]
  more: boolean
  count: number
  // Which side answered ("local" / "remote"). Absent on a page synthesized
  // from a 404, which came from neither.
  source?: string
}

// VNDB-specific query params. `from` selects the data source ("local" vs the
// upstream VNDB), `response_size` toggles the large/small payload variant.
export interface VNDBQueryParams extends PaginationParams {
  from?: 'local' | 'remote'
  response_size?: 'small' | 'large'
  [key: string]: unknown
}

// Marks listing query params. `cid` filters by category id (or "all" for the
// flat across-categories list).
export interface MarksQueryParams extends PaginationParams {
  cid?: number | 'all'
}


/* ─── Full entity payloads ─────────────────────────────────────────────────── */
// Shape returned by `response_size=large` endpoints. These are the ones used by
// detail pages.

export interface VN {
  id: string
  title: string
  alttitle?: string
  titles: Array<{
    lang: string
    title: string
    latin?: string
    official: boolean
    main: boolean
  }>
  aliases: string[]
  olang: string
  devstatus: number
  released?: string
  languages: string[]
  platforms: string[]
  image?: {
    url: string
    dims: [number, number]
    thumbnail: string
    thumbnail_dims: [number, number]
    sexual: number
    violence: number
  }
  length?: number
  length_minutes?: number
  length_votes: number
  description?: string
  average?: number
  rating?: number
  votecount: number
  screenshots: Array<{
    url: string
    dims: [number, number]
    sexual: number
    violence: number
    thumbnail: string
    thumbnail_dims: [number, number]
    release: {
      id: string
      title: string
      alttitle?: string
    }
  }>
  relations: Array<{
    id: string
    title: string
    alttitle?: string
    relation: string
    relation_official: boolean
  }>
  tags: Array<{
    id: string
    name: string
    category: string
    rating: number
    spoiler: number
    lie: boolean
  }>
  developers: Array<{
    id: string
    name: string
    original?: string
  }>
  publishers: Array<{
    id: string
    name: string
    original?: string
    languages: string[]
  }>
  editions: Array<{
    eid: string
    lang?: string
    name: string
    official: boolean
  }>
  staff: Array<{
    id: string
    name: string
    original?: string
    eid?: number
    role: string
    note?: string
  }>
  va: Array<{
    note?: string
    staff: {
      id: string
      name: string
      original?: string
    }
    character: {
      id: string
      name: string
      original?: string
    }
  }>
  extlinks: Array<{
    url: string
    label: string
    name: string
    id: string
  }>
  characters: Array<{
    id: string
    name: string
    original?: string
    sex?: [string, string]
    image?: {
      url: string
      dims: [number, number]
      sexual: number
      violence: number
    }
    vns: Array<{
      id: string
      role: string
      spoiler: number
    }>
  }>
  releases?: Array<{
    id: string
    title: string
    alttitle?: string
    released?: string
    minage?: number
    patch: boolean
    official: boolean
    uncensored?: boolean
    media: Array<{
      medium: string
      qty: number
    }>
    platforms?: string[]
    languages: Array<{
      lang: string
      title?: string
      latin?: string
      mtl: boolean
      main: boolean
    }>
    vns: Array<{
      id: string
      rtype: string
    }>
    producers: Array<{
      id: string
      developer: boolean
      publisher: boolean
      name: string
      original?: string
    }>
  }>
}

export interface Release {
  id: string
  title: string
  alttitle?: string
  languages: Array<{
    lang: string
    title?: string
    latin?: string
    mtl: boolean
    main: boolean
  }>
  platforms: string[]
  media: Array<{
    medium: string
    qty: number
  }>
  vns: Array<{
    id: string
    title: string
    alttitle?: string
    rtype: string
  }>
  producers?: Array<{
    id: string
    developer: boolean
    publisher: boolean
    name: string
    original?: string
  }>
  images: Array<{
    id: string
    type: string
    vn?: string
    languages?: string[]
    photo: boolean
    url: string
    dims: [number, number]
    sexual: number
    violence: number
    thumbnail: string
    thumbnail_dims: [number, number]
  }>
  released: string
  minage?: number
  patch: boolean
  freeware: boolean
  uncensored?: boolean
  official: boolean
  has_ero: boolean
  resolution?: string | [number, number]
  engine?: string
  voiced?: number
  notes?: string
  gtin?: string
  catalog?: string
  extlinks: Array<{
    url: string
    label: string
    name: string
    id: string
  }>
}

export interface Character {
  id: string
  name: string
  original?: string
  aliases: string[]
  description?: string
  image?: {
    url: string
    dims: [number, number]
    sexual: number
    violence: number
  }
  blood_type?: string
  height?: number
  weight?: number
  bust?: number
  waist?: number
  hips?: number
  cup?: string
  age?: number
  // Stored as a String column on the backend, so it arrives as a JSON
  // string like "[9,1]" ([month, day]). Parse via formatBirthday.
  birthday?: [number, number] | string
  sex?: [string, string]
  vns: Array<{
    id: string
    role: string
    title: string
    alttitle?: string
    release?: {
      id: string
      title: string
      alttitle?: string
    }
  }>
  traits: Array<{
    id: string
    name: string
    group_id?: string
    group_name?: string
    spoiler: number
    lie: boolean
  }>
  seiyuu: Array<{
    id: string
    name: string
    original?: string
    note?: string
  }>
}

export interface Producer {
  id: string
  name: string
  original?: string
  aliases: string[]
  lang: string
  type: string
  description?: string
  extlinks: Array<{
    url: string
    label: string
    name: string
    id: string
  }>
}

export interface Staff {
  id: string
  aid: string
  ismain: boolean
  name: string
  original?: string
  lang: string
  gender?: string
  description?: string
  extlinks: Array<{
    url: string
    label: string
    name: string
    id: string
  }>
  aliases: Array<{
    aid: string
    name: string
    latin?: string
    is_main: boolean
  }>
}

export interface Tag {
  id: string
  name: string
  aliases: string[]
  description: string
  category: string
  searchable: boolean
  applicable: boolean
  vn_count: number
}

export interface Trait {
  id: string
  name: string
  aliases: string[]
  description: string
  searchable: boolean
  applicable: boolean
  group_id?: string
  group_name?: string
  char_count: number
}


/* ─── Small entity payloads ────────────────────────────────────────────────── */
// Shape returned by `response_size=small` endpoints — enough to render a card or list
// row, but stripped of heavy nested data.

export interface VN_Small {
  id: string
  title: string
  alttitle?: string
  titles: Array<{
    lang: string
    title: string
    latin?: string
    official: boolean
    main: boolean
  }>
  released: string
  developers: Array<{
    id: string
    name: string
    original?: string
  }>
  image?: {
    url: string
    dims: [number, number]
    thumbnail: string
    thumbnail_dims: [number, number]
    sexual: number
    violence: number
  }
}

export interface Release_Small {
  id: string
  title: string
  alttitle?: string
  released: string
  minage?: number
  patch: boolean
  official: boolean
  uncensored?: boolean
  media: Array<{
    medium: string
    qty: number
  }>
  platforms?: string[]
  languages: Array<{
    lang: string
    title?: string
    latin?: string
    mtl: boolean
    main: boolean
  }>
  vns: Array<{
    id: string
    rtype: string
    title?: string
    alttitle?: string
  }>
  producers: Array<{
    id: string
    developer: boolean
    publisher: boolean
    name: string
    original?: string
  }>
}

export interface Character_Small {
  id: string
  name: string
  original?: string
  sex?: [string, string]
  vns: Array<{
    id: string
    role: string
    spoiler: number
  }>
  image?: {
    url: string
    dims: [number, number]
    sexual: number
    violence: number
  }
}

export interface Producer_Small {
  id: string
  name: string
  original?: string
}

export interface Staff_Small {
  id: string
  name: string
  original?: string
}

export interface Tag_Small {
  id: string
  name: string
  category: string
}

export interface Trait_Small {
  id: string
  name: string
  group_id?: string
  group_name?: string
}


/* ─── User domain ──────────────────────────────────────────────────────────── */
// Auth, plus the per-user "categories" (named lists) and the "marks"
// (membership rows pairing a category with an entity).

export interface User {
  id: number
  is_admin: boolean
  username: string
  email: string
  created_at: string
  updated_at: string
}

export interface Category {
  id: number
  user_id: number
  category_name: string
  marks: Mark[]
  type: 'vn' | 'character' | 'producer' | 'staff' | 'release' | 'tag' | 'trait'
  created_at: string
  updated_at: string
}

export interface Mark {
  id: number
  marked_at: string
}

// Read-only public view of a user's `played`/`playing` VN collections, plus
// their VN ratings keyed by numeric mark id. Returned by the public endpoint.
export interface PublicVNCollections {
  username: string
  collections: Array<{ category_name: string; marks: Mark[] }>
  ratings: Record<number, number>
}

// Track metadata from musicserve's /meta/<vnid> (tags are best-effort nulls).
export interface MusicMeta {
  id: string
  duration: number | null
  title: string | null
  artist: string | null
  album: string | null
  format: string
  has_cover: boolean
}


/* ─── Relation graph ───────────────────────────────────────────────────────── */
// The connected component of VN-to-VN relations rooted at one title, returned
// by `/v{id}/relations/graph`. `nodes` carry display metadata; `edges` are
// already deduplicated and oriented by the backend (directed types point
// earliest → latest, symmetric types carry `directed: false`).

export interface RelationGraphNode {
  id: string
  title: string
  alttitle?: string
  titles: VN["titles"]
  image?: VN["image"]
  released?: string
  devstatus: number
}

export interface RelationGraphEdge {
  a: string
  b: string
  relation: string
  official: boolean
  directed: boolean
}

export interface RelationGraph {
  root: string
  nodes: RelationGraphNode[]
  edges: RelationGraphEdge[]
  truncated: boolean
}
