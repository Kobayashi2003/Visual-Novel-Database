/** Batch English → Japanese name lookups against transserve, with a shared cache.
 *
 * Used by tag / trait chips in original-text mode: pass the names to display
 * plus `enabled` (the SearchContext `showOriginal` flag) and get back a
 * resolver. The resolver returns the Japanese translation once it has loaded,
 * the original English term while a request is in flight or when there is no
 * term entry, and the original term verbatim whenever `enabled` is false.
 *
 * The cache is module-level, so translations are fetched once and reused across
 * every chip list and across client-side navigations for the page session.
 */
"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"

// Normalized source term -> display string (translation, or the original term
// when transserve has no entry — the backend's fallback already echoes it).
const cache = new Map<string, string>()

const normalize = (term: string) => term.trim().replace(/\s+/g, " ").toLowerCase()

export function useTerm(terms: string[], enabled: boolean): (term: string) => string {
  // Bumped when a batch resolves so consumers re-render with the new names.
  const [, setVersion] = useState(0)

  // Terms we still need a translation for (deduped, order-independent).
  const missing = enabled
    ? Array.from(new Set(terms.filter(t => t && !cache.has(normalize(t)))))
    : []
  // Stable effect key. The "\x1f" unit separator keeps distinct word sets from
  // aliasing to the same key (e.g. ["ab","c"] vs ["a","bc"] → both "abc").
  const missingKey = missing.map(normalize).sort().join("\x1f")

  useEffect(() => {
    if (!enabled || missing.length === 0) return
    const controller = new AbortController()
    api.translate.term(missing, true, controller.signal)
      .then(({ results }) => {
        for (const term of missing) {
          const target = results[term]
          cache.set(normalize(term), typeof target === "string" && target ? target : term)
        }
        setVersion(v => v + 1)
      })
      .catch(() => { /* leave uncached — the resolver falls back to the original */ })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, missingKey])

  return (term: string) => (enabled ? cache.get(normalize(term)) ?? term : term)
}
