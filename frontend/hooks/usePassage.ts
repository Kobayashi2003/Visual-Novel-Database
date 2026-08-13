/** Single passage (long-form text) English → Japanese lookup against transserve.
 *
 * Companion to `useTerm` (which handles short tag / trait *names*). Used by
 * the tag / trait detail pages to localise the *description* in original-text
 * mode: pass the source text plus `enabled` (the SearchContext `showOriginal`
 * flag) and get back the string to render. While a request is in flight, when
 * transserve has no entry, or whenever `enabled` is false, the original source
 * text is returned verbatim — so the description always renders, and the BBCode
 * markup (which the stored translation preserves token-for-token) stays valid.
 *
 * The cache is module-level, keyed by the exact source text, so a description is
 * fetched once and reused across client-side navigations for the page session.
 */
"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"

// Source text -> display string (translation, or the original text on a miss —
// the backend's fallback already echoes it).
const cache = new Map<string, string>()

export function usePassage(text: string | null | undefined, enabled: boolean): string {
  // Bumped when the lookup resolves so consumers re-render with the translation.
  const [, setVersion] = useState(0)

  const src = text ?? ""
  const need = enabled && src !== "" && !cache.has(src)

  useEffect(() => {
    if (!need) return
    const controller = new AbortController()
    api.translate.passage([src], true, controller.signal)
      .then(({ results }) => {
        const target = results[src]
        cache.set(src, typeof target === "string" && target ? target : src)
        setVersion(v => v + 1)
      })
      .catch(() => { /* leave uncached — falls back to the original text */ })
    return () => controller.abort()
  }, [need, src])

  if (!enabled || src === "") return src
  return cache.get(src) ?? src
}
