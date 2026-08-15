/** Retired. The showcase this route used to serve was folded into the music
 *  library, which is where its cassette deck and cards now live. Kept as a
 *  redirect because the path was shared. */
import { redirect } from "next/navigation"

export default function KobayashiPage() {
  redirect("/music")
}
