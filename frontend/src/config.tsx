import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export interface AppConfig { launch_mode: string; simulated: boolean; registration_enabled: boolean; release: string }
// Until the server answers we assume the most cautious wording (simulated), never an unlabeled "real" mode.
const DEFAULT: AppConfig = { launch_mode: 'development', simulated: true, registration_enabled: true, release: 'unknown' }
const Ctx = createContext<AppConfig>(DEFAULT)

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<AppConfig>(DEFAULT)
  useEffect(() => {
    fetch('/api/config/', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null)).then((c) => c && setCfg(c)).catch(() => undefined)
  }, [])
  return <Ctx.Provider value={cfg}>{children}</Ctx.Provider>
}

export const useConfig = () => useContext(Ctx)
