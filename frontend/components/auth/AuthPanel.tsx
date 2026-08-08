/** Glassy sign-in / sign-up card — the whole of `/login`. */
"use client"

import { useEffect, useState } from "react"
import { motion } from "motion/react"
import { ArrowRight, Eye, EyeOff, KeyRound, Loader2, Lock, Mail, Ticket, User } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { validateUsername, validateEmail, validatePassword, PASSWORD_MIN_LENGTH } from "@/lib/validation"
import { useUserContext } from "@/context/UserContext"

// Shared styling for the auth inputs; `pl-10` leaves room for a leading icon,
// and callers add the right padding (`pr-3`, or `pr-10` when there's a trailing
// control like the password eye).
const AUTH_INPUT = "w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 text-sm text-white outline-none transition-colors placeholder:text-muted/50 focus:border-accent/60 focus:bg-white/[0.07]"

function AuthField({ icon: Icon, ...props }: { icon: React.ComponentType<{ className?: string }> } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="relative">
      <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/60" />
      <input {...props} className={cn(AUTH_INPUT, "pr-3")} />
    </div>
  )
}

function AuthPasswordField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/60" />
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(AUTH_INPUT, "pr-10")}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setShow(s => !s)}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted/60 transition-colors hover:text-white"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  )
}

export function AuthPanel({ redirectTo }: {
  /** Where to land after a successful submit; the context reloads in place
   *  when omitted. Must already include the basePath. */
  redirectTo?: string
}) {
  const { login, register } = useUserContext()
  const [mode, setMode] = useState<"login" | "register">("login")

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [invitationCode, setInvitationCode] = useState("")

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [codeSending, setCodeSending] = useState(false)
  const [codeNotice, setCodeNotice] = useState("")
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  const switchMode = (m: "login" | "register") => { setMode(m); setError(""); setCodeNotice("") }

  const handleSendCode = async () => {
    const emailError = validateEmail(email)
    if (emailError) { setError(emailError); return }
    setError(""); setCodeNotice(""); setCodeSending(true)
    try {
      await api.user.sendVerificationCode(email)
      setCodeNotice("Code sent — check your email.")
      setCooldown(60)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send the code.")
    } finally {
      setCodeSending(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    try {
      if (mode === "login") {
        setLoading(true)
        await login(username, password, redirectTo)
      } else {
        if (!invitationCode.trim()) { setError("Enter your invitation code."); return }
        const ue = validateUsername(username); if (ue) { setError(ue); return }
        const ee = validateEmail(email); if (ee) { setError(ee); return }
        if (!code.trim()) { setError("Enter the verification code from your email."); return }
        const pe = validatePassword(password); if (pe) { setError(pe); return }
        if (password !== confirmPassword) { setError("Passwords do not match."); return }
        setLoading(true)
        await register(username, email, password, code, invitationCode, redirectTo)
      }
      // On success the context navigates away; nothing more to do here.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.")
      setLoading(false)
    }
  }

  const sendLabel = cooldown > 0 ? `${cooldown}s` : codeSending ? "…" : "Send"

  return (
    <div className="relative flex min-h-screen flex-1 items-center justify-center overflow-hidden px-4 py-16">
      <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-[480px] w-[480px] max-w-[120vw] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/20 blur-[140px]" />

      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-sm rounded-3xl border border-white/10 bg-white/[0.04] p-7 shadow-2xl shadow-black/50 backdrop-blur-xl"
      >
        <div className="mb-6 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-white/50">Visual Novel Database</p>
          <h1 className="mt-1 bg-linear-to-br from-white to-white/70 bg-clip-text text-3xl font-black tracking-tight text-transparent">VNDB</h1>
        </div>

        {/* Mode toggle */}
        <div className="mb-6 flex rounded-full border border-white/10 bg-white/5 p-1">
          {(["login", "register"] as const).map(m => (
            <button key={m} type="button" onClick={() => switchMode(m)} className="relative flex-1 rounded-full px-4 py-2 text-sm font-semibold transition-colors">
              {mode === m && <motion.span layoutId="auth-pill" className="absolute inset-0 rounded-full bg-accent" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
              <span className={cn("relative z-10", mode === m ? "text-black" : "text-muted hover:text-white")}>{m === "login" ? "Sign in" : "Sign up"}</span>
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          {/* Fields fade in when the mode changes (re-keyed). */}
          <motion.div key={mode} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="flex flex-col gap-3">
            {mode === "register" && (
              <AuthField icon={Ticket} value={invitationCode} onChange={e => setInvitationCode(e.target.value)} placeholder="Invitation code" />
            )}
            <AuthField icon={User} value={username} onChange={e => setUsername(e.target.value)} placeholder={mode === "login" ? "Username or email" : "Username"} autoComplete="username" />
            {mode === "register" && (
              <AuthField icon={Mail} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" autoComplete="email" />
            )}
            {mode === "register" && (
              <div className="flex flex-col gap-1">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/60" />
                    <input
                      inputMode="numeric"
                      maxLength={6}
                      value={code}
                      onChange={e => setCode(e.target.value)}
                      placeholder="6-digit code"
                      className={cn(AUTH_INPUT, "pr-3")}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={codeSending || cooldown > 0}
                    className="shrink-0 rounded-xl border border-white/10 bg-white/5 px-4 text-xs font-semibold text-white transition-colors hover:bg-white/10 disabled:opacity-40"
                  >
                    {sendLabel}
                  </button>
                </div>
                {codeNotice && <p className="px-1 text-xs text-accent">{codeNotice}</p>}
              </div>
            )}
            <AuthPasswordField value={password} onChange={setPassword} placeholder={mode === "login" ? "Password" : `Password (${PASSWORD_MIN_LENGTH}+ characters)`} />
            {mode === "register" && (
              <AuthPasswordField value={confirmPassword} onChange={setConfirmPassword} placeholder="Confirm password" />
            )}
          </motion.div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 flex items-center justify-center gap-2 rounded-full bg-accent py-2.5 text-sm font-bold text-black transition-colors hover:bg-accent-hover disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
            {loading ? (mode === "login" ? "Signing in…" : "Creating account…") : (mode === "login" ? "Sign in" : "Create account")}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-muted">
          {mode === "login" ? "New here? " : "Already have an account? "}
          <button type="button" onClick={() => switchMode(mode === "login" ? "register" : "login")} className="font-semibold text-white hover:text-accent">
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
      </motion.div>
    </div>
  )
}
