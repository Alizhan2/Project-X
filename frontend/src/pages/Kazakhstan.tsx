import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, request } from '../api'
import { t, locales, type Language } from '../i18n'
import { useLanguage } from '../useLanguage'

type City = { id: string; name: Record<Language, string>; region: Record<Language, string> }
type Catalog = { cities: City[]; currency: string; timezone: string }
const zone = 'Asia/Almaty'
const localDate = (date: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)

export default function Kazakhstan() {
  const language = useLanguage()
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [now, setNow] = useState(() => new Date())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const searchController = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    request<Catalog>('GET', '/api/kazakhstan/catalog/', undefined, { signal: controller.signal })
      .then(setCatalog).catch(() => { if (!controller.signal.aborted) setLoadError(true) })
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => { controller.abort(); searchController.current?.abort(); clearInterval(timer) }
  }, [])
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    const params = new URLSearchParams(Array.from(values.entries(), ([key, value]) => [key, String(value)]))
    searchController.current?.abort()
    const controller = new AbortController()
    searchController.current = controller
    setBusy(true); setMessage(''); setFields({})
    try {
      await request('GET', `/api/kazakhstan/search/?${params}`, undefined, { signal: controller.signal })
      // Offer display and booking require a certified provider adapter, not just a successful HTTP response.
      setMessage('Real ticket sales are not yet available.')
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof ApiError) {
        setFields(error.fields)
        setMessage(error.code === 'provider_not_connected'
          ? 'Real ticket search is awaiting provider access. No prices or availability have been checked.' : error.message)
      } else setMessage('Could not reach the server. Check your connection and try again.')
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }
  const errorFor = (name: string) => fields[name] ? <span className="field-error" id={`kz-${name}-error`}>{t(fields[name])}</span> : null
  const fieldProps = (name: string) => ({ 'aria-invalid': !!fields[name], 'aria-describedby': fields[name] ? `kz-${name}-error` : undefined })
  return <section className="kazakhstan">
    <header className="kz-heading">
      <div><h1>Doedu Kazakhstan</h1><p>{t('Plan your journey across Kazakhstan.')}</p></div>
      <div className="kz-clock"><strong>{new Intl.DateTimeFormat(locales[language], { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)}</strong><span>{t('Kazakhstan time')} · UTC+5</span><span>{t('Currency')}: ₸ · KZT</span></div>
    </header>
    <aside className="kz-notice"><h2>{t('Real ticket sales are not yet available.')}</h2><p>{t('We are preparing a connection to 1TR.kz. City names are real; schedules, prices and available seats have not been supplied yet.')}</p></aside>
    {loadError && <p role="alert">{t('Could not load the city directory. Reload the page to try again.')}</p>}
    {!catalog && !loadError && <p role="status">{t('Loading…')}</p>}
    {catalog && <>
      <form className="card search-form" onSubmit={search} aria-label={t('Kazakhstan journey search')}>
        {(['origin', 'destination'] as const).map((name, index) => <label className="field" key={name}>{t(index === 0 ? 'From' : 'To')}
          <select name={name} defaultValue={index === 0 ? 'kz-almaty' : 'kz-astana'} {...fieldProps(name)}>
            {catalog.cities.map(city => <option value={city.id} key={city.id}>{city.name[language]} — {city.region[language]}</option>)}
          </select>{errorFor(name)}</label>)}
        <label className="field">{t('Transport')}<select name="modes" defaultValue="bus,train"><option value="bus,train">{t('Bus and train')}</option><option value="bus">{t('Bus')}</option><option value="train">{t('Train')}</option></select></label>
        <label className="field">{t('Date')}<input name="date" type="date" required defaultValue={localDate(new Date(now.getTime() + 86_400_000))} min={localDate(now)} {...fieldProps('date')} />{errorFor('date')}</label>
        <label className="field">{t('Departure time (UTC+5)')}<input name="time" type="time" required defaultValue="06:00" {...fieldProps('time')} />{errorFor('time')}</label>
        <label className="field">{t('Passengers')}<input name="passengers" type="number" min="1" max="9" required defaultValue="1" {...fieldProps('passengers')} />{errorFor('passengers')}</label>
        <p className="muted small">{t('Search is not connected yet. No reservation or payment will be made.')}</p>
        <button className="primary" disabled={busy}>{t(busy ? 'Searching…' : 'Check search availability')}</button>
      </form>
      {message && <p className="kz-notice" role="status">{t(message)}</p>}
      <h2>{t('Cities and regions')}</h2><p className="muted">{t('20 cities: regional centres and cities of republican significance. This directory does not indicate ticket availability.')}</p>
      <ul className="kz-cities">{catalog.cities.map(city => <li key={city.id}><strong>{city.name[language]}</strong><span>{city.region[language]}</span></li>)}</ul>
    </>}
  </section>
}
