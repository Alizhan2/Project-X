import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { Link, useSearchParams } from 'react-router-dom'
import LegSummary from '../components/LegSummary'
import { useItinerary } from '../hooks'
import { duration, money } from '../format'

export default function Journey() {
  useLanguage()
  const [p] = useSearchParams()
  const legs = p.get('legs') ?? '', passengers = p.get('passengers') ?? '1', seen = p.get('total')
  const arriveBy = p.get('arrive_by') || undefined
  const st = useItinerary(legs, passengers, arriveBy)
  return (
    <>
      <h1>{t("Journey details")}</h1>
      {arriveBy && <p>{t("Arrive by")} {arriveBy.replace('T', ' ')}  {t("(Europe/Berlin). Checked against the current timetable; not a punctuality guarantee.")}</p>}
      {st.kind === 'loading' && <p>{t("Loading journey…")}</p>}
      {st.kind === 'error' && (
        <div className="card" role="alert">
          <p className="status-bad">{st.error.status === 409 ? st.error.message : t("Could not load this journey.")}</p>
          <p><Link to="/">{t("Search again")}</Link></p>
        </div>
      )}
      {st.kind === 'ready' && (() => {
        const it = st.data
        const changed = seen && seen !== it.total_price
        return (
          <section className="card">
            {changed && (
              <p className="warn" role="status">
                 {t("The price changed since your search: it was")} {money(seen, it.currency)}  {t("and is now")} {money(it.total_price, it.currency)}.
              </p>
            )}
            <p className="muted">{duration(it.duration_minutes)} · {it.transfers === 0 ? t("Direct") : t("{0} transfer(s)", {0: it.transfers})} · <span className="badge">{t("Simulated data")}</span></p>
            <LegSummary it={it} />
            <p className="price-line">{t("Total for")} {it.passengers}  {t("passenger(s):")} <strong>{money(it.total_price, it.currency)}</strong></p>
            <Link className="button primary" to={`/book?${new URLSearchParams({ legs, passengers, total: it.total_price, ...(arriveBy ? { arrive_by: arriveBy } : {}) })}`}>{t("Continue to traveller details")}</Link>
          </section>
        )
      })()}
    </>
  )
}
