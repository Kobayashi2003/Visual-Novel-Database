/** Home page — paginated grid of recent VN releases filtered by year and month. */
"use client"

import { useEffect, useState, useRef, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { motion, AnimatePresence } from "motion/react"
import { ArrowBigLeftIcon, ArrowBigRightIcon } from "lucide-react"

import { useUrlParams } from "@/hooks/useUrlParams"
import { api } from "@/lib/api"
import { PAGE_LIMIT } from "@/lib/constants"
import { VN_Small } from "@/lib/types"
import { useUserContext } from "@/context/UserContext"

import { YearSelector } from "@/components/selector/YearSelector"
import { MonthSelector } from "@/components/selector/MonthSelector"
import { SexualLevelSelector } from "@/components/selector/SexualLevelSelector"
import { ViolenceLevelSelector } from "@/components/selector/ViolenceLevelSelector"
import { CardTypeSwitch } from "@/components/selector/CardTypeSwitch"
import { GridLayoutSwitch } from "@/components/selector/GridLayoutSwitch"
import { PaginationButtons } from "@/components/button/PaginationButtons"
import { IconButton } from "@/components/button/IconButton"
import { Loading, ErrorPanel, NotFound } from "@/components/status/StatusPanel"
import { VNsCardsGrid } from "@/components/card/CardsGrid"

function HomeContent() {
  const searchParams = useSearchParams()
  const { updateKey, updateMultipleKeys } = useUrlParams()
  const { defaultSexualLevel, defaultViolenceLevel } = useUserContext()

  /* ─── URL-derived params ───────────────────────────────────────────────── */

  const currentPage = searchParams.get("page") ? parseInt(searchParams.get("page")!) : 1
  // "00" is the "any" sentinel from YearSelector / MonthSelector.
  const selectedYear = searchParams.get("year") || `${new Date().getFullYear()}`
  const selectedMonth = searchParams.get("month") || `${(new Date().getMonth() + 1).toString().padStart(2, "0")}`

  /* ─── State ────────────────────────────────────────────────────────────── */

  const [status, setStatus] = useState<"loading" | "error" | "notFound" | null>(null)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [vns, setVns] = useState<VN_Small[]>([])
  const [totalPages, setTotalPages] = useState(0)
  const [cardType, setCardType] = useState<"image" | "text">("image")
  const [layout, setLayout] = useState<"single" | "grid">("grid")
  const [sexualLevel, setSexualLevel] = useState(defaultSexualLevel)
  const [violenceLevel, setViolenceLevel] = useState(defaultViolenceLevel)

  const abortRef = useRef<AbortController | null>(null)

  /* ─── Data fetching ────────────────────────────────────────────────────── */

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" })

    const fetchVNs = async () => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setVns([])
      setTotalPages(0)
      setStatus("loading")
      setStatusMsg(null)
      try {
        // The OR-of-AND `released` filter handles both "exact year" and
        // "year+month range" forms VNDB exposes for partial release dates.
        let released = ""
        if (selectedYear !== "00" && selectedMonth === "00") {
          released = `(>=${selectedYear}-01-01+<=${selectedYear}-12-31),(=${selectedYear})`
        } else if (selectedYear !== "00" && selectedMonth !== "00") {
          const lastDay = new Date(parseInt(selectedYear), parseInt(selectedMonth), 0).getDate()
          released = `(>=${selectedYear}-${selectedMonth}-01+<=${selectedYear}-${selectedMonth}-${lastDay}),(=${selectedYear}-${selectedMonth})`
        }
        const response = await api.small.vn({ released, olang: "ja", sort: "released", reverse: true, page: currentPage, limit: PAGE_LIMIT }, ctrl.signal)
        setVns(response.results)
        setTotalPages(Math.ceil(response.count / PAGE_LIMIT) || 1)
        setStatus(response.results.length === 0 ? "notFound" : null)
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return
        setStatus("error")
        setStatusMsg(error instanceof Error ? error.message : String(error))
      }
    }

    fetchVNs()
    return () => abortRef.current?.abort()
  }, [currentPage, selectedYear, selectedMonth])

  /* ─── Month navigation ─────────────────────────────────────────────────── */

  // Date arrow guards: don't let the user step past the supported VNDB range
  // (1985-01 through next-year-12).
  const monthAddable = () => {
    const yr = parseInt(selectedYear), mo = parseInt(selectedMonth)
    if (yr === new Date().getFullYear() + 1) return mo !== 12
    return true
  }

  const monthSubable = () => {
    const yr = parseInt(selectedYear), mo = parseInt(selectedMonth)
    if (yr === 1985) return mo !== 1
    return true
  }

  const handleMonthAdd = () => {
    const mo = parseInt(selectedMonth), yr = parseInt(selectedYear)
    if (mo === 12) updateMultipleKeys({ month: "01", year: (yr + 1).toString(), page: "1" })
    else updateMultipleKeys({ month: (mo + 1).toString().padStart(2, "0"), year: selectedYear, page: "1" })
  }

  const handleMonthSub = () => {
    const mo = parseInt(selectedMonth), yr = parseInt(selectedYear)
    if (mo === 1) updateMultipleKeys({ month: "12", year: (yr - 1).toString(), page: "1" })
    else updateMultipleKeys({ month: (mo - 1).toString().padStart(2, "0"), year: selectedYear, page: "1" })
  }

  /* ─── Render ────────────────────────────────────────────────────────────── */

  return (
    <main className="container mx-auto flex-1 flex flex-col p-4 pb-8">
      {/* Row 1: card switches (left) + year/month nav (right) */}
      <div className="flex items-center gap-2 mb-2">
        <div className="flex gap-2 shrink-0">
          <CardTypeSwitch cardType={cardType} setCardType={setCardType} />
          <GridLayoutSwitch layout={layout} setLayout={setLayout} />
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <IconButton
            icon={<ArrowBigLeftIcon className="w-4 h-4 fill-amber-100" />}
            onClick={handleMonthSub}
            disabled={status === "loading" || selectedYear === "00" || selectedMonth === "00" || !monthSubable()}
            tooltip="Previous Month"
            className="hover:bg-white/5 max-sm:hidden"
          />
          <YearSelector selectedYear={selectedYear} setSelectedYear={v => updateMultipleKeys({ year: v, page: "1" })} disabled={status === "loading"} />
          <MonthSelector selectedMonth={selectedYear === "00" ? "00" : selectedMonth} setSelectedMonth={v => updateMultipleKeys({ month: v, page: "1" })} disabled={status === "loading" || selectedYear === "00"} />
          <IconButton
            icon={<ArrowBigRightIcon className="w-4 h-4 fill-amber-100" />}
            onClick={handleMonthAdd}
            disabled={status === "loading" || selectedYear === "00" || selectedMonth === "00" || !monthAddable()}
            tooltip="Next Month"
            className="hover:bg-white/5 max-sm:hidden"
          />
        </div>
      </div>
      {/* Row 2: level selectors — always side-by-side (abbreviated labels on mobile) */}
      <div className="flex gap-2 mb-4">
        <SexualLevelSelector sexualLevel={sexualLevel} setSexualLevel={setSexualLevel} className="w-full" />
        <ViolenceLevelSelector violenceLevel={violenceLevel} setViolenceLevel={setViolenceLevel} className="w-full" />
      </div>

      <AnimatePresence mode="wait">
        {status !== null && (
          <motion.div
            key="status"
            initial={{ filter: "blur(20px)", opacity: 0 }}
            animate={{ filter: "blur(0px)", opacity: 1 }}
            exit={{ filter: "blur(20px)", opacity: 0 }}
            transition={{ duration: 0.4, ease: "easeInOut" }}
            className="grow flex justify-center items-center"
          >
            {status === "loading" && <Loading message="Loading..." />}
            {status === "error" && <ErrorPanel message={statusMsg || "Unknown error"} />}
            {status === "notFound" && <NotFound message="No VNs found" />}
          </motion.div>
        )}
        {status === null && (
          <motion.div
            key="grid"
            initial={{ filter: "blur(20px)", opacity: 0 }}
            animate={{ filter: "blur(0px)", opacity: 1 }}
            exit={{ filter: "blur(20px)", opacity: 0 }}
            transition={{ duration: 0.4, ease: "easeInOut" }}
          >
            <VNsCardsGrid vns={vns} layout={layout} cardType={cardType} sexualLevel={sexualLevel} violenceLevel={violenceLevel} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grow" />
      {vns.length > 0 && (
        <div className="flex justify-center mt-4">
          <PaginationButtons totalPages={totalPages} currentPage={currentPage} onPageChange={p => updateKey("page", p.toString())} />
        </div>
      )}
    </main>
  )
}

export default function Home() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><Loading message="Loading..." /></div>}>
      <HomeContent />
    </Suspense>
  )
}
