/** User collections page — browse, search, sort, and bulk-edit marked items per category. */
"use client"

import { useEffect, useState, useMemo, useRef, useCallback, Suspense } from "react"
import { useSearchParams, useRouter, usePathname } from "next/navigation"
import {
  LayoutGrid, LayoutList, AlignJustify, Rows3, ArrowDown, ArrowUp,
  Pencil, Menu, Library, X, ChevronDown, Search,
} from "lucide-react"

import { useUrlParams } from "@/hooks/useUrlParams"
import { useUserContext } from "@/context/UserContext"
import { api } from "@/lib/api"
import { cn, numericId } from "@/lib/utils"
import { dedupeLatestMarks, sortMarksByDate, reorderById } from "@/lib/marks"
import {
  SORT_OPTIONS, LOCAL_SORTS, VIEW_MODES, SHELF_SUPPORTED_TYPES,
  prefixForType, type ViewMode,
} from "@/lib/collections"
import { PAGE_LIMIT, COLLECTION_TYPE_MAP } from "@/lib/constants"
import type {
  Category, Mark,
  VN_Small, Release_Small, Character_Small, Producer_Small,
  Staff_Small, Tag_Small, Trait_Small,
} from "@/lib/types"

import { SexualLevelSelector } from "@/components/selector/SexualLevelSelector"
import { ViolenceLevelSelector } from "@/components/selector/ViolenceLevelSelector"
import { CollectionSidebar } from "@/components/category/CollectionSidebar"
import { MoveToDialog } from "@/components/category/MoveToDialog"
import {
  VNsCardsGrid, ReleasesCardsGrid, CharactersCardsGrid,
  ProducersCardsGrid, StaffCardsGrid, TagsCardsGrid, TraitsCardsGrid,
  CollectionCardProps,
} from "@/components/card/CardsGrid"
import { CardsShelfRow } from "@/components/card/CardsShelfRow"
import { PaginationButtons } from "@/components/button/PaginationButtons"
import { ErrorPanel, Loading } from "@/components/status/StatusPanel"
import { EditModeBar } from "./_components/EditModeBar"


/* ─── Grid dispatch ────────────────────────────────────────────────────────── */
// Maps an entity type to its card grid; the only render code the page keeps
// inline, since it threads the page's content-level + collection chrome props.

interface CollectionGridProps extends CollectionCardProps {
  view: ViewMode
  sexualLevel?: "safe" | "suggestive" | "explicit"
  violenceLevel?: "tame" | "violent" | "brutal"
}

function renderCollectionGrid(type: string, items: unknown[], props: CollectionGridProps) {
  const { sexualLevel, violenceLevel, ...rest } = props
  switch (type) {
    case "vn":        return <VNsCardsGrid        vns={items as VN_Small[]}                sexualLevel={sexualLevel} violenceLevel={violenceLevel} {...rest} />
    case "release":   return <ReleasesCardsGrid   releases={items as Release_Small[]}      {...rest} />
    case "character": return <CharactersCardsGrid characters={items as Character_Small[]}  sexualLevel={sexualLevel} violenceLevel={violenceLevel} {...rest} />
    case "producer":  return <ProducersCardsGrid  producers={items as Producer_Small[]}    {...rest} />
    case "staff":     return <StaffCardsGrid      staff={items as Staff_Small[]}           {...rest} />
    case "tag":       return <TagsCardsGrid       tags={items as Tag_Small[]}              {...rest} />
    case "trait":     return <TraitsCardsGrid     traits={items as Trait_Small[]}          {...rest} />
    default:          return null
  }
}


/* ─── Main content ─────────────────────────────────────────────────────────── */
// Wrapped in <Suspense> at the bottom because `useSearchParams` requires it.

function CollectionContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const { updateMultipleKeys } = useUrlParams()
  const { user, isLoading: authLoading, defaultSexualLevel, defaultViolenceLevel } = useUserContext()
  const [sexualLevel, setSexualLevel] = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  /* ─── State ────────────────────────────────────────────────────────────── */

  /* URL-driven filters */
  const type    = searchParams.get("type")  ?? "vn"
  const cidRaw  = searchParams.get("cid")   ?? "all"
  const q       = searchParams.get("q")     ?? ""
  const sort    = searchParams.get("sort")  ?? "date_added"
  const order   = searchParams.get("order") ?? "desc"

  const activeCategory: number | "all" = cidRaw === "all" ? "all" : parseInt(cidRaw)

  // Page index is kept local — paging shouldn't grow the URL or affect history.
  const [page, setPage] = useState(1)

  /* Server-derived state */
  const [categories, setCategories]               = useState<Category[]>([])
  const [items, setItems]                         = useState<unknown[]>([])
  const [totalCount, setTotalCount]               = useState(0)
  const [loadingCategories, setLoadingCategories] = useState(false)
  const [loadingItems, setLoadingItems]           = useState(false)
  // What the last fetch failed with, so a failure is not shown as an empty
  // collection — which reads as the collection having been lost.
  const [itemsError, setItemsError]               = useState<string | null>(null)
  // Personal ratings for the current type, keyed by numeric mark id.
  const [ratings, setRatings]                     = useState<Record<number, number>>({})

  /* UI state */
  const [editMode, setEditMode]                   = useState(false)
  const [selectedIds, setSelectedIds]             = useState<Set<string>>(new Set())
  const [moveDialogOpen, setMoveDialogOpen]       = useState(false)
  const [moveSingleId, setMoveSingleId]           = useState<string | null>(null)
  const [showMobileSidebar, setShowMobileSidebar] = useState(false)
  const [view, setView]                           = useState<ViewMode>("grid")

  const abortRef = useRef<AbortController | null>(null)

  /* ─── Derived state & effects ──────────────────────────────────────────── */

  /* Search input: local state + IME-safe debounced commit to URL */
  const [searchInput, setSearchInput] = useState(q)
  const [isComposing, setIsComposing] = useState(false)
  const lastCommittedRef              = useRef(q)

  // External URL change → sync local input (e.g. browser back, link change).
  useEffect(() => {
    if (q !== lastCommittedRef.current) {
      setSearchInput(q)
      lastCommittedRef.current = q
    }
  }, [q])

  // Local input change → debounced URL update. Skip while composing IME, but
  // re-run on `isComposing` change so the final committed text actually fires.
  // Also auto-switches off `date_added` sort when a search is active —
  // userserve has no title index, so "date_added + search" has no honest answer.
  useEffect(() => {
    if (isComposing) return
    if (searchInput === lastCommittedRef.current) return
    const t = setTimeout(() => {
      lastCommittedRef.current = searchInput
      const updates: Record<string, string> = { q: searchInput }
      if (searchInput && LOCAL_SORTS.has(sort)) {
        const fallback = (SORT_OPTIONS[type] ?? SORT_OPTIONS.vn)[1]?.value
        if (fallback) updates.sort = fallback
      }
      updateMultipleKeys(updates)
    }, 300)
    return () => clearTimeout(t)
  }, [searchInput, isComposing, sort, type, updateMultipleKeys])

  const clearSearch = useCallback(() => {
    setSearchInput("")
    lastCommittedRef.current = ""
    updateMultipleKeys({ q: "" })
  }, [updateMultipleKeys])

  // Restore last-used view mode from localStorage.
  useEffect(() => {
    const stored = localStorage.getItem("collectionView") as ViewMode | null
    if (stored && (VIEW_MODES as string[]).includes(stored)) setView(stored)
  }, [])

  // Shelf mode is only valid when viewing all collections of a supported type.
  // If conditions change underneath it, fall back to grid for rendering — but
  // we don't overwrite the stored view, so flipping back to "all"+vn restores it.
  const isShelf =
    view === "shelf" &&
    activeCategory === "all" &&
    SHELF_SUPPORTED_TYPES.has(type)
  const shelfAvailable =
    activeCategory === "all" && SHELF_SUPPORTED_TYPES.has(type)
  const effectiveView: ViewMode = isShelf ? "shelf" : (view === "shelf" ? "grid" : view)

  // Reset to page 1 whenever the result set could change.
  useEffect(() => { setPage(1) }, [q, sort, order, type, cidRaw])

  /* Flat mark list for the current type+category, sorted by `marked_at`.
     For "All", we dedupe by id keeping the latest marked_at to match the
     userserve aggregation — otherwise the date-added badge on a card and the
     page-order from userserve can disagree. */
  const allMarks = useMemo<Mark[]>(() => {
    const dir = order === "asc" ? "asc" : "desc"
    if (activeCategory === "all") {
      return sortMarksByDate(dedupeLatestMarks(categories.flatMap(c => c.marks)), dir)
    }
    const cat = categories.find(c => c.id === activeCategory)
    return cat ? sortMarksByDate(cat.marks, dir) : []
  }, [categories, activeCategory, order])

  // Lookup table: `${prefix}${id}` → marked_at, used to render date badges.
  const markedAtMap = useMemo<Record<string, string>>(() => {
    const prefix = prefixForType(type)
    const map: Record<string, string> = {}
    for (const m of allMarks) map[`${prefix}${m.id}`] = m.marked_at
    return map
  }, [allMarks, type])

  // Same `${prefix}${id}` keying as markedAtMap, so cards can look up a rating
  // by the card id the adapters produce.
  const ratingsMap = useMemo<Record<string, number>>(() => {
    const prefix = prefixForType(type)
    const map: Record<string, number> = {}
    for (const [markId, value] of Object.entries(ratings)) map[`${prefix}${markId}`] = value
    return map
  }, [ratings, type])

  const refreshCategories = useCallback(async () => {
    if (!user) return
    const data = await api.category.get(type)
    setCategories(data)
  }, [user, type])

  // Load categories when the user or active type changes; reset cid to "all"
  // if the previously selected category no longer exists under the new type.
  useEffect(() => {
    if (!user) { setCategories([]); return }
    setLoadingCategories(true)
    api.category.get(type)
      .then(data => {
        setCategories(data)
        if (cidRaw !== "all") {
          const exists = data.some(c => c.id === parseInt(cidRaw))
          if (!exists) {
            const params = new URLSearchParams(searchParams)
            params.delete("cid")
            router.replace(`${pathname}?${params.toString()}`)
          }
        }
      })
      .catch(() => setCategories([]))
      .finally(() => setLoadingCategories(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, type])

  // Load personal ratings for the current type (cheap id→rating map).
  useEffect(() => {
    if (!user) { setRatings({}); return }
    let cancelled = false
    api.rating.get(type)
      .then(data => { if (!cancelled) setRatings(data) })
      .catch(() => { if (!cancelled) setRatings({}) })
    return () => { cancelled = true }
  }, [user, type])

  // Drives re-fetch of the "my_rating" page when the relevant ratings change.
  // A stable "" outside that sort means rating edits never refetch other views.
  const ratingSortSignature = useMemo(() => {
    if (sort !== "my_rating") return ""
    return allMarks.map(m => `${m.id}:${ratings[m.id] ?? 0}`).join(",")
  }, [sort, allMarks, ratings])

  /* Fetch the current page of items.
     Three strategies:
       - date_added + no search → userserve paginates by `marked_at`, then we
         hydrate the page from VNDB and re-order to match the userserve order.
       - my_rating + no search → order ids locally by rating, paginate, then
         hydrate from VNDB and re-order to match.
       - everything else → fetch the full id set from VNDB with the requested
         sort + (optional) search applied. */
  useEffect(() => {
    abortRef.current?.abort()
    if (isShelf) {
      // Shelf rows fetch their own items per category; the main flat list is unused.
      setItems([])
      setTotalCount(0)
      setLoadingItems(false)
      return
    }
    if (!user || allMarks.length === 0) {
      setItems([])
      setTotalCount(0)
      setLoadingItems(false)
      return
    }

    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoadingItems(true)
    setItemsError(null)

    const run = async () => {
      try {
        if (sort === "date_added" && !q) {
          const cidParam: number | "all" = activeCategory === "all" ? "all" : (activeCategory as number)
          const marksPage = await api.category.getMarks(
            type,
            { cid: cidParam, sort: "marked_at", reverse: order !== "asc", page, limit: PAGE_LIMIT },
            ctrl.signal,
          )
          const pageIds = marksPage.results.map(m => m.id)
          if (pageIds.length === 0) {
            setItems([])
            setTotalCount(marksPage.count ?? 0)
            return
          }
          const data = await api.small.byIdsForType(type, pageIds, { limit: PAGE_LIMIT }, ctrl.signal)
          const ordered = reorderById(data.results as { id: string }[], pageIds)
          setItems(ordered)
          setTotalCount(marksPage.count ?? ordered.length)
        } else if (sort === "my_rating" && !q) {
          // Sort the marks by personal rating client-side (VNDB can't), then
          // paginate and hydrate the page, preserving the local order.
          const ordered = [...allMarks].sort((a, b) => {
            const ra = ratings[a.id] ?? 0
            const rb = ratings[b.id] ?? 0
            if (ra !== rb) return order === "asc" ? ra - rb : rb - ra
            // Tiebreak: most recently added first.
            return new Date(b.marked_at).getTime() - new Date(a.marked_at).getTime()
          })
          const total = ordered.length
          const start = (page - 1) * PAGE_LIMIT
          const pageIds = ordered.slice(start, start + PAGE_LIMIT).map(m => m.id)
          if (pageIds.length === 0) {
            setItems([])
            setTotalCount(total)
            return
          }
          const data = await api.small.byIdsForType(type, pageIds, { limit: PAGE_LIMIT }, ctrl.signal)
          setItems(reorderById(data.results as { id: string }[], pageIds))
          setTotalCount(total)
        } else {
          const allIds = allMarks.map(m => m.id)
          const params: Record<string, unknown> = {
            sort: LOCAL_SORTS.has(sort) ? "id" : sort,
            reverse: order === "desc",
            page,
            limit: PAGE_LIMIT,
            ...(q ? { search: q } : {}),
          }
          const data = await api.small.byIdsForType(type, allIds, params, ctrl.signal)
          setItems(data.results)
          setTotalCount(data.count)
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name !== "AbortError") {
          setItems([])
          setTotalCount(0)
          setItemsError(e.message)
        }
      } finally {
        if (!ctrl.signal.aborted) setLoadingItems(false)
      }
    }
    run()
    return () => ctrl.abort()
  // `ratings` is read only in the my_rating branch; `ratingSortSignature`
  // captures the relevant changes, so listing `ratings` directly would refetch
  // every other view on each rating edit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allMarks, sort, order, page, q, type, user, activeCategory, isShelf, ratingSortSignature])


  /* ─── Handlers ─────────────────────────────────────────────────────────── */

  // Optimistically update the rating map; revert on failure. `value === 0`
  // clears the rating (StarRating emits 0 when the current star is re-clicked).
  const handleRate = async (itemId: string, value: number) => {
    const markId = numericId(itemId)
    const prev = ratings[markId] ?? 0
    if (value === prev) return
    setRatings(cur => {
      const next = { ...cur }
      if (value === 0) delete next[markId]
      else next[markId] = value
      return next
    })
    try {
      if (value === 0) await api.rating.clear(type, markId)
      else await api.rating.set(type, markId, value)
    } catch {
      setRatings(cur => {
        const next = { ...cur }
        if (prev === 0) delete next[markId]
        else next[markId] = prev
        return next
      })
    }
  }

  const handleRemove = async (itemId: string) => {
    const markId = numericId(itemId)
    if (activeCategory === "all") {
      // In "All" view we have to discover which category currently owns this mark.
      const cat = categories.find(c => c.marks.some(m => m.id === markId))
      if (!cat) return
      await api.category.removeMark(type, cat.id, markId)
    } else {
      await api.category.removeMark(type, activeCategory as number, markId)
    }
    await refreshCategories()
  }

  const handleMove = (itemId: string) => {
    setMoveSingleId(itemId)
    setMoveDialogOpen(true)
  }

  const handleMoveConfirm = async (targetCategoryId: number) => {
    const fromCategoryId = activeCategory === "all" ? null : (activeCategory as number)
    if (moveSingleId) {
      const markId = numericId(moveSingleId)
      const sourceCat = fromCategoryId != null
        ? fromCategoryId
        : categories.find(c => c.marks.some(m => m.id === markId))?.id
      if (sourceCat != null) {
        await api.category.moveMarks(type, sourceCat, targetCategoryId, [markId])
      }
    } else if (selectedIds.size > 0) {
      const markIds = Array.from(selectedIds).map(numericId)
      if (fromCategoryId != null) {
        await api.category.moveMarks(type, fromCategoryId, targetCategoryId, markIds)
      }
    }
    setMoveSingleId(null)
    setSelectedIds(new Set())
    setEditMode(false)
    setMoveDialogOpen(false)
    await refreshCategories()
  }

  const handleBatchDelete = async () => {
    const markIds = Array.from(selectedIds).map(numericId)
    if (activeCategory === "all") {
      // Marks may live across several categories; remove from each in parallel.
      const groups = new Map<number, number[]>()
      for (const markId of markIds) {
        const cat = categories.find(c => c.marks.some(m => m.id === markId))
        if (cat) {
          const arr = groups.get(cat.id) ?? []
          arr.push(markId)
          groups.set(cat.id, arr)
        }
      }
      await Promise.all(Array.from(groups.entries()).map(([catId, ids]) =>
        api.category.removeMarks(type, catId, ids)
      ))
    } else {
      await api.category.removeMarks(type, activeCategory as number, markIds)
    }
    setSelectedIds(new Set())
    setEditMode(false)
    await refreshCategories()
  }

  const handleToggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const currentPageIds = useMemo(
    () => items.map(it => (it as { id: string }).id),
    [items]
  )
  const allCurrentSelected = currentPageIds.length > 0 && currentPageIds.every(id => selectedIds.has(id))

  const handleToggleSelectAll = () => {
    if (allCurrentSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev)
        for (const id of currentPageIds) next.delete(id)
        return next
      })
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev)
        for (const id of currentPageIds) next.add(id)
        return next
      })
    }
  }

  const handleTypeChange = (newType: string) => {
    setItems([])   // Drop stale items so we don't briefly render with the wrong card grid.
    const params = new URLSearchParams()
    params.set("type", newType)
    router.push(`${pathname}?${params.toString()}`)
    setEditMode(false)
    setSelectedIds(new Set())
  }

  const handleCategorySelect = (id: number | "all") => {
    const params = new URLSearchParams(searchParams)
    if (id === "all") params.delete("cid")
    else params.set("cid", String(id))
    router.push(`${pathname}?${params.toString()}`)
    setShowMobileSidebar(false)
    setEditMode(false)
    setSelectedIds(new Set())
  }

  const handleCreate = async (name: string) => {
    await api.category.create(type, name)
    await refreshCategories()
  }

  const handleRename = async (id: number, name: string) => {
    await api.category.update(type, id, name)
    await refreshCategories()
  }

  const handleDelete = async (id: number) => {
    await api.category.delete(type, id)
    if (activeCategory === id) {
      const params = new URLSearchParams(searchParams)
      params.delete("cid")
      router.replace(`${pathname}?${params.toString()}`)
    }
    await refreshCategories()
  }

  const setViewPersisted = (v: ViewMode) => {
    setView(v)
    localStorage.setItem("collectionView", v)
    // Edit mode has no meaning in shelf view (no batch ops, no page concept),
    // so drop any in-flight edit state when switching to it.
    if (v === "shelf") {
      setEditMode(false)
      setSelectedIds(new Set())
    }
  }

  /* Derived values for the render pass */
  const totalPages = Math.ceil(totalCount / PAGE_LIMIT)
  const activeCategoryName = activeCategory === "all"
    ? `All ${COLLECTION_TYPE_MAP[type]?.label ?? type}s`
    : (categories.find(c => c.id === activeCategory)?.category_name ?? "")
  const sortOptions = SORT_OPTIONS[type] ?? SORT_OPTIONS.vn
  const canMove = activeCategory !== "all" && categories.length > 1


  /* ─── Render ───────────────────────────────────────────────────────────── */

  return (
    // At lg+ this is a two-column shell (sidebar + main) that scrolls inside a
    // viewport-height box. Below lg the sidebar collapses to an overlay, so we
    // drop the fixed height / inner scroll and let the page scroll normally —
    // which also lets the global header auto-hide on scroll.
    <div className="flex lg:h-[calc(100vh_-_var(--header-h,56px))] lg:overflow-hidden">
      {/* Desktop sidebar */}
      <CollectionSidebar
        className="hidden lg:flex shrink-0 w-64"
        activeType={type}
        activeCategory={activeCategory}
        categories={categories}
        onTypeChange={handleTypeChange}
        onCategorySelect={handleCategorySelect}
        onCreate={handleCreate}
        onRename={handleRename}
        onDelete={handleDelete}
      />

      {/* Mobile sidebar overlay */}
      {showMobileSidebar && (
        <div
          className="lg:hidden fixed inset-0 z-50 bg-black/60"
          onClick={() => setShowMobileSidebar(false)}
        >
          <div
            className="absolute left-0 inset-y-0 w-64"
            onClick={e => e.stopPropagation()}
          >
            <CollectionSidebar
              className="flex w-full h-full"
              activeType={type}
              activeCategory={activeCategory}
              categories={categories}
              onTypeChange={handleTypeChange}
              onCategorySelect={handleCategorySelect}
              onCreate={handleCreate}
              onRename={handleRename}
              onDelete={handleDelete}
            />
          </div>
        </div>
      )}

      {/* Main content */}
      <div className={cn("flex-1 min-w-0 lg:overflow-y-auto lg:overscroll-contain", editMode && "pb-24")}>
        <div className="px-4 lg:px-6 py-6 max-w-7xl mx-auto">

          {authLoading && (
            <div className="flex justify-center py-24">
              <Loading />
            </div>
          )}

          {user && (
            <>
              {/* Category heading */}
              <div className="flex items-center gap-3 mb-4">
                <h1 className="text-2xl font-bold text-white">
                  {activeCategoryName}
                  {(isShelf ? allMarks.length : totalCount) > 0 && (
                    <span className="text-muted font-normal text-base ml-2">
                      {isShelf ? allMarks.length : totalCount}
                    </span>
                  )}
                </h1>
              </div>

              {/* Content level selectors */}
              <div className="flex gap-2 mb-3">
                <SexualLevelSelector sexualLevel={sexualLevel} setSexualLevel={setSexualLevel} className="w-full" />
                <ViolenceLevelSelector violenceLevel={violenceLevel} setViolenceLevel={setViolenceLevel} className="w-full" />
              </div>

              {/* Search / sort / view bar.
                  Shelf mode skips sort / order / search / edit — each shelf is
                  fixed to `marked_at desc` and shows a snippet, so those
                  controls have nothing to act on. */}
              <div className="flex flex-wrap items-center gap-2 mb-4">
                {/* Mobile: sidebar toggle — sits left of the search box on small
                    screens; the desktop sidebar is always visible at lg+. */}
                <button
                  className="lg:hidden shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-elevated border border-white/10 text-sm text-muted hover:text-white hover:bg-white/10 transition-colors"
                  onClick={() => setShowMobileSidebar(true)}
                  title="Collections"
                >
                  <Menu className="w-4 h-4" />
                  <span className="hidden sm:inline">Collections</span>
                </button>

                {!isShelf && (
                  <div className="flex-1 min-w-40 lg:w-64 lg:flex-none relative">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted/60" />
                    <input
                      type="text"
                      value={searchInput}
                      onChange={e => setSearchInput(e.target.value)}
                      onCompositionStart={() => setIsComposing(true)}
                      onCompositionEnd={e => {
                        setIsComposing(false)
                        setSearchInput(e.currentTarget.value)
                      }}
                      placeholder="Search in collection…"
                      className="w-full bg-elevated border border-white/10 rounded-lg pl-8 pr-7 py-1.5 text-sm text-white placeholder:text-muted/50 outline-none focus:border-white/30 transition-colors"
                    />
                    {searchInput && (
                      <button
                        onClick={clearSearch}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-white"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                )}

                {!isShelf && (
                  <div className="relative">
                    <select
                      value={sort}
                      onChange={e => updateMultipleKeys({ sort: e.target.value })}
                      className="appearance-none bg-elevated border border-white/10 rounded-lg pl-3 pr-8 py-1.5 text-sm text-white outline-none focus:border-white/30 cursor-pointer transition-colors"
                    >
                      {sortOptions.map(o => {
                        const disabled = !!q && o.value === "date_added"
                        return (
                          <option key={o.value} value={o.value} disabled={disabled}>
                            {o.label}{disabled ? " (clear search)" : ""}
                          </option>
                        )
                      })}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
                  </div>
                )}

                {!isShelf && (
                  <button
                    onClick={() => updateMultipleKeys({ order: order === "desc" ? "asc" : "desc" })}
                    className="p-1.5 rounded-lg bg-elevated border border-white/10 text-muted hover:text-white hover:bg-white/10 transition-colors"
                    title={order === "desc" ? "Descending" : "Ascending"}
                  >
                    {order === "desc" ? <ArrowDown className="w-4 h-4" /> : <ArrowUp className="w-4 h-4" />}
                  </button>
                )}

                {/* View mode toggle */}
                <div className={cn("flex rounded-lg overflow-hidden border border-white/10", isShelf && "ml-auto")}>
                  {(["grid", "list", "compact", "shelf"] as ViewMode[]).map(v => {
                    if (v === "shelf" && !shelfAvailable) return null
                    return (
                      <button
                        key={v}
                        onClick={() => setViewPersisted(v)}
                        className={cn(
                          "p-1.5 transition-colors",
                          view === v ? "bg-white/15 text-white" : "text-muted hover:text-white hover:bg-white/10 bg-elevated"
                        )}
                        title={v.charAt(0).toUpperCase() + v.slice(1)}
                      >
                        {v === "grid"    && <LayoutGrid    className="w-4 h-4" />}
                        {v === "list"    && <LayoutList    className="w-4 h-4" />}
                        {v === "compact" && <AlignJustify  className="w-4 h-4" />}
                        {v === "shelf"   && <Rows3         className="w-4 h-4" />}
                      </button>
                    )
                  })}
                </div>

                {!isShelf && (
                  <button
                    onClick={() => { setEditMode(!editMode); setSelectedIds(new Set()) }}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition-colors",
                      editMode
                        ? "bg-accent/20 border-accent text-accent"
                        : "bg-elevated border-white/10 text-muted hover:text-white hover:bg-white/10"
                    )}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                    {editMode ? "Done" : "Edit"}
                  </button>
                )}
              </div>


              {/* Loading categories */}
              {loadingCategories && (
                <div className="flex justify-center py-24"><Loading /></div>
              )}

              {/* Empty state: no categories */}
              {!loadingCategories && categories.length === 0 && (
                <div className="flex flex-col items-center justify-center py-24 gap-4 text-muted">
                  <Library className="w-12 h-12 opacity-40" />
                  <p className="text-base">No collections yet</p>
                  <button
                    onClick={() => setShowMobileSidebar(true)}
                    className="lg:hidden px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg text-sm transition-colors"
                  >
                    Create a Collection
                  </button>
                  <p className="hidden lg:block text-sm">Use the sidebar to create your first collection</p>
                </div>
              )}

              {/* Items */}
              {!loadingCategories && categories.length > 0 && (
                <>
                  {isShelf ? (
                    allMarks.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted">
                        <Library className="w-12 h-12 opacity-40" />
                        <p className="text-base">No marks yet</p>
                      </div>
                    ) : (
                      <div>
                        {categories
                          .filter(cat => cat.marks.length > 0)
                          .map(cat => (
                            <CardsShelfRow
                              key={cat.id}
                              type={type}
                              category={cat}
                              sexualLevel={sexualLevel}
                              violenceLevel={violenceLevel}
                              onRemove={handleRemove}
                              onMove={canMove ? handleMove : undefined}
                              markedAtMap={markedAtMap}
                              onSeeAll={handleCategorySelect}
                            />
                          ))}
                      </div>
                    )
                  ) : loadingItems ? (
                    <div className="flex justify-center py-24"><Loading /></div>
                  ) : itemsError ? (
                    <div className="flex justify-center py-24"><ErrorPanel message={itemsError} /></div>
                  ) : items.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted">
                      <Library className="w-12 h-12 opacity-40" />
                      <p className="text-base">This collection is empty</p>
                    </div>
                  ) : (
                    renderCollectionGrid(type, items, {
                      view: effectiveView,
                      sexualLevel,
                      violenceLevel,
                      onRemove: handleRemove,
                      onMove:   handleMove,
                      editMode,
                      selectedIds,
                      onToggleSelect: handleToggleSelect,
                      markedAtMap,
                      ratingsMap,
                      onRate: handleRate,
                    })
                  )}

                  {/* Pagination — hidden in shelf mode (each shelf has its own "See all"). */}
                  {!isShelf && totalPages > 1 && (
                    <div className="mt-8">
                      <PaginationButtons
                        totalPages={totalPages}
                        currentPage={page}
                        onPageChange={p => setPage(p)}
                      />
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Floating batch action bar (Spotify-style) */}
      {user && editMode && (
        <EditModeBar
          selectedCount={selectedIds.size}
          allCurrentSelected={allCurrentSelected}
          hasCurrentPage={currentPageIds.length > 0}
          canMove={canMove}
          onToggleSelectAll={handleToggleSelectAll}
          onMove={() => { setMoveSingleId(null); setMoveDialogOpen(true) }}
          onDelete={handleBatchDelete}
          onClose={() => { setEditMode(false); setSelectedIds(new Set()) }}
        />
      )}

      {/* Move dialog */}
      <MoveToDialog
        open={moveDialogOpen}
        setOpen={setMoveDialogOpen}
        categories={categories}
        currentCategoryId={activeCategory === "all" ? null : (activeCategory as number)}
        onMove={handleMoveConfirm}
      />
    </div>
  )
}


export default function CollectionPage() {
  return (
    <Suspense fallback={
      <div className="flex justify-center items-center py-24">
        <Loading />
      </div>
    }>
      <CollectionContent />
    </Suspense>
  )
}
