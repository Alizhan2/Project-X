import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchBookings, type Booking } from '../api'
import { clock, dayLabel, money } from '../format'

export default function MyJourneys() {
  const [list, setList] = useState<Booking[] | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchBookings(ctrl.signal).then((r) => setList(r.results)).catch((e: unknown) => { if (!ctrl.signal.aborted) setErr(e instanceof ApiError ? e : new ApiError('Unexpected error.')) })
    return () => ctrl.abort()
  }, [])
  return (
    <>
      <h1>My journeys</h1>
      {err && <p className="status-bad" role="alert">{err.message}</p>}
      {!list && !err && <p>Loading…</p>}
      {list && list.length === 0 && <div className="card empty"><p><strong>No journeys yet.</strong></p><Link to="/">Search for a journey</Link></div>}
      {list && list.length > 0 && (
        <ul className="result-list">
          {list.map((b) => (
            <li key={b.reference} className="card result">
              <div>
                <p><Link to={`/booking/${b.reference}`}><strong>{b.reference}</strong></Link> <span className="badge">{b.status_label}</span></p>
                <p>{b.legs[0].from} → {b.legs[b.legs.length - 1].to}</p>
                <p className="muted">{dayLabel(b.legs[0].departs_at)} · {clock(b.legs[0].departs_at)} · {b.passengers} passenger(s)</p>
              </div>
              <p className="price">{money(b.total_amount, b.currency)}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
