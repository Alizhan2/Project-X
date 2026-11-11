import { useEffect, useState } from 'react'
import { request } from '../api'
import { t, locales } from '../i18n'
import { useLanguage } from '../useLanguage'

import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../authContext'
import KazakhstanPlanner from '../components/KazakhstanPlanner'
import { zone, localDate, cityMatches, type City } from '../kazakhstan'
import UpcomingJourney from '../components/UpcomingJourney'
type Catalog = { cities: City[]; currency: string; timezone: string; simulated?: boolean; geography?: { url: string; as_of: string; city_count: number } }

export default function Kazakhstan() {
  const language = useLanguage()
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [now, setNow] = useState(() => new Date())
  const [directoryQuery, setDirectoryQuery] = useState('')
  const [region, setRegion] = useState('')
  const location = useLocation()
  const { user } = useAuth()
  useEffect(() => {
    const controller = new AbortController()
    request<Catalog>('GET', '/api/kazakhstan/catalog/', undefined, { signal: controller.signal })
      .then(setCatalog).catch(() => { if (!controller.signal.aborted) setLoadError(true) })
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [])
  useEffect(() => {
    if (location.hash === '#my-plans' && catalog && user) document.getElementById('my-plans')?.scrollIntoView()
  }, [location.hash, catalog, user])
  return <section className="kazakhstan">
    <header className="kz-heading">
      <div><h1>Doedu Kazakhstan</h1><p>{t('Plan your journey across Kazakhstan.')}</p></div>
      <div className="kz-clock"><strong>{new Intl.DateTimeFormat(locales[language], { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)}</strong><span>{t('Kazakhstan time')} · UTC+5</span><span>{t('Currency')}: ₸ · KZT</span></div>
    </header>
    <p className="muted">{t("Real cities · saved plans · KZT · Kazakhstan time")}</p>
    <aside className="kz-notice"><h2>{t(catalog?.simulated ? 'Kazakhstan booking demo' : 'Real ticket sales are not yet available.')}</h2><p>{t(catalog?.simulated ? 'The cities are real. Routes, departure times, prices, seats, payments and confirmations are simulated. No real ticket is issued.' : 'We are preparing a connection to 1TR.kz. City names are real; schedules, prices and available seats have not been supplied yet.')}</p></aside>
    {loadError && <p role="alert">{t('Could not load the city directory. Reload the page to try again.')}</p>}
    {!catalog && !loadError && <p role="status">{t('Loading…')}</p>}
    {catalog && <>
      {catalog.simulated && <UpcomingJourney />}
      <KazakhstanPlanner key={`${user?.id ?? "guest"}:${location.search}`} cities={catalog.cities} search={location.search} today={localDate(now)} demo={catalog.simulated ?? false} />
      <section aria-labelledby="kz-directory-heading">
        <h2 id="kz-directory-heading">{t('Cities and regions')}</h2><p className="muted">{t('{0} cities of Kazakhstan. The directory does not indicate real ticket availability.', { 0: catalog.cities.length })}</p>
        {catalog.geography && <p className="small muted"><a href={catalog.geography.url} target="_blank" rel="noopener noreferrer">{t('Official KATO directory')}</a> · {t('Updated {0}', { 0: catalog.geography.as_of })}</p>}
        <div className="search-form">
          <label className="field">{t('Find a city')}<input type="search" value={directoryQuery} onChange={e => setDirectoryQuery(e.target.value)} placeholder={t('City or region in any of three languages')} /></label>
          <label className="field">{t('Region')}<select value={region} onChange={e => setRegion(e.target.value)}><option value="">{t('All regions')}</option>{[...new Map(catalog.cities.map(city => [city.region.en, city.region])).entries()].sort((a, b) => a[1][language].localeCompare(b[1][language], locales[language])).map(([key, names]) => <option key={key} value={key}>{names[language]}</option>)}</select></label>
        </div>
        {(() => {
          const shown = catalog.cities.filter(city => (!region || city.region.en === region) && cityMatches(city, directoryQuery))
          return <><p role="status" className="small muted">{t('{0} matching cities.', { 0: shown.length })}</p>{!shown.length && <p>{t('Try another spelling or select All regions.')}</p>}<ul className="kz-cities">{shown.map(city => <li key={city.id}><strong>{city.name[language]}</strong><span>{city.region[language]}</span></li>)}</ul></>
        })()}
      </section>
      <p className="small"><Link to="/demo">{t('Other demo scenarios (fictional region, EUR)')}</Link></p>
    </>}
  </section>
}
