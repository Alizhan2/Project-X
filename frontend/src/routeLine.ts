// Geometry for the route overview. Pure (no DOM, no i18n) so it can be unit-tested.
export interface RouteLeg {
  departs_at: string; arrives_at: string; from: string; to: string; mode: string; route_code: string; note?: string
}
export interface RouteSegment {
  kind: 'leg' | 'change'
  index: number          // leg index (for a change: the leg it follows)
  minutes: number        // leg duration, or time between arrival and the next departure
  weight: number         // relative width
}

export const minutesBetween = (a: string, b: string) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 60000))

// Widths grow with duration but sub-linearly (square root): a 12 minute taxi stays readable next to a 2 hour train.
const LEG_MIN_WEIGHT = 4
const CHANGE_MIN_WEIGHT = 1.6

export function layoutRoute(legs: RouteLeg[]): RouteSegment[] {
  const out: RouteSegment[] = []
  legs.forEach((leg, index) => {
    const minutes = minutesBetween(leg.departs_at, leg.arrives_at)
    out.push({ kind: 'leg', index, minutes, weight: Math.max(LEG_MIN_WEIGHT, Math.sqrt(minutes)) })
    const next = legs[index + 1]
    if (next) {
      const gap = minutesBetween(leg.arrives_at, next.departs_at)
      out.push({ kind: 'change', index, minutes: gap, weight: Math.max(CHANGE_MIN_WEIGHT, Math.sqrt(gap) * 0.55) })
    }
  })
  return out
}
