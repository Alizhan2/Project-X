import type { Language } from './i18n'
export type City = { id: string; name: Record<Language, string>; region: Record<Language, string> }
export type PlanValues = { origin: string; destination: string; date: string; time: string; passengers: string; modes: string }
export type Plan = Omit<PlanValues, 'passengers'> & { passengers: number; id: number; note: string }
export const zone = 'Asia/Almaty'
export const localDate = (date: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
export function defaults(now = new Date()): PlanValues {
  return { origin: 'kz-almaty', destination: 'kz-astana', date: localDate(new Date(now.getTime() + 86400000)), time: '06:00', passengers: '1', modes: 'bus,train' }
}
const keys = ['origin', 'destination', 'date', 'time', 'passengers', 'modes'] as const
export function sharePath(values: PlanValues) {
  const params = new URLSearchParams()
  for (const key of keys) params.set(key, values[key])
  return `/kazakhstan?${params}`
}
export function readShared(search: string, cities: City[], now = new Date()): { values: PlanValues; invalid: boolean } {
  const params = new URLSearchParams(search), values = defaults(now)
  let invalid = false
  for (const key of keys) {
    if (!params.has(key)) continue
    const value = params.get(key) ?? ''
    const valid = key === 'origin' || key === 'destination' ? cities.some(c => c.id === value)
      : key === 'passengers' ? /^[1-9]$/.test(value)
      : key === 'modes' ? ['bus', 'train', 'bus,train'].includes(value)
      : key === 'time' ? /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
      : /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
    if (valid) values[key] = value
    else invalid = true
  }
  return { values, invalid }
}
export function cityMatches(city: City, query: string) {
  const normalized = query.trim().normalize('NFKC').toLocaleLowerCase()
  return [...Object.values(city.name), ...Object.values(city.region)].some(name => name.normalize('NFKC').toLocaleLowerCase().includes(normalized))
}
