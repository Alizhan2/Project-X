import type { Booking } from './api'

// Offline copies of confirmed, upcoming bookings so a traveller can still see their plan without a connection.
// Privacy: stored only on this device in localStorage; contact e-mail, payment attempts, refunds and the activity log
// are NOT kept; everything is deleted on sign-out and replaced when a different account signs in.
const KEY = 'doedu.offline.v1'
const MAX_COPIES = 5
const KEEP_AFTER_ARRIVAL_MS = 24 * 3600 * 1000

export interface OfflineCopy { savedAt: string; booking: Booking }
interface Store { userId: number; items: OfflineCopy[] }

function read(): Store | null {
  try { const raw = localStorage.getItem(KEY); return raw ? (JSON.parse(raw) as Store) : null } catch { return null }
}
function write(store: Store | null) {
  try { if (store && store.items.length) localStorage.setItem(KEY, JSON.stringify(store)); else localStorage.removeItem(KEY) } catch { /* Storage may be unavailable: offline copies are a convenience. */ }
}

export function saveOfflineCopy(userId: number, booking: Booking, now = Date.now()) {
  const store = read()
  const current = store && store.userId === userId ? store : { userId, items: [] as OfflineCopy[] }
  const others = current.items.filter(i => i.booking.reference !== booking.reference)
  const last = booking.legs.filter(l => l.status === 'booked').at(-1)
  const keep = booking.status === 'confirmed' && last !== undefined && Date.parse(last.arrives_at) + KEEP_AFTER_ARRIVAL_MS > now
  const safe: Booking = { ...booking, contact_email: '', payments: [], refunds: [], activity: undefined }
  write({ userId, items: keep ? [{ savedAt: new Date(now).toISOString(), booking: safe }, ...others].slice(0, MAX_COPIES) : others })
}

export const offlineCopies = (): OfflineCopy[] => read()?.items ?? []
export const getOfflineCopy = (reference: string) => offlineCopies().find(i => i.booking.reference === reference)
export const clearOfflineCopies = () => write(null)
/** Signing in as a different account must never reveal the previous account's copies. */
export function pruneOfflineCopies(userId: number) { const s = read(); if (s && s.userId !== userId) write(null) }
