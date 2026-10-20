import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchBookings, type Booking } from '../api'
import { clock, dayLabel, money, repeatSearchUrl } from '../format'

export default function MyJourneys() {
  useLanguage()
  const [list, setList] = useState<Booking[] | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchBookings(ctrl.signal).then((r) => setList(r.results)).catch((e: unknown) => { if (!ctrl.signal.aborted) setErr(e instanceof ApiError ? e : new ApiError(t("Unexpected error."))) })
    return () => ctrl.abort()
  }, [])
  return (
    <>
      <h1>{t("My journeys")}</h1>
      {err && <p className="status-bad" role="alert">{t(err.message)}</p>}
      {!list && !err && <p>{t("Loading…")}</p>}
      {list && list.length === 0 && <div className="card empty"><p><strong>{t("No journeys yet.")}</strong></p><Link to="/">{t("Search for a journey")}</Link></div>}
      {list && list.length > 0 && (
        <ul className="result-list">
          {list.map((b) => (
            <li key={b.reference} className="card result">
              <div>
                <p><Link to={`/booking/${b.reference}`}><strong>{b.reference}</strong></Link> <span className="badge">{t(b.status_label)}</span></p>
                <p>{placeName(b.legs[0].from)} → {placeName(b.legs[b.legs.length - 1].to)}</p>
                <p className="muted">{dayLabel(b.legs[0].departs_at)} · {clock(b.legs[0].departs_at)} · {b.passengers}  {t("passenger(s)")}</p>
              </div>
              <div className="result-price"><p className="price">{money(b.total_amount, b.currency)}</p>
                <Link to={repeatSearchUrl(b.legs[0].from_code, b.legs[b.legs.length - 1].to_code, b.passengers)}>{t("Repeat journey")}</Link>
                <span className="muted small">{t("New search at current prices")}</span></div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
