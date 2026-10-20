import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchBookings, fetchSavedTravellers, removeTraveller, type Booking, type SavedTraveller } from '../api'
import { clock, dayLabel, money, repeatSearchUrl } from '../format'
import { offlineCopies, type OfflineCopy } from '../offline'

export default function MyJourneys() {
  useLanguage()
  const [list, setList] = useState<Booking[] | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [saved, setSaved] = useState<SavedTraveller[]>([])
  const [offline, setOffline] = useState<OfflineCopy[] | null>(null)
  useEffect(() => { fetchSavedTravellers().then(setSaved).catch(() => undefined) }, [])
  useEffect(() => {
    const ctrl = new AbortController()
    fetchBookings(ctrl.signal).then((r) => setList(r.results)).catch((e: unknown) => {
      if (ctrl.signal.aborted) return
      const copies = e instanceof ApiError && e.status === 0 ? offlineCopies() : []     // status 0 = server unreachable
      if (copies.length) setOffline(copies)
      else setErr(e instanceof ApiError ? e : new ApiError(t("Unexpected error.")))
    })
    return () => ctrl.abort()
  }, [])
  return (
    <>
      <h1>{t("My journeys")}</h1>
      {offline && (
        <section aria-labelledby="offline-h">
          <p className="card warn-card" role="status">{t('You are offline. These are copies saved on this device; they may be out of date.')}</p>
          <h2 id="offline-h">{t('Saved on this device')}</h2>
          <ul className="result-list">{offline.map(({ booking: b, savedAt }) => (
            <li key={b.reference} className="card result"><div>
              <p><Link to={`/booking/${b.reference}`}><strong>{b.reference}</strong></Link></p>
              <p>{placeName(b.legs[0].from)} → {placeName(b.legs[b.legs.length - 1].to)}</p>
              <p className="muted">{dayLabel(b.legs[0].departs_at)} · {clock(b.legs[0].departs_at)} · {t('Saved {0}', { 0: `${dayLabel(savedAt)} ${clock(savedAt)}` })}</p>
            </div></li>))}</ul>
        </section>
      )}
      {err && <p className="status-bad" role="alert">{t(err.message)}</p>}
      {!list && !err && !offline && <p>{t("Loading…")}</p>}
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
      {saved.length > 0 && (
        <section className="card saved-manage" aria-labelledby="saved-h">
          <h2 id="saved-h">{t('Saved travellers')}</h2>
          <p className="muted small">{t('Names are stored only if you choose to save them. They are used to fill the booking form.')}</p>
          <ul>
            {saved.map(s => (
              <li key={s.id}>{s.full_name}
                <button type="button" className="link" aria-label={t('Remove {0}', { 0: s.full_name })}
                  onClick={async () => { await removeTraveller(s.id).catch(() => undefined); setSaved(old => old.filter(x => x.id !== s.id)) }}>{t('Remove')}</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}
