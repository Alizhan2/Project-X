import { useEffect, useState } from 'react'
import { request } from '../api'
import { t, locales } from '../i18n'
import { useLanguage } from '../useLanguage'

import { useLocation } from 'react-router-dom'
import { useAuth } from '../authContext'
import KazakhstanPlanner from '../components/KazakhstanPlanner'
import { zone, localDate, type City } from '../kazakhstan'
type Catalog = { cities: City[]; currency: string; timezone: string }

export default function Kazakhstan() {
  const language = useLanguage()
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [now, setNow] = useState(() => new Date())
  const location = useLocation()
  const { user } = useAuth()
  useEffect(() => {
    const controller = new AbortController()
    request<Catalog>('GET', '/api/kazakhstan/catalog/', undefined, { signal: controller.signal })
      .then(setCatalog).catch(() => { if (!controller.signal.aborted) setLoadError(true) })
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [])
  return <section className="kazakhstan">
    <header className="kz-heading">
      <div><h1>Doedu Kazakhstan</h1><p>{t('Plan your journey across Kazakhstan.')}</p></div>
      <div className="kz-clock"><strong>{new Intl.DateTimeFormat(locales[language], { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)}</strong><span>{t('Kazakhstan time')} · UTC+5</span><span>{t('Currency')}: ₸ · KZT</span></div>
    </header>
    <aside className="kz-notice"><h2>{t('Real ticket sales are not yet available.')}</h2><p>{t('We are preparing a connection to 1TR.kz. City names are real; schedules, prices and available seats have not been supplied yet.')}</p></aside>
    {loadError && <p role="alert">{t('Could not load the city directory. Reload the page to try again.')}</p>}
    {!catalog && !loadError && <p role="status">{t('Loading…')}</p>}
    {catalog && <>
      <KazakhstanPlanner key={`${user?.id ?? "guest"}:${location.search}`} cities={catalog.cities} search={location.search} today={localDate(now)} />
      <h2>{t('Cities and regions')}</h2><p className="muted">{t('20 cities: regional centres and cities of republican significance. This directory does not indicate ticket availability.')}</p>
      <ul className="kz-cities">{catalog.cities.map(city => <li key={city.id}><strong>{city.name[language]}</strong><span>{city.region[language]}</span></li>)}</ul>
    </>}
  </section>
}
