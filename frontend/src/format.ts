import { t, getLanguage, locales } from './i18n.ts'
// Times arrive as ISO strings with the demo-region offset; we display the wall-clock time
// as written by the server so the UI never silently shifts to the browser's timezone.
export const clock = (iso: string) => iso.slice(11, 16)
const monthNames = {
  ru: ['янв.', 'февр.', 'мар.', 'апр.', 'мая', 'июн.', 'июл.', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.'],
  kk: ['қаң.', 'ақп.', 'нау.', 'сәу.', 'мам.', 'мау.', 'шіл.', 'там.', 'қыр.', 'қаз.', 'қар.', 'жел.'],
}
const weekdays = { ru: ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'], kk: ['жс', 'дс', 'сс', 'ср', 'бс', 'жм', 'сб'] }
export const dayLabel = (iso: string) => {
  const date = new Date(iso.slice(0, 10) + 'T12:00:00Z')
  const lang = getLanguage()
  // Some Chromium builds lack complete Kazakh ICU data and render “M10, Wed”.
  if (lang !== 'en') return `${weekdays[lang][date.getUTCDay()]}, ${date.getUTCDate()} ${monthNames[lang][date.getUTCMonth()]}`
  return date.toLocaleDateString(locales.en, { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
}
export const sameDay = (a: string, b: string) => a.slice(0, 10) === b.slice(0, 10)
export const duration = (min: number) => t("{0} h {1} min", {0: Math.floor(min / 60), 1: String(min % 60).padStart(2, "0")})
export const money = (amount: string, currency: string) => `${currency} ${amount}`

// Searches use the transport region's calendar, independent of the passenger's device timezone.
export const regionToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Berlin' })
export const repeatSearchUrl = (origin: string, destination: string, passengers = 1) => `/?${new URLSearchParams({
  origin, destination, passengers: String(passengers), date: regionToday(), time: '06:00', repeat: '1',
})}`
