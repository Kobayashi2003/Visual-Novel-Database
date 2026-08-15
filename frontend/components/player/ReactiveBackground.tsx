/** The music library's full-page background (the global wallpaper is suppressed
 *  on that route — see (main)/layout.tsx).
 *
 *  Deliberately quiet: no particles, no rings — just layered depth.
 *    • a static base wash so the black never reads flat;
 *    • two enormous blurred colour fields drifting on minute-scale CSS
 *      loops, far below conscious attention;
 *    • one accent glow behind the deck that breathes slowly at rest and
 *      swells gently with the bass envelope while music plays — the only
 *      audio-reactive element, kept subtle on purpose;
 *    • a vignette and a static grain to finish the surface.
 *  The drift stops under prefers-reduced-motion; the envelope loop pauses
 *  with the tab. */
"use client"

import { useEffect, useRef, useState } from "react"
import { motion, useMotionValue, useSpring } from "motion/react"

import { usePlayer } from "@/context/PlayerContext"


// Inline SVG turbulence noise, tiled. Cheap, static, no asset request.
const NOISE_URI =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"

const DRIFT_CSS = `
@keyframes kby-drift-a{
  0%,100%{transform:translate3d(-3%,-2%,0) scale(1)}
  50%{transform:translate3d(4%,3%,0) scale(1.07)}
}
@keyframes kby-drift-b{
  0%,100%{transform:translate3d(3%,2%,0) scale(1.05)}
  50%{transform:translate3d(-4%,-3%,0) scale(1)}
}
.kby-drift-a{animation:kby-drift-a 80s ease-in-out infinite}
.kby-drift-b{animation:kby-drift-b 95s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){.kby-drift-a,.kby-drift-b{animation:none}}
`

const band = (data: Uint8Array, from: number, to: number) => {
  let sum = 0
  for (let i = from; i < to; i++) sum += data[i]
  return sum / ((to - from) * 255)
}


export function ReactiveBackground() {
  const { analyserRef, playing } = usePlayer()
  const [reduced, setReduced] = useState(false)

  const playingRef = useRef(playing)
  useEffect(() => { playingRef.current = playing }, [playing])

  useEffect(() => {
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  }, [])

  /* The one reactive layer: the deck-side glow. Springs keep it liquid. */
  const glowScale = useSpring(useMotionValue(1), { stiffness: 90, damping: 16 })
  const glowOpacity = useSpring(useMotionValue(0.3), { stiffness: 80, damping: 18 })

  useEffect(() => {
    if (reduced) return
    const data = new Uint8Array(128)
    let bassEnv = 0
    let prev = performance.now()
    let raf = 0

    const loop = (now: number) => {
      raf = requestAnimationFrame(loop)
      const dt = Math.min(0.05, (now - prev) / 1000)
      prev = now
      const t = now / 1000

      let bass = 0
      const analyser = analyserRef.current
      if (analyser && playingRef.current) {
        analyser.getByteFrequencyData(data)
        bass = band(data, 2, 9)
      }
      // Fast attack, slow release — breathes with the music, never twitches.
      bassEnv = Math.max(bass, bassEnv * Math.pow(0.25, dt))

      glowScale.set(1 + Math.sin(t * 0.5) * 0.035 + bassEnv * 0.16)
      glowOpacity.set(0.26 + Math.sin(t * 0.4) * 0.05 + bassEnv * 0.34)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [reduced, analyserRef, glowScale, glowOpacity])

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <style>{DRIFT_CSS}</style>

      {/* Static depth wash */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse 90% 60% at 70% 110%, rgba(25,25,31,0.9) 0%, transparent 60%),
            radial-gradient(ellipse 60% 45% at 12% -8%, rgba(40,40,48,0.55) 0%, transparent 60%)`,
        }}
      />

      {/* Drifting colour fields — minute-scale, barely-there */}
      <div
        className="kby-drift-a absolute right-[-18%] top-[-22%] h-[60rem] w-[60rem] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(29,185,84,0.07) 0%, rgba(22,100,52,0.04) 45%, transparent 70%)" }}
      />
      <div
        className="kby-drift-b absolute bottom-[-28%] left-[-16%] h-[64rem] w-[64rem] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(58,58,70,0.5) 0%, rgba(40,40,50,0.22) 45%, transparent 70%)" }}
      />

      {/* Bass-breathing glow behind the deck */}
      <motion.div
        style={{
          scale: glowScale,
          opacity: glowOpacity,
          background: "radial-gradient(circle, rgba(29,185,84,0.13) 0%, rgba(29,185,84,0.04) 40%, transparent 68%)",
        }}
        className="absolute right-[-14%] top-[-16%] h-[56rem] w-[56rem]"
      />

      {/* Vignette */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse 120% 95% at 50% 40%, transparent 60%, rgba(0,0,0,0.5) 100%)" }}
      />

      {/* Grain */}
      <div
        className="absolute inset-0 opacity-[0.05] mix-blend-overlay"
        style={{ backgroundImage: NOISE_URI }}
      />
    </div>
  )
}
