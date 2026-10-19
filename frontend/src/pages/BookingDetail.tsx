import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, cancelBooking, fetchBooking, fetchQuote, type Booking, type CancellationQuote } from '../api'
import RecoveryPanel from '../components/RecoveryPanel'
import Timeline from '../components/Timeline'
import { clock, money } from '../format'

const REASONS: Record<string, string> = {
  service_cancelled: 'one of your services was cancelled by the operator',
  connection_missed: 'a delay means you can no longer make a connection',
  taxi_unavailable: 'a delay moves your taxi pickup outside its service hours',
}

export default function BookingDetail() {
  const { ref = '' } = useParams()
  const [b, setB] = useState<Booking | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [quote, setQuote] = useState<CancellationQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [recovered, setRecovered] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) =>
    fetchBooking(ref, signal).then(setB).catch((e: unknown) => { if (!signal?.aborted) setErr(e instanceof ApiError ? e : new ApiError('Unexpected error.')) }), [ref])
  useEffect(() => { const ctrl = new AbortController(); load(ctrl.signal); return () => ctrl.abort() }, [load])

  async function startCancel() {
    setMsg(null)
    try { setQuote(await fetchQuote(ref)) } catch (e) { setMsg(e instanceof ApiError ? e.message : 'Unexpected error.') }
  }
  async function confirmCancel() {
    if (!quote) return
    setBusy(true); setMsg(null)
    try {
      setB(await cancelBooking(ref, quote.total_refund)); setQuote(null)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'refund_changed') {
        setMsg(`The refund changed to ${money(String(e.data.new_refund), b?.currency ?? 'EUR')} since you looked. Please review it again.`)
        setQuote(await fetchQuote(ref))
      } else setMsg(e instanceof ApiError ? e.message : 'Unexpected error.')
    } finally { setBusy(false) }
  }

  if (err) return <p className="status-bad" role="alert">{err.status === 404 ? 'Booking not found.' : err.message}</p>
  if (!b) return <p>Loading…</p>
  return (
    <>
      {b.status === 'confirmed' && !b.disruption?.reason && (
        <div className="card success" role="status">
          <h1>Booking confirmed (simulated)</h1>
          <p>Reference <strong data-testid="reference">{b.reference}</strong>. {b.simulated_notice}</p>
        </div>
      )}
      {(b.status !== 'confirmed' || b.disruption?.reason) && <h1>Booking <span data-testid="reference">{b.reference}</span></h1>}

      {recovered && <p className="card success" role="status">{recovered}</p>}
      {b.disruption?.status === 'broken' && (
        <div className="card danger-card" role="alert">
          <h2>Your journey is disrupted</h2>
          <p>Leg {(b.disruption.problem_sequence ?? 0) + 1} cannot be used: {REASONS[b.disruption.reason] ?? 'a service changed'}.</p>
          <p>You can cancel below for a full refund of every unused leg.</p>
        </div>
      )}
      {b.disruption?.status === 'delayed' && (
        <div className="card warn-card" role="status">
          <p><strong>A service on your journey is delayed.</strong> Your connections still work
            {b.disruption.arrival_delay_minutes ? `; you arrive about ${b.disruption.arrival_delay_minutes} minutes later.` : ' and your arrival time is unchanged.'}
          </p>
        </div>
      )}

      {b.status === 'confirmed' && b.disruption?.status === 'broken' && (
        <RecoveryPanel booking={b} onChanged={(nb, m) => { setB(nb); setQuote(null); setRecovered(m) }} onCancel={startCancel} />
      )}

      <section className="card">
        <p>Status: <span className="badge" data-testid="status">{b.status_label}</span></p>
        {b.status === 'pending_payment' && <p><Link to={`/booking/${b.reference}/pay`}>Continue to payment</Link></p>}
        {b.status === 'expired' && <p className="warn">The reservation expired and the places were released. Nothing was charged.</p>}
        <Timeline legs={b.legs.filter((l) => l.status === 'booked').map((l) => ({ departs_at: l.departs_at, arrives_at: l.arrives_at, from: l.from, to: l.to, mode: l.mode, operator: l.operator, route_code: l.route_code }))} />
        {b.legs.some((l) => l.status === 'replaced') && (
          <details>
            <summary>Original legs that were replaced (history)</summary>
            <ul className="muted small">{b.legs.filter((l) => l.status === 'replaced').map((l) => <li key={l.sequence}>{l.route_code}: {l.from} → {l.to}, {clock(l.departs_at)}, paid {money(l.unit_price, b.currency)}{l.price_basis === 'vehicle' ? ' per taxi' : ' per passenger'}</li>)}</ul>
          </details>
        )}
        <p>Passengers: {b.travellers.join(', ')}</p>
        <p>Net paid: <strong>{money(b.total_amount, b.currency)}</strong> (prices fixed at purchase)</p>
        <ul className="muted small">{b.legs.map((l) => <li key={l.sequence}>{l.route_code}: {l.cancellation_policy}</li>)}</ul>

        {b.refunds.map((r, i) => (
          <p key={i} className="success card" role="status" data-testid="refund">
            Refund: <strong>{money(r.amount, b.currency)}</strong> — {r.reason} ({r.status}, simulated).
          </p>
        ))}

        {b.cancellable && b.status === 'confirmed' && !quote && (
          <p><button className="secondary" onClick={startCancel}>Cancel this journey…</button></p>
        )}
        {msg && <p className="status-bad" role="alert">{msg}</p>}
        {quote && (
          <div className="card" role="region" aria-label="Cancellation and refund">
            <h2>Cancel and refund</h2>
            {quote.disrupted && <p className="warn">Because your journey is disrupted, unused legs are refunded in full.</p>}
            <table className="legs">
              <thead><tr><th scope="col">Leg</th><th scope="col">Paid</th><th scope="col">Refund</th><th scope="col">Why</th></tr></thead>
              <tbody>
                {quote.lines.map((l) => (
                  <tr key={l.sequence}><th scope="row">{l.route_code}</th><td>{money(l.paid, b.currency)}</td><td>{money(l.refund, b.currency)} ({l.percent}%)</td><td>{l.reason}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="price-line">You will receive: <strong data-testid="quote-total">{money(quote.total_refund, b.currency)}</strong> (simulated refund)</p>
            <div className="actions">
              <button className="primary danger" disabled={busy} onClick={confirmCancel}>Confirm cancellation</button>
              <button className="secondary" disabled={busy} onClick={() => setQuote(null)}>Keep my booking</button>
            </div>
          </div>
        )}

        {b.payments.length > 0 && (
          <>
            <h2>Payment attempts (simulated)</h2>
            <ul>{b.payments.map((p, i) => <li key={i}>{p.purpose === 'replacement' ? 'Replacement top-up: ' : ''}{p.status} — {money(p.amount, b.currency)}{p.failure_reason && ` — ${p.failure_reason}`}</li>)}</ul>
          </>
        )}
      </section>
    </>
  )
}
