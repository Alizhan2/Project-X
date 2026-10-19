// The seed command defines "today" in the demo timezone (Europe/Berlin), not the machine's timezone.
// Demo day = that date + 1. Returns a Date at noon UTC so formatting with timeZone:'UTC' is stable.
export function demoDay(): Date {
  const [y, m, d] = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Berlin' }).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + 1, 12))
}
export const demoDayIso = () => demoDay().toISOString().slice(0, 10)
export const demoDayLabel = () => demoDay().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
