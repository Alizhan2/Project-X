import type { Language } from './i18n'
export type City = { id: string; name: Record<Language, string>; region: Record<Language, string>; aliases?: string[] }
export type PlanValues = { origin: string; destination: string; date: string; time: string; passengers: string; modes: string; time_mode: 'departure' | 'arrival'; wheelchair_required: string; max_price: string }
export type Plan = Omit<PlanValues, 'passengers' | 'wheelchair_required' | 'max_price'> & { passengers: number; wheelchair_required: boolean; max_price: string | null; id: number; note: string }
export type Sort = 'departure' | 'latest_departure' | 'price' | 'duration'
export const zone = 'Asia/Almaty'
export const localDate = (date: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
export const defaultSort = (values: PlanValues): Sort => values.time_mode === 'arrival' ? 'latest_departure' : 'departure'
export function defaults(now = new Date()): PlanValues {
  return { origin: 'kz-almaty', destination: 'kz-astana', date: localDate(new Date(now.getTime() + 86400000)), time: '06:00', passengers: '1', modes: 'bus,train', time_mode: 'departure', wheelchair_required: 'false', max_price: '' }
}
// Keep tenge values as decimal strings: Number would round large amounts and budget boundaries.
export function normalizePrice(value: string): string | null {
  const raw = value.trim().replace(',', '.')
  if (!raw) return ''
  if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(raw)) return null
  const [whole, fraction = ''] = raw.split('.')
  return `${whole.replace(/^0+(?=\d)/, '')}.${fraction.padEnd(2, '0')}`
}
const keys = ['origin', 'destination', 'date', 'time', 'passengers', 'modes', 'time_mode', 'wheelchair_required', 'max_price'] as const
export function sharePath(values: PlanValues, executed = false, sort: Sort = defaultSort(values)) {
  const params = new URLSearchParams()
  for (const key of keys) {
    if (key === 'max_price' && !values.max_price) continue
    params.set(key, key === 'max_price' ? normalizePrice(values[key]) ?? values[key] : values[key])
  }
  if (executed) { params.set('search', '1'); params.set('sort', sort) }
  return `/?${params}`
}
export function readShared(search: string, cities: City[], now = new Date()): { values: PlanValues; invalid: boolean; executed: boolean; sort: Sort } {
  const params = new URLSearchParams(search), values = defaults(now)
  let invalid = false
  for (const key of keys) {
    if (!params.has(key)) continue
    if (params.getAll(key).length !== 1) { invalid = true; continue }
    const value = params.get(key) ?? ''
    const valid = key === 'origin' || key === 'destination' ? cities.some(c => c.id === value)
      : key === 'passengers' ? /^[1-9]$/.test(value)
      : key === 'modes' ? ['bus', 'train', 'bus,train'].includes(value)
      : key === 'time_mode' ? ['departure', 'arrival'].includes(value)
      : key === 'wheelchair_required' ? ['true', 'false'].includes(value)
      : key === 'max_price' ? normalizePrice(value) !== null
      : key === 'time' ? /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
      : /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
    if (valid) {
      if (key === 'max_price') values.max_price = normalizePrice(value)!
      else if (key === 'time_mode') values.time_mode = value as PlanValues['time_mode']
      else values[key] = value
    } else invalid = true
  }
  const requestedSort = params.get('sort')
  const sort = requestedSort && ['departure', 'latest_departure', 'price', 'duration'].includes(requestedSort) ? requestedSort as Sort : defaultSort(values)
  if (requestedSort && requestedSort !== sort) invalid = true
  if (params.has('search') && params.get('search') !== '1') invalid = true
  if (params.getAll('search').length > 1 || params.getAll('sort').length > 1) invalid = true
  return { values, invalid, executed: params.get('search') === '1' && !invalid, sort }
}
export function cityMatches(city: City, query: string) {
  const normalize = (value: string) => value.trim().normalize('NFKC').toLocaleLowerCase().replaceAll('ё', 'е')
  const normalized = normalize(query)
  return [...Object.values(city.name), ...Object.values(city.region), ...(city.aliases ?? [])].some(name => normalize(name).includes(normalized))
}
