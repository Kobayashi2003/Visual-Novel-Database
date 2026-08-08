/** Auth state and login/register/logout actions, backed by the userserve API. */
"use client"

import { createContext, useContext, useState, useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import type { User, SexualLevel, ViolenceLevel, ImageSource, VNCharacterLayout } from "@/lib/types"
import { api, setSessionExpiredHandler, refreshAccessToken } from "@/lib/api"

interface UserContextType {
  user: User | null
  isLoading: boolean
  defaultSexualLevel: SexualLevel
  defaultViolenceLevel: ViolenceLevel
  imageSource: ImageSource
  vnCharacterLayout: VNCharacterLayout
  register: (username: string, email: string, password: string, code: string, invitationCode: string, redirectTo?: string) => Promise<void>
  login: (username: string, password: string, redirectTo?: string) => Promise<void>
  logout: () => Promise<void>
  changeEmail: (newEmail: string, code: string, password: string) => Promise<void>
  deleteAccount: (password: string) => Promise<void>
  updateDefaultSexualLevel: (v: SexualLevel) => void
  updateDefaultViolenceLevel: (v: ViolenceLevel) => void
  updateImageSource: (v: ImageSource) => void
  updateVNCharacterLayout: (v: VNCharacterLayout) => void
}

const UserContext = createContext<UserContextType | undefined>(undefined)

// Full navigation, not a client-side push, so every provider and cached fetch is
// rebuilt for the new session. `redirectTo` already carries the basePath.
const navigateAfterAuth = (redirectTo?: string) => {
  if (redirectTo) window.location.assign(redirectTo)
  else window.location.reload()
}

export function useUserContext() {
  const context = useContext(UserContext)
  if (context === undefined) throw new Error("useUserContext must be used within a UserProvider")
  return context
}

export function UserProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [defaultSexualLevel, setDefaultSexualLevel] = useState<SexualLevel>(
    () => (typeof window !== "undefined" ? (localStorage.getItem("defaultSexualLevel") as SexualLevel) || "safe" : "safe")
  )
  const [defaultViolenceLevel, setDefaultViolenceLevel] = useState<ViolenceLevel>(
    () => (typeof window !== "undefined" ? (localStorage.getItem("defaultViolenceLevel") as ViolenceLevel) || "tame" : "tame")
  )
  const [imageSource, setImageSource] = useState<ImageSource>(
    () => (typeof window !== "undefined" ? (localStorage.getItem("imageSource") as ImageSource) || "imgserve" : "imgserve")
  )
  const [vnCharacterLayout, setVNCharacterLayout] = useState<VNCharacterLayout>(
    () => (typeof window !== "undefined" ? (localStorage.getItem("vnCharacterLayout") as VNCharacterLayout) || "grid" : "grid")
  )

  const updateDefaultSexualLevel = (v: SexualLevel) => {
    localStorage.setItem("defaultSexualLevel", v)
    setDefaultSexualLevel(v)
  }
  const updateDefaultViolenceLevel = (v: ViolenceLevel) => {
    localStorage.setItem("defaultViolenceLevel", v)
    setDefaultViolenceLevel(v)
  }
  // Read at image-fetch time by `convertToImgserveUrl`; already-loaded images
  // keep their URLs until the next fetch/navigation.
  const updateImageSource = (v: ImageSource) => {
    localStorage.setItem("imageSource", v)
    setImageSource(v)
  }
  // Picks the VN page's Characters layout (grid vs. one-card-at-a-time slider).
  const updateVNCharacterLayout = (v: VNCharacterLayout) => {
    localStorage.setItem("vnCharacterLayout", v)
    setVNCharacterLayout(v)
  }

  // A session that dies while the page is open: the proxy only runs on
  // navigation, so without this the user would sit on a page whose every request
  // now 401s. Send them to the sign-in panel instead of leaving errors on screen.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null)
      if (pathname === "/login") return
      // `next` is consumed by a plain location.assign, so it needs the basePath
      // that `pathname` (router-relative) has stripped off.
      const here = window.location.pathname + window.location.search
      router.replace(`/login?next=${encodeURIComponent(here)}`)
    })
  }, [router, pathname])

  // Re-establish the session on mount. `/me` is the only authority on whether
  // someone is signed in; a 401 here simply means they are not.
  useEffect(() => {
    const initializeUser = async () => {
      try {
        setUser(await api.user.me())
      } catch {
        setUser(null)
      }
      setIsLoading(false)
    }
    initializeUser()
  }, [])

  // Renew the access cookie ahead of expiry: `<img>` / `<audio>` fetch through
  // the same edge gate and get a bare 401 they cannot retry. Must stay below the
  // backend's JWT_ACCESS_TOKEN_MINUTES (default 30).
  useEffect(() => {
    if (!user) return
    const REFRESH_INTERVAL_MS = 20 * 60 * 1000
    let lastRefresh = Date.now()
    const renew = () => { lastRefresh = Date.now(); refreshAccessToken() }

    const interval = setInterval(renew, REFRESH_INTERVAL_MS)
    // Hidden tabs throttle timers, so renew on the way back too — but only if
    // the cookie is actually getting stale. Without the elapsed check, flicking
    // between tabs would hammer /refresh (rate-limited to 30/min) and rotate the
    // cookie every time.
    const onVisible = () => {
      if (document.visibilityState !== "visible") return
      if (Date.now() - lastRefresh >= REFRESH_INTERVAL_MS) renew()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      clearInterval(interval)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [user])

  // The server sets the auth cookies on these responses; the navigation that
  // follows re-mounts the tree, and that fresh mount is what loads the user via
  // `/me`. Fetching or storing the user here would only be thrown away.
  const register = async (username: string, email: string, password: string, code: string, invitationCode: string, redirectTo?: string) => {
    await api.user.register(username, email, password, code, invitationCode)
    navigateAfterAuth(redirectTo)
  }

  const login = async (username: string, password: string, redirectTo?: string) => {
    await api.user.login(username, password)
    navigateAfterAuth(redirectTo)
  }

  const logout = async () => {
    try {
      await api.user.logout()
    } catch {
      // Best-effort server-side revoke; drop the local session regardless.
    }
    setUser(null)
    window.location.reload()
  }

  // Rebind the account email. The session itself is unaffected (the user id
  // never changes), so only the cached user object is patched in place.
  const changeEmail = async (newEmail: string, code: string, password: string) => {
    const response = await api.user.changeEmail(newEmail, code, password)
    setUser((u) => (u ? { ...u, email: response.email } : u))
  }

  // Permanently remove the account. The backend verifies `password` and clears
  // the auth cookies on success; the page is reloaded so every Server Component
  // re-renders for the (now signed-out) session.
  const deleteAccount = async (password: string) => {
    if (!user) throw new Error("Not signed in")
    await api.user.deleteAccount(user.username, password)
    setUser(null)
    window.location.reload()
  }

  return (
    <UserContext.Provider value={{ user, register, login, logout, changeEmail, deleteAccount, isLoading, defaultSexualLevel, defaultViolenceLevel, imageSource, vnCharacterLayout, updateDefaultSexualLevel, updateDefaultViolenceLevel, updateImageSource, updateVNCharacterLayout }}>
      {children}
    </UserContext.Provider>
  )
}
