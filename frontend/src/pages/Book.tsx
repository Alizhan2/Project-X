import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, createBooking } from '../api'
import { useAuth } from '../auth'
import LegSummary from '../components/LegSummary'
import { useItinerary } from '../hooks'
import { money } from '../format'

export default function Book() {
  const [p] = useSearchParams()
  const legs = p.get('legs') ?? '', passengers = p.get('passengers') ?? '1'
  const [expected, setExpected] = useState(p.get('total') ?? '')
  const { user } = useAuth()
  const nav = useNavigate()
  const st = useItinerary(legs, passengers)
  const n = Number(passengers)
  const [names, setNames] = useState<string[]>(() => Array.from({ length: n }, (_, i) => (i === 0 ? (user?.name ?? '') : '')))
  const [email, setEmail] = useState(user?.email ?? '')
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  // One key per form instance: a double click or retry replays the same checkout instead of booking twice.
  const key = useRef(crypto.randomUUID())

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (st.kind !== 'ready') return
    setBusy(true); setErr(null)
    try {
      const booking = await createBooking({
        passengers: n, contact_email: email, travellers: names, expected_total: expected || undefined,
        legs: st.data.selection,
      }, key.current)
      nav(`/booking/${booking.reference}/pay`, { replace: true })
    } catch (x) {
      setErr(x instanceof ApiError ? x : new ApiError('Something went wrong.'))
    } finally { setBusy(false) }
  }

  const changedTotal = err?.code === 'offer_changed' ? String(err.data.new_total) : null
  return (
    <>
      <h1>Traveller details</h1>
      {st.kind === 'loading' && <p>Loading journey…</p>}
      {st.kind === 'error' && <div className="card" role="alert"><p className="status-bad">{st.error.message}</p><Link to="/">Search again</Link></div>}
      {st.kind === 'ready' && (
        <div className="two-col">
          <form className="card" onSubmit={submit} noValidate>
            {err && !changedTotal && (
              <div role="alert" className="status-bad">
                <p>{err.message}</p>
                {['unavailable', 'no_capacity', 'invalid_leg'].includes(err.code ?? '') && <p><Link to="/">Search again</Link></p>}
              </div>
            )}
            {changedTotal && (
              <div role="alert" className="warn">
                <p>The price changed to {money(changedTotal, st.data.currency)}.</p>
                <button type="button" className="primary" onClick={() => { setExpected(changedTotal); setErr(null) }}>Accept new price</button>
              </div>
            )}
            <div className="field">
              <label htmlFor="contact">Contact email</label>
              <input id="contact" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!err?.fields.contact_email} />
              {err?.fields.contact_email && <span className="field-error">{err.fields.contact_email}</span>}
            </div>
            {names.map((v, i) => (
              <div className="field" key={i}>
                <label htmlFor={`t${i}`}>Passenger {i + 1} full name</label>
                <input id={`t${i}`} required value={v} onChange={(e) => setNames(names.map((x, j) => (j === i ? e.target.value : x)))} />
              </div>
            ))}
            {err?.fields.travellers && <p className="field-error">{err.fields.travellers}</p>}
            <p className="muted small">We only keep names and a contact email. No documents or card details are collected.</p>
            <button className="primary" type="submit" disabled={busy}>Reserve and continue to payment</button>
          </form>
          <aside className="card" aria-label="Order summary">
            <h2>Summary</h2>
            <LegSummary it={st.data} />
            <p className="price-line">Total: <strong>{money(st.data.total_price, st.data.currency)}</strong></p>
          </aside>
        </div>
      )}
    </>
  )
}
