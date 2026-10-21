import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchFollows, fetchWatches, removeWatch, unfollowLine, type LineFollow, type Watch } from '../api'
import { clock, dayLabel, money } from '../format'
import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'

export default function Alerts() {
  useLanguage()
  const [data, setData] = useState<{ max_active: number; results: Watch[] } | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [follows, setFollows] = useState<{ max_follows: number; results: LineFollow[] } | null>(null)
  useEffect(() => { fetchFollows().then(setFollows).catch(() => undefined) }, [])
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
          <h2>{t('Journey alerts')}</h2>
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

          <section aria-labelledby="followed-h" className="followed-lines">
            <h2 id="followed-h">{t('Followed lines')}</h2>
            {follows && follows.results.length === 0 && <p className="muted">{t('No followed lines yet. Open a journey and choose "Follow" for a line.')}</p>}
            {follows && follows.results.length > 0 && (
              <ul className="result-list">
                {follows.results.map(f => (
                  <li key={f.id} className="card alert-item">
                    <div><p><strong>{f.route_code}</strong> · {f.operator}</p><p className="muted">{placeName(f.from)} → {placeName(f.to)}</p></div>
                    <button type="button" className="link" aria-label={t('Unfollow {0}', { 0: f.route_code })}
                      onClick={async () => { await unfollowLine(f.id).catch(() => undefined); setFollows(x => x && ({ ...x, results: x.results.filter(y => y.id !== f.id) })) }}>{t('Unfollow')}</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  )
}
