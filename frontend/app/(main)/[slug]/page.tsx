/** Catch-all `/[slug]` route — dispatches to search results or a per-entity detail page. */
"use client"

import { useState, useEffect, useRef, Suspense } from "react"
import { useParams, useSearchParams } from "next/navigation"
import { motion, AnimatePresence } from "motion/react"

import { useUrlParams } from "@/hooks/useUrlParams"
import { useSearchContext } from "@/context/SearchContext"
import { useUserContext } from "@/context/UserContext"
import { api } from "@/lib/api"
import { PAGE_LIMIT } from "@/lib/constants"
import type {
  VN_Small, Release_Small, Character_Small, Producer_Small,
  Staff_Small, Tag_Small, Trait_Small, VNDBQueryParams,
} from "@/lib/types"

import { SexualLevelSelector } from "@/components/selector/SexualLevelSelector"
import { ViolenceLevelSelector } from "@/components/selector/ViolenceLevelSelector"
import { CardTypeSwitch } from "@/components/selector/CardTypeSwitch"
import { GridLayoutSwitch } from "@/components/selector/GridLayoutSwitch"
import { PaginationButtons } from "@/components/button/PaginationButtons"
import { Loading, ErrorPanel, NotFound } from "@/components/status/StatusPanel"
import { VNDetailPage } from "@/components/vn/VNDetailPage"
import { CharacterDetailPage } from "@/components/character/CharacterDetailPage"
import { StaffDetailPage } from "@/components/staff/StaffDetailPage"
import { ProducerDetailPage } from "@/components/producer/ProducerDetailPage"
import { TraitDetailPage } from "@/components/trait/TraitDetailPage"
import { TagDetailPage } from "@/components/tag/TagDetailPage"
import { ReleaseDetailPage } from "@/components/release/ReleaseDetailPage"
import {
  VNsCardsGrid, ReleasesCardsGrid, CharactersCardsGrid,
  ProducersCardsGrid, StaffCardsGrid, TagsCardsGrid, TraitsCardsGrid,
} from "@/components/card/CardsGrid"

// `/v`, `/c`, … → search results; `/v123`, `/c45`, … → detail pages.
// The same seven letters as COLLECTION_TYPES, because those are the types
// `fetchFn` below can fetch and the backend will accept.
const SEARCH_TYPES = /^[vrpcsgi]$/
const DETAIL_TYPES = /^[vrpcsgi]\d+$/


/* ─── Search results ───────────────────────────────────────────────────────── */

function SearchResultsContent({ slug }: { slug: string }) {
  const type = slug as "v" | "r" | "c" | "p" | "s" | "g" | "i"
  const searchParams = useSearchParams()
  const { updateKey } = useUrlParams()
  const { sortBy } = useSearchContext()
  const { defaultSexualLevel, defaultViolenceLevel } = useUserContext()

  const currentPage = parseInt(searchParams.get("page") || "1")

  /* ─── State ────────────────────────────────────────────────────────────── */

  const [status, setStatus] = useState<"loading" | "error" | "notFound" | null>(null)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [totalPages, setTotalPages] = useState(0)

  const [vns, setVns] = useState<VN_Small[]>([])
  const [releases, setReleases] = useState<Release_Small[]>([])
  const [characters, setCharacters] = useState<Character_Small[]>([])
  const [producers, setProducers] = useState<Producer_Small[]>([])
  const [staff, setStaff] = useState<Staff_Small[]>([])
  const [tags, setTags] = useState<Tag_Small[]>([])
  const [traits, setTraits] = useState<Trait_Small[]>([])

  const [cardType, setCardType] = useState<"image" | "text">("image")
  const [layout, setLayout] = useState<"single" | "grid">("grid")
  const [sexualLevel, setSexualLevel] = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  const abortRef = useRef<AbortController | null>(null)

  /* ─── Data fetching ────────────────────────────────────────────────────── */

  // Stable string form so the effect re-runs exactly when the query changes.
  const searchParamsString = searchParams.toString()

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" })

    const fetchItems = async () => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setVns([]); setReleases([]); setCharacters([]); setProducers([])
      setStaff([]); setTags([]); setTraits([])
      setTotalPages(0)
      setStatus("loading")
      setStatusMsg(null)
      try {
        // Forward every URL param to the API as a filter (`tag`, `lang`, …),
        // plus the trio we manage ourselves (`page`, `limit`, `sort`).
        const queryParams: VNDBQueryParams = { page: currentPage, limit: PAGE_LIMIT, sort: sortBy }
        for (const [key, value] of new URLSearchParams(searchParamsString).entries()) {
          queryParams[key as keyof VNDBQueryParams] = value as string
        }
        const fetchFn = {
          v: api.small.vn, r: api.small.release, c: api.small.character,
          p: api.small.producer, s: api.small.staff, g: api.small.tag, i: api.small.trait,
        }
        const response = await fetchFn[type as keyof typeof fetchFn](queryParams, ctrl.signal)
        setTotalPages(Math.ceil(response.count / PAGE_LIMIT))
        if (response.results.length === 0) {
          setStatus("notFound")
        } else {
          if (type === "v") setVns(response.results as VN_Small[])
          else if (type === "r") setReleases(response.results as Release_Small[])
          else if (type === "c") setCharacters(response.results as Character_Small[])
          else if (type === "p") setProducers(response.results as Producer_Small[])
          else if (type === "s") setStaff(response.results as Staff_Small[])
          else if (type === "g") setTags(response.results as Tag_Small[])
          else if (type === "i") setTraits(response.results as Trait_Small[])
          setStatus(null)
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return
        setStatus("error")
        setStatusMsg(error instanceof Error ? error.message : String(error))
      }
    }

    fetchItems()
    return () => abortRef.current?.abort()
  }, [currentPage, searchParamsString, type, sortBy])

  /* ─── Render ────────────────────────────────────────────────────────────── */

  return (
    <main className="container mx-auto flex-1 flex flex-col p-4 pb-8">
      {(type === "v" || type === "c") && (
        <div className="flex flex-col gap-2 mb-4">
          {/* Row 1: card switches */}
          <div className="flex gap-2">
            <CardTypeSwitch cardType={cardType} setCardType={setCardType} />
            <GridLayoutSwitch layout={layout} setLayout={setLayout} />
          </div>
          {/* Row 2: level selectors — always side-by-side (abbreviated labels on mobile) */}
          <div className="flex gap-2">
            <SexualLevelSelector sexualLevel={sexualLevel} setSexualLevel={setSexualLevel} className="w-full" />
            <ViolenceLevelSelector violenceLevel={violenceLevel} setViolenceLevel={setViolenceLevel} className="w-full" />
          </div>
        </div>
      )}
      {(type === "r" || type === "p" || type === "s" || type === "g" || type === "i") && (
        <GridLayoutSwitch layout={layout} setLayout={setLayout} className="mb-4" />
      )}

      <AnimatePresence mode="wait">
        {status !== null && (
          <motion.div key="status" initial={{ filter: "blur(20px)", opacity: 0 }} animate={{ filter: "blur(0px)", opacity: 1 }} exit={{ filter: "blur(20px)", opacity: 0 }} transition={{ duration: 0.4 }} className="grow flex justify-center items-center">
            {status === "loading" && <Loading message="Loading..." />}
            {status === "error" && <ErrorPanel message={statusMsg || "Unknown error"} />}
            {status === "notFound" && <NotFound message="No items found" />}
          </motion.div>
        )}
        {status === null && (
          <motion.div key="content" initial={{ filter: "blur(20px)", opacity: 0 }} animate={{ filter: "blur(0px)", opacity: 1 }} exit={{ filter: "blur(20px)", opacity: 0 }} transition={{ duration: 0.4 }} className="w-full">
            {type === "v" && <VNsCardsGrid vns={vns} layout={layout} cardType={cardType} sexualLevel={sexualLevel} violenceLevel={violenceLevel} />}
            {type === "c" && <CharactersCardsGrid characters={characters} layout={layout} cardType={cardType} sexualLevel={sexualLevel} violenceLevel={violenceLevel} />}
            {type === "r" && <ReleasesCardsGrid releases={releases} layout={layout} />}
            {type === "p" && <ProducersCardsGrid producers={producers} layout={layout} />}
            {type === "s" && <StaffCardsGrid staff={staff} layout={layout} />}
            {type === "g" && <TagsCardsGrid tags={tags} layout={layout} />}
            {type === "i" && <TraitsCardsGrid traits={traits} layout={layout} />}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grow" />
      {totalPages > 0 && (
        <div className="flex justify-center mt-4">
          <PaginationButtons totalPages={totalPages} currentPage={currentPage} onPageChange={p => updateKey("page", p.toString())} />
        </div>
      )}
    </main>
  )
}


/* ─── Detail-page dispatcher ───────────────────────────────────────────────── */

function DetailContent({ slug }: { slug: string }) {
  const type = slug[0]
  const numericId = parseInt(slug.slice(1), 10)

  if (type === "v") return <VNDetailPage id={numericId} />
  if (type === "c") return <CharacterDetailPage id={numericId} />
  if (type === "s") return <StaffDetailPage id={numericId} />
  if (type === "p") return <ProducerDetailPage id={numericId} />
  if (type === "i") return <TraitDetailPage id={numericId} />
  if (type === "g") return <TagDetailPage id={numericId} />
  if (type === "r") return <ReleaseDetailPage id={numericId} />

  return (
    <main className="container mx-auto flex-1 p-4 pb-8">
      <div className="flex items-center justify-center h-64 text-muted">
        <p className="text-sm">Detail view for <span className="text-white font-bold">{slug}</span> — coming soon.</p>
      </div>
    </main>
  )
}


/* ─── Page entry ───────────────────────────────────────────────────────────── */

function SlugContent() {
  const params = useParams()
  const slug = (params.slug as string) || ""

  if (SEARCH_TYPES.test(slug)) {
    return (
      <Suspense fallback={<div className="flex-1 flex items-center justify-center"><Loading message="Loading..." /></div>}>
        <SearchResultsContent slug={slug} />
      </Suspense>
    )
  }

  if (DETAIL_TYPES.test(slug)) {
    return <DetailContent slug={slug} />
  }

  return (
    <main className="container mx-auto flex-1 flex items-center justify-center p-4">
      <NotFound message={`Unknown route: /${slug}`} />
    </main>
  )
}

export default function SlugPage() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><Loading message="Loading..." /></div>}>
      <SlugContent />
    </Suspense>
  )
}
