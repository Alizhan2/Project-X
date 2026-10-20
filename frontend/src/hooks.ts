import { useEffect, useState } from 'react'
import { ApiError, fetchItinerary, type Itinerary } from './api'

export type Load<T> =
  | { kind: 'loading' }
  | { kind: 'ready'; data: T }
  | { kind: 'error'; error: ApiError }

export function useItinerary(legs: string, passengers: string, arriveBy?: string): Load<Itinerary> {
  const [state, setState] = useState<Load<Itinerary>>({ kind: 'loading' })
  useEffect(() => {
    const ctrl = new AbortController()
    fetchItinerary(legs, passengers, ctrl.signal, arriveBy)
      .then((data) => setState({ kind: 'ready', data }))
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setState({ kind: 'error', error: e instanceof ApiError ? e : new ApiError('Unexpected error.') })
      })
    return () => ctrl.abort()
  }, [legs, passengers, arriveBy])
  return state
}

/** Current time, refreshed every second (drives the reservation countdown). */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
