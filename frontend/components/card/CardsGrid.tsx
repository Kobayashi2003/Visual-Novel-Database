/** Per-entity card grids for search results and the user-collections page.
 *
 *  A single generic core (`CardsGridBase`) renders the grid / list / compact
 *  views; each entity type only supplies an `adapter` that maps its payload
 *  onto the shared `CardItem` shape. */
"use client"

import { useRouter } from "next/navigation"
import { cn, formatRelativeDate, shouldBlur } from "@/lib/utils"
import { X, FolderInput, Check, Star } from "lucide-react"
import { ImageCard } from "./ImageCard"
import { TextCard } from "./TextCard"
import { CompactRow } from "./CompactRow"
import { StarRating } from "@/components/common/StarRating"
import { enumLabel } from "@/lib/enums"
import { useSearchContext } from "@/context/SearchContext"
import { displayTitle, displayName } from "@/lib/original"
import type {
  SexualLevel, ViolenceLevel,
  VN_Small, Release_Small, Character_Small, Producer_Small,
  Staff_Small, Tag_Small, Trait_Small,
} from "@/lib/types"


/* ─── In-card secondary link ───────────────────────────────────────────────── */

/** A name inside a card that navigates somewhere *other* than the card's own
 *  target — e.g. a VN card's developer. The card is itself a `<Link>`, so this
 *  swallows the card-navigation click (preventDefault/stopPropagation, mirroring
 *  the in-card action buttons) and routes to its own href instead. */
function CardCreditLink({ href, children }: { href: string; children: React.ReactNode }) {
  const router = useRouter()
  return (
    <button
      type="button"
      onClick={e => { e.preventDefault(); e.stopPropagation(); router.push(href) }}
      className="text-muted hover:text-accent transition-colors"
    >
      {children}
    </button>
  )
}


/* ─── Generic image card (handles content-rating blur) ─────────────────────── */

type ImageProps = {
  url: string
  dims: [number, number]
  thumbnail?: string
  thumbnail_dims?: [number, number]
  sexual: number
  violence: number
}

interface GenImageCardProps {
  title: string
  msgs: React.ReactNode[]
  image?: ImageProps
  link?: string
  sexualLevel?: SexualLevel
  violenceLevel?: ViolenceLevel
  layout?: "single" | "grid"
  tooltip?: string
  className?: string
  imageOverlay?: React.ReactNode
}

const BLUR = "blur-lg hover:blur-none"

function getBlurClass(
  image: ImageProps | undefined,
  sexualLevel: string,
  violenceLevel: string
): string {
  if (!image) return ""
  return shouldBlur(image.sexual, image.violence, sexualLevel, violenceLevel) ? BLUR : ""
}

export function GenImageCard({
  title, msgs, image, link,
  sexualLevel = "safe", violenceLevel = "tame",
  layout = "grid", tooltip, className, imageOverlay
}: GenImageCardProps) {
  const blurClass = getBlurClass(image, sexualLevel, violenceLevel)

  return (
    <ImageCard
      url={image?.thumbnail || image?.url || ""}
      title={title}
      msgs={msgs}
      link={link}
      className={cn(className, blurClass, "transition-all duration-300")}
      tooltip={tooltip}
      layout={layout === "grid" ? "grid" : "list"}
      imageOverlay={imageOverlay}
    />
  )
}

/* Quick-rate overlay drawn over a card thumbnail: a compact badge while the
   card is idle (so ratings are visible at a glance), swapped for an interactive
   star bar on hover. Lives inside the thumbnail's relative/overflow-hidden box. */
function CardRatingOverlay({ value, onRate, size }: {
  value: number
  onRate: (value: number) => void
  size: number
}) {
  return (
    <>
      {value > 0 && (
        <div className="absolute top-1 left-1 z-10 flex items-center gap-0.5 rounded-full bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-yellow-400 group-hover:opacity-0 transition-opacity pointer-events-none">
          <Star className="w-2.5 h-2.5 fill-yellow-400 text-yellow-400" />
          {value}
        </div>
      )}
      {/* Interactive star bar is hover-revealed, so it's useless on touch and a
          mis-tap hazard near the card link — hide it below `lg`. The read-only
          rating badge above stays so mobile users still see their score. */}
      <div className="absolute inset-x-0 bottom-1 z-10 hidden lg:flex justify-center opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="rounded-full bg-black/80 px-1 py-0.5 backdrop-blur-sm">
          <StarRating value={value} onChange={onRate} size={size} />
        </div>
      </div>
    </>
  )
}

const gridClass = (layout: "single" | "grid") =>
  layout === "grid"
    ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 sm:gap-3"
    : "flex flex-col gap-2"


/* ─── Shared collection props + hover-action wrapper ──────────────────────── */

export interface CollectionCardProps {
  // "shelf" is accepted only so the parent's `ViewMode` flows through cleanly;
  // CardsGridBase treats it as "grid" since shelf rendering happens elsewhere.
  view?: "grid" | "list" | "compact" | "shelf"
  editMode?: boolean
  selectedIds?: Set<string>
  markedAtMap?: Record<string, string>
  /** Personal ratings keyed by card id (e.g. "v17" → 4). */
  ratingsMap?: Record<string, number>
  onRemove?: (id: string) => void
  onMove?: (id: string) => void
  onToggleSelect?: (id: string) => void
  onRate?: (id: string, value: number) => void
}

// Adds hover-actions (remove/move), edit-mode checkbox, and a date-added badge
// on top of any card. Used to make the same card components reusable across
// search results (plain) and the user-collections page (with collection chrome).
export function CollectionWrapper({
  id, children,
  onRemove, onMove, editMode, selectedIds, onToggleSelect, markedAtMap
}: CollectionCardProps & { id: string; children: React.ReactNode }) {
  const selected = selectedIds?.has(id)
  const markedAt = markedAtMap?.[id]
  const isActive = !!(onRemove || onMove || editMode)
  if (!isActive) return <>{children}</>

  return (
    <div className={cn("relative group", selected && "ring-2 ring-accent rounded-lg overflow-hidden")}>
      {children}

      {editMode && (
        <>
          {/* Click-capture overlay: clicking the card toggles selection instead of navigating */}
          <button
            type="button"
            onClick={() => onToggleSelect?.(id)}
            aria-label={selected ? "Deselect" : "Select"}
            className="absolute inset-0 z-10 cursor-pointer rounded-lg"
          />
          {/* Custom checkbox indicator */}
          <div className="absolute top-1.5 left-1.5 z-20 pointer-events-none">
            <div className={cn(
              "w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors",
              selected
                ? "bg-accent border-accent shadow-md"
                : "bg-black/50 border-white/70 backdrop-blur-sm"
            )}>
              {selected && <Check className="w-3 h-3 text-black" strokeWidth={3} />}
            </div>
          </div>
        </>
      )}

      {!editMode && (onRemove || onMove) && (
        <div className="absolute top-1 right-1 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          {onMove && (
            <button
              onClick={e => { e.preventDefault(); onMove(id) }}
              className="p-1 rounded-full bg-black/70 text-white hover:bg-black/90 transition-colors"
              title="Move to..."
            >
              <FolderInput className="w-3 h-3" />
            </button>
          )}
          {onRemove && (
            <button
              onClick={e => { e.preventDefault(); onRemove(id) }}
              className="p-1 rounded-full bg-black/70 text-white hover:bg-red-500/80 transition-colors"
              title="Remove"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      )}

      {markedAt && !editMode && (
        <div className="absolute inset-x-0 bottom-0 px-2 py-1.5 text-xs text-white/80 bg-linear-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded-b">
          Added {formatRelativeDate(markedAt)}
        </div>
      )}
    </div>
  )
}


/* ─── Generic grid core ────────────────────────────────────────────────────── */

/** The shared shape every entity card is rendered from. */
export interface CardItem {
  id: string
  link: string
  title: string
  /** Supplementary line for the compact row (year, role, category, …). */
  subtitle?: React.ReactNode
  /** Secondary lines for text / image cards. May contain in-card links. */
  msgs: React.ReactNode[]
  /** Image source for image-card entities (VN / Character); omitted otherwise. */
  image?: ImageProps
  /** Compact-row thumbnail URL. `undefined` → no thumbnail column. */
  thumbnail?: string
}

/** Maps one entity payload onto a `CardItem`. */
export type CardAdapter<T> = (item: T, showOriginal: boolean) => CardItem

interface CardsGridBaseProps<T> extends CollectionCardProps {
  items: T[]
  adapter: CardAdapter<T>
  /** Whether this entity can render image cards (VN / Character). */
  supportsImage?: boolean
  cardType?: "image" | "text"
  layout?: "single" | "grid"
  sexualLevel?: SexualLevel
  violenceLevel?: ViolenceLevel
}

function CardsGridBase<T>({
  items, adapter, supportsImage,
  cardType = "image", layout = "grid",
  sexualLevel = "safe", violenceLevel = "tame",
  view, onRemove, onMove, editMode, selectedIds, onToggleSelect, markedAtMap,
  ratingsMap, onRate,
}: CardsGridBaseProps<T>) {
  const { showOriginal } = useSearchContext()
  const effectiveLayout: "single" | "grid" =
    view === "list" ? "single" : view === "grid" ? "grid" : layout
  const cards = items.map((item, idx) => ({ idx, ...adapter(item, showOriginal) }))

  // Quick-rate is hidden in edit mode (the card is a selection target there).
  const canRate = !!onRate && !editMode

  if (view === "compact") {
    return (
      <div className="flex flex-col">
        {cards.map(card => (
          <CompactRow
            key={`${card.id}-${card.idx}`}
            index={card.idx + 1}
            title={card.title}
            subtitle={card.subtitle}
            thumbnail={card.thumbnail}
            markedAt={markedAtMap?.[card.id]}
            rating={ratingsMap?.[card.id] ?? 0}
            onRate={canRate ? value => onRate!(card.id, value) : undefined}
            onRemove={onRemove ? () => onRemove(card.id) : undefined}
            onMove={onMove ? () => onMove(card.id) : undefined}
            selected={selectedIds?.has(card.id)}
            editMode={editMode}
            onToggleSelect={onToggleSelect ? () => onToggleSelect(card.id) : undefined}
            link={card.link}
          />
        ))}
      </div>
    )
  }

  const useImageCard = supportsImage && cardType === "image"
  const ratingSize = effectiveLayout === "grid" ? 16 : 13

  return (
    <div className={gridClass(effectiveLayout)}>
      {cards.map(card => (
        <CollectionWrapper
          key={`${card.id}-${card.idx}`} id={card.id}
          onRemove={onRemove} onMove={onMove}
          editMode={editMode} selectedIds={selectedIds}
          onToggleSelect={onToggleSelect} markedAtMap={markedAtMap}
        >
          {useImageCard ? (
            <GenImageCard
              image={card.image} title={card.title} msgs={card.msgs} link={card.link}
              sexualLevel={sexualLevel} violenceLevel={violenceLevel}
              layout={effectiveLayout}
              imageOverlay={canRate ? (
                <CardRatingOverlay
                  value={ratingsMap?.[card.id] ?? 0}
                  onRate={value => onRate!(card.id, value)}
                  size={ratingSize}
                />
              ) : undefined}
            />
          ) : (
            <TextCard
              title={card.title} msgs={card.msgs} link={card.link} layout={effectiveLayout}
              footer={canRate ? (
                <StarRating
                  value={ratingsMap?.[card.id] ?? 0}
                  onChange={value => onRate!(card.id, value)}
                  size={14}
                  className={cn(
                    // Hidden on touch (mirrors the compact row + image overlay) to
                    // avoid mis-taps; `hidden`/`sm:flex` override StarRating's `flex`.
                    "transition-opacity hidden sm:flex",
                    (ratingsMap?.[card.id] ?? 0) > 0 ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                  )}
                />
              ) : undefined}
            />
          )}
        </CollectionWrapper>
      ))}
    </div>
  )
}


/* ─── Per-entity adapters ──────────────────────────────────────────────────── */

const vnAdapter: CardAdapter<VN_Small> = (vn, showOriginal) => {
  const dev = vn.developers?.[0]
  const developer = dev
    ? <CardCreditLink href={`/${dev.id}`}>{displayName(dev, showOriginal)}</CardCreditLink>
    : null
  const year = vn.released ? vn.released.substring(0, 4) : ""
  const subtitle = developer
    ? <>{developer}{year && <><span className="text-white/30"> · </span>{year}</>}</>
    : (year || undefined)
  return {
    id: vn.id,
    link: `/${vn.id}`,
    title: displayTitle(vn, showOriginal),
    subtitle,
    msgs: [developer, vn.released || ""].filter(Boolean),
    image: vn.image,
    thumbnail: vn.image?.thumbnail || vn.image?.url,
  }
}

const releaseAdapter: CardAdapter<Release_Small> = (r, showOriginal) => {
  const langs = r.languages?.map(l => l.lang).join(", ") || ""
  return {
    id: r.id,
    link: `/${r.id}`,
    title: displayTitle(r, showOriginal),
    subtitle: [r.released, langs].filter(Boolean).join(" · "),
    msgs: [r.released, langs].filter(Boolean),
  }
}

const characterAdapter: CardAdapter<Character_Small> = (c, showOriginal) => {
  const role = c.vns?.[0]?.role ? enumLabel('CHARACTER_ROLE', c.vns[0].role) : ""
  return {
    id: c.id,
    link: `/${c.id}`,
    title: displayName(c, showOriginal),
    subtitle: role,
    msgs: [role].filter(Boolean),
    image: c.image,
    thumbnail: c.image?.url,
  }
}

const producerAdapter: CardAdapter<Producer_Small> = (p, showOriginal) => ({
  id: p.id,
  link: `/${p.id}`,
  title: displayName(p, showOriginal),
  msgs: [],
})

const staffAdapter: CardAdapter<Staff_Small> = (s, showOriginal) => ({
  id: s.id,
  link: `/${s.id}`,
  title: displayName(s, showOriginal),
  msgs: [],
})

const tagAdapter: CardAdapter<Tag_Small> = t => ({
  id: t.id,
  link: `/${t.id}`,
  title: t.name,
  subtitle: t.category,
  msgs: [t.category],
})

const traitAdapter: CardAdapter<Trait_Small> = t => ({
  id: t.id,
  link: `/${t.id}`,
  title: t.name,
  subtitle: t.group_name,
  msgs: [t.group_name || ""].filter(Boolean),
})


/* ─── Per-entity grids (thin wrappers over the generic core) ───────────────── */

interface VNsCardsGridProps extends CollectionCardProps {
  vns: VN_Small[]
  cardType?: "image" | "text"
  layout?: "single" | "grid"
  sexualLevel?: SexualLevel
  violenceLevel?: ViolenceLevel
}

export function VNsCardsGrid({ vns, ...props }: VNsCardsGridProps) {
  return <CardsGridBase items={vns} adapter={vnAdapter} supportsImage {...props} />
}

interface ReleasesCardsGridProps extends CollectionCardProps {
  releases: Release_Small[]
  layout?: "single" | "grid"
}

export function ReleasesCardsGrid({ releases, ...props }: ReleasesCardsGridProps) {
  return <CardsGridBase items={releases} adapter={releaseAdapter} {...props} />
}

interface CharactersCardsGridProps extends CollectionCardProps {
  characters: Character_Small[]
  cardType?: "image" | "text"
  layout?: "single" | "grid"
  sexualLevel?: SexualLevel
  violenceLevel?: ViolenceLevel
}

export function CharactersCardsGrid({ characters, ...props }: CharactersCardsGridProps) {
  return <CardsGridBase items={characters} adapter={characterAdapter} supportsImage {...props} />
}

interface ProducersCardsGridProps extends CollectionCardProps {
  producers: Producer_Small[]
  layout?: "single" | "grid"
}

export function ProducersCardsGrid({ producers, ...props }: ProducersCardsGridProps) {
  return <CardsGridBase items={producers} adapter={producerAdapter} {...props} />
}

interface StaffCardsGridProps extends CollectionCardProps {
  staff: Staff_Small[]
  layout?: "single" | "grid"
}

export function StaffCardsGrid({ staff, ...props }: StaffCardsGridProps) {
  return <CardsGridBase items={staff} adapter={staffAdapter} {...props} />
}

interface TagsCardsGridProps extends CollectionCardProps {
  tags: Tag_Small[]
  layout?: "single" | "grid"
}

export function TagsCardsGrid({ tags, ...props }: TagsCardsGridProps) {
  return <CardsGridBase items={tags} adapter={tagAdapter} {...props} />
}

interface TraitsCardsGridProps extends CollectionCardProps {
  traits: Trait_Small[]
  layout?: "single" | "grid"
}

export function TraitsCardsGrid({ traits, ...props }: TraitsCardsGridProps) {
  return <CardsGridBase items={traits} adapter={traitAdapter} {...props} />
}


/* ─── Type-erased adapter dispatch (used by CardsShelfRow) ─────────────────── */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ADAPTERS: Record<string, CardAdapter<any>> = {
  vn:        vnAdapter,
  release:   releaseAdapter,
  character: characterAdapter,
  producer:  producerAdapter,
  staff:     staffAdapter,
  tag:       tagAdapter,
  trait:     traitAdapter,
}

export function adapterForType(type: string): CardAdapter<unknown> {
  return (ADAPTERS[type] ?? ADAPTERS.vn) as CardAdapter<unknown>
}

const IMAGE_TYPES = new Set(["vn", "character"])

/** Whether this entity type renders an image-backed card (vs text-only). */
export function supportsImageForType(type: string): boolean {
  return IMAGE_TYPES.has(type)
}
