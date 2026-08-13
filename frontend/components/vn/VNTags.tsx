/** Tag chips on the VN page, grouped by content / sexual / technical with spoiler reveal. */
"use client"

import Link from "next/link"
import { cn } from "@/lib/utils"
import { enumLabel } from "@/lib/enums"
import { useSpoilerLevel } from "@/hooks/useSpoilerLevel"
import { useTerm } from "@/hooks/useTerm"
import { useSearchContext } from "@/context/SearchContext"
import type { VN } from "@/lib/types"

type VNTag = VN["tags"][number]

const CATEGORY_ORDER = ["cont", "ero", "tech"] as const

interface VNTagsProps {
  tags: VNTag[]
  sexualLevel: string
}

export function VNTags({ tags, sexualLevel }: VNTagsProps) {
  const spoiler = useSpoilerLevel(
    tags.some(t => t.spoiler === 1),
    tags.some(t => t.spoiler === 2),
  )

  // Original-text mode: render tag names via transserve (Japanese), falling
  // back to the English name for anything the dictionary doesn't have.
  const { showOriginal } = useSearchContext()
  const translate = useTerm(tags.map(t => t.name), showOriginal)

  // Group by category, sort by rating desc within each group
  const grouped = CATEGORY_ORDER.reduce<Record<string, VNTag[]>>((acc, cat) => {
    acc[cat] = tags
      .filter(t => t.category === cat)
      .sort((a, b) => b.rating - a.rating)
    return acc
  }, {})

  /* ── Render ────────────────────────────────────────────────────────────── */

  return (
    <div className="flex flex-col gap-4">
      {spoiler.hasAnySpoilers && (
        <button
          onClick={spoiler.cycle}
          className={cn("text-xs transition-colors self-start", spoiler.buttonColor)}
        >
          {spoiler.buttonLabel}
        </button>
      )}

      {CATEGORY_ORDER.map(cat => {
        const catTags = grouped[cat] ?? []
        if (catTags.length === 0) return null

        // Hide ero group unless sexualLevel is explicit
        if (cat === "ero" && sexualLevel !== "explicit") {
          return (
            <div key={cat}>
              <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">
                {enumLabel('CATEGORY', cat)}
              </p>
              <p className="text-xs text-muted italic">
                Set Sexual filter to Explicit to view sexual content tags.
              </p>
            </div>
          )
        }

        // Filter by current spoiler level
        const visibleTags = catTags.filter(t => t.spoiler <= spoiler.spoilerLevel)
        const hiddenMinor = catTags.filter(t => t.spoiler === 1 && spoiler.spoilerLevel < 1).length
        const hiddenMajor = catTags.filter(t => t.spoiler === 2 && spoiler.spoilerLevel < 2).length

        return (
          <div key={cat}>
            <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">
              {enumLabel('CATEGORY', cat)}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {visibleTags.map(tag => (
                <Link
                  key={tag.id}
                  href={`/${tag.id}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors",
                    tag.lie
                      ? "bg-white/5 text-muted line-through hover:bg-white/10"
                      : "bg-white/10 text-white/90 hover:bg-white/20",
                    tag.spoiler === 1 && "border border-yellow-500/30",
                    tag.spoiler === 2 && "border border-orange-500/40"
                  )}
                >
                  <span>{translate(tag.name)}</span>
                  <span className={cn(
                    "font-mono",
                    tag.rating >= 2.5 ? "text-accent" : "text-muted"
                  )}>
                    {tag.rating.toFixed(1)}
                  </span>
                </Link>
              ))}

              {/* Minor spoiler hint */}
              {hiddenMinor > 0 && (
                <button
                  onClick={() => spoiler.setSpoilerLevel(1)}
                  className="inline-flex items-center px-2.5 py-1 rounded-full text-xs bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 transition-colors border border-yellow-500/20"
                >
                  +{hiddenMinor} minor spoiler{hiddenMinor !== 1 ? "s" : ""}
                </button>
              )}

              {/* Major spoiler hint */}
              {hiddenMajor > 0 && (
                <button
                  onClick={() => spoiler.setSpoilerLevel(2)}
                  className="inline-flex items-center px-2.5 py-1 rounded-full text-xs bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors border border-orange-500/20"
                >
                  +{hiddenMajor} major spoiler{hiddenMajor !== 1 ? "s" : ""}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
