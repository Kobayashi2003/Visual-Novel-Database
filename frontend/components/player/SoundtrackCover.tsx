/** A soundtrack's own cover art, or a placeholder.
 *
 *  musicserve answers 404 when a soundtrack carries no cover of its own, and the
 *  visual novel's cover is deliberately not substituted — it is a different
 *  picture, and showing it here would misrepresent the release. So the fallback
 *  is an icon, not another image.
 */
"use client"

import { useEffect, useState } from "react"
import { Music } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

export function SoundtrackCover({
  vnid,
  blur = false,
  className,
  iconClassName = "h-1/3 w-1/3 text-white/25",
}: {
  vnid: string | null
  blur?: boolean
  className?: string
  iconClassName?: string
}) {
  const [failed, setFailed] = useState(false)
  // A new soundtrack deserves its own attempt; without this the placeholder
  // would stick for the rest of the session after the first coverless one.
  useEffect(() => setFailed(false), [vnid])

  if (!vnid || failed) {
    return (
      <div className={cn("flex items-center justify-center bg-white/[0.03]", className)}>
        <Music className={iconClassName} />
      </div>
    )
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={api.music.coverUrl(vnid)}
      alt=""
      draggable={false}
      onError={() => setFailed(true)}
      className={cn("object-cover", blur && "blur-[2px]", className)}
    />
  )
}
