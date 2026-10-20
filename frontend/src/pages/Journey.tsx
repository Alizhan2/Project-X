import { Link, useSearchParams } from 'react-router-dom'
import LegSummary from '../components/LegSummary'
import { useItinerary } from '../hooks'
import { duration, money } from '../format'

export default function Journey() {
  const [p] = useSearchParams()
  const legs = p.get('legs') ?? '', passengers = p.get('passengers') ?? '1', seen = p.get('total')
  const arriveBy = p.get('arrive_by') || undefined
  const st = useItinerary(legs, passengers, arriveBy)
  return (
    <>
      <h1>Journey details</h1>
      {arriveBy && <p>Arrive by {arriveBy.replace('T', ' ')} (Europe/Berlin). Checked against the current timetable; not a punctuality guarantee.</p>}
      {st.kind === 'loading' && <p>Loading journey…</p>}
      {st.kind === 'error' && (
        <div className="card" role="alert">
          <p className="status-bad">{st.error.status === 409 ? st.error.message : 'Could not load this journey.'}</p>
          <p><Link to="/">Search again</Link></p>
        </div>
      )}
      {st.kind === 'ready' && (() => {
        const it = st.data
        const changed = seen && seen !== it.total_price
        return (
          <section className="card">
            {changed && (
              <p className="warn" role="status">
                The price changed since your search: it was {money(seen, it.currency)} and is now {money(it.total_price, it.currency)}.
              </p>
            )}
            <p className="muted">{duration(it.duration_minutes)} · {it.transfers === 0 ? 'Direct' : `${it.transfers} transfer(s)`} · <span className="badge">Simulated data</span></p>
            <LegSummary it={it} />
            <p className="price-line">Total for {it.passengers} passenger(s): <strong>{money(it.total_price, it.currency)}</strong></p>
            <Link className="button primary" to={`/book?${new URLSearchParams({ legs, passengers, total: it.total_price, ...(arriveBy ? { arrive_by: arriveBy } : {}) })}`}>Continue to traveller details</Link>
          </section>
        )
      })()}
    </>
  )
}
