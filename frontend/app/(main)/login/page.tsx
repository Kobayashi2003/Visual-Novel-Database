/** Sign-in page — where the middleware sends signed-out visitors. */
"use client"

import { Suspense } from "react"
import { useSearchParams } from "next/navigation"

import { AuthPanel } from "@/components/auth/AuthPanel"

// `next` comes back as a URL parameter, so it is attacker-controllable: only
// site-relative paths are honoured, and `//host` is rejected as that is a
// protocol-relative URL onto another origin.
function safeNext(raw: string | null): string | undefined {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return undefined
  return raw
}

function LoginForm() {
  const next = useSearchParams().get("next")
  return <AuthPanel redirectTo={safeNext(next)} />
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  )
}
