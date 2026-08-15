/** List view: one visual novel per row, expanding in place to its tracks.
 *
 *  The track list is fetched on first expand, not with the page — the library
 *  listing carries only ids and counts, and a page of twenty albums would
 *  otherwise mean twenty extra requests for lists nobody has opened.
 */
"use client"

import { useState } from "react"
import Link from "next/link"
import { ChevronDown, ExternalLink, Play } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { displayTitle } from "@/lib/original"
import { useSearchContext } from "@/context/SearchContext"
import { usePlayer, trackKey } from "@/context/PlayerContext"
import { SoundtrackCover } from "@/components/player/SoundtrackCover"
import type { Soundtrack } from "@/lib/types"

import { TrackLine, type Album } from "../page"

export function SoundtrackRow({ album, blur, onPlay }: {
  album: Album
  blur: boolean
  onPlay: (soundtrack: Soundtrack, startAt: number) => void
}) {
  const { track } = usePlayer()
  const { showOriginal } = useSearchContext()
  const [open, setOpen] = useState(false)
  const [soundtrack, setSoundtrack] = useState<Soundtrack | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async (): Promise<Soundtrack | null> => {
    if (soundtrack) return soundtrack
    setLoading(true)
    try {
      const st = await api.music.soundtrack(album.vnid)
      setSoundtrack(st)
      return st
    } catch {
      return null
    } finally {
      setLoading(false)
    }
  }

  const toggle = async () => {
    setOpen(o => !o)
    if (!open) await load()
  }

  const playAll = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const st = await load()
    if (st) onPlay(st, 0)
  }

  const title = album.vn ? displayTitle(album.vn, showOriginal) : album.vnid

  return (
    <div>
      <div
        onClick={toggle}
        className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-white/[0.03]"
      >
        <SoundtrackCover vnid={album.vnid} blur={blur}
          className="h-11 w-11 shrink-0 rounded ring-1 ring-white/10"
          iconClassName="h-4 w-4 text-white/25" />

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{title}</p>
          <p className="text-xs text-muted">
            {album.trackCount} {album.trackCount === 1 ? "track" : "tracks"}
          </p>
        </div>

        {/* Opening the work is its own control: the row itself expands, so a
            whole-row link would take the click that reveals the tracks. */}
        <Link
          href={`/${album.vnid}`}
          onClick={e => e.stopPropagation()}
          aria-label={`Open ${title}`}
          className="rounded p-1.5 text-muted hover:text-white"
        >
          <ExternalLink className="h-4 w-4" />
        </Link>
        <button
          onClick={playAll}
          aria-label={`Play ${title}`}
          className="rounded-full bg-accent p-1.5 text-black hover:brightness-110"
        >
          <Play className="h-3.5 w-3.5 fill-current" />
        </button>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted transition-transform", open && "rotate-180")} />
      </div>

      {open && (
        <div className="border-t border-white/5 bg-black/20 px-3 py-2">
          {loading && <p className="px-2 py-2 text-xs text-muted">Loading…</p>}
          {!loading && soundtrack?.results.map(t => (
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
          {!loading && !soundtrack && (
            <p className="px-2 py-2 text-xs text-red-400">Could not load this soundtrack.</p>
          )}
        </div>
      )}
    </div>
  )
}
