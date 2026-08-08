/** Public, read-only showcase of kobayashi's `Playing` / `Played` VN collections.
 *  Logged-in viewers only (covers depend on an authenticated image session).
 *
 *  Self-contained by directory: every bespoke control this Spotify-flavoured page
 *  needs lives in `./_components` (auth card, turntable music player, animated
 *  toolbar controls, tilt cards, custom cursor, audio-reactive background)
 *  rather than the shared component tree, so the showcase's distinct styling
 *  never leaks into — or drifts with — the rest of the app. This file owns the
 *  data flow, state machine, and page assembly.
 *
 *  The hero is a cassette deck streaming per-VN theme music from musicserve.
 *  Cards are pure track pickers (this page doesn't navigate into details):
 *  vivid cards have a tape and toggle it on click, dimmed ones don't. Once
 *  the deck scrolls out of view the bottom now-playing bar auto-docks. */
"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { motion, useMotionTemplate, useMotionValue, useScroll, useTransform } from "motion/react"
import { Library, Search } from "lucide-react"

import { api } from "@/lib/api"
import { cn, numericId, shouldBlur } from "@/lib/utils"
import { displayTitle, displayName } from "@/lib/original"
import { dedupeLatestMarks, sortMarksByDate, reorderById } from "@/lib/marks"
import { PAGE_LIMIT } from "@/lib/constants"
import { useUserContext } from "@/context/UserContext"
import { useSearchContext } from "@/context/SearchContext"
import type { PublicVNCollections, VN_Small, VNDBQueryParams } from "@/lib/types"

import { Counter, HeroTitle, GitHubLink } from "./_components/hero"
import { SegmentedControl, SortMenu, SearchBox, PageNav, type SortKey, LOCAL_SORTS, VNDB_SORT } from "./_components/controls"
import { VNCell, CustomCursor, Loader, ErrorMessage } from "./_components/cards"
import { PlayerProvider, usePlayer, type Track } from "./_components/player"
import { CassetteDeck } from "./_components/cassette"
import { NowPlayingBar, useNowPlayingBarVisible } from "./_components/bar"
import { KobayashiBackground } from "./_components/background"


// The fixed account this page showcases, and the two tabs (in display order).
const USERNAME = "kobayashi"
const TABS = [
  { key: "playing", label: "Playing" },
  { key: "played",  label: "Played"  },
] as const
type TabKey = typeof TABS[number]["key"]

const GRID_CLASS =
  "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 sm:gap-3"


/* ─── Page ─────────────────────────────────────────────────────────────────── */

export default function KobayashiPage() {
  return (
    <PlayerProvider>
      <Showcase />
    </PlayerProvider>
  )
}

function Showcase() {
  const { user, isLoading: authLoading, defaultSexualLevel, defaultViolenceLevel } = useUserContext()
  const { showOriginal } = useSearchContext()

  /* ── State ─────────────────────────────────────────────────────────────── */

  const [sexualLevel, setSexualLevel]     = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  const [data, setData]       = useState<PublicVNCollections | null>(null)
  const [status, setStatus]   = useState<"loading" | "error" | null>("loading")
  const [errorMsg, setErrorMsg] = useState("")

  const [tab, setTab]     = useState<TabKey>("playing")
  const [page, setPage]   = useState(1)
  const [sort, setSort]   = useState<SortKey>("date_added")
  const [order, setOrder] = useState<"asc" | "desc">("desc")

  // Search: local input (IME-safe) committed to `q` after a debounce.
  const [searchInput, setSearchInput] = useState("")
  const [isComposing, setIsComposing] = useState(false)
  const [q, setQ] = useState("")

  // The hydrated page tagged with the request key it belongs to (so a stale
  // tab/sort/search/page never shows), plus the total result count for paging.
  const [loaded, setLoaded] = useState<{ key: string; items: VN_Small[]; count: number }>({ key: "", items: [], count: 0 })
  // Which vnids have a theme track on musicserve (keyed "v123").
  const [musicAvail, setMusicAvail] = useState<Record<string, boolean>>({})
  // Marks the toolbar's natural position; used both for the pin transform and
  // to compute where to scroll back to after a results-changing operation.
  const sentinelRef = useRef<HTMLDivElement>(null)

  const player = usePlayer()
  const barVisible = useNowPlayingBarVisible()

  /* ── Effects, derived state & handlers ─────────────────────────────────── */

  /* Fetch the two collections once a signed-in viewer is present. */
  useEffect(() => {
    if (authLoading) return
    if (!user) { setStatus(null); return }
    let cancelled = false
    setStatus("loading")
    api.publicCollections.vn(USERNAME)
      .then(res => { if (!cancelled) { setData(res); setStatus(null) } })
      .catch(e => { if (!cancelled) { setStatus("error"); setErrorMsg(e?.message ?? "Failed to load") } })
    return () => { cancelled = true }
  }, [user, authLoading])

  /* Marks grouped per tab: merge same-named categories (case-insensitive),
     dedupe by id keeping the latest mark, newest first. */
  const marksByTab = useMemo(() => {
    const pick = (name: string) => {
      const marks = (data?.collections ?? [])
        .filter(c => c.category_name.trim().toLowerCase() === name)
        .flatMap(c => c.marks)
      return sortMarksByDate(dedupeLatestMarks(marks), "desc")
    }
    return { playing: pick("playing"), played: pick("played") }
  }, [data])

  const totalUnique = useMemo(() => {
    const ids = new Set<number>()
    for (const m of marksByTab.playing) ids.add(m.id)
    for (const m of marksByTab.played)  ids.add(m.id)
    return ids.size
  }, [marksByTab])

  const activeMarks = marksByTab[tab]
  const requestKey = `${tab}|${sort}|${order}|${q}|${page}`

  // Ids of the active tab sorted locally (for the date_added / my_rating sorts);
  // VNDB-delegated sorts ignore this and order the full id set server-side.
  const localSortedIds = useMemo(() => {
    const ratings = data?.ratings ?? {}
    const sorted = [...activeMarks]
    if (sort === "my_rating") {
      sorted.sort((a, b) => {
        const ra = ratings[a.id] ?? 0, rb = ratings[b.id] ?? 0
        if (ra !== rb) return order === "asc" ? ra - rb : rb - ra
        return b.marked_at.localeCompare(a.marked_at)
      })
    } else {
      sorted.sort((a, b) => order === "asc" ? a.marked_at.localeCompare(b.marked_at) : b.marked_at.localeCompare(a.marked_at))
    }
    return sorted.map(m => m.id)
  }, [activeMarks, sort, order, data])

  /* One batch round-trip to musicserve for every mark in either tab: which
     VNs have a theme track. Drives the ♪ badges, the pick-then-open click
     interception, and the playlist. */
  useEffect(() => {
    const ids = new Set<string>()
    for (const m of marksByTab.playing) ids.add(`v${m.id}`)
    for (const m of marksByTab.played)  ids.add(`v${m.id}`)
    if (ids.size === 0) { setMusicAvail({}); return }
    const ctrl = new AbortController()
    api.music.available([...ids], ctrl.signal)
      .then(setMusicAvail)
      .catch(() => setMusicAvail({}))
    return () => ctrl.abort()
  }, [marksByTab])

  /* Hydrate the current page for the active tab/sort/search, tagged with its
     request key so a stale result never shows. Local sorts paginate the marks
     client-side then hydrate that page; VNDB sorts (and any search) hand the
     whole id set to VNDB and let it sort / filter / paginate. The cleanup
     aborts any in-flight fetch, so a stale response never overwrites a newer. */
  useEffect(() => {
    const allIds = activeMarks.map(m => m.id)
    if (allIds.length === 0) {
      setLoaded({ key: data ? requestKey : "", items: [], count: 0 })
      return
    }
    const ctrl = new AbortController()
    const run = async () => {
      if (!q && LOCAL_SORTS.has(sort)) {
        const pageIds = localSortedIds.slice((page - 1) * PAGE_LIMIT, page * PAGE_LIMIT)
        const res = await api.small.byIds.vn(pageIds, { limit: PAGE_LIMIT }, ctrl.signal)
        setLoaded({ key: requestKey, items: reorderById(res.results, pageIds), count: allIds.length })
      } else {
        const vndbSort = q && LOCAL_SORTS.has(sort) ? "searchrank" : (VNDB_SORT[sort] ?? "title")
        const params: VNDBQueryParams = { sort: vndbSort, reverse: order === "desc", page, limit: PAGE_LIMIT, ...(q ? { search: q } : {}) }
        const res = await api.small.byIds.vn(allIds, params, ctrl.signal)
        setLoaded({ key: requestKey, items: res.results, count: res.count })
      }
    }
    run().catch(e => { if (e?.name !== "AbortError") setLoaded({ key: requestKey, items: [], count: 0 }) })
    return () => ctrl.abort()
  }, [requestKey, activeMarks, localSortedIds, q, sort, order, page, data])

  /* ── Player wiring ─────────────────────────────────────────────────────── */

  const trackFor = (vn: VN_Small): Track => ({
    vnid: vn.id,
    title: displayTitle(vn, showOriginal),
    developer: vn.developers?.[0] ? displayName(vn.developers[0], showOriginal) : "",
    vnCover: vn.image ? (vn.image.thumbnail || vn.image.url) : null,
    blur: vn.image ? shouldBlur(vn.image.sexual, vn.image.violence, sexualLevel, violenceLevel) : false,
  })

  /* Playlist = the playable items among the visible results, in display
     order; prev/next cycles through what the user can currently see. */
  const { setPlaylist } = player
  useEffect(() => {
    setPlaylist(
      loaded.items
        .filter(vn => musicAvail[vn.id])
        .map(vn => ({
          vnid: vn.id,
          title: displayTitle(vn, showOriginal),
          developer: vn.developers?.[0] ? displayName(vn.developers[0], showOriginal) : "",
          vnCover: vn.image ? (vn.image.thumbnail || vn.image.url) : null,
          blur: vn.image ? shouldBlur(vn.image.sexual, vn.image.violence, sexualLevel, violenceLevel) : false,
        })),
    )
  }, [loaded.items, musicAvail, showOriginal, sexualLevel, violenceLevel, setPlaylist])


  // After a results-changing op, return to the top of the results — but if the
  // title is already hidden (toolbar pinned), stop at the pin line so the
  // toolbar stays stuck and the title stays hidden instead of popping back up.
  //
  // The pinned check is read NOW (against the current layout, before React
  // commits the change), but the scroll itself is deferred to the next frame —
  // i.e. AFTER the new results render. This matters for search: filtering a long
  // list down to a few matches collapses the document height, and if we scrolled
  // against the old tall layout the browser would clamp the scroll up past the
  // pin line and re-reveal the hero. Scrolling post-commit avoids that clamp.
  const resetScroll = () => {
    const s = sentinelRef.current
    const wasPinned = !!s && s.getBoundingClientRect().top <= 0
    requestAnimationFrame(() => {
      const el = sentinelRef.current
      if (!wasPinned || !el) { window.scrollTo({ top: 0, behavior: "smooth" }); return }
      const pinTop = el.getBoundingClientRect().top + window.scrollY
      window.scrollTo({ top: pinTop + 2, behavior: "smooth" })
    })
  }

  // Debounced, IME-safe commit of the search box to `q`. Only fires when the
  // trimmed value actually changes, and resets to page 1 on a new query.
  useEffect(() => {
    if (isComposing) return
    const next = searchInput.trim()
    if (next === q) return
    const t = setTimeout(() => { setQ(next); setPage(1); resetScroll() }, 300)
    return () => clearTimeout(t)
  }, [searchInput, isComposing, q])

  const selectTab   = (key: TabKey) => { setTab(key); setPage(1); resetScroll() }
  const selectSort  = (s: SortKey) => { setSort(s); setPage(1); resetScroll() }
  const toggleOrder = () => { setOrder(o => (o === "desc" ? "asc" : "desc")); setPage(1); resetScroll() }

  // The current page is ready to show only when the hydrated items belong to
  // the active request — otherwise a fetch is still in flight.
  const ready = loaded.key === requestKey
  const totalPages = Math.max(1, Math.ceil(loaded.count / PAGE_LIMIT))

  const goToPage = (p: number) => {
    setPage(p)
    resetScroll()
  }

  // Scroll-collapsing hero: as the page scrolls down the hero fades and drifts
  // upward, and re-reveals on the way back up. (The toolbar pins itself to the
  // top via the sentinel + transform below — not CSS sticky.)
  const { scrollY } = useScroll()
  const heroOpacity = useTransform(scrollY, [0, 200], [1, 0])
  const heroY       = useTransform(scrollY, [0, 200], [0, -32])
  const heroScale   = useTransform(scrollY, [0, 200], [1, 0.96])

  // Pin the controls bar to the top ourselves rather than via `position:
  // sticky` — this page's nested scroll containers (root html/body use
  // overflow-x-hidden, which forces overflow-y:auto) defeat CSS sticky. The
  // sentinel (declared above) marks the bar's natural position; once it scrolls
  // above the viewport top we translate the bar down by the same amount so it
  // stays pinned at the top, and flag `stuck` for the frosted-toolbar styling.
  const barY = useMotionValue(0)
  const [stuck, setStuck] = useState(false)
  useEffect(() => {
    const onScroll = () => {
      const s = sentinelRef.current
      if (!s) { barY.set(0); setStuck(false); return }
      const top = s.getBoundingClientRect().top
      const offset = top < 0 ? -top : 0
      barY.set(offset)
      setStuck(offset > 0)
    }
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [status, barY])

  // Cursor spotlight that softly follows the mouse across the results grid.
  const spotX = useMotionValue(-9999)
  const spotY = useMotionValue(-9999)
  const spotlight = useMotionTemplate`radial-gradient(280px circle at ${spotX}px ${spotY}px, rgba(255,255,255,0.06), transparent 72%)`

  /* ── Gated states ─────────────────────────────────────────────────────── */

  // No signed-out branch: the proxy redirects to /login before this renders, and
  // a session that dies later is redirected by UserContext.
  if (authLoading || !user) {
    return <div className="flex flex-1 items-center justify-center py-32"><Loader /></div>
  }

  /* ── Page ─────────────────────────────────────────────────────────────── */

  return (
    <main className={cn("kby-cursor relative flex-1", barVisible && "pb-20")}>
      <CustomCursor />
      <KobayashiBackground />
      {/* Hero — simply fades + drifts away as the page scrolls (no background
          wash), and re-reveals on scroll up. */}
      <motion.header style={{ opacity: heroOpacity }} className="relative">
        <motion.div
          style={{ y: heroY, scale: heroScale, transformOrigin: "top left" }}
          // Title block leads and takes ALL the flexible space; the deck has
          // a fixed footprint pinned to the right edge (lg+), so together
          // they fill the hero with just the gap between them. Below lg the
          // deck centres underneath the title.
          className="mx-auto flex w-full max-w-7xl flex-col items-stretch gap-8 px-4 pt-12 pb-12 lg:flex-row lg:items-center lg:justify-between lg:gap-10 lg:px-6 lg:pt-16 lg:pb-14"
        >
          <div className="min-w-0 flex-1">
            <motion.p
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="text-xs font-semibold uppercase tracking-[0.3em] text-white/60 sm:text-sm"
            >
              Visual Novel Collection
            </motion.p>
            <HeroTitle name={data?.username ?? USERNAME} />
            <motion.p
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.12 }}
              className="mt-4 text-sm text-muted sm:text-base"
            >
              {data && (
                <>
                  <span className="font-semibold text-white"><Counter value={totalUnique} /></span> titles
                  <span className="mx-1.5 text-white/30">·</span>
                  <Counter value={marksByTab.playing.length} /> playing
                  <span className="mx-1.5 text-white/30">·</span>
                  <Counter value={marksByTab.played.length} /> played
                  <span className="mx-1.5 text-white/30">·</span>
                </>
              )}
              <GitHubLink />
            </motion.p>
          </div>

          <CassetteDeck />
        </motion.div>
      </motion.header>

      {/* Body */}
      <div className="mx-auto max-w-7xl px-4 pb-16 lg:px-6">
        {status === "loading" && (
          <div className="flex justify-center py-24"><Loader /></div>
        )}

        {status === "error" && (
          <ErrorMessage message={errorMsg || "Failed to load collection"} />
        )}

        {status === null && data && (
          <>
            {/* Zero-height marker for the bar's natural position (see the pin
                effect above). */}
            <div ref={sentinelRef} aria-hidden className="h-0" />

            {/* Controls: animated tab pill + content-level selectors. On this
                page there is no global header, so once the hero scrolls away
                this row pins flush to the very top and transforms into a frosted
                toolbar — its background, shadow and a compact title all animate
                in (see `stuck`). */}
            <motion.div style={{ y: barY }} className="relative z-20 mb-6">
              {/* Full-bleed frosted background — spans the whole viewport width
                  when pinned, and is invisible while resting in the page flow. */}
              <div
                aria-hidden
                className={cn(
                  "absolute inset-y-0 left-1/2 -z-10 w-screen -translate-x-1/2 border-b transition-[background-color,border-color,box-shadow] duration-300",
                  stuck
                    ? "border-white/5 bg-background/80 shadow-lg shadow-black/30 backdrop-blur-xl"
                    : "border-transparent bg-transparent shadow-none",
                )}
              />

              <div className="flex flex-col gap-3 py-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center">
              {/* Compact title that expands in once the toolbar pins — the
                  hero's name "collapsing" down into the toolbar. Links home;
                  non-interactive (and untabbable) while collapsed. */}
              <Link
                href="/"
                aria-label="Go to home"
                aria-hidden={!stuck}
                tabIndex={stuck ? 0 : -1}
                className={cn(
                  "overflow-hidden whitespace-nowrap text-lg font-black tracking-tight text-white transition-all duration-300 hover:text-accent",
                  stuck ? "mr-3 max-w-[12rem] opacity-100" : "pointer-events-none mr-0 max-w-0 opacity-0",
                )}
              >
                {data.username || USERNAME}
              </Link>
              <div className="inline-flex rounded-full border border-white/10 bg-white/5 p-1 backdrop-blur-sm">
                {TABS.map(t => {
                  const active = tab === t.key
                  return (
                    <button
                      key={t.key}
                      onClick={() => selectTab(t.key)}
                      className="relative rounded-full px-5 py-2 text-sm font-semibold transition-colors"
                    >
                      {active && (
                        <motion.span
                          layoutId="kobayashi-tab-pill"
                          className="absolute inset-0 rounded-full bg-accent"
                          transition={{ type: "spring", stiffness: 400, damping: 32 }}
                        />
                      )}
                      <span className={cn("relative z-10", active ? "text-black" : "text-muted hover:text-white")}>
                        {t.label}
                        <span className={cn("ml-1.5 tabular-nums", active ? "text-black/70" : "text-white/40")}>
                          {marksByTab[t.key].length}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <SearchBox value={searchInput} onValueChange={setSearchInput} onComposingChange={setIsComposing} />
                <SortMenu value={sort} order={order} onChange={selectSort} onToggleOrder={toggleOrder} />
                <SegmentedControl
                  id="sexual"
                  ariaLabel="Sexual content level"
                  value={sexualLevel}
                  onChange={setSexualLevel}
                  segments={[
                    { value: "safe",       label: "Safe",       short: "Safe", tone: "neutral" },
                    { value: "suggestive", label: "Suggestive", short: "Sug",  tone: "amber"   },
                    { value: "explicit",   label: "Explicit",   short: "Exp",  tone: "red"     },
                  ]}
                />
                <SegmentedControl
                  id="violence"
                  ariaLabel="Violence level"
                  value={violenceLevel}
                  onChange={setViolenceLevel}
                  segments={[
                    { value: "tame",    label: "Tame",    short: "Tame", tone: "neutral" },
                    { value: "violent", label: "Violent", short: "Vio",  tone: "amber"   },
                    { value: "brutal",  label: "Brutal",  short: "Bru",  tone: "red"     },
                  ]}
                />
              </div>
              </div>
            </motion.div>

            {/* Results — a reserved min-height keeps the document from
                collapsing when content swaps (loader / shorter results), so the
                toolbar can stay pinned and the hidden title doesn't pop back.
                A cursor-following spotlight overlays the grid. */}
            <div
              className="relative flex min-h-screen flex-col"
              onMouseMove={e => {
                const r = e.currentTarget.getBoundingClientRect()
                spotX.set(e.clientX - r.left)
                spotY.set(e.clientY - r.top)
              }}
              onMouseLeave={() => { spotX.set(-9999); spotY.set(-9999) }}
            >
              <motion.div aria-hidden className="pointer-events-none absolute inset-0 z-10" style={{ background: spotlight }} />
              {activeMarks.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-24 text-muted">
                  <Library className="h-12 w-12 opacity-40" />
                  <p className="text-base">Nothing in {tab === "playing" ? "Playing" : "Played"} yet</p>
                </div>
              ) : !ready ? (
                <div className="flex flex-1 items-center justify-center py-24"><Loader /></div>
              ) : loaded.items.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-24 text-muted">
                  <Search className="h-12 w-12 opacity-40" />
                  <p className="text-base">{q ? `No matches for “${q}”` : "No results"}</p>
                </div>
              ) : (
                // Re-key on the request so the scroll-reveal replays on change.
                <div key={requestKey} className={cn(GRID_CLASS, "relative z-0")}>
                  {loaded.items.map((vn, i) => {
                    const playable = !!musicAvail[vn.id]
                    const selected = player.track?.vnid === vn.id
                    return (
                      <VNCell
                        key={vn.id}
                        vn={vn}
                        index={i}
                        rating={data.ratings[numericId(vn.id)] ?? 0}
                        showOriginal={showOriginal}
                        sexualLevel={sexualLevel}
                        violenceLevel={violenceLevel}
                        playable={playable}
                        selected={selected}
                        playing={selected && player.playing}
                        // play() toggles when the card is already the loaded
                        // track, so the hover button doubles as pause.
                        onToggle={() => player.play(trackFor(vn))}
                      />
                    )
                  })}
                </div>
              )}

              {ready && totalPages > 1 && (
                <div className="mt-10">
                  <PageNav page={page} totalPages={totalPages} onChange={goToPage} />
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <NowPlayingBar visible={barVisible} />
    </main>
  )
}
