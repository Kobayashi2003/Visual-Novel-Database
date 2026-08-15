/** The player's always-on surface, mounted once by the main layout.
 *
 *  Renders nothing until something is playing, so a visitor who never opens the
 *  music library never sees it. Once a track is loaded the bar stays across
 *  navigation — that is the whole point of the player living in the layout.
 */
"use client"

import { usePlayer } from "@/context/PlayerContext"
import { NowPlayingBar } from "./NowPlayingBar"

export function GlobalNowPlaying() {
  const { track } = usePlayer()
  return <NowPlayingBar visible={!!track} />
}
