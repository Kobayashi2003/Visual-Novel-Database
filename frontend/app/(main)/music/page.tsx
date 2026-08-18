/** The music library.
 *
 *  One visual novel is one album, so the library is a list of visual novels that
 *  have a soundtrack — never a flat list of tracks. musicserve knows only ids
 *  and filenames, so the titles and cover art here come from vndbserve and imgserve,
 *  joined client-side against the ids musicserve reports.
 *
 *  Two views over the same data: a list that expands a soundtrack in place, and
 *  a grid that opens one in a dialog. Playback itself belongs to the layout —
 *  this page only fills the queue.
 */
"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { LayoutGrid, List, Music, Play, Upload } from "lucide-react"

import { api } from "@/lib/api"
import { cn, numericId, shouldBlur } from "@/lib/utils"
import { displayTitle } from "@/lib/original"
import { useUserContext } from "@/context/UserContext"
import { useSearchContext } from "@/context/SearchContext"
import { usePlayer, type QueueTrack } from "@/context/PlayerContext"
import { SoundtrackCover } from "@/components/player/SoundtrackCover"
import type { Soundtrack, VN_Small } from "@/lib/types"

import { SoundtrackRow } from "./_components/SoundtrackRow"
import { SoundtrackCard, SoundtrackDialog } from "./_components/SoundtrackGrid"
import { UploadPanel } from "./_components/UploadPanel"

export type View = "list" | "grid"

/** A library entry: what musicserve knows, joined with what vndbserve knows. */
export interface Album {
  vnid: string
  trackCount: number
  vn: VN_Small | null
}

const PAGE_LIMIT = 24

export default function MusicPage() {
  const { user, defaultSexualLevel, defaultViolenceLevel } = useUserContext()
  const { showOriginal } = useSearchContext()
  const { playQueue } = usePlayer()

  const [view, setView] = useState<View>("list")
  const [albums, setAlbums] = useState<Album[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openVnid, setOpenVnid] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)

  /* Two round trips, not one per album: musicserve returns the ids, then vndbserve
     is asked for all of them at once. */
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    try {
      const page = await api.music.list({ limit: PAGE_LIMIT }, signal)
      const ids = page.results.map(r => numericId(r.id))
      const vns = ids.length
        ? await api.small.byIds.vn(ids, {}, signal).then(r => r.results)
        : []
      const byId = new Map(vns.map(v => [v.id, v]))
      setAlbums(page.results.map(r => ({
        vnid: r.id, trackCount: r.track_count, vn: byId.get(r.id) ?? null,
      })))
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    load(ctrl.signal)
    return () => ctrl.abort()
  }, [load])

  const blurOf = useCallback((vn: VN_Small | null) =>
    !!vn?.image && shouldBlur(vn.image.sexual, vn.image.violence, defaultSexualLevel, defaultViolenceLevel),
    [defaultSexualLevel, defaultViolenceLevel])

  /** Turn a fetched soundtrack into queue entries and start at `startAt`. */
  const playSoundtrack = useCallback((album: Album, st: Soundtrack, startAt = 0) => {
    const vnTitle = album.vn ? displayTitle(album.vn, showOriginal) : album.vnid
    const tracks: QueueTrack[] = st.results.map(t => ({
      ...t, vnid: album.vnid, vnTitle, blur: blurOf(album.vn),
    }))
    playQueue(tracks, startAt)
  }, [playQueue, blurOf, showOriginal])

  const open = useMemo(
    () => albums.find(a => a.vnid === openVnid) ?? null,
    [albums, openVnid])

  return (
    <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-24 lg:px-6">
      <header className="mb-5 flex items-center gap-3">
        <h1 className="flex items-center gap-2 text-lg font-semibold">
          <Music className="h-5 w-5 text-accent" />
          Music
          {!loading && (
            <span className="text-sm font-normal text-muted">
              {albums.length} {albums.length === 1 ? "soundtrack" : "soundtracks"}
            </span>
          )}
        </h1>

        <div className="ml-auto flex items-center gap-2">
          {user?.is_admin && (
            <button
              onClick={() => setUploadOpen(true)}
              className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-black hover:brightness-110"
            >
              <Upload className="h-4 w-4" /> Upload
            </button>
          )}
          <div className="flex rounded-md ring-1 ring-white/10">
            {([["list", List], ["grid", LayoutGrid]] as const).map(([v, Icon]) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                aria-label={`${v} view`}
                className={cn("p-1.5 first:rounded-l-md last:rounded-r-md",
                  view === v ? "bg-white/10 text-white" : "text-muted hover:text-white")}
              >
                <Icon className="h-4 w-4" />
              </button>
            ))}
          </div>
        </div>
      </header>

      {loading && <p className="py-16 text-center text-sm text-muted">Loading…</p>}
      {error && !loading && <p className="py-16 text-center text-sm text-red-400">{error}</p>}

      {!loading && !error && albums.length === 0 && (
        <div className="flex flex-col items-center gap-3 py-20 text-center">
          <SoundtrackCover vnid={null} className="h-16 w-16 rounded-lg" iconClassName="h-6 w-6 text-white/20" />
          <p className="text-sm text-muted">No soundtracks yet.</p>
          {user?.is_admin && (
            <button onClick={() => setUploadOpen(true)} className="text-sm text-accent hover:underline">
              Upload the first one
            </button>
          )}
        </div>
      )}

      {!loading && !error && albums.length > 0 && (
        view === "list" ? (
          <div className="divide-y divide-white/5 rounded-lg ring-1 ring-white/10">
            {albums.map(a => (
              <SoundtrackRow
                key={a.vnid}
                album={a}
                blur={blurOf(a.vn)}
                onPlay={(st, i) => playSoundtrack(a, st, i)}
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {albums.map(a => (
              <SoundtrackCard
                key={a.vnid}
                album={a}
                blur={blurOf(a.vn)}
                onOpen={() => setOpenVnid(a.vnid)}
              />
            ))}
          </div>
        )
      )}

      {open && (
        <SoundtrackDialog
          album={open}
          blur={blurOf(open.vn)}
          onClose={() => setOpenVnid(null)}
          onPlay={(st, i) => playSoundtrack(open, st, i)}
        />
      )}

      {uploadOpen && (
        <UploadPanel onClose={() => setUploadOpen(false)} onUploaded={() => { setUploadOpen(false); load() }} />
      )}
    </div>
  )
}

/** Shared by the row and the dialog: a track line with its number and length. */
export function TrackLine({ ordinal, title, artist, duration, active, onPlay }: {
  ordinal: number
  title: string
  artist: string | null
  duration: number | null
  active: boolean
  onPlay: () => void
}) {
  return (
    <button
      onClick={onPlay}
      className={cn("group flex w-full items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-white/5",
        active && "bg-white/5")}
    >
      <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted group-hover:hidden">{ordinal}</span>
      <Play className="hidden h-3 w-3 shrink-0 fill-current text-accent group-hover:block" />
      <span className={cn("min-w-0 flex-1 truncate text-sm", active ? "text-accent" : "text-white/90")}>
        {title}
      </span>
      {artist && <span className="hidden shrink-0 truncate text-xs text-muted sm:block">{artist}</span>}
      <span className="shrink-0 tabular-nums text-xs text-muted">
        {duration ? `${Math.floor(duration / 60)}:${String(Math.floor(duration % 60)).padStart(2, "0")}` : "—"}
      </span>
    </button>
  )
}
