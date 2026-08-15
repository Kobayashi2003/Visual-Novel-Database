/** The cassette deck: the kobayashi hero's music player.
 *
 *  A compact tape-deck unit: the cassette shell (cover-art label, two reels
 *  behind the window), a live VU spectrum strip fed by the player's analyser,
 *  a scrubbable tape-position strip, and the transport row (order mode ·
 *  prev/play/next · volume).
 *
 *  The tape physics is real: playback progress moves tape from the left
 *  (supply) spool to the right (take-up) spool, and each hub's angular speed
 *  is linear-tape-speed ÷ its current spool radius — so the emptying reel
 *  visibly spins faster, exactly like a real cassette. All state comes from
 *  the PlayerProvider; this file is pure presentation + gesture handling. */
"use client"

import { useEffect, useRef, useState } from "react"
import {
  motion, useAnimationFrame, useMotionValue, useTransform, type MotionValue,
} from "motion/react"
import {
  Music, Pause, Play, Repeat, Repeat1, Shuffle, SkipBack, SkipForward,
  Volume2, VolumeX,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { usePlayer, formatTime, type PlayOrder } from "@/context/PlayerContext"
import { SoundtrackCover } from "./SoundtrackCover"


/* ─── Geometry ─────────────────────────────────────────────────────────────── */

const CASS_W = 368
const CASS_H = 188

const SPOOL_MIN = 19         // take-up spool at track start / supply at end
const SPOOL_MAX = 36
const HUB_R = 14
// Linear tape speed (px/s); hub angular speed = TAPE_SPEED / spoolR.
const TAPE_SPEED = 64


/* ─── Equalizer bars (shared with the cards + now-playing bar) ──────────────── */

export function EqBars({ playing, className }: { playing: boolean; className?: string }) {
  return (
    <span className={cn("flex items-end gap-[2px]", className)} aria-hidden>
      {[0.9, 0.5, 0.75].map((h, i) => (
        <motion.span
          key={i}
          className="w-[3px] rounded-full bg-accent"
          animate={playing ? { height: ["30%", `${h * 100}%`, "45%", "85%", "30%"] } : { height: "30%" }}
          transition={playing
            ? { duration: 0.9 + i * 0.13, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.25 }}
          style={{ minHeight: 2 }}
        />
      ))}
    </span>
  )
}


/* ─── Reel: spool of tape + spinning hub ───────────────────────────────────── */

function Reel({ spoolR, playing }: { spoolR: MotionValue<number>; playing: boolean }) {
  const angle = useMotionValue(0)
  const vel = useRef(0)
  const reduced = useRef(false)
  useEffect(() => {
    reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  }, [])

  // Inertial spin; target speed tracks the spool's CURRENT radius, so the
  // two reels never spin alike and both drift as the tape transfers.
  useAnimationFrame((_, delta) => {
    if (reduced.current) return
    const r = Math.max(SPOOL_MIN, spoolR.get())
    const target = playing ? (TAPE_SPEED / r) * (180 / Math.PI) : 0
    vel.current += (target - vel.current) * Math.min(1, delta / 600)
    if (Math.abs(vel.current) < 0.02 && !playing) return
    angle.set((angle.get() + (vel.current * delta) / 1000) % 360)
  })

  const spoolSize = useTransform(spoolR, r => r * 2)
  return (
    <div className="relative flex items-center justify-center">
      {/* Tape spool — its radius IS the remaining tape */}
      <motion.div
        style={{ width: spoolSize, height: spoolSize }}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#241a12] shadow-[inset_0_0_6px_rgba(0,0,0,0.8)] ring-1 ring-black/60"
      />
      {/* Hub with drive teeth */}
      <motion.div
        style={{ rotate: angle, width: HUB_R * 2, height: HUB_R * 2 }}
        className="relative rounded-full bg-[#dcdce0] shadow-sm ring-2 ring-[#2a2a2e]"
      >
        <div
          className="absolute inset-[3px] rounded-full"
          style={{ background: "repeating-conic-gradient(#2a2a2e 0deg 24deg, #dcdce0 24deg 60deg)" }}
        />
        <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#151517]" />
      </motion.div>
    </div>
  )
}


/* ─── The cassette shell ───────────────────────────────────────────────────── */

function Cassette() {
  const { track, playing, timeMV, duration } = usePlayer()
  const total = duration || track?.duration || 0

  const progress = useTransform(timeMV, t => (total > 0 ? Math.min(1, Math.max(0, t / total)) : 0))
  const leftR = useTransform(progress, p => SPOOL_MAX - (SPOOL_MAX - SPOOL_MIN) * p)
  const rightR = useTransform(progress, p => SPOOL_MIN + (SPOOL_MAX - SPOOL_MIN) * p)

  const sub = [track?.artist, track?.vnTitle].filter(Boolean).join(" · ")

  return (
    <div
      className="relative mx-auto overflow-hidden rounded-xl bg-gradient-to-b from-[#232328] to-[#19191d] shadow-xl shadow-black/50 ring-1 ring-white/10"
      style={{ width: CASS_W, height: CASS_H }}
    >
      {/* Corner screws */}
      {[
        "left-1.5 top-1.5", "right-1.5 top-1.5",
        "left-1.5 bottom-1.5", "right-1.5 bottom-1.5",
      ].map(pos => (
        <span key={pos} aria-hidden className={cn("absolute h-1.5 w-1.5 rounded-full bg-black/70 ring-1 ring-white/10", pos)} />
      ))}

      {/* Label: cover + side-A badge + title lines */}
      <div className="mx-4 mt-3 flex h-12 items-center gap-2.5 rounded-md bg-[#101013] px-2.5 ring-1 ring-white/10">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-black text-black">A</span>
        {track ? (
          <>
            <SoundtrackCover vnid={track.vnid} blur={track.blur}
              className="h-8 w-8 shrink-0 rounded-sm ring-1 ring-white/15"
              iconClassName="h-3.5 w-3.5 text-white/30" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold leading-tight text-white">{track.title}</p>
              {sub && <p className="truncate text-[10px] leading-tight text-muted">{sub}</p>}
            </div>
            <EqBars playing={playing} className="h-3 w-4 shrink-0" />
          </>
        ) : (
          <p className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted">
            <Music className="h-3 w-3 shrink-0 text-accent" />
            <span className="truncate">No tape loaded — click a glowing card below</span>
          </p>
        )}
      </div>

      {/* Window with the two reels */}
      <div className="mx-auto mt-2.5 grid h-[88px] w-[250px] grid-cols-2 items-center rounded-lg bg-black/60 shadow-[inset_0_2px_8px_rgba(0,0,0,0.8)] ring-1 ring-white/10">
        <Reel spoolR={leftR} playing={playing} />
        <Reel spoolR={rightR} playing={playing} />
        {/* Tape run along the head opening */}
        <div aria-hidden className="pointer-events-none absolute inset-x-[78px] bottom-[34px] h-[2px] bg-[#3a2a1c]" />
      </div>

      {/* Bottom head-opening holes */}
      <div aria-hidden className="absolute inset-x-0 bottom-2.5 flex items-center justify-center gap-7">
        {[0, 1, 2, 3, 4].map(i => (
          <span key={i} className={cn("rounded-full bg-black/80 ring-1 ring-white/10", i === 2 ? "h-2.5 w-4 rounded-md" : "h-2 w-2")} />
        ))}
      </div>
    </div>
  )
}


/* ─── VU spectrum strip (the deck's audio-reactive display) ────────────────── */

function VUStrip() {
  const { analyserRef, playing } = usePlayer()
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return

    const W = canvas.width = canvas.offsetWidth
    const H = canvas.height = canvas.offsetHeight
    const BARS = 27
    const SEGS = 6
    const gapX = 3, gapY = 2
    const barW = (W - gapX * (BARS - 1)) / BARS
    const segH = (H - gapY * (SEGS - 1)) / SEGS

    const data = new Uint8Array(128)
    const levels = new Float32Array(BARS)
    let raf = 0
    let prev = performance.now()

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw)
      const dt = Math.min(0.05, (now - prev) / 1000)
      prev = now

      const analyser = analyserRef.current
      if (analyser && playing) analyser.getByteFrequencyData(data)
      else data.fill(0)

      ctx.clearRect(0, 0, W, H)
      for (let i = 0; i < BARS; i++) {
        const v = data[2 + Math.floor(i * 3.2)] / 255
        // Fast attack, smooth release per bar.
        levels[i] = Math.max(v, levels[i] * Math.pow(0.08, dt))
        const lit = Math.round(levels[i] * SEGS)
        for (let s = 0; s < SEGS; s++) {
          const on = s < lit
          const topSeg = s >= SEGS - 2
          ctx.fillStyle = on
            ? (topSeg ? "rgba(30,215,96,0.95)" : "rgba(29,185,84,0.8)")
            : "rgba(255,255,255,0.06)"
          ctx.fillRect(
            i * (barW + gapX),
            H - (s + 1) * segH - s * gapY,
            barW, segH,
          )
        }
      }
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); ctx.clearRect(0, 0, W, H) }
  }, [playing, analyserRef])

  return <canvas ref={ref} aria-hidden className="h-[22px] w-full" />
}


/* ─── Scrubbable tape-position strip ───────────────────────────────────────── */

function SeekStrip() {
  const { track, duration, timeMV, seek } = usePlayer()
  const total = duration || track?.duration || 0

  const [scrub, setScrub] = useState<number | null>(null)
  const dragging = useRef(false)

  const progressWidth = useTransform(timeMV, t => `${total > 0 ? Math.min(100, (t / total) * 100) : 0}%`)
  const currentText = useTransform(timeMV, t => formatTime(scrub ?? t))

  const ratioFor = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
  }
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!track || total <= 0) return
    dragging.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    setScrub(ratioFor(e) * total)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragging.current) setScrub(ratioFor(e) * total)
  }
  const onPointerUp = () => {
    if (!dragging.current) return
    dragging.current = false
    setScrub(prevScrub => {
      if (prevScrub !== null) seek(prevScrub)
      return null
    })
  }

  return (
    <div className="flex items-center gap-2">
      <motion.span className="w-8 shrink-0 text-right tabular-nums text-[10px] text-white/80">
        {currentText}
      </motion.span>
      <div
        data-cursor="pointer"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className={cn("group relative h-3 flex-1", track ? "cursor-pointer" : "opacity-50")}
        style={{ touchAction: "none" }}
        aria-label="Seek"
      >
        <div className="absolute inset-x-0 top-1/2 h-[4px] -translate-y-1/2 overflow-hidden rounded-full bg-white/10">
          {scrub !== null ? (
            <div className="h-full rounded-full bg-accent" style={{ width: `${total > 0 ? (scrub / total) * 100 : 0}%` }} />
          ) : (
            <motion.div className="h-full rounded-full bg-accent" style={{ width: progressWidth }} />
          )}
        </div>
        {/* Thumb only materialises while scrubbing */}
        {scrub !== null && total > 0 && (
          <div
            className="pointer-events-none absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
            style={{ left: `${(scrub / total) * 100}%` }}
          />
        )}
      </div>
      <span className="w-8 shrink-0 tabular-nums text-[10px] text-muted">{formatTime(total)}</span>
    </div>
  )
}


/* ─── Transport (order · prev/play/next · volume) ──────────────────────────── */

const VOLUME_CSS = `
.kby-vol{appearance:none;-webkit-appearance:none;width:5rem;height:4px;border-radius:9999px;cursor:pointer;outline:none;
  background:linear-gradient(to right,var(--accent) var(--p),rgba(255,255,255,0.15) var(--p));}
.kby-vol::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:10px;height:10px;border-radius:9999px;background:#fff;
  opacity:0;transition:opacity .15s;box-shadow:0 1px 4px rgba(0,0,0,0.5)}
.kby-vol:hover::-webkit-slider-thumb,.kby-vol:active::-webkit-slider-thumb{opacity:1}
.kby-vol::-moz-range-thumb{width:10px;height:10px;border:none;border-radius:9999px;background:#fff;opacity:0;transition:opacity .15s}
.kby-vol:hover::-moz-range-thumb,.kby-vol:active::-moz-range-thumb{opacity:1}
`

const ORDER_META: Record<PlayOrder, { label: string; Icon: typeof Repeat }> = {
  sequence: { label: "Order: play in order", Icon: Repeat },
  shuffle:  { label: "Order: shuffle",       Icon: Shuffle },
  repeat:   { label: "Order: repeat one",    Icon: Repeat1 },
}

function IconBtn({ label, onClick, disabled, active, children }: {
  label: string; onClick: () => void; disabled?: boolean; active?: boolean; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-full transition-colors disabled:opacity-30",
        active ? "text-accent" : "text-muted hover:text-white disabled:hover:text-muted",
      )}
    >
      {children}
    </button>
  )
}

function OrderButton() {
  const { order, cycleOrder } = usePlayer()
  const { label, Icon } = ORDER_META[order]
  return (
    <IconBtn label={label} onClick={cycleOrder} active={order !== "sequence"}>
      <Icon className="h-4 w-4" />
    </IconBtn>
  )
}

/** Order + transport + volume. `deck` spreads the three groups across the
 *  console; `bar` keeps everything inline for the docked now-playing bar. */
export function TransportControls({ variant = "deck" }: { variant?: "deck" | "bar" }) {
  const { track, playing, toggle, next, prev, volume, setVolume, queue } = usePlayer()
  const [lastVol, setLastVol] = useState(0.8)
  const muted = volume === 0
  const deck = variant === "deck"

  const transport = (
    <div className="flex items-center gap-1.5">
      <IconBtn label="Previous" onClick={prev} disabled={!track || queue.length === 0}>
        <SkipBack className="h-4 w-4 fill-current" />
      </IconBtn>
      <motion.button
        type="button"
        aria-label={playing ? "Pause" : "Play"}
        onClick={toggle}
        disabled={!track}
        whileTap={{ scale: 0.92 }}
        className={cn(
          "flex items-center justify-center rounded-full bg-accent text-black shadow-lg shadow-accent/30 transition-colors hover:bg-accent-hover disabled:opacity-30",
          deck ? "h-10 w-10" : "h-9 w-9",
        )}
      >
        {playing
          ? <Pause className="h-4.5 w-4.5 fill-current" />
          : <Play className="ml-0.5 h-4.5 w-4.5 fill-current" />}
      </motion.button>
      <IconBtn label="Next" onClick={next} disabled={!track || queue.length === 0}>
        <SkipForward className="h-4 w-4 fill-current" />
      </IconBtn>
    </div>
  )

  const volumeGroup = (
    <div className="flex items-center gap-1">
      <IconBtn
        label={muted ? "Unmute" : "Mute"}
        onClick={() => {
          if (muted) setVolume(lastVol || 0.8)
          else { setLastVol(volume); setVolume(0) }
        }}
      >
        {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
      </IconBtn>
      <input
        type="range"
        aria-label="Volume"
        min={0} max={1} step={0.01}
        value={volume}
        onChange={e => setVolume(parseFloat(e.target.value))}
        className={cn("kby-vol", !deck && "hidden md:block")}
        style={{ "--p": `${volume * 100}%` } as React.CSSProperties}
      />
    </div>
  )

  return (
    <div className={cn("flex items-center", deck ? "w-full justify-between" : "gap-1.5")}>
      <style>{VOLUME_CSS}</style>
      {deck ? (
        <>
          <OrderButton />
          {transport}
          {volumeGroup}
        </>
      ) : (
        <>
          {transport}
          {volumeGroup}
          <OrderButton />
        </>
      )}
    </div>
  )
}


/* ─── The deck unit ────────────────────────────────────────────────────────── */

export function CassetteDeck() {
  return (
    // The inner unit is laid out at a fixed 400px (the cassette geometry is
    // pixel-based); on wide screens the whole deck scales up from its right
    // edge so the hero's two blocks fill the row with just the gap between.
    <div className="mx-auto hidden w-[400px] shrink-0 select-none sm:block lg:mx-0 xl:origin-right xl:scale-[1.12] 2xl:scale-[1.22]">
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-sm">
        <Cassette />
        <div className="mt-3">
          <VUStrip />
        </div>
        <div className="mt-2">
          <SeekStrip />
        </div>
        <div className="mt-2.5 border-t border-white/5 pt-2.5">
          <TransportControls variant="deck" />
        </div>
      </div>
    </div>
  )
}
