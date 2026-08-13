/** Dense, single-character info card used by the VN page's slider layout and the
 *  expanded characters view. Shows everything about a character *except* their
 *  related-VNs list. The thin embedded character drives the image/name/sex/role
 *  (instant); the full payload (traits, physical stats, aliases, description,
 *  voice actors) is lazily fetched and fills in. */
"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { cn, shouldBlur, formatBirthday } from "@/lib/utils"
import { enumLabel, CHARACTER_ROLE_CLASS } from "@/lib/enums"
import { ICON } from "@/lib/icons"
import { displayName } from "@/lib/original"
import { groupTraits } from "@/lib/traits"
import { characterSpoiler } from "@/lib/characters"
import { useSearchContext } from "@/context/SearchContext"
import { useTerm } from "@/hooks/useTerm"
import { useCharacterFull } from "@/hooks/useCharacterFull"
import { InlineList } from "@/components/detail/InfoPrimitives"
import { ImageWithFallback } from "@/components/common/ImageWithFallback"
import { BBCodeText } from "@/components/common/BBCodeText"
import { Lightbox } from "@/components/common/Lightbox"
import type { VN } from "@/lib/types"

type VNCharacter = VN["characters"][number]


/* ─── Constants & helpers ──────────────────────────────────────────────────── */

interface VNCharacterCardProps {
  /** The VN being viewed — selects this character's spoiler entry. */
  vnId: string
  base: VNCharacter
  role: string
  sexualLevel: string
  violenceLevel: string
  spoilerLevel: 0 | 1 | 2
  /** Clamp the card to a fixed height with a truncation fade (slider mode). */
  clamp?: boolean
  /** Invoked from the truncation fade — jump to this card in the expanded view. */
  onExpand?: () => void
  /** Reports whether this character has minor/major spoiler traits, once its full
   *  payload loads — lets a parent offer a global reveal toggle. */
  onSpoilerTraits?: (id: string, minor: boolean, major: boolean) => void
}

/** A row of "label value" stats joined by dim middots; null entries are skipped,
 *  and the row renders nothing if everything is absent. */
function StatRow({ items }: { items: Array<[string, React.ReactNode] | null> }) {
  const present = items.filter((x): x is [string, React.ReactNode] => x !== null)
  if (present.length === 0) return null
  return (
    <div className="flex flex-wrap items-baseline gap-y-0.5 text-xs">
      {present.map(([label, value], i) => (
        <span key={i} className="inline-flex items-baseline">
          {i > 0 && <span className="text-white/20 mx-2">·</span>}
          <span className="text-muted mr-1">{label}</span>
          <span className="text-white/90">{value}</span>
        </span>
      ))}
    </div>
  )
}

/* ─── Character card ───────────────────────────────────────────────────────── */

export function VNCharacterCard({ vnId, base, role, sexualLevel, violenceLevel, spoilerLevel, clamp, onExpand, onSpoilerTraits }: VNCharacterCardProps) {
  const { showOriginal } = useSearchContext()
  const { character: full, loading } = useCharacterFull(base.id)
  const [coverOpen, setCoverOpen] = useState(false)
  const [revealTraits, setRevealTraits] = useState<0 | 1 | 2>(0)

  const blur = base.image
    ? shouldBlur(base.image.sexual, base.image.violence, sexualLevel, violenceLevel)
    : false

  const sexApparent = base.sex?.[0]
  const sexReal = base.sex?.[1]
  const hasSexSpoiler = !!(sexApparent && sexReal && sexReal !== sexApparent && sexReal !== "n")

  const birthday = formatBirthday(full?.birthday)
  const cup = full?.cup ? `${full.cup.toUpperCase()} cup` : null
  const bustValue =
    full?.bust != null ? `${full.bust} cm${cup ? ` (${cup})` : ""}` : (cup ?? null)

  // Trait spoilers reveal per-card — the full character (with traits) is already
  // fetched here, so this works even when the VN has no spoiler-role characters
  // and the panel shows no global toggle. The effective level never drops below
  // what that toggle has already revealed.
  const effectiveSpoiler = Math.max(spoilerLevel, revealTraits) as 0 | 1 | 2
  const traitGroups = full ? groupTraits(full.traits, effectiveSpoiler, sexualLevel) : null

  // Original-text mode: render trait names via transserve (Japanese), falling
  // back to the English name for anything the dictionary doesn't have.
  const translate = useTerm((full?.traits ?? []).map(t => t.name), showOriginal)

  // This character's own spoiler weight in *this* VN — tints the card edge so a
  // revealed spoiler character stands out from ordinary ones.
  const charSpoiler = characterSpoiler(base, vnId)

  // Once the full payload loads, tell the parent whether this character hides any
  // spoiler traits, so a panel can show a global reveal toggle.
  useEffect(() => {
    if (!full || !onSpoilerTraits) return
    const { hiddenMinor, hiddenMajor } = groupTraits(full.traits, 0, sexualLevel)
    onSpoilerTraits(base.id, hiddenMinor > 0, hiddenMajor > 0)
  }, [full, sexualLevel, base.id, onSpoilerTraits])

  return (
    <div className={cn(
      "relative rounded-lg bg-surface border p-3 gap-4",
      charSpoiler === 2 ? "border-orange-500/50"
      : charSpoiler === 1 ? "border-yellow-500/40"
      : "border-white/5",
      // Expanded cards stack the cover above the info on phones; the clamped
      // slider preview keeps the compact cover-left layout at every width.
      clamp ? "flex max-h-80 overflow-hidden" : "flex flex-col items-center sm:flex-row sm:items-stretch",
    )}>
      {/* Cover */}
      <div className="w-28 sm:w-32 shrink-0">
        <div
          className="relative w-full aspect-3/4 rounded-lg overflow-hidden bg-elevated cursor-pointer group"
          onClick={() => base.image && setCoverOpen(true)}
        >
          {base.image ? (
            <ImageWithFallback
              src={base.image.url}
              alt={base.name}
              fill
              className={cn("object-cover object-top transition-all duration-300", blur && "blur-xl scale-105")}
              sizes="128px"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-muted text-xs">No image</div>
          )}
          {/* Decorative hover dim only — must not capture pointer events, or it
              sits over the fallback's Reload button and forwards the click to
              the cover (opening the lightbox on a broken image) instead. */}
          <div className="pointer-events-none absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
        </div>
      </div>

      {coverOpen && base.image && (
        <Lightbox
          images={[{ url: base.image.url, blurred: blur }]}
          index={0}
          onClose={() => setCoverOpen(false)}
          onIndexChange={() => {}}
        />
      )}

      {/* Info — w-full so it spans when stacked under the centred cover on phones. */}
      <div className="flex-1 w-full min-w-0 flex flex-col gap-2">
        {/* Header: name + role */}
        <div className="flex items-start justify-between gap-2">
          <Link
            href={`/${base.id}`}
            className="text-sm font-semibold text-white hover:text-accent transition-colors leading-snug"
          >
            {displayName(base, showOriginal)}
          </Link>
          <span className={cn(
            "text-xs px-1.5 py-0.5 rounded font-medium shrink-0",
            CHARACTER_ROLE_CLASS[role] ?? "bg-white/10 text-white/60"
          )}>
            {enumLabel('CHARACTER_ROLE', role)}
          </span>
        </div>

        {/* Sex */}
        {sexApparent && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className={cn(
              (ICON.CHARACTER_SEX as Record<string, string>)[sexApparent],
              "charsex-" + sexApparent
            )} />
            <span className="text-white/90">
              {enumLabel('CHARACTER_SEX', sexApparent)}
              {hasSexSpoiler && spoilerLevel < 2 && <span className="text-yellow-500/70"> (?)</span>}
              {hasSexSpoiler && spoilerLevel >= 2 && sexReal && (
                <span className="text-yellow-400"> → {enumLabel('CHARACTER_SEX', sexReal)}</span>
              )}
            </span>
          </div>
        )}

        {/* Physical stats — related values share a row */}
        <StatRow items={[
          full?.age != null ? ["Age", full.age] : null,
          birthday ? ["Birthday", birthday] : null,
          full?.blood_type ? ["Blood", full.blood_type.toUpperCase()] : null,
        ]} />
        <StatRow items={[
          full?.height != null ? ["Height", `${full.height} cm`] : null,
          full?.weight != null ? ["Weight", `${full.weight} kg`] : null,
        ]} />
        <StatRow items={[
          bustValue != null ? ["Bust", bustValue] : null,
          full?.waist != null ? ["Waist", `${full.waist} cm`] : null,
          full?.hips != null ? ["Hips", `${full.hips} cm`] : null,
        ]} />

        {/* Aliases */}
        {full && full.aliases.length > 0 && (
          <div className="text-xs">
            <span className="text-muted mr-1">Aliases</span>
            <InlineList className="text-white/80" items={full.aliases} />
          </div>
        )}

        {/* Voice actors */}
        {full && full.seiyuu.length > 0 && (
          <div className="text-xs flex flex-wrap items-baseline gap-x-1">
            <span className="text-muted mr-1">CV</span>
            <InlineList
              className="text-white/90"
              items={full.seiyuu.map((s, idx) => (
                <Link key={`${s.id}-${idx}`} href={`/${s.id}`} className="hover:text-accent transition-colors">
                  {displayName(s, showOriginal)}
                  {s.note && <span className="text-muted/60"> ({s.note})</span>}
                </Link>
              ))}
            />
          </div>
        )}

        {/* Traits */}
        {traitGroups && (traitGroups.groups.length > 0 || traitGroups.hiddenMinor > 0 || traitGroups.hiddenMajor > 0) && (
          <div className="flex flex-col gap-1.5 mt-0.5">
            {traitGroups.groups.map(([grp, grpTraits]) => (
              <div key={grp}>
                <p className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">{grp}</p>
                <div className="flex flex-wrap gap-1">
                  {grpTraits.map(t => (
                    <Link
                      key={t.id}
                      href={`/${t.id}`}
                      className={cn(
                        "inline-flex items-center px-2 py-0.5 rounded-full text-xs transition-colors",
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
            ))}

            {/* Per-card spoiler-trait reveal (yellow = minor, orange = major). */}
            {(traitGroups.hiddenMinor > 0 || traitGroups.hiddenMajor > 0) && (
              <div className="flex flex-wrap gap-1.5">
                {traitGroups.hiddenMinor > 0 && (
                  <button
                    type="button"
                    onClick={() => setRevealTraits(s => (s < 1 ? 1 : s))}
                    className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 transition-colors border border-yellow-500/20"
                  >
                    +{traitGroups.hiddenMinor} minor spoiler trait{traitGroups.hiddenMinor !== 1 ? "s" : ""}
                  </button>
                )}
                {traitGroups.hiddenMajor > 0 && (
                  <button
                    type="button"
                    onClick={() => setRevealTraits(2)}
                    className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors border border-orange-500/20"
                  >
                    +{traitGroups.hiddenMajor} major spoiler trait{traitGroups.hiddenMajor !== 1 ? "s" : ""}
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Description */}
        {full?.description && (
          <div className="mt-0.5">
            <BBCodeText text={full.description} />
          </div>
        )}

        {/* Loading skeleton for the lazily-fetched detail */}
        {loading && !full && (
          <div className="flex flex-col gap-2 mt-0.5 animate-pulse">
            <div className="h-3 w-3/4 rounded bg-white/10" />
            <div className="h-3 w-1/2 rounded bg-white/10" />
            <div className="h-3 w-2/3 rounded bg-white/10" />
          </div>
        )}
      </div>

      {/* Truncation fade → jump to this card in the expanded view. A tall
          gradient deepening to near-black signals there's more below the cut. */}
      {clamp && onExpand && (
        <button
          type="button"
          onClick={onExpand}
          className="group/fade absolute inset-x-0 bottom-0 flex items-end justify-center pb-2.5 pt-20 bg-linear-to-t from-black/95 via-black/70 to-transparent transition-colors"
        >
          <span className="text-xs font-medium text-white/70 group-hover/fade:text-accent transition-colors">
            Show full details ›
          </span>
        </button>
      )}
    </div>
  )
}
