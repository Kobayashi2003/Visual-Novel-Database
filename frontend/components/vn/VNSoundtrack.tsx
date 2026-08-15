/** The visual novel's soundtrack, if the library holds one.
 *
 *  Renders nothing at all when it does not — most works have no music, and an
 *  empty "Soundtrack" heading on every page would be noise.
 *
 *  Playing from here fills the queue with this soundtrack, exactly as the music
 *  library does; the player itself lives in the layout, so the track keeps
 *  playing when the visitor moves on.
 */
"use client"

import { useEffect, useState } from "react"
import { Play } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { formatTime, usePlayer, trackKey, type QueueTrack } from "@/context/PlayerContext"
import { Section } from "@/components/detail/InfoPrimitives"
import { SoundtrackCover } from "@/components/player/SoundtrackCover"
import type { Soundtrack } from "@/lib/types"

export function VNSoundtrack({ vnid, vnTitle, blur }: {
  vnid: string
  vnTitle: string
  blur: boolean
}) {
  const { track, playQueue } = usePlayer()
  const [soundtrack, setSoundtrack] = useState<Soundtrack | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    // A 404 is the normal answer here — it means no soundtrack, not a failure.
    api.music.soundtrack(vnid, ctrl.signal).then(setSoundtrack).catch(() => setSoundtrack(null))
    return () => ctrl.abort()
  }, [vnid])

  if (!soundtrack || soundtrack.results.length === 0) return null

  const queue: QueueTrack[] = soundtrack.results.map(t => ({ ...t, vnid, vnTitle, blur }))

  return (
    <Section title="Soundtrack" count={soundtrack.track_count}>
    <div className="flex gap-4">
      <div className="hidden shrink-0 sm:block">
        <SoundtrackCover vnid={vnid} blur={blur}
          className="h-24 w-24 rounded-lg ring-1 ring-white/10"
          iconClassName="h-7 w-7 text-white/20" />
        <button
          onClick={() => playQueue(queue, 0)}
          className="mt-2 flex w-24 items-center justify-center gap-1.5 rounded-md bg-accent py-1.5 text-xs font-semibold text-black hover:brightness-110"
        >
          <Play className="h-3 w-3 fill-current" /> Play
        </button>
      </div>

      <ul className="min-w-0 flex-1">
        {soundtrack.results.map((t, i) => {
          const active = !!track && trackKey(track) === `${vnid}:${t.ordinal}`
          return (
            <li key={t.ordinal}>
              <button
                onClick={() => playQueue(queue, i)}
                className={cn("group flex w-full items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-white/5",
                  active && "bg-white/5")}
              >
                <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted group-hover:hidden">
                  {t.ordinal}
                </span>
                <Play className="hidden h-3 w-3 shrink-0 fill-current text-accent group-hover:block" />
                <span className={cn("min-w-0 flex-1 truncate text-sm", active ? "text-accent" : "text-white/90")}>
                  {t.title}
                </span>
                {t.artist && (
                  <span className="hidden shrink-0 truncate text-xs text-muted sm:block">{t.artist}</span>
                )}
                <span className="shrink-0 tabular-nums text-xs text-muted">
                  {t.duration ? formatTime(t.duration) : "—"}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
    </Section>
  )
}
