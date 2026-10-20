import messages from './messages.json' with { type: 'json' }
export type Language = 'en' | 'ru' | 'kk'
export const languages: Language[] = ['en', 'ru', 'kk']
export const localeNames = { en: 'English', ru: 'Русский', kk: 'Қазақша' }
export const locales = { en: 'en-GB', ru: 'ru-RU', kk: 'kk-KZ' }
const supported = (value: string | null): Language | undefined => {
  const base = value?.toLowerCase().split('-')[0]
  return languages.includes(base as Language) ? base as Language : undefined
}
function initialLanguage(): Language {
  if (typeof window === 'undefined') return 'en'
  const linkLanguage = supported(new URLSearchParams(window.location.search).get('lang'))
  if (linkLanguage) {
    try { localStorage.setItem('doedu.language', linkLanguage) } catch { /* Storage may be unavailable. */ }
    return linkLanguage
  }
  try { const saved = supported(localStorage.getItem('doedu.language')); if (saved) return saved } catch { /* Storage may be unavailable. */ }
  return navigator.languages.map(supported).find(Boolean) ?? 'en'
}
let language: Language = initialLanguage()
const listeners = new Set<() => void>()
export const getLanguage = () => language
export const subscribeLanguage = (callback: () => void) => { listeners.add(callback); return () => { listeners.delete(callback) } }
export function setLanguage(next: Language) {
  if (!languages.includes(next)) return
  language = next
  try { localStorage.setItem('doedu.language', next) } catch { /* Private browsers may deny storage. */ }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = next
    document.title = t('Doedu — multimodal journeys')
    const url = new URL(window.location.href)
    if (url.searchParams.has('lang')) { url.searchParams.set('lang', next); window.history.replaceState(window.history.state, '', url) }
  }
  listeners.forEach(listener => listener())
}
if (typeof document !== 'undefined') document.documentElement.lang = language
const catalog: Record<string, { ru: string; kk: string }> = messages
// Match only authored message templates. User names, IDs and codes are never globally rewritten.
const escapePattern = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const patterns = Object.entries(catalog).flatMap(([source, translations]) =>
  [source, translations.ru, translations.kk].filter(value => /\{\w+\}/.test(value)).map(value => {
    const keys: string[] = []
    const parts = value.split(/(\{\w+\})/g).map(part => {
      if (/^\{\w+\}$/.test(part)) { keys.push(part.slice(1, -1)); return '(.+?)' }
      return escapePattern(part)
    })
    return { source, keys, specificity: value.replace(/\{\w+\}/g, '').length, pattern: new RegExp('^' + parts.join('') + '$', 's') }
  })).sort((a, b) => b.specificity - a.specificity)
const canonical = new Map(Object.entries(catalog).flatMap(([source, v]) => [[v.ru, source], [v.kk, source]] as [string, string][]))
export function t(source: string, values: Record<string, unknown> = {}, depth = 0): string {
  let key = catalog[source] ? source : canonical.get(source) ?? source
  let params = values
  if (!(key in catalog) && depth < 4) {
    for (const entry of patterns) {
      const match = entry.pattern.exec(source)
      if (match) { key = entry.source; params = Object.fromEntries(entry.keys.map((name, i) => [name, t(match[i + 1], {}, depth + 1)])); break }
    }
  }
  const translated = language === 'en' ? key : catalog[key]?.[language] ?? key
  return translated.replace(/\{(\w+)\}/g, (match, name: string) => name in params ? String(params[name]) : match)
}

// Only synthetic seed names have translations. Operator-authored names stay intact.
export const placeName = (name: string) => language === 'en' ? name : catalog[`place:${name}`]?.[language] ?? name
if (typeof document !== 'undefined') document.title = t('Doedu — multimodal journeys')
