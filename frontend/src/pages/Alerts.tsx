import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchWatches, removeWatch, type Watch } from '../api'
import { clock, dayLabel, money } from '../format'
import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'

export default function Alerts() {
  useLanguage()
  const [data, setData] = useState<{ max_active: number; results: Watch[] } | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchWatches(ctrl.signal).then(setData).catch((e: unknown) => { if (!ctrl.signal.aborted) setErr(e instanceof ApiError ? e : new ApiError(t('Unexpected error.'))) })
    return () => ctrl.abort()
  }, [])
  const active = data?.results.filter(w => w.status === 'active').length ?? 0
  return (
    <>
      <h1>{t('Alerts')}</h1>
      {err && <p className="status-bad" role="alert">{t(err.message)}</p>}
      {!data && !err && <p>{t('Loading…')}</p>}
      {data && (
        <>
          <p className="muted">{t('You can have up to {0} active alerts.', { 0: data.max_active })} {t('Alerts only notify you. They do not hold places or prices, and everything here is simulated.')}</p>
          {data.results.length === 0 && <div className="card empty"><p><strong>{t('No alerts yet.')}</strong></p><p className="muted">{t('Search for a journey and choose "Notify me" under the results.')}</p><Link to="/">{t('Search for a journey')}</Link></div>}
          <ul className="result-list">
            {data.results.map(w => (
              <li key={w.id} className="card alert-item">
                <div>
                  <p><strong>{placeName(w.origin.name)} → {placeName(w.destination.name)}</strong> <span className={`badge alert-${w.status}`}>{t(w.status === 'active' ? 'Active' : w.status === 'triggered' ? 'Notified' : 'Date passed')}</span></p>
                  <p className="muted">{dayLabel(w.date)} · {t('Depart after')} {w.time} · {t('For {0} passenger(s)', { 0: w.passengers })}</p>
                  <p>{w.kind === 'price'
                    ? <>{t('Price drop')}: {w.baseline_price && w.currency ? t('Cheapest when you last looked: {0}', { 0: money(w.baseline_price, w.currency) }) : ''}</>
                    : t('Journey becomes available')}</p>
                  {w.last_checked_at && <p className="muted small">{t('Last checked {0}', { 0: `${dayLabel(w.last_checked_at)} ${clock(w.last_checked_at)}` })}</p>}
                </div>
                <div className="actions">
                  <Link className="button secondary" to={w.link}>{t('Open search')}</Link>
                  <button type="button" className="link" aria-label={t('Remove alert {0}', { 0: `${placeName(w.origin.name)} → ${placeName(w.destination.name)} ${dayLabel(w.date)}` })}
                    onClick={async () => { await removeWatch(w.id).catch(() => undefined); setData(d => d && ({ ...d, results: d.results.filter(x => x.id !== w.id) })) }}>{t('Remove')}</button>
                </div>
              </li>
            ))}
          </ul>
          {active === 0 && data.results.length > 0 && <p className="muted small">{t('Finished alerts stay here until you remove them.')}</p>}
        </>
      )}
    </>
  )
}
