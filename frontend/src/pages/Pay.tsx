import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError, abandonBooking, fetchBooking, payBooking, type Booking } from '../api'
import { useNow } from '../hooks'
import { money } from '../format'

export default function Pay() {
  const { ref = '' } = useParams()
  const nav = useNavigate()
  const [booking, setBooking] = useState<Booking | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [declined, setDeclined] = useState<string | null>(null)
  const key = useRef(crypto.randomUUID())
  const now = useNow()

  useEffect(() => {
    const ctrl = new AbortController()
    fetchBooking(ref, ctrl.signal).then(setBooking).catch((e: unknown) => { if (!ctrl.signal.aborted) setErr(e instanceof ApiError ? e : new ApiError('Unexpected error.')) })
    return () => ctrl.abort()
  }, [ref])

  if (err && !booking) return <p className="status-bad" role="alert">{err.status === 404 ? 'Booking not found.' : err.message}</p>
  if (!booking) return <p>Loading…</p>

  const left = Math.max(0, Math.floor((new Date(booking.expires_at).getTime() - now) / 1000))
  const expired = booking.status === 'expired' || (booking.status === 'pending_payment' && left === 0)
  if (booking.status === 'confirmed') return <Navigate to={`/booking/${ref}`} replace />

  async function run(outcome: 'success' | 'failure') {
    setBusy(true); setErr(null); setDeclined(null)
    try {
      const res = await payBooking(ref, outcome, key.current)
      if (res.payment.status === 'failed') {
        setDeclined(res.payment.failure_reason)
        setBooking(res.booking)
        key.current = crypto.randomUUID() // next click is a new attempt, not a replay
      } else {
        nav(`/booking/${ref}`, { replace: true })
      }
    } catch (x) {
      const e = x instanceof ApiError ? x : new ApiError('Unexpected error.')
      if (e.code === 'already_paid') nav(`/booking/${ref}`, { replace: true })
      else { setErr(e); if (e.code === 'expired') fetchBooking(ref).then(setBooking).catch(() => undefined) }
    } finally { setBusy(false) }
  }

  if (expired) {
    return (
      <section className="card" role="alert">
        <h1>Reservation expired</h1>
        <p>Your places were released because payment was not completed in time. Nothing was charged.</p>
        <Link className="button primary" to="/">Search again</Link>
      </section>
    )
  }
  if (booking.status === 'cancelled') return <p>This reservation was cancelled. <Link to="/">Search again</Link></p>

  const mm = String(Math.floor(left / 60)).padStart(2, '0'), ss = String(left % 60).padStart(2, '0')
  return (
    <>
      <h1>Payment</h1>
      <section className="card">
        <p><strong>Places held for you.</strong> Time left to pay: <strong data-testid="countdown">{mm}:{ss}</strong></p>
        <p>Total to pay: <strong>{money(booking.total_amount, booking.currency)}</strong> · Reference {booking.reference}</p>
        <div className="sim-panel" role="group" aria-labelledby="sim-h">
          <h2 id="sim-h">Payment simulator</h2>
          <p>
            This is a demonstration. No real payment is taken and no card details are requested. Choose an outcome to
            see how the booking behaves.
          </p>
          {declined && <p className="status-bad" role="alert">Payment failed: {declined} Your places are still held — you can try again.</p>}
          {err && <p className="status-bad" role="alert">{err.message}</p>}
          <div className="actions">
            <button className="primary" disabled={busy} onClick={() => run('success')}>Simulate successful payment</button>
            <button className="secondary" disabled={busy} onClick={() => run('failure')}>Simulate failed payment</button>
          </div>
        </div>
        <p><button className="link" disabled={busy} onClick={async () => { await abandonBooking(ref).catch(() => undefined); nav('/journeys') }}>Cancel this reservation</button></p>
      </section>
    </>
  )
}
