import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { NotificationsContext } from './notificationsContext'
import { fetchNotifications, markAllRead, markRead, type AppNotification } from './api'
import { useAuth } from './authContext'

const POLL_MS = 15000 // polling, not websockets: simplest thing that works for the MVP

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [state, setState] = useState<{ unread: number; items: AppNotification[] }>({ unread: 0, items: [] })
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    if (!user) return
    const ctrl = new AbortController()
    const load = () => fetchNotifications(ctrl.signal).then((r) => setState({ unread: r.unread, items: r.results })).catch(() => undefined)
    load()
    const id = setInterval(load, POLL_MS)
    return () => { ctrl.abort(); clearInterval(id) }
  }, [user, tick])

  const read = useCallback(async (id: number) => { await markRead(id); refresh() }, [refresh])
  const readAll = useCallback(async () => { await markAllRead(); refresh() }, [refresh])
  const value = useMemo(() => ({ ...(user ? state : { unread: 0, items: [] }), refresh, read, readAll }), [user, state, refresh, read, readAll])
  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
}
