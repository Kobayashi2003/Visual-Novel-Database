"use client"

import { useEffect, useState, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { useUrlParams } from "@/hooks/useUrlParams"
import { motion, AnimatePresence } from "motion/react"

import { cn } from "@/lib/utils"
import { YearSelector } from "@/components/selector/YearSelector"
import { MonthSelector } from "@/components/selector/MonthSelector"
import { SexualLevelSelector } from "@/components/selector/SexualLevelSelector"
import { ViolenceLevelSelector } from "@/components/selector/ViolenceLevelSelector"
import { CardTypeSwitch } from "@/components/selector/CardTypeSwtich"
import { GridLayoutSwitch } from "@/components/selector/GridLayoutSwitch"
import { PaginationButtons } from "@/components/button/PaginationButtons"
import { IconButton } from "@/components/button/IconButton"
import { ArrowBigLeftIcon, ArrowBigRightIcon } from "lucide-react"

import { Loading } from "@/components/status/Loading"
import { Error } from "@/components/status/Error"
import { NotFound } from "@/components/status/NotFound"

import { VNsCardsGrid } from "@/components/card/CardsGrid"

import { VN_Small } from "@/lib/types"
import { api } from "@/lib/api"

function HomeContent() {
  const searchParams = useSearchParams()
  const { updateKey, updateMultipleKeys } = useUrlParams()

  const itemsPerPage = 24

  const currentPage = searchParams.get("page") ? parseInt(searchParams.get("page") as string) : 1
  const selectedYear = searchParams.get("year") || `${new Date().getFullYear().toString()}`
  const selectedMonth = searchParams.get("month") || `${(new Date().getMonth() + 1).toString().padStart(2, '0')}`

  const [vnsState, setVnsState] = useState({
    state: null as "loading" | "error" | "notFound" | null,
    message: null as string | null
  })

  const [totalPages, setTotalPages] = useState(0)
  const [vns, setVNs] = useState<VN_Small[]>([])

  const [cardType, setCardType] = useState<"image" | "text">("image")
  const [layout, setLayout] = useState<"single" | "grid">("grid")
  const [sexualLevel, setSexualLevel] = useState<"safe" | "suggestive" | "explicit">("safe")
  const [violenceLevel, setViolenceLevel] = useState<"tame" | "violent" | "brutal">("tame")

  const [abortController, setAbortController] = useState<AbortController | null>(null)

  const fetchVNs = async () => {
    try {
      abortController?.abort()
      const newController = new AbortController()
      setAbortController(newController)

      setVNs([])
      setTotalPages(0)
      setVnsState({
        state: "loading",
        message: null
      })

      let released = ""
      if (selectedYear === "00") {
        released = ""
      } else if (selectedYear !== "00" && selectedMonth === "00") {
        const startYearStr = `${selectedYear}-01-01`
        const endYearStr = `${selectedYear}-12-31`

        released = `(>=${startYearStr}+<=${endYearStr}),(=${selectedYear})`
      } else if (selectedYear !== "00" && selectedMonth !== "00") {
        const startDateStr = `${selectedYear}-${selectedMonth}-01`

        const lastDay = new Date(Number.parseInt(selectedYear), Number.parseInt(selectedMonth), 0).getDate()
        const endDateStr = `${selectedYear}-${selectedMonth}-${lastDay}`

        released = `(>=${startDateStr}+<=${endDateStr}),(=${selectedYear}-${selectedMonth})`
      }

      const response = await api.small.vn({
        released: released,
        olang: "ja",
        sort: "released",
        reverse: true,
        page: currentPage,
        limit: itemsPerPage,
      }, newController.signal)

      setVNs(response.results)
      setTotalPages(Math.ceil(response.count / itemsPerPage) || 1)
      if (response.results.length === 0) {
        setVnsState({
          state: "notFound",
          message: null
        })
      } else {
        setVnsState({
          state: null,
          message: null
        })
      }
    } catch (error) {
      setVnsState({
        state: "error",
        message: "Failed to fetch VNs. Please try again."
      })
    }
  }

  const handleYearChange = (value: string) => {
    updateMultipleKeys({ year: value, page: "1" })
  }

  const handleMonthChange = (value: string) => {
    updateMultipleKeys({ month: value, page: "1" })
  }

  const handleMonthAdd = () => {
    const currentSelectedMonth = Number.parseInt(selectedMonth)
    const newMonth = currentSelectedMonth + 1
    if (newMonth > 12) {
      updateMultipleKeys({ month: "01", year: (Number.parseInt(selectedYear) + 1).toString(), page: "1" })
    } else {
      updateMultipleKeys({ month: newMonth.toString().padStart(2, "0"), year: selectedYear, page: "1" })
    }
  }

  const handleMonthSub = () => {
    const currentSelectedMonth = Number.parseInt(selectedMonth)
    const newMonth = currentSelectedMonth - 1
    if (newMonth < 1) {
      updateMultipleKeys({ month: "12", year: (Number.parseInt(selectedYear) - 1).toString(), page: "1" })
    } else {
      updateMultipleKeys({ month: newMonth.toString().padStart(2, "0"), year: selectedYear, page: "1" })
    }
  }

  const monthAddable = () => {
    const currentYear = new Date().getFullYear()
    const currentSelectedYear = Number.parseInt(selectedYear)
    const currentSelectedMonth = Number.parseInt(selectedMonth)
    if (currentSelectedYear === currentYear + 1) {
      return currentSelectedMonth !== 12
    }
    return true
  }

  const monthSubable = () => {
    const currentSelectedYear = Number.parseInt(selectedYear)
    const currentSelectedMonth = Number.parseInt(selectedMonth)
    if (currentSelectedYear === 1985) {
      return currentSelectedMonth !== 1
    }
    return true
  }

  const handlePageChange = (page: number) => {
    updateKey("page", page.toString())
  }

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" })
    fetchVNs()
  }, [currentPage, selectedYear, selectedMonth])

  useEffect(() => {
    return () => {
      abortController?.abort()
    }
  }, [abortController])

  return (
    <main className="container mx-auto min-h-screen flex flex-col p-4 pb-8">
      <div className={cn(
        "flex mb-4",
        "flex-col items-center gap-2",
        "sm:flex-row sm:justify-between sm:gap-4"
      )}>
        <div className="w-full sm:flex-1 flex justify-start gap-2">
          {/* Card Type Selector */}
          <CardTypeSwitch
            cardType={cardType}
            setCardType={setCardType}
          />
          {/* Grid Layout Switch */}
          <GridLayoutSwitch
            layout={layout}
            setLayout={setLayout}
          />
        </div>
        <div className="w-full sm:flex-1 flex justify-center gap-2">
          {/* Month Sub Button */}
          <IconButton
            icon={<ArrowBigLeftIcon className="w-4 h-4 fill-amber-100" />}
            onClick={handleMonthSub}
            disabled={vnsState.state === "loading" || selectedYear === "00" || selectedMonth === "00" || !monthSubable()}
            tooltip="Previous Month"
            tooltipPosition="top"
            className="hover:bg-white/5 max-sm:hidden"
          />
          {/* Year Selector */}
          <YearSelector
            selectedYear={selectedYear}
            setSelectedYear={handleYearChange}
            disabled={vnsState.state === "loading"}
            className="w-full sm:w-auto"
          />
          {/* Month Selector */}
          <MonthSelector
            selectedMonth={selectedYear === "00" ? "00" : selectedMonth}
            setSelectedMonth={handleMonthChange}
            disabled={vnsState.state === "loading" || selectedYear === "00"}
            className="w-full sm:w-auto"
          />
          {/* Month Add Button */}
          <IconButton
            icon={<ArrowBigRightIcon className="w-4 h-4 fill-amber-100" />}
            onClick={handleMonthAdd}
            disabled={vnsState.state === "loading" || selectedYear === "00" || selectedMonth === "00" || !monthAddable()}
            tooltip="Next Month"
            tooltipPosition="top"
            className="hover:bg-white/5 max-sm:hidden"
          />
        </div>
        <div className="w-full sm:flex-1 flex justify-end gap-2">
          {/* Sexual Level Selector */}
          <SexualLevelSelector
            sexualLevel={sexualLevel}
            setSexualLevel={(value: string) => setSexualLevel(value as "safe" | "suggestive" | "explicit")}
            className="w-full sm:w-auto"
          />
          {/* Divider */}
          <div className="w-px bg-gray-300 dark:bg-gray-700 hidden lg:block" />
          {/* Violence Level Selector */}
          <ViolenceLevelSelector
            violenceLevel={violenceLevel}
            setViolenceLevel={(value: string) => setViolenceLevel(value as "tame" | "violent" | "brutal")}
            className="w-full sm:w-auto"
          />
        </div>
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key="status"
          initial={{ filter: "blur(20px)", opacity: 0 }}
          animate={{ filter: "blur(0px)", opacity: 1 }}
          exit={{ filter: "blur(20px)", opacity: 0 }}
          transition={{ duration: 0.4, ease: "easeInOut" }}
          className={cn(
            "flex-grow flex justify-center items-center",
            vnsState.state === null && "hidden"
          )}
        >
          {vnsState.state === "loading" && <Loading message="Loading..." />}
          {vnsState.state === "error" && <Error message={`${vnsState.message || "Unknown error"}`} />}
          {vnsState.state === "notFound" && <NotFound message="No VNs found" />}
        </motion.div>
        
        <motion.div
          key="vns-grid-container"
          initial={{ filter: "blur(20px)", opacity: 0 }}
          animate={{ filter: "blur(0px)", opacity: 1 }}
          exit={{ filter: "blur(20px)", opacity: 0 }}
          transition={{ duration: 0.4, ease: "easeInOut" }}
          className={cn(
            vnsState.state !== null && "hidden"
          )}
        >
          <VNsCardsGrid
            vns={vns}
            layout={layout}
            cardType={cardType}
            sexualLevel={sexualLevel}
            violenceLevel={violenceLevel}
          />
        </motion.div>
      </AnimatePresence>
      {/* Keep the footer at the bottom of the page */}
      <div className="flex-grow"></div>
      {/* Pagination */}
      {vns.length > 0 && (
        <div className="flex justify-center mt-4">
          <PaginationButtons
            totalPages={totalPages}
            currentPage={currentPage}
            onPageChange={handlePageChange}
          />
        </div>
      )}
    </main>
  )
}

export default function Home() {
  return (
    <Suspense fallback={<Loading message="Loading..." />}>
      <HomeContent />
    </Suspense>
  )
}