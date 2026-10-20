// Times arrive as ISO strings with the demo-region offset; we display the wall-clock time
// as written by the server so the UI never silently shifts to the browser's timezone.
export const clock = (iso: string) => iso.slice(11, 16)
export const dayLabel = (iso: string) =>
  new Date(iso.slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC',
  })
export const sameDay = (a: string, b: string) => a.slice(0, 10) === b.slice(0, 10)
export const duration = (min: number) => `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')} min`
export const money = (amount: string, currency: string) => `${currency} ${amount}`

// Searches use the transport region's calendar, independent of the passenger's device timezone.
export const regionToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Berlin' })
export const repeatSearchUrl = (origin: string, destination: string, passengers = 1) => `/?${new URLSearchParams({
  origin, destination, passengers: String(passengers), date: regionToday(), time: '06:00', repeat: '1',
})}`
