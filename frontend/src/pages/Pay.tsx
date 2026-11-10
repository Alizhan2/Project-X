import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError, abandonBooking, fetchBooking, payBooking, reconcilePayment, type Booking, type PaymentOutcome } from '../api'
import { useNow } from '../hooks'
import { money } from '../format'

export default function Pay() {
  useLanguage()
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
    fetchBooking(ref, ctrl.signal).then(setBooking).catch((e: unknown) => { if (!ctrl.signal.aborted) setErr(e instanceof ApiError ? e : new ApiError(t('Unexpected error.'))) })
    return () => ctrl.abort()
  }, [ref])

  if (err && !booking) return <p className="status-bad" role="alert">{err.status === 404 ? t('Booking not found.') : t(err.message)}</p>
  if (!booking) return <p>{t('Loading…')}</p>

  const pending = booking.payments.find(p => p.purpose === 'initial' && ['pending', 'created'].includes(p.status))
  const left = Math.max(0, Math.floor((new Date(booking.expires_at).getTime() - now) / 1000))
  const expired = booking.status === 'expired' || (booking.status === 'pending_payment' && left === 0)
  if (booking.status === 'confirmed') return <Navigate to={`/booking/${ref}`} replace />

  async function run(outcome: PaymentOutcome, reconcile = false) {
    setBusy(true); setErr(null); setDeclined(null)
    try {
      const res = reconcile
        ? await reconcilePayment(ref, outcome === 'failure' ? 'failure' : 'success', pending?.idempotency_key ?? key.current)
        : await payBooking(ref, outcome, key.current)
      setBooking(res.booking)
      if (res.payment.status === 'failed') {
        setDeclined(res.payment.failure_reason)
        key.current = crypto.randomUUID()
      } else if (res.booking.status === 'confirmed') {
        nav(`/booking/${ref}`, { replace: true })
      }
    } catch (x) {
      const e = x instanceof ApiError ? x : new ApiError(t('Unexpected error.'))
      if (e.code === 'already_paid') nav(`/booking/${ref}`, { replace: true })
      else { setErr(e); fetchBooking(ref).then(setBooking).catch(() => undefined) }
    } finally { setBusy(false) }
  }

  if (expired && !pending) return <section className="card" role="alert">
    <h1>{t('Reservation expired')}</h1>
    <p>{t('The reservation ended. Check payment and refund history for the final settlement.')}</p>
    <Link to={`/booking/${ref}`}>{t('View payment and refund history')}</Link>
    <p><Link className="button primary" to="/demo">{t('Search again')}</Link></p>
  </section>
  if (booking.status === 'cancelled' && !pending) return <p>{t('This reservation was cancelled.')} <Link to={`/booking/${ref}`}>{t('View payment and refund history')}</Link></p>

  const mm = String(Math.floor(left / 60)).padStart(2, '0'), ss = String(left % 60).padStart(2, '0')
  return <>
    <h1>{t('Payment')}</h1>
    <section className="card">
      {!expired && <p><strong>{t('Places held for you.')}</strong> {t('Time left to pay:')} <strong data-testid="countdown">{mm}:{ss}</strong></p>}
      <p>{t('Total to pay:')} <strong>{money(booking.total_amount, booking.currency)}</strong> {t('· Reference')} {booking.reference}</p>
      <div className="sim-panel" role="group" aria-labelledby="sim-h">
        <h2 id="sim-h">{t('Payment simulator')}</h2>
        <p>{t('This is a demonstration. No real payment is taken and no card details are requested. Choose an outcome to see how the booking behaves.')}</p>
        {declined && <p className="status-bad" role="alert">{t('Payment failed:')} {t(declined)} {t('Your places are still held — you can try again.')}</p>}
        {err && <p className="status-bad" role="alert">{t(err.message)}</p>}
        {pending ? <div role="status" className="warn-card">
          <p><strong>{t('Payment result pending')}</strong></p>
          <p>{t('We are checking the original payment. A new payment is blocked until its result is known.')}</p>
          {expired && <p>{t('The reservation expired. A late successful charge will be refunded separately; the booking will not reopen.')}</p>}
          <div className="actions">
            <button className="primary" disabled={busy} onClick={() => run('success', true)}>{t('Reconcile as successful (simulated)')}</button>
            <button className="secondary" disabled={busy} onClick={() => run('failure', true)}>{t('Reconcile as failed (simulated)')}</button>
          </div>
        </div> : <div className="actions">
          <button className="primary" disabled={busy || expired} onClick={() => run('success')}>{t('Simulate successful payment')}</button>
          <button className="secondary" disabled={busy || expired} onClick={() => run('failure')}>{t('Simulate failed payment')}</button>
          <button className="secondary" disabled={busy || expired} onClick={() => run('pending')}>{t('Simulate unknown payment result')}</button>
        </div>}
      </div>
      {!pending && <p><button className="link" disabled={busy} onClick={async () => { await abandonBooking(ref).catch(() => undefined); nav('/journeys') }}>{t('Cancel this reservation')}</button></p>}
    </section>
  </>
}
