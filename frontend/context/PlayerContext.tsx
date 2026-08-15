/** The application's music player: one <audio> element, mounted once.
 *
 *  Lives here rather than on a page so playback survives navigation — starting a
 *  track and then opening a visual novel does not stop the music.
 *
 *  Owns the audio element (streaming from musicserve), the WebAudio analyser the
 *  deck's VU display and the reactive background read from, the play queue, and
 *  the play-order mode.
 *
 *  Time flows through a MotionValue updated by a rAF loop while playing, so the
 *  reels and progress animate without re-rendering their subtree.
 */
"use client"

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode, type RefObject,
} from "react"
import { useMotionValue, type MotionValue } from "motion/react"

import { api } from "@/lib/api"
import type { MusicTrack } from "@/lib/types"


/** A queued track: the file, plus the visual novel it belongs to so the player
 *  can name and link what is playing. musicserve has no database, so a track is
 *  identified by its soundtrack and its position in it — see `trackKey`. */
export interface QueueTrack extends MusicTrack {
  vnid: string
  /** The visual novel's title, for display. Not the track's own. */
  vnTitle: string
  /** Content filter verdict from the caller, applied to the cover. */
  blur: boolean
}

export const trackKey = (t: Pick<QueueTrack, "vnid" | "ordinal">) => `${t.vnid}:${t.ordinal}`

/** Playback-order modes, cycled by the deck's order button:
 *  sequence — walk the queue in order (wrapping);
 *  shuffle  — jump to a random other track;
 *  repeat   — loop the current track when it ends (manual skips still step). */
export type PlayOrder = "sequence" | "shuffle" | "repeat"

interface PlayerContextValue {
  track: QueueTrack | null
  playing: boolean
  order: PlayOrder
  duration: number
  volume: number
  queue: QueueTrack[]
  /** Replace the queue and start at `startAt` (default: its first track). */
  playQueue: (tracks: QueueTrack[], startAt?: number) => void
  /** Add to the end of the queue without disturbing what is playing. */
  enqueue: (tracks: QueueTrack[]) => void
  clearQueue: () => void
  play: (track: QueueTrack) => void
  toggle: () => void
  next: () => void
  prev: () => void
  seek: (seconds: number) => void
  setVolume: (v: number) => void
  cycleOrder: () => void
  /** Current playback position in seconds; rAF-smooth while playing. */
  timeMV: MotionValue<number>
  /** Live analyser over the playing audio (null until first play). */
  analyserRef: RefObject<AnalyserNode | null>
}

const PlayerContext = createContext<PlayerContextValue | null>(null)

export function usePlayer(): PlayerContextValue {
  const ctx = useContext(PlayerContext)
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider")
  return ctx
}

export const formatTime = (s: number) => {
  if (!isFinite(s) || s < 0) return "0:00"
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}

const VOLUME_KEY = "vndb-player-volume"
const ORDER_KEY = "vndb-player-order"
const ORDER_CYCLE: PlayOrder[] = ["sequence", "shuffle", "repeat"]


export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)

  const [track, setTrack] = useState<QueueTrack | null>(null)
  const [playing, setPlaying] = useState(false)
  const [order, setOrder] = useState<PlayOrder>("sequence")
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.8)
  const [queue, setQueue] = useState<QueueTrack[]>([])

  const timeMV = useMotionValue(0)

  /* Restore persisted volume / order once on the client. */
  useEffect(() => {
    const v = parseFloat(localStorage.getItem(VOLUME_KEY) ?? "")
    if (!isNaN(v)) setVolumeState(Math.min(1, Math.max(0, v)))
    const o = localStorage.getItem(ORDER_KEY) as PlayOrder | null
    if (o && ORDER_CYCLE.includes(o)) setOrder(o)
  }, [])

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume
  }, [volume])

  /* Wire the analyser the first time playback starts. A media element can only
     ever be wrapped in ONE MediaElementSource, so this runs once; from then on
     all audio flows element → analyser → speakers. */
  const ensureAnalyser = useCallback(() => {
    const audio = audioRef.current
    if (!audio || audioCtxRef.current) {
      audioCtxRef.current?.resume().catch(() => {})
      return
    }
    try {
      const ctx = new AudioContext()
      const source = ctx.createMediaElementSource(audio)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)
      analyser.connect(ctx.destination)
      audioCtxRef.current = ctx
      analyserRef.current = analyser
    } catch {
      // WebAudio unavailable — plain playback still works, visuals stay idle.
    }
  }, [])

  /* rAF-smooth playback clock while playing (timeupdate alone is ~4 Hz — too
     coarse for the reels / progress ring). */
  useEffect(() => {
    if (!playing) return
    let raf = 0
    const tick = () => {
      const a = audioRef.current
      if (a) timeMV.set(a.currentTime)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, timeMV])

  const play = useCallback((t: QueueTrack) => {
    const audio = audioRef.current
    if (!audio) return
    ensureAnalyser()
    if (track && trackKey(track) === trackKey(t)) {
      // Re-selecting the current track toggles rather than restarting.
      if (audio.paused) audio.play().catch(() => {})
      else audio.pause()
      return
    }
    setTrack(t)
    // The listing already carried the duration, so the UI has a scale to draw
    // before the stream's own metadata arrives.
    setDuration(t.duration ?? 0)
    timeMV.set(0)
    audio.src = api.music.trackUrl(t.vnid, t.ordinal)
    audio.play().catch(() => {})
  }, [track, ensureAnalyser, timeMV])

  const playQueue = useCallback((tracks: QueueTrack[], startAt = 0) => {
    setQueue(tracks)
    if (tracks.length) play(tracks[Math.min(Math.max(0, startAt), tracks.length - 1)])
  }, [play])

  const enqueue = useCallback((tracks: QueueTrack[]) => {
    setQueue(q => {
      const seen = new Set(q.map(trackKey))
      return [...q, ...tracks.filter(t => !seen.has(trackKey(t)))]
    })
  }, [])

  const clearQueue = useCallback(() => setQueue([]), [])

  const toggle = useCallback(() => {
    const audio = audioRef.current
    if (!audio || !track) return
    ensureAnalyser()
    if (audio.paused) audio.play().catch(() => {})
    else audio.pause()
  }, [track, ensureAnalyser])

  const step = useCallback((dir: 1 | -1) => {
    if (!track || queue.length === 0) return
    const key = trackKey(track)
    const idx = queue.findIndex(t => trackKey(t) === key)
    // The current track may have dropped out of the queue; fall back to the
    // queue edge in the travel direction.
    const nextIdx = idx === -1
      ? (dir === 1 ? 0 : queue.length - 1)
      : (idx + dir + queue.length) % queue.length
    play(queue[nextIdx])
  }, [track, queue, play])

  const playRandomOther = useCallback(() => {
    if (queue.length === 0) return
    if (queue.length === 1) { play(queue[0]); return }
    const cur = track ? queue.findIndex(t => trackKey(t) === trackKey(track)) : -1
    let idx = Math.floor(Math.random() * queue.length)
    if (idx === cur) idx = (idx + 1) % queue.length
    play(queue[idx])
  }, [queue, track, play])

  /* Manual skips honour shuffle; sequence and repeat both just step (repeat only
     changes what happens when a track ENDS). */
  const next = useCallback(
    () => (order === "shuffle" ? playRandomOther() : step(1)),
    [order, playRandomOther, step])
  const prev = useCallback(
    () => (order === "shuffle" ? playRandomOther() : step(-1)),
    [order, playRandomOther, step])

  const onEnded = useCallback(() => {
    if (order === "repeat") {
      const audio = audioRef.current
      if (!audio) return
      audio.currentTime = 0
      audio.play().catch(() => {})
      return
    }
    if (order === "shuffle") { playRandomOther(); return }
    step(1)
  }, [order, playRandomOther, step])

  const cycleOrder = useCallback(() => {
    setOrder(o => {
      const nextOrder = ORDER_CYCLE[(ORDER_CYCLE.indexOf(o) + 1) % ORDER_CYCLE.length]
      localStorage.setItem(ORDER_KEY, nextOrder)
      return nextOrder
    })
  }, [])

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    const target = Math.min(Math.max(0, seconds), duration || audio.duration || 0)
    audio.currentTime = target
    timeMV.set(target)
  }, [duration, timeMV])

  const setVolume = useCallback((v: number) => {
    const clamped = Math.min(1, Math.max(0, v))
    setVolumeState(clamped)
    localStorage.setItem(VOLUME_KEY, String(clamped))
  }, [])

  /* Lock-screen / media-key integration. */
  useEffect(() => {
    if (!("mediaSession" in navigator)) return
    const ms = navigator.mediaSession
    if (track) {
      ms.metadata = new MediaMetadata({
        title: track.title,
        artist: track.artist || "",
        album: track.album || track.vnTitle,
      })
    }
    ms.setActionHandler("play", () => audioRef.current?.play().catch(() => {}))
    ms.setActionHandler("pause", () => audioRef.current?.pause())
    ms.setActionHandler("previoustrack", prev)
    ms.setActionHandler("nexttrack", next)
    return () => {
      ms.setActionHandler("play", null)
      ms.setActionHandler("pause", null)
      ms.setActionHandler("previoustrack", null)
      ms.setActionHandler("nexttrack", null)
    }
  }, [track, prev, next])

  const value = useMemo<PlayerContextValue>(() => ({
    track, playing, order, duration, volume, queue,
    playQueue, enqueue, clearQueue, play, toggle, next, prev, seek, setVolume,
    cycleOrder, timeMV, analyserRef,
  }), [track, playing, order, duration, volume, queue,
       playQueue, enqueue, clearQueue, play, toggle, next, prev, seek, setVolume, cycleOrder, timeMV])

  return (
    <PlayerContext.Provider value={value}>
      {/* The one true audio element. Same-origin stream, so the analyser needs
          no CORS handshake. */}
      <audio
        ref={audioRef}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={onEnded}
        onDurationChange={e => {
          const d = e.currentTarget.duration
          if (isFinite(d) && d > 0) setDuration(d)
        }}
        onTimeUpdate={e => { if (!playing) timeMV.set(e.currentTarget.currentTime) }}
      />
      {children}
    </PlayerContext.Provider>
  )
}
