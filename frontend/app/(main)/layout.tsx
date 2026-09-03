/** Layout for the main app: background, header, and global context providers. */
"use client"

import { useRef, useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useOnScroll } from "@/hooks/useOnScroll"
import { UserProvider } from "@/context/UserContext"
import { SearchProvider } from "@/context/SearchContext"
import { PlayerProvider } from "@/context/PlayerContext"
import { GlobalNowPlaying } from "@/components/player/GlobalNowPlaying"
import { IMGSERVE_BASE_URL } from "@/lib/constants"
import { HeaderBar } from "@/components/header/HeaderBar"

export default function MainLayout({ children }: { children: React.ReactNode }) {
  // Defer the (large) page background so content images win the network first.
  // Once the browser goes idle we prefetch it through an `Image()` tagged
  // `fetchPriority: "low"` — the lowest the network stack offers — and only
  // promote it to the CSS `background-image` after it has fully decoded. That
  // keeps it off the critical path entirely: a CSS background alone is still
  // fetched at the layout engine's discretion (and can't carry a priority hint),
  // whereas this paints from cache with zero extra contention.
  const pathname = usePathname()
  // /login is reached without a session, so imgserve would 401 — don't ask.
  const wantsBackground = pathname !== "/login"

  const [bgUrl, setBgUrl] = useState<string | undefined>(undefined)
  useEffect(() => {
    if (!wantsBackground) return
    const src = `${IMGSERVE_BASE_URL}/bg`
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void) => number
      cancelIdleCallback?: (id: number) => void
    }
    let img: (HTMLImageElement & { fetchPriority?: string }) | null = null
    const load = () => {
      img = new Image()
      img.fetchPriority = "low"
      img.decoding = "async"
      img.onload = () => setBgUrl(`url(${src})`)
      img.src = src
    }
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(load)
      return () => { w.cancelIdleCallback?.(id); if (img) img.onload = null }
    }
    const t = setTimeout(load, 200)
    return () => { clearTimeout(t); if (img) img.onload = null }
  }, [wantsBackground])

  // The relation-graph page (`/{slug}/rg`) is full-bleed with its own frosted
  // header overlay, so the global header — and its top-edge peek — must stay out.
  // /login is standalone too — its header would only offer search that 401s.
  const hideHeader = pathname === "/login" || pathname.endsWith("/rg")
  // A route that paints its own full-page background suppresses the global
  // wallpaper, which would otherwise stack underneath and fight it. No route
  // does at the moment; the flag stays because the wash below and the wallpaper
  // have to be turned off together wherever one is.
  const bespokeBg = false

  // Drives the auto-hide header (`trigger` === hidden): shown at the top of the
  // page and after a short scroll up, hidden once the user scrolls back down.
  // It slides out of view via a transform rather than collapsing its reserved
  // strip, so toggling it never reflows the page.
  const { trigger: headerHidden } = useOnScroll()

  const [mounted, setMounted] = useState(false)
  const headerRef = useRef<HTMLDivElement>(null)
  const [headerHeight, setHeaderHeight] = useState(0)

  // Measure the header so the spacer below can reserve its exact height —
  // ResizeObserver keeps the spacer in sync if the header reflows. Re-runs when
  // `hideHeader` toggles: the header is unmounted on the Kobayashi page, so this
  // must re-measure (and re-observe) the moment it re-appears on another route —
  // otherwise the height stays stale at 0 and the fixed header overlaps content.
  useEffect(() => {
    const header = headerRef.current
    if (!header) return
    setHeaderHeight(header.offsetHeight)
    const observer = new ResizeObserver(entries => {
      setHeaderHeight(entries[0].target.clientHeight)
    })
    observer.observe(header)
    return () => observer.disconnect()
  }, [hideHeader])

  // `mounted` gates the header/spacer until the client has hydrated, so the
  // SSR markup doesn't show a header that disappears on the first scroll tick.
  useEffect(() => {
    setMounted(true)
    return () => setMounted(false)
  }, [])

  return (
    <SearchProvider>
      <UserProvider>
        <PlayerProvider>
        <div
          style={{
            // Height reserved for the fixed header so inner-scrolling pages can
            // size themselves to `calc(100vh - var(--header-h))`. Constant while
            // the header exists (it auto-hides by sliding over content, not by
            // reclaiming this strip); only the header-less routes drop it to 0.
            "--header-h": hideHeader ? "0px" : `${headerHeight}px`,
          } as React.CSSProperties}
        >
          {/* The wallpaper, as a layer of its own rather than this element's
              `background-attachment: fixed`. Both paint the image against the
              viewport; the difference is that a fixed attachment belongs to a
              scrolling box and has to be re-rasterized against the moved
              content on every frame, where a fixed-position layer is
              rasterized once and composited from then on. It matters here
              because a frosted header and blurred cards sit on top of it.

              Behind everything, which is what the negative z-index is for: no
              ancestor up to the root creates a stacking context, so this
              paints below every in-flow background — including the wash. */}
          {!bespokeBg && bgUrl && (
            <div
              aria-hidden
              className="pointer-events-none fixed inset-0 -z-10 bg-cover bg-center bg-no-repeat"
              style={{ backgroundImage: bgUrl }}
            />
          )}
          {/* On a bespoke-background route the translucent wash goes too: it is
              an in-flow background and so paints over any -z layer beneath it,
              which would dim exactly what that route is painting. The body
              colour is the base there instead. */}
          <div className={cn(
            "min-h-screen overflow-x-clip text-white flex flex-col",
            !bespokeBg && "bg-background/80",
          )}>
            {!hideHeader && (
              <>
                <div
                  ref={headerRef}
                  className={cn(
                    "fixed inset-x-0 top-0 z-10",
                    "bg-background/90 backdrop-blur-sm",
                    // Slide out of view rather than fade: transform is composited,
                    // so showing/hiding doesn't repaint the frosted blur or the
                    // content behind it. Off-screen, the blur isn't computed at all.
                    "transition-transform duration-300 ease-out will-change-transform",
                    headerHidden ? "-translate-y-full" : "translate-y-0",
                    !mounted && "hidden"
                  )}
                >
                  <HeaderBar hidden={headerHidden} />
                </div>
                {/* Constant spacer reserving the header's strip — never animated,
                    so the page never reflows as the header shows/hides. */}
                <div
                  style={{ height: `${headerHeight}px` }}
                  className={cn(!mounted && "hidden")}
                />
              </>
            )}
            <div className="flex-1 flex flex-col">
              {children}
            </div>
          </div>
          {/* Mounted beside the page, not inside it: playback has to survive
              navigation, so the bar and the audio element outlive any route. */}
          <GlobalNowPlaying />
        </div>
        </PlayerProvider>
      </UserProvider>
    </SearchProvider>
  )
}
