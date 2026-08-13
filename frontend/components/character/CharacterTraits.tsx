/** Traits panel on the character page — groups + spoiler reveal buttons. */
"use client"

import Link from "next/link"
import { cn } from "@/lib/utils"
import { groupTraits, type CharTrait } from "@/lib/traits"
import { useTerm } from "@/hooks/useTerm"
import { useSearchContext } from "@/context/SearchContext"

interface CharacterTraitsProps {
  traits: CharTrait[]
  spoilerLevel: 0 | 1 | 2
  sexualLevel: string
  onRevealMinor: () => void
  onRevealMajor: () => void
}

export function CharacterTraits({ traits, spoilerLevel, sexualLevel, onRevealMinor, onRevealMajor }: CharacterTraitsProps) {
  const { groups, hiddenMinor, hiddenMajor } = groupTraits(traits, spoilerLevel, sexualLevel)

  // Original-text mode: render trait names via transserve (Japanese), falling
  // back to the English name for anything the dictionary doesn't have.
  const { showOriginal } = useSearchContext()
  const translate = useTerm(traits.map(t => t.name), showOriginal)

  const noTraits = groups.length === 0 && hiddenMinor === 0 && hiddenMajor === 0

  return (
    <div className="flex flex-col gap-3">
      {noTraits && <p className="text-xs text-muted italic">No traits listed.</p>}
      {groups.map(([grp, grpTraits]) => {
        return (
          <div key={grp}>
            <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">{grp}</p>
            <div className="flex flex-wrap gap-1.5">
              {grpTraits.map(t => (
                <Link
                  key={t.id}
                  href={`/${t.id}`}
                  className={cn(
                    "inline-flex items-center px-2.5 py-1 rounded-full text-xs transition-colors",
                    t.lie
                      ? "bg-white/5 text-muted line-through hover:bg-white/10"
                      : "bg-white/10 text-white/90 hover:bg-white/20",
                    t.spoiler === 1 && "border border-yellow-500/30",
                    t.spoiler === 2 && "border border-orange-500/40"
                  )}
                >
                  {translate(t.name)}
                </Link>
              ))}
            </div>
          </div>
        )
      })}

      {/* Spoiler reveal hints */}
      {(hiddenMinor > 0 || hiddenMajor > 0) && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {hiddenMinor > 0 && (
            <button
              onClick={onRevealMinor}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 transition-colors border border-yellow-500/20"
            >
              +{hiddenMinor} minor spoiler trait{hiddenMinor !== 1 ? "s" : ""}
            </button>
          )}
          {hiddenMajor > 0 && (
            <button
              onClick={onRevealMajor}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors border border-orange-500/20"
            >
              +{hiddenMajor} major spoiler trait{hiddenMajor !== 1 ? "s" : ""}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
