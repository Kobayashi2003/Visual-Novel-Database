/** The player's transport row and its level meter.
 *
 *  Presentation only — every piece of state comes from the PlayerProvider. Kept
 *  apart from any one player skin so the docked bar and whatever the library
 *  puts on screen share the same controls.
 */
"use client"

import { useState } from "react"
import { motion } from "motion/react"
import {
  Pause, Play, Repeat, Repeat1, Shuffle, SkipBack, SkipForward,
  Volume2, VolumeX,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { usePlayer, type PlayOrder } from "@/context/PlayerContext"


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
