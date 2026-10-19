import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, opServices, type OpService } from '../../api'
import { clock, dayLabel } from '../../format'

export default function Services() {
  const [rows, setRows] = useState<OpService[] | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => { opServices().then((r) => setRows(r.results)).catch((e: unknown) => setErr(e instanceof ApiError ? e : new ApiError('Unexpected error.'))) }, [])
  return (
    <>
      <h1>My services</h1>
      <p><Link className="button primary" to="/operator/new">Create a service</Link></p>
      {err && <p className="status-bad" role="alert">{err.message}</p>}
      {!rows && !err && <p>Loading…</p>}
      {rows && rows.length === 0 && <div className="card empty"><p>You have no upcoming services.</p></div>}
      {rows && rows.length > 0 && (
        <table className="legs card" data-testid="services-table">
          <caption className="sr-only">Upcoming services of your operator</caption>
          <thead><tr><th scope="col">Service</th><th scope="col">Departs</th><th scope="col">Status</th><th scope="col">Booked / capacity</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <th scope="row">{s.route_code} <span className="muted small">{s.first_stop} → {s.last_stop}</span></th>
                <td>{dayLabel(s.departs_at)} {clock(s.departs_at)}</td>
                <td><span className={`badge status-${s.status}`}>{s.status}{s.status === 'delayed' ? ` +${s.delay_minutes} min` : ''}</span></td>
                <td>{s.places_taken} / {s.capacity}</td>
                <td><Link to={`/operator/services/${s.id}`}>Manage<span className="sr-only"> {s.route_code} {clock(s.departs_at)}</span></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
