/** Docked now-playing bar.
 *
 *  Auto-docks: once a track is loaded it slides in whenever the cassette deck
 *  has scrolled out of view (and is simply always the player surface on
 *  narrow viewports, where the deck is hidden). Mini spinning-reel cassette,
 *  marquee title, compact transport, click-to-seek progress line. */
"use client"

import { useEffect, useRef, useState } from "react"
import { AnimatePresence, motion, useAnimationFrame, useMotionValue, useTransform } from "motion/react"

import { usePlayer, formatTime } from "@/context/PlayerContext"
import { SoundtrackCover } from "./SoundtrackCover"
import { TransportControls, EqBars } from "./Transport"


// Past this scroll depth the hero deck is out of sight and the bar takes over.
const DOCK_SCROLL_Y = 420

/** Whether the bar is on screen — the page also needs this, to reserve
 *  bottom padding so the last grid row can scroll clear of the bar. */
export function useNowPlayingBarVisible(): boolean {
  const { track } = usePlayer()
  const [narrow, setNarrow] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)")
    const update = () => setNarrow(mq.matches)
    update()
    mq.addEventListener("change", update)
    return () => mq.removeEventListener("change", update)
  }, [])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > DOCK_SCROLL_Y)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return !!track && (narrow || scrolled)
}


/* Mini cassette: label = cover art, two spinning hubs in the window. */
function MiniCassette({ vnid, blur, spinning }: { vnid: string | null; blur: boolean; spinning: boolean }) {
  const angle = useMotionValue(0)
  const vel = useRef(0)
  useAnimationFrame((_, delta) => {
    const target = spinning ? 160 : 0
    vel.current += (target - vel.current) * Math.min(1, delta / 600)
    if (Math.abs(vel.current) < 0.02 && !spinning) return
    angle.set((angle.get() + (vel.current * delta) / 1000) % 360)
  })

  return (
    <div className="relative h-10 w-[60px] shrink-0 overflow-hidden rounded-md bg-gradient-to-b from-[#232328] to-[#19191d] shadow-md shadow-black/60 ring-1 ring-white/15">
      {/* Label strip = the cover */}
      <div className="absolute inset-x-1 top-1 h-3.5 overflow-hidden rounded-[3px] bg-[#101013] ring-1 ring-white/10">
        <SoundtrackCover vnid={vnid} blur={blur} className="h-full w-full" iconClassName="h-2 w-2 text-white/25" />
      </div>
      {/* Window with two hubs */}
      <div className="absolute inset-x-2 bottom-1 flex h-4 items-center justify-around rounded-[3px] bg-black/60 ring-1 ring-white/10">
        {[0, 1].map(i => (
          <motion.span
            key={i}
            style={{ rotate: angle }}
            className="relative h-2.5 w-2.5 rounded-full bg-[#dcdce0] ring-1 ring-[#2a2a2e]"
          >
            <span
              className="absolute inset-[1.5px] rounded-full"
              style={{ background: "repeating-conic-gradient(#2a2a2e 0deg 30deg, #dcdce0 30deg 72deg)" }}
            />
          </motion.span>
        ))}
      </div>
    </div>
  )
}


/* Title that auto-marquees when it overflows its box. */
function MarqueeTitle({ text, sub }: { text: string; sub?: string }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLSpanElement>(null)
  const [overflowPx, setOverflowPx] = useState(0)

  useEffect(() => {
    const box = boxRef.current
    const span = textRef.current
    if (!box || !span) return
    const measure = () => setOverflowPx(Math.max(0, span.scrollWidth - box.clientWidth))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(box)
    return () => ro.disconnect()
  }, [text, sub])

  const full = sub ? `${text} — ${sub}` : text
  return (
    <div ref={boxRef} className="min-w-0 flex-1 overflow-hidden whitespace-nowrap">
      <motion.span
        ref={textRef}
        key={full}
        className="inline-block text-sm font-semibold text-white"
        animate={overflowPx > 0 ? { x: [0, -overflowPx - 16, 0] } : { x: 0 }}
        transition={overflowPx > 0
          ? { duration: Math.max(6, overflowPx / 18), repeat: Infinity, ease: "linear", repeatDelay: 1.6 }
          : { duration: 0 }}
      >
        {text}
        {sub && <span className="ml-2 font-normal text-muted">{sub}</span>}
      </motion.span>
    </div>
  )
}


export function NowPlayingBar({ visible }: { visible: boolean }) {
  const { track, playing, duration, timeMV, seek } = usePlayer()
  // The listing carried the duration, so the scale is known before the stream's
  // own metadata arrives.
  const total = duration || track?.duration || 0

  const progress = useTransform(timeMV, t => (total > 0 ? Math.min(1, t / total) : 0))
  const progressX = useTransform(progress, p => `${(p - 1) * 100}%`)
  const timeText = useTransform(timeMV, t => formatTime(t))

  const onSeekClick = (e: React.PointerEvent<HTMLDivElement>) => {
    if (total <= 0) return
    const r = e.currentTarget.getBoundingClientRect()
    seek(((e.clientX - r.left) / r.width) * total)
  }

  return (
    <AnimatePresence>
      {visible && track && (
        <motion.div
          initial={{ y: 88 }}
          animate={{ y: 0 }}
          exit={{ y: 88 }}
          transition={{ type: "spring", stiffness: 300, damping: 32 }}
          className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-background/85 shadow-[0_-8px_32px_rgba(0,0,0,0.5)] backdrop-blur-xl"
        >
          {/* Click-to-seek progress line along the top edge */}
          <div
            data-cursor="pointer"
            onPointerDown={onSeekClick}
            className="group absolute inset-x-0 -top-1.5 h-3 cursor-pointer"
            aria-label="Seek"
          >
            <div className="absolute inset-x-0 top-1.5 h-[3px] overflow-hidden bg-white/10">
              <motion.div
                style={{ x: progressX }}
                className="h-full w-full bg-accent transition-[height] group-hover:h-[5px]"
              />
            </div>
          </div>

          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 lg:px-6">
            <MiniCassette vnid={track.vnid} blur={!!track.blur} spinning={playing} />
            <EqBars playing={playing} className="hidden h-3.5 w-4 shrink-0 sm:flex" />
            <MarqueeTitle
              text={track.title}
              sub={[track.artist, track.vnTitle].filter(Boolean).join(" · ") || undefined}
            />
            <span className="hidden shrink-0 tabular-nums text-xs text-muted md:inline">
              <motion.span className="text-white/90">{timeText}</motion.span>
              {" / "}{formatTime(total)}
            </span>
            <TransportControls variant="bar" />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
