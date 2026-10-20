import { useEffect, useState, type ReactNode } from 'react'
import { ConfigContext, DEFAULT_CONFIG, type AppConfig } from './configContext'

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<AppConfig>(DEFAULT_CONFIG)
  useEffect(() => {
    fetch('/api/config/', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null)).then((c) => c && setCfg(c)).catch(() => undefined)
  }, [])
  return <ConfigContext.Provider value={cfg}>{children}</ConfigContext.Provider>
}
