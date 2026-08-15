/** Grid view: a wall of covers, one per visual novel, opening its soundtrack in
 *  a dialog. The card shows the visual novel's own cover — this is a shelf of
 *  works — while the dialog shows the soundtrack's cover beside the track list,
 *  which is a different picture and often absent.
 */
"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ExternalLink, Music, Play, X } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { displayTitle } from "@/lib/original"
import { useSearchContext } from "@/context/SearchContext"
import { usePlayer, trackKey } from "@/context/PlayerContext"
import { SoundtrackCover } from "@/components/player/SoundtrackCover"
import type { Soundtrack } from "@/lib/types"

import { TrackLine, type Album } from "../page"


export function SoundtrackCard({ album, blur, onOpen }: {
  album: Album
  blur: boolean
  onOpen: () => void
}) {
  const { showOriginal } = useSearchContext()
  const cover = album.vn?.image?.thumbnail ?? album.vn?.image?.url ?? null
  const title = album.vn ? displayTitle(album.vn, showOriginal) : album.vnid

  return (
    <div onClick={onOpen} role="button" tabIndex={0}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen() } }}
      className="group cursor-pointer text-left" data-cursor="pointer">
      <div className="relative aspect-[3/4] overflow-hidden rounded-lg bg-white/[0.03] ring-1 ring-white/10">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" draggable={false}
            className={cn("h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]",
              blur && "blur-md")} />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Music className="h-6 w-6 text-white/20" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
        {/* The card opens the track list; reaching the work is a separate,
            explicit control rather than a second meaning for the same click. */}
        <Link
          href={`/${album.vnid}`}
          onClick={e => e.stopPropagation()}
          aria-label={`Open ${title}`}
          className="absolute left-2 top-2 rounded-md bg-black/60 p-1.5 text-white/80 opacity-0 backdrop-blur-sm transition-opacity hover:text-white group-hover:opacity-100"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <span className="absolute bottom-2 right-2 flex h-8 w-8 translate-y-2 items-center justify-center rounded-full bg-accent text-black opacity-0 transition-all group-hover:translate-y-0 group-hover:opacity-100">
          <Play className="h-3.5 w-3.5 fill-current" />
        </span>
      </div>
      <p className="mt-1.5 truncate text-sm font-medium text-white">{title}</p>
      <p className="text-xs text-muted">
        {album.trackCount} {album.trackCount === 1 ? "track" : "tracks"}
      </p>
    </div>
  )
}


export function SoundtrackDialog({ album, blur, onClose, onPlay }: {
  album: Album
  blur: boolean
  onClose: () => void
  onPlay: (soundtrack: Soundtrack, startAt: number) => void
}) {
  const { track } = usePlayer()
  const { showOriginal } = useSearchContext()
  const [soundtrack, setSoundtrack] = useState<Soundtrack | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    api.music.soundtrack(album.vnid, ctrl.signal).then(setSoundtrack).catch(() => setError(true))
    return () => ctrl.abort()
  }, [album.vnid])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const title = album.vn ? displayTitle(album.vn, showOriginal) : album.vnid

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label={title}
        className="max-h-[80vh] w-full max-w-lg overflow-hidden rounded-xl bg-[#16161a] shadow-2xl ring-1 ring-white/10"
      >
        <div className="flex items-center gap-3 border-b border-white/10 p-4">
          <SoundtrackCover vnid={album.vnid} blur={blur}
            className="h-14 w-14 shrink-0 rounded ring-1 ring-white/10"
            iconClassName="h-5 w-5 text-white/25" />
          <div className="min-w-0 flex-1">
            <Link href={`/${album.vnid}`} onClick={onClose}
              className="flex items-center gap-1.5 text-sm font-semibold text-white hover:text-accent">
              <span className="truncate">{title}</span>
              <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
            </Link>
            <p className="text-xs text-muted">
              {album.trackCount} {album.trackCount === 1 ? "track" : "tracks"}
            </p>
          </div>
          {soundtrack && (
            <button
              onClick={() => onPlay(soundtrack, 0)}
              className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-black hover:brightness-110"
            >
              <Play className="h-3.5 w-3.5 fill-current" /> Play
            </button>
          )}
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-2">
          {!soundtrack && !error && <p className="px-2 py-6 text-center text-xs text-muted">Loading…</p>}
          {error && <p className="px-2 py-6 text-center text-xs text-red-400">Could not load this soundtrack.</p>}
          {soundtrack?.results.map(t => (
            <TrackLine
              key={t.ordinal}
              ordinal={t.ordinal}
              title={t.title}
              artist={t.artist}
              duration={t.duration}
              active={!!track && trackKey(track) === `${album.vnid}:${t.ordinal}`}
              onPlay={() => onPlay(soundtrack, t.ordinal - 1)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
