/** HTTP client for the VNDB proxy, image cache, and userserve backends. */

import {
  VN, Release, Character, Producer, Staff, Tag, Trait,
  VN_Small, Release_Small, Character_Small, Producer_Small,
  Staff_Small, Tag_Small, Trait_Small, User, Category, Mark,
  VNDBQueryParams, MarksQueryParams, PaginatedResponse,
  RelationGraph, RelationGraphNode, Soundtrack, SoundtrackSummary,
} from "./types"
import {
  VNDB_BASE_URL, IMGSERVE_BASE_URL, USERSERVE_BASE_URL, TRANSSERVE_BASE_URL,
  MUSICSERVE_BASE_URL, COLLECTION_TYPE_MAP,
} from "./constants"


/* ─── Base URL resolution ──────────────────────────────────────────────────── */
// On the server the URL can be overridden via env vars (so SSR can hit the
// internal hostnames); on the client we always use the same-origin /vndb,
// /imgserve, /userserve paths, which Caddy (prod) or Next.js rewrites (dev)
// forward to the matching Flask backend.

const getBaseUrl = (type: "vndb" | "imgserve" | "userserve" | "transserve" | "musicserve") => {
  if (typeof window === "undefined") {
    switch (type) {
      case "vndb": return process.env.NEXT_PUBLIC_VNDB_BASE_URL || VNDB_BASE_URL
      case "imgserve": return process.env.NEXT_PUBLIC_IMGSERVE_BASE_URL || IMGSERVE_BASE_URL
      case "userserve": return process.env.NEXT_PUBLIC_USERSERVE_BASE_URL || USERSERVE_BASE_URL
      case "transserve": return process.env.NEXT_PUBLIC_TRANSSERVE_BASE_URL || TRANSSERVE_BASE_URL
      case "musicserve": return process.env.NEXT_PUBLIC_MUSICSERVE_BASE_URL || MUSICSERVE_BASE_URL
    }
  } else {
    switch (type) {
      case "vndb": return VNDB_BASE_URL
      case "imgserve": return IMGSERVE_BASE_URL
      case "userserve": return USERSERVE_BASE_URL
      case "transserve": return TRANSSERVE_BASE_URL
      case "musicserve": return MUSICSERVE_BASE_URL
    }
  }
}


/* ─── Generic VNDB fetchers ────────────────────────────────────────────────── */
// Two flavours: paginated list (`fetchVNDB`) and single-item by id
// (`fetchVNDBById`). Both accept an optional `processor` so callers can rewrite
// image URLs (or do other per-item massaging) before the data reaches React.

const fetchVNDB = async <T>(
  endpoint: string,
  params: VNDBQueryParams = {},
  processor?: (item: T) => T,
  abortSignal?: AbortSignal,
): Promise<PaginatedResponse<T>> => {
  const queryString = new URLSearchParams(params as Record<string, string>).toString()
  const url = `${getBaseUrl("vndb")}/${endpoint}?${queryString}`
  try {
    const data = await fetchJson<PaginatedResponse<T>>(url, { method: "GET", signal: abortSignal }, "HTTP")
    return processor ? processVNDBResponse(data, processor) : data
  } catch (error) {
    // vndb answers 404 when a query matches nothing. For a list that is an
    // empty page, not a failure — only a single-item lookup treats it as one.
    if (error instanceof ApiError && error.status === 404) {
      return { results: [], more: false, count: 0 } as PaginatedResponse<T>
    }
    throw error
  }
}

const fetchVNDBById = async <T>(
  endpoint: string,
  params: VNDBQueryParams = {},
  processor?: (item: T) => T,
  abortSignal?: AbortSignal,
): Promise<T> => {
  const queryString = new URLSearchParams(params as Record<string, string>).toString()
  const url = `${getBaseUrl("vndb")}/${endpoint}?${queryString}`
  // A 404 propagates as an ApiError: for a lookup by id, "no such thing" is
  // the failure the caller wants to hear about.
  const data = await fetchJson<PaginatedResponse<T>>(url, { method: "GET", signal: abortSignal }, "HTTP")
  const result: T = data.results?.[0]
  if (!result) throw new ApiError(`Not found: ${endpoint}`, 404)
  return processor ? processor(result) : result
}


/* ─── Session-aware fetch ──────────────────────────────────────────────────── */
// Every backend sits behind the edge's auth gate, so all calls carry the session
// cookie and must survive an expired access token — not just the userserve ones.
// State-changing userserve requests additionally echo the CSRF token.

/** Error thrown by `fetchUserserve` for non-2xx responses. Carries the
 *  backend's structured `code` (e.g. "password_too_short") alongside a
 *  human-readable `message`, so callers can branch on `code` or simply surface
 *  `message` to the user. */
export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}

// A 401 from userserve triggers one refresh attempt; the failed request is then
// replayed once. Concurrent 401s share a single in-flight refresh.

// Endpoints where a 401 is terminal and must never trigger a refresh-retry.
const AUTH_ENDPOINTS = ["login", "register", "logout"]

let refreshInFlight: Promise<boolean> | null = null
let sessionExpiredHandler: (() => void) | null = null

/** Registered by UserContext so the UI can react when the session ends. */
export function setSessionExpiredHandler(handler: () => void) {
  sessionExpiredHandler = handler
}

/** Read a non-httpOnly cookie value — used to fetch the JWT CSRF tokens that
 *  flask-jwt-extended issues alongside the access / refresh cookies. */
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/** Exchange the refresh cookie for a fresh access cookie. Returns whether the
 *  refresh succeeded; concurrent callers share one in-flight request. Exported
 *  for UserContext's proactive renewal — see the timer there. */
export async function refreshAccessToken(): Promise<boolean> {
  if (typeof window === "undefined") return false
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const csrf = readCookie("csrf_refresh_token")
        const res = await fetch(`${getBaseUrl("userserve")}/refresh`, {
          method: "POST",
          credentials: "include",
          headers: csrf ? { "X-CSRF-TOKEN": csrf } : {},
        })
        return res.ok
      } catch {
        return false
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

/** Shared fetch: sends session cookies, and on a 401 refreshes once and replays.
 *  `buildInit` is a factory because refreshing rotates the `csrf_access_token`
 *  cookie — a replay reusing the original headers would echo a stale token. */
async function fetchWithSession(
  url: string,
  buildInit: () => RequestInit,
  { skipRefresh = false }: { skipRefresh?: boolean } = {},
  isRetry = false,
): Promise<Response> {
  const response = await fetch(url, { ...buildInit(), credentials: "include" })

  // Access token expired → refresh once, then replay the original request.
  if (
    response.status === 401 && !isRetry && !skipRefresh &&
    typeof window !== "undefined"
  ) {
    const refreshed = await refreshAccessToken()
    if (refreshed) return fetchWithSession(url, buildInit, { skipRefresh }, true)
    // Refresh was rejected → the session is over.
    sessionExpiredHandler?.()
  }
  return response
}

/** Fetch + parse for the plain-JSON backends (vndb, transserve, musicserve). */
const fetchJson = async <T>(url: string, init: RequestInit, label: string): Promise<T> => {
  const response = await fetchWithSession(url, () => init)
  if (!response.ok) throw new ApiError(`${label} error! status: ${response.status}`, response.status)
  return response.json()
}

const fetchUserserve = async <T>(
  endpoint: string,
  method: "GET" | "POST" | "PUT" | "DELETE",
  body?: unknown,
  abortSignal?: AbortSignal,
): Promise<T> => {
  const response = await fetchWithSession(
    `${getBaseUrl("userserve")}/${endpoint}`,
    () => {
      const headers: HeadersInit = { 'Content-Type': 'application/json' }
      // State-changing requests must echo the CSRF token from the cookie that
      // flask-jwt-extended issued alongside the access cookie.
      if (method !== "GET") {
        const csrf = readCookie("csrf_access_token")
        if (csrf) headers['X-CSRF-TOKEN'] = csrf
      }
      return {
        method, headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: abortSignal,
      }
    },
    // A 401 from login/register/logout is terminal — never refresh-retry it.
    { skipRefresh: AUTH_ENDPOINTS.includes(endpoint) },
  )

  if (!response.ok) {
    // userserve reports failures as `{ error: code, message: text }`; fall back
    // to a generic message when the body is missing or not JSON.
    let code: string | undefined
    let message = `Request failed (${response.status})`
    try {
      const payload = await response.json()
      if (payload?.message) message = payload.message
      if (payload?.error) code = payload.error
    } catch { /* error body was not JSON */ }
    throw new ApiError(message, response.status, code)
  }
  return await response.json()
}


/* ─── URL / route helpers ──────────────────────────────────────────────────── */

// Map a high-level collection name (e.g. `"vn"`) onto the single-letter VNDB
// route prefix (`"v"`). Falls back to the input if the type isn't registered.
function typeRoute(type: string): string {
  return COLLECTION_TYPE_MAP[type]?.route ?? type
}

// Rewrite VNDB-hosted image URLs to go through our imgserve proxy. Leaves
// unknown URL shapes untouched.
function convertToImgserveUrl(url: string): string {
  // "direct" image source (Settings) — bypass imgserve and hand the VNDB CDN
  // URL straight to the browser. Read from localStorage, like the guard above,
  // so this plain function need not be a hook.
  if (typeof window !== "undefined" && localStorage.getItem("imageSource") === "direct") {
    return url
  }

  // Preserve the <dir> segment so the URL maps 1:1 onto imgserve's on-disk
  // layout (<type>/<dir>/<id>.jpg). Caddy's file_server fast path serves
  // cache hits straight from disk by URL — only possible if the URL carries
  // the dir VNDB already embeds in its CDN path.
  const match = url.match(/^https?:\/\/[^/]+\/(cv|sf|ch|cv\.t|sf\.t|ch\.t)\/(\d+)\/(\d+)\.jpg$/)
  if (!match) return url
  const [, type, dir, id] = match
  return `${getBaseUrl("imgserve")}/img/${type}/${dir}/${id}.jpg`
}


/* ─── Per-entity image post-processors ─────────────────────────────────────── */
// VNDB returns absolute image URLs; we mirror them through imgserve so the
// browser hits our cache. One processor per entity that carries images.

function processVNImages(vn: VN): VN {
  return {
    ...vn,
    image: vn.image && { ...vn.image, url: convertToImgserveUrl(vn.image.url), thumbnail: convertToImgserveUrl(vn.image.thumbnail) },
    characters: vn.characters.map(c => ({ ...c, image: c.image && { ...c.image, url: convertToImgserveUrl(c.image.url) } })),
    screenshots: vn.screenshots.map(s => ({ ...s, url: convertToImgserveUrl(s.url), thumbnail: convertToImgserveUrl(s.thumbnail) })),
  }
}

function processCharacterImages(character: Character): Character {
  return { ...character, image: character.image && { ...character.image, url: convertToImgserveUrl(character.image.url) } }
}

function processReleaseImages(release: Release): Release {
  return { ...release, images: release.images.map(img => ({ ...img, url: convertToImgserveUrl(img.url), thumbnail: convertToImgserveUrl(img.thumbnail) })) }
}

function processSmallVNImages(vn: VN_Small): VN_Small {
  return { ...vn, image: vn.image && { ...vn.image, url: convertToImgserveUrl(vn.image.url), thumbnail: convertToImgserveUrl(vn.image.thumbnail) } }
}

function processSmallCharacterImages(character: Character_Small): Character_Small {
  return { ...character, image: character.image && { ...character.image, url: convertToImgserveUrl(character.image.url) } }
}

function processGraphNodeImage(node: RelationGraphNode): RelationGraphNode {
  return { ...node, image: node.image && { ...node.image, url: convertToImgserveUrl(node.image.url), thumbnail: convertToImgserveUrl(node.image.thumbnail) } }
}

// Maps a per-item processor across the `results` array of a paginated response.
function processVNDBResponse<T>(response: PaginatedResponse<T>, processor: (item: T) => T): PaginatedResponse<T> {
  return { ...response, results: response.results.map(processor) }
}


/* ─── Public API surface ───────────────────────────────────────────────────── */

export const api = {

  /* VNDB: paginated, large */
  vn: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<VN>(`v`, params, processVNImages, abortSignal)
  },
  release: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Release>(`r`, params, processReleaseImages, abortSignal)
  },
  producer: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Producer>(`p`, params, undefined, abortSignal)
  },
  character: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Character>(`c`, params, processCharacterImages, abortSignal)
  },
  staff: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Staff>(`s`, params, undefined, abortSignal)
  },
  tag: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Tag>(`g`, params, undefined, abortSignal)
  },
  trait: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
    params.response_size = "large"; return fetchVNDB<Trait>(`i`, params, undefined, abortSignal)
  },

  /* VNDB: single item by id, large */
  by_id: {
    vn: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<VN>(`v${id}`, params, processVNImages, abortSignal)
    },
    release: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Release>(`r${id}`, params, processReleaseImages, abortSignal)
    },
    character: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Character>(`c${id}`, params, processCharacterImages, abortSignal)
    },
    producer: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Producer>(`p${id}`, params, undefined, abortSignal)
    },
    staff: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Staff>(`s${id}`, params, undefined, abortSignal)
    },
    tag: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Tag>(`g${id}`, params, undefined, abortSignal)
    },
    trait: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "large"; return fetchVNDBById<Trait>(`i${id}`, params, undefined, abortSignal)
    },
  },

  /* VNDB: relation graph — the connected component of VN-to-VN relations rooted
     at a VN. Returns a single graph object (not the paginated list shape), so it
     has its own fetcher; node cover images are mirrored through imgserve. */
  relationGraph: async (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal): Promise<RelationGraph> => {
    const queryString = new URLSearchParams(params as Record<string, string>).toString()
    const url = `${getBaseUrl("vndb")}/v${id}/rg${queryString ? `?${queryString}` : ""}`
    const data = await fetchJson<{ results: RelationGraph }>(
      url, { method: "GET", signal: abortSignal }, "HTTP",
    )
    const graph = data.results
    return { ...graph, nodes: graph.nodes.map(processGraphNodeImage) }
  },

  /* VNDB: small variants (list cards, autocomplete, …) */
  small: {
    vn: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<VN_Small>(`v`, params, processSmallVNImages, abortSignal)
    },
    release: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Release_Small>(`r`, params, undefined, abortSignal)
    },
    character: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Character_Small>(`c`, params, processSmallCharacterImages, abortSignal)
    },
    producer: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Producer_Small>(`p`, params, undefined, abortSignal)
    },
    staff: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Staff_Small>(`s`, params, undefined, abortSignal)
    },
    tag: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Tag_Small>(`g`, params, undefined, abortSignal)
    },
    trait: (params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      params.response_size = "small"; return fetchVNDB<Trait_Small>(`i`, params, undefined, abortSignal)
    },

    by_id: {
      vn: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<VN_Small>(`v${id}`, params, processSmallVNImages, abortSignal)
      },
      release: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Release_Small>(`r${id}`, params, undefined, abortSignal)
      },
      character: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Character_Small>(`c${id}`, params, processSmallCharacterImages, abortSignal)
      },
      producer: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Producer_Small>(`p${id}`, params, undefined, abortSignal)
      },
      staff: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Staff_Small>(`s${id}`, params, undefined, abortSignal)
      },
      tag: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Tag_Small>(`g${id}`, params, undefined, abortSignal)
      },
      trait: (id: number, params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        params.response_size = "small"; return fetchVNDBById<Trait_Small>(`i${id}`, params, undefined, abortSignal)
      },
    },

    // Batched fetch — short-circuits on empty lists so callers don't have to.
    byIds: {
      vn: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as VN_Small[], more: false, count: 0 })
        return fetchVNDB<VN_Small>(`v`, { ...params, response_size: "small", id: ids.map(id => `v${id}`).join(",") }, processSmallVNImages, abortSignal)
      },
      release: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Release_Small[], more: false, count: 0 })
        return fetchVNDB<Release_Small>(`r`, { ...params, response_size: "small", id: ids.map(id => `r${id}`).join(",") }, undefined, abortSignal)
      },
      character: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Character_Small[], more: false, count: 0 })
        return fetchVNDB<Character_Small>(`c`, { ...params, response_size: "small", id: ids.map(id => `c${id}`).join(",") }, processSmallCharacterImages, abortSignal)
      },
      producer: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Producer_Small[], more: false, count: 0 })
        return fetchVNDB<Producer_Small>(`p`, { ...params, response_size: "small", id: ids.map(id => `p${id}`).join(",") }, undefined, abortSignal)
      },
      staff: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Staff_Small[], more: false, count: 0 })
        return fetchVNDB<Staff_Small>(`s`, { ...params, response_size: "small", id: ids.map(id => `s${id}`).join(",") }, undefined, abortSignal)
      },
      tag: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Tag_Small[], more: false, count: 0 })
        return fetchVNDB<Tag_Small>(`g`, { ...params, response_size: "small", id: ids.map(id => `g${id}`).join(",") }, undefined, abortSignal)
      },
      trait: (ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
        if (!ids.length) return Promise.resolve({ results: [] as Trait_Small[], more: false, count: 0 })
        return fetchVNDB<Trait_Small>(`i`, { ...params, response_size: "small", id: ids.map(id => `i${id}`).join(",") }, undefined, abortSignal)
      },
    },

    // Type-erased dispatcher over `byIds`. Callers that only have `type` as a
    // string (collection page, shelf rows) shouldn't have to write the switch.
    byIdsForType: (type: string, ids: number[], params: VNDBQueryParams = {}, abortSignal?: AbortSignal) => {
      const b = api.small.byIds
      switch (type) {
        case "vn":        return b.vn(ids, params, abortSignal)
        case "release":   return b.release(ids, params, abortSignal)
        case "character": return b.character(ids, params, abortSignal)
        case "producer":  return b.producer(ids, params, abortSignal)
        case "staff":     return b.staff(ids, params, abortSignal)
        case "tag":       return b.tag(ids, params, abortSignal)
        case "trait":     return b.trait(ids, params, abortSignal)
        default:          return b.vn(ids, params, abortSignal)
      }
    },
  },

  /* Userserve: auth */
  user: {
    login: (username: string, password: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ username: string }>("login", "POST", { username, password }, abortSignal),
    sendVerificationCode: (email: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>("send_verification_code", "POST", { email }, abortSignal),
    register: (username: string, email: string, password: string, code: string, invitationCode: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ username: string }>("register", "POST", { username, email, password, code, invitation_code: invitationCode }, abortSignal),
    changePassword: (oldPassword: string, newPassword: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>("change_password", "POST", { old_password: oldPassword, new_password: newPassword }, abortSignal),
    changeEmail: (newEmail: string, code: string, password: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ email: string }>("change_email", "POST", { new_email: newEmail, code, password }, abortSignal),
    deleteAccount: (username: string, password: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>(`u${username}`, "DELETE", { password }, abortSignal),
    forgotPassword: (email: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>("forgot_password", "POST", { email }, abortSignal),
    resetPassword: (token: string, newPassword: string, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>("reset_password", "POST", { token, new_password: newPassword }, abortSignal),
    logout: (abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>("logout", "POST", undefined, abortSignal),
    me: (abortSignal?: AbortSignal) =>
      fetchUserserve<User>("me", "GET", undefined, abortSignal),
    get: (username: string, abortSignal?: AbortSignal) =>
      fetchUserserve<User>(`u${username}`, "GET", undefined, abortSignal),
  },

  /* Userserve: categories and their marks */
  category: {
    get: (type: string, abortSignal?: AbortSignal) =>
      fetchUserserve<Category[]>(`${typeRoute(type)}/c`, "GET", undefined, abortSignal),
    create: (type: string, categoryName: string, abortSignal?: AbortSignal) =>
      fetchUserserve<Category>(`${typeRoute(type)}/c`, "POST", { category_name: categoryName }, abortSignal),
    update: (type: string, categoryId: number, newCategoryName: string, abortSignal?: AbortSignal) =>
      fetchUserserve<Category>(`${typeRoute(type)}/c${categoryId}`, "PUT", { category_name: newCategoryName }, abortSignal),
    delete: (type: string, categoryId: number, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>(`${typeRoute(type)}/c${categoryId}`, "DELETE", undefined, abortSignal),

    addMark: (type: string, categoryId: number, markId: number, abortSignal?: AbortSignal) =>
      fetchUserserve<Category>(`${typeRoute(type)}/c${categoryId}/m`, "POST", { mark_id: markId }, abortSignal),
    removeMark: (type: string, categoryId: number, markId: number, abortSignal?: AbortSignal) =>
      fetchUserserve<Category>(`${typeRoute(type)}/c${categoryId}/m`, "DELETE", { mark_id: markId }, abortSignal),
    removeMarks: (type: string, categoryId: number, markIds: number[], abortSignal?: AbortSignal) =>
      fetchUserserve<Category>(`${typeRoute(type)}/c${categoryId}/m`, "DELETE", { mark_ids: markIds }, abortSignal),
    moveMarks: (type: string, fromCategoryId: number, toCategoryId: number, markIds: number[], abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>(`${typeRoute(type)}/c/m`, "PUT", { category_from_id: fromCategoryId, category_to_id: toCategoryId, mark_ids: markIds }, abortSignal),
    getMarks: (type: string, params: MarksQueryParams = {}, abortSignal?: AbortSignal) => {
      const query = new URLSearchParams(params as Record<string, string>).toString()
      return fetchUserserve<{ results: Mark[]; count?: number; more: boolean }>(
        `${typeRoute(type)}/c/m?${query}`, "GET", undefined, abortSignal,
      )
    },
  },

  /* Userserve: personal 1–5 ratings, keyed by entity (independent of category) */
  rating: {
    // The backend serialises the map with string keys; parse them back to the
    // numeric mark ids the rest of the app uses.
    get: async (type: string, abortSignal?: AbortSignal): Promise<Record<number, number>> => {
      const raw = await fetchUserserve<Record<string, number>>(`${typeRoute(type)}/r`, "GET", undefined, abortSignal)
      const ratings: Record<number, number> = {}
      for (const [markId, value] of Object.entries(raw)) ratings[Number(markId)] = value
      return ratings
    },
    getOne: async (type: string, markId: number, abortSignal?: AbortSignal): Promise<number> => {
      const { rating } = await fetchUserserve<{ rating: number }>(`${typeRoute(type)}/r${markId}`, "GET", undefined, abortSignal)
      return rating
    },
    set: (type: string, markId: number, rating: number, abortSignal?: AbortSignal) =>
      fetchUserserve<{ rating: number }>(`${typeRoute(type)}/r${markId}`, "PUT", { rating }, abortSignal),
    clear: (type: string, markId: number, abortSignal?: AbortSignal) =>
      fetchUserserve<{ message: string }>(`${typeRoute(type)}/r${markId}`, "DELETE", undefined, abortSignal),
  },

  /* Transserve: English → Japanese term base (used to localise tag / trait
     names in original-text mode). `fallback` (default true) makes the backend
     echo the source term for any name it doesn't have a translation for, so
     callers always get a displayable string. The response maps each *input*
     term to its target; `matched` flags which were real hits. */
  translate: {
    term: async (
      terms: string[],
      fallback = true,
      abortSignal?: AbortSignal,
    ): Promise<{ results: Record<string, string | null>; matched: Record<string, boolean> }> => {
      if (!terms.length) return { results: {}, matched: {} }
      return fetchJson(`${getBaseUrl("transserve")}/term/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ terms, fallback }),
        signal: abortSignal,
      }, "Transserve")
    },

    /* Transserve passage memory: English → Japanese for long-form text such as
       tag / trait descriptions (used in original-text mode). The lookup keys on
       a normalized hash of the source, so callers send the exact English text.
       `fallback` (default true) echoes the source for any passage without a
       stored translation, so callers always get a displayable string. */
    passage: async (
      texts: string[],
      fallback = true,
      abortSignal?: AbortSignal,
    ): Promise<{ results: Record<string, string | null>; matched: Record<string, boolean> }> => {
      if (!texts.length) return { results: {}, matched: {} }
      return fetchJson(`${getBaseUrl("transserve")}/passage/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texts, fallback }),
        signal: abortSignal,
      }, "Transserve")
    },
  },

  /* Musicserve: VN theme music keyed by vnid ("v17"). The audio stream and
     cover are plain GETs handed straight to <audio src> / <img src> (Range
     seeking and 404s are the browser's problem), so only URL builders live
     here; metadata and batch availability are JSON calls. */
  /* musicserve: one visual novel is one soundtrack, and a track is addressed by
     its position in it. There is no database behind this — the folder layout on
     disk is the index. */
  music: {
    trackUrl: (vnid: string, ordinal: number) =>
      `${getBaseUrl("musicserve")}/soundtracks/${vnid}/tracks/${ordinal}`,
    // 404s when the soundtrack has no cover of its own. Callers show a
    // placeholder rather than substituting the VN's cover — a different picture.
    coverUrl: (vnid: string) => `${getBaseUrl("musicserve")}/soundtracks/${vnid}/cover`,

    soundtrack: (vnid: string, abortSignal?: AbortSignal): Promise<Soundtrack> =>
      fetchJson(`${getBaseUrl("musicserve")}/soundtracks/${vnid}`, { signal: abortSignal }, "Musicserve"),

    list: (params: { page?: number; limit?: number } = {}, abortSignal?: AbortSignal) => {
      const qs = new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)]),
      ).toString()
      return fetchJson<PaginatedResponse<SoundtrackSummary>>(
        `${getBaseUrl("musicserve")}/soundtracks${qs ? `?${qs}` : ""}`,
        { signal: abortSignal }, "Musicserve")
    },

    // Which of `ids` have a soundtrack. Keys in the result echo the input ids.
    available: async (ids: string[], abortSignal?: AbortSignal): Promise<Record<string, boolean>> => {
      if (!ids.length) return {}
      const data = await fetchJson<{ available: Record<string, boolean> }>(
        `${getBaseUrl("musicserve")}/soundtracks/available`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
          signal: abortSignal,
        }, "Musicserve")
      return data.available
    },

    /* Admin only — the edge forwards userserve's verdict, and musicserve
       checks it. A non-admin gets 403 from the service, not from here. */

    upload: async (vnid: string, files: File[], opts: { replace?: boolean } = {}) => {
      const body = new FormData()
      for (const f of files) body.append("files", f)
      const url = `${getBaseUrl("musicserve")}/soundtracks/${vnid}/tracks${opts.replace ? "?replace=true" : ""}`
      const res = await fetchWithSession(url, () => ({ method: "POST", body }))
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new ApiError(detail.message || `Upload failed (${res.status})`, res.status, detail.error)
      }
      return res.json() as Promise<{ id: string; stored: string[] }>
    },

    deleteTrack: async (vnid: string, ordinal: number) => {
      const res = await fetchWithSession(
        `${getBaseUrl("musicserve")}/soundtracks/${vnid}/tracks/${ordinal}`,
        () => ({ method: "DELETE" }))
      if (!res.ok) throw new ApiError(`Delete failed (${res.status})`, res.status)
    },

    deleteSoundtrack: async (vnid: string) => {
      const res = await fetchWithSession(
        `${getBaseUrl("musicserve")}/soundtracks/${vnid}`, () => ({ method: "DELETE" }))
      if (!res.ok) throw new ApiError(`Delete failed (${res.status})`, res.status)
    },
  },
}
