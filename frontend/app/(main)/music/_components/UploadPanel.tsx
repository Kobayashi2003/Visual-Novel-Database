/** Admin upload: pick a visual novel, attach its soundtrack, send it in one go.
 *
 *  The visual novel is chosen by searching vndb rather than typed as an id, so
 *  the files land on a work the uploader can see rather than a number they had
 *  to look up.
 *
 *  One request carries the whole album — musicserve stores each file and answers
 *  409 for a name already there, which is surfaced rather than silently
 *  overwritten. `replace` is an explicit choice.
 */
"use client"

import { useEffect, useRef, useState } from "react"
import { Search, Upload, X } from "lucide-react"

import { api, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { displayTitle } from "@/lib/original"
import { useSearchContext } from "@/context/SearchContext"
import type { VN_Small } from "@/lib/types"

export function UploadPanel({ onClose, onUploaded }: {
  onClose: () => void
  onUploaded: () => void
}) {
  const { showOriginal } = useSearchContext()
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<VN_Small[]>([])
  const [picked, setPicked] = useState<VN_Small | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose, busy])

  /* Debounced search — one request per pause, not per keystroke. */
  useEffect(() => {
    if (picked || query.trim().length < 2) { setResults([]); return }
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      api.small.vn({ search: query.trim(), limit: 6 }, ctrl.signal)
        .then(r => setResults(r.results))
        .catch(() => setResults([]))
    }, 300)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [query, picked])

  const submit = async () => {
    if (!picked || files.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await api.music.upload(picked.id, files, { replace })
      onUploaded()
    } catch (e) {
      const err = e as ApiError
      setError(err.status === 409
        ? "Some of those filenames are already in this soundtrack. Tick replace to overwrite them."
        : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      onClick={() => !busy && onClose()}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label="Upload a soundtrack"
        className="w-full max-w-lg overflow-hidden rounded-xl bg-[#16161a] shadow-2xl ring-1 ring-white/10"
      >
        <div className="flex items-center gap-2 border-b border-white/10 p-4">
          <Upload className="h-4 w-4 text-accent" />
          <p className="flex-1 text-sm font-semibold text-white">Upload a soundtrack</p>
          <button onClick={onClose} disabled={busy} aria-label="Close"
            className="rounded p-1 text-muted hover:text-white disabled:opacity-40">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          {/* Which visual novel */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Visual novel</label>
            {picked ? (
              <div className="flex items-center gap-2 rounded-md bg-white/5 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm text-white">{displayTitle(picked, showOriginal)}</span>
                <span className="shrink-0 font-mono text-xs text-muted">{picked.id}</span>
                <button onClick={() => { setPicked(null); setQuery("") }}
                  className="text-xs text-accent hover:underline">change</button>
              </div>
            ) : (
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted" />
                <input
                  autoFocus
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Search by title…"
                  className="w-full rounded-md bg-black/40 py-2 pl-8 pr-3 text-sm text-white ring-1 ring-white/10 placeholder:text-muted focus:outline-none focus:ring-accent/60"
                />
                {results.length > 0 && (
                  <ul className="mt-1 max-h-44 overflow-y-auto rounded-md bg-black/60 ring-1 ring-white/10">
                    {results.map(v => (
                      <li key={v.id}>
                        <button onClick={() => setPicked(v)}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-white/5">
                          <span className="min-w-0 flex-1 truncate text-sm text-white/90">{displayTitle(v, showOriginal)}</span>
                          <span className="shrink-0 font-mono text-xs text-muted">{v.id}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Which files */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Audio files</label>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".mp3,.m4a,.flac,.ogg,.opus,.wav"
              onChange={e => setFiles(Array.from(e.target.files ?? []))}
              className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-white/15"
            />
            {files.length > 0 && (
              <p className="mt-1.5 text-xs text-muted">
                {files.length} file{files.length === 1 ? "" : "s"} ·{" "}
                {(files.reduce((n, f) => n + f.size, 0) / 1024 ** 2).toFixed(1)} MB
              </p>
            )}
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              A name starting with a number keeps its own order; anything else is
              numbered after the tracks already there.
            </p>
          </div>

          <label className="flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={replace} onChange={e => setReplace(e.target.checked)}
              className="accent-[color:var(--color-accent,#7dd3a0)]" />
            Overwrite files with the same name
          </label>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button
            onClick={submit}
            disabled={busy || !picked || files.length === 0}
            className={cn("w-full rounded-md py-2 text-sm font-semibold",
              busy || !picked || files.length === 0
                ? "bg-white/10 text-muted"
                : "bg-accent text-black hover:brightness-110")}
          >
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  )
}
