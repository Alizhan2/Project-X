import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { AuthContext } from './authContext'
import { clearOfflineCopies, pruneOfflineCopies } from './offline'
import { fetchMe, login as apiLogin, logout as apiLogout, register as apiRegister, type User } from './api'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchMe(ctrl.signal)
      .then((r) => setUser(r.user))
      .catch(() => undefined)
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false) })
    return () => ctrl.abort()
  }, [])

  const login = useCallback(async (e: string, p: string) => { const u = await apiLogin(e, p); pruneOfflineCopies(u.id); setUser(u) }, [])
  const register = useCallback(async (e: string, n: string, p: string) => { const u = await apiRegister(e, n, p); pruneOfflineCopies(u.id); setUser(u) }, [])
  const refresh = useCallback(async () => setUser((await fetchMe()).user), [])
  const logout = useCallback(async () => { clearOfflineCopies(); await apiLogout(); setUser(null) }, [])
  const value = useMemo(() => ({ user, loading, login, register, logout, refresh }), [user, loading, login, register, logout, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
