/** Image card — grid layout (square thumbnail) or list layout (thumbnail left, text right). */
"use client"

import { useEffect, useState, useCallback } from "react"
import Image from "next/image"
import Link from "next/link"
import { cn } from "@/lib/utils"
import { ImageOff, RotateCw } from "lucide-react"

interface ImageCardProps {
  title: string
  url: string
  msgs?: React.ReactNode[]
  link?: string
  tooltip?: string
  layout?: "grid" | "list"
  className?: string
  /** Absolutely-positioned content drawn over the thumbnail (e.g. quick-rate). */
  imageOverlay?: React.ReactNode
}

export function ImageCard({ title, url, msgs, link, tooltip, layout = "grid", className, imageOverlay }: ImageCardProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [imgUrl, setImgUrl] = useState(url)

  useEffect(() => {
    setLoading(true)
    setError(false)
    setImgUrl(url)
  }, [url])

  // A cached image can finish loading before React attaches onLoad; this ref
  // catches that case so the card doesn't sit on its skeleton forever. Stable
  // identity is fine — the `key={imgUrl}` remount below re-runs it per URL.
  const imgRef = useCallback((img: HTMLImageElement | null) => {
    if (img?.complete && img.naturalWidth > 0) {
      setLoading(false)
      setError(false)
    }
  }, [])

  const handleRetry = (e: React.MouseEvent) => {
    // The button sits inside a <Link>; preventDefault stops the anchor from
    // navigating to the card's detail page when only a retry was intended.
    e.preventDefault()
    e.stopPropagation()
    setLoading(true)
    setError(false)
    setImgUrl(`${url}${url.includes("?") ? "&" : "?"}${Date.now()}`)
  }

  /* ── Render ────────────────────────────────────────────────────────────── */

  const imageContent = (
    <>
      {imgUrl && (
        <Image
          key={imgUrl}
          ref={imgRef}
          src={imgUrl}
          alt={title || ""}
          fill
          loading="lazy"
          onLoad={() => { setLoading(false); setError(false) }}
          onError={() => { setLoading(false); setError(true) }}
          className={cn("object-cover transition-opacity duration-300", loading || error ? "opacity-0" : "opacity-100")}
        />
      )}
      {imgUrl && loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-elevated">
          <div className={cn("rounded-full bg-white/10 animate-pulse", layout === "grid" ? "w-8 h-8" : "w-6 h-6")} />
        </div>
      )}
      {/* No cover at all → a static placeholder, not the perpetual loader. */}
      {!imgUrl && (
        <div className="absolute inset-0 flex items-center justify-center bg-elevated">
          <ImageOff className={cn("text-muted/50", layout === "grid" ? "w-8 h-8" : "w-6 h-6")} />
        </div>
      )}
      {imgUrl && error && (
        <div className={cn("absolute inset-0 flex flex-col items-center justify-center bg-elevated", layout === "grid" ? "gap-2" : "gap-1")}>
          <ImageOff className={cn("text-muted", layout === "grid" ? "w-8 h-8" : "w-6 h-6")} />
          <button onClick={handleRetry} className="p-1 rounded-full hover:bg-white/10">
            <RotateCw className={cn("text-muted", layout === "grid" ? "w-4 h-4" : "w-3 h-3")} />
          </button>
        </div>
      )}
    </>
  )

  const card = layout === "grid" ? (
    <div className={cn(
      "bg-surface hover:bg-elevated",
      "rounded-lg p-2 border border-white/5",
      "hover:scale-105 transition-all duration-300",
      link ? "cursor-pointer" : "cursor-default",
      className
    )} title={tooltip}>
      <div className="relative w-full aspect-square rounded overflow-hidden">
        {imageContent}
        {imageOverlay}
      </div>
      <div className="mt-2 px-1">
        <p className="truncate font-semibold text-xs sm:text-sm text-white">{title}</p>
        {msgs?.map((msg, i) => (
          <p key={i} className="truncate text-xs text-muted">{msg}</p>
        ))}
      </div>
    </div>
  ) : (
    <div className={cn(
      "bg-surface hover:bg-elevated",
      "rounded-lg p-3 border border-white/5",
      "flex gap-3",
      "transition-all duration-300",
      link ? "cursor-pointer" : "cursor-default",
      className
    )} title={tooltip}>
      <div className="relative w-24 h-32 shrink-0 rounded overflow-hidden">
        {imageContent}
        {imageOverlay}
      </div>
      <div className="flex-1 min-w-0 py-1">
        <p className="font-semibold text-sm text-white line-clamp-2">{title}</p>
        {msgs?.map((msg, i) => (
          <p key={i} className="text-xs text-muted mt-1 truncate">{msg}</p>
        ))}
      </div>
    </div>
  )

  return link ? <Link href={link}>{card}</Link> : card
}
