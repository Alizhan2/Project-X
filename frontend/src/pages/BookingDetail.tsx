import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, cancelBooking, fetchBooking, fetchQuote, type Booking, type CancellationQuote } from '../api'
import RecoveryPanel from '../components/RecoveryPanel'
import Timeline from '../components/Timeline'
import JourneyDownloads from '../components/JourneyDownloads'
import { clock, money } from '../format'
import { netPaid } from '../bookingAmounts'

const REASONS: Record<string, string> = {
  service_cancelled: 'one of your services was cancelled by the operator',
  connection_missed: 'a delay means you can no longer make a connection',
  taxi_unavailable: 'a delay moves your taxi pickup outside its service hours',
}

export default function BookingDetail() {
  useLanguage()
  const { ref = '' } = useParams()
  const [b, setB] = useState<Booking | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [quote, setQuote] = useState<CancellationQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [recovered, setRecovered] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) =>
    fetchBooking(ref, signal).then(setB).catch((e: unknown) => { if (!signal?.aborted) setErr(e instanceof ApiError ? e : new ApiError(t("Unexpected error."))) }), [ref])
  useEffect(() => {
    const ctrl = new AbortController()
    load(ctrl.signal)
    const timer = setInterval(() => {
      // Refresh quietly; transient network failures do not hide an already loaded booking.
      fetchBooking(ref, ctrl.signal).then(data => { if (!ctrl.signal.aborted) setB(data) }).catch(() => undefined)
    }, 15000)
    return () => { ctrl.abort(); clearInterval(timer) }
  }, [load, ref])

  async function startCancel() {
    setMsg(null)
    try { setQuote(await fetchQuote(ref)) } catch (e) { setMsg(e instanceof ApiError ? e.message : t("Unexpected error.")) }
  }
  async function confirmCancel() {
    if (!quote) return
    setBusy(true); setMsg(null)
    try {
      setB(await cancelBooking(ref, quote.total_refund)); setQuote(null)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'refund_changed') {
        setMsg(t("The refund changed to {0} since you looked. Please review it again.", {0: money(String(e.data.new_refund), b?.currency ?? 'EUR')}))
        setQuote(await fetchQuote(ref))
      } else setMsg(e instanceof ApiError ? e.message : t("Unexpected error."))
    } finally { setBusy(false) }
  }

  if (err) return <p className="status-bad" role="alert">{err.status === 404 ? t("Booking not found.") : t(err.message)}</p>
  if (!b) return <p>{t("Loading…")}</p>
  return (
    <>
      {b.status === 'confirmed' && !b.disruption?.reason && (
        <div className="card success" role="status">
          <h1>{t("Booking confirmed (simulated)")}</h1>
          <p>{t("Reference")} <strong data-testid="reference">{b.reference}</strong>. {t(b.simulated_notice)}</p>
        </div>
      )}
      {b.disruption?.status === 'broken' ? <><h1>{t('Your journey has changed.')}<br />{t('Choose a new plan.')}</h1><p className="muted small">{t('Reference')} <span data-testid="reference">{b.reference}</span></p></> : (b.status !== 'confirmed' || b.disruption?.reason) && <h1>{t("Booking")} <span data-testid="reference">{b.reference}</span></h1>}

      {recovered && <p className="card success" role="status">{t(recovered)}</p>}
      {b.disruption?.status === 'broken' && (
        <div className="card disruption-banner" role="alert">
          <h2>{t("Your journey is disrupted")}</h2>
          <p>{t("Leg")} {(b.disruption.problem_sequence ?? 0) + 1}  {t("cannot be used:")} {t(REASONS[b.disruption.reason] ?? "a service changed")}.</p>
          <p>{t("You can cancel below for a full refund of every unused leg.")}</p>
        </div>
      )}
      {b.disruption?.status === 'delayed' && (
        <div className="card warn-card" role="status">
          <p><strong>{t("A service on your journey is delayed.")}</strong>  {t("Your connections still work")} {b.disruption.arrival_delay_minutes ? t("; you arrive about {0} minutes later.", {0: b.disruption.arrival_delay_minutes}) : t(" and your arrival time is unchanged.")}
          </p>
        </div>
      )}

      {b.status === 'confirmed' && b.disruption?.status === 'broken' && (
        <RecoveryPanel booking={b} onChanged={(nb, m) => { setB(nb); setQuote(null); setRecovered(m) }} onCancel={startCancel} />
      )}

      <section className="card">
        <p>{t("Status:")} <span className="badge" data-testid="status">{t(b.status_label)}</span></p>
        {b.status === 'pending_payment' && <p><Link to={`/booking/${b.reference}/pay`}>{t("Continue to payment")}</Link></p>}
        {b.status === 'expired' && <p className="warn">{t("The reservation expired and the places were released. Nothing was charged.")}</p>}
        {b.travel_plan && <p className="muted small">{t("Current timetable · checked at")} {clock(b.travel_plan.generated_at)}  {t("(Europe/Berlin). Progress is estimated, not GPS tracking.")}</p>}
        <Timeline legs={b.travel_plan ? b.travel_plan.legs.map(l => ({ ...l, note: l.state === 'unavailable' ? t("Service unavailable") : l.departs_at !== l.scheduled_departs_at ? t("Originally booked departure: {0}", {0: clock(l.scheduled_departs_at)}) : undefined })) : b.legs.filter((l) => l.status === 'booked')} />
        {b.status === 'confirmed' && <JourneyDownloads reference={b.reference} disrupted={b.disruption?.status === 'broken'} />}
        {b.legs.some((l) => l.status === 'replaced') && (
          <details>
            <summary>{t("Original legs that were replaced (history)")}</summary>
            <ul className="muted small">{b.legs.filter((l) => l.status === 'replaced').map((l) => <li key={l.sequence}>{l.route_code}: {placeName(l.from)} → {placeName(l.to)}, {clock(l.departs_at)}{t(", paid")} {money(l.unit_price, b.currency)}{l.price_basis === 'vehicle' ? t(" per taxi") : t(" per passenger")}</li>)}</ul>
          </details>
        )}
        <p>{t("Passengers:")} {b.travellers.join(', ')}</p>
        <p>{t("Net paid:")} <strong data-testid="net-paid">{money(netPaid(b), b.currency)}</strong>  {t("(prices fixed at purchase)")}</p>
        <ul className="muted small">{b.legs.map((l) => <li key={l.sequence}>{l.route_code}: {t(l.cancellation_policy)}</li>)}</ul>

        {b.refunds.map((r, i) => (
          <p key={i} className="success card" role="status" data-testid="refund">
             {t("Refund:")} <strong>{money(r.amount, b.currency)}</strong> — {t(r.reason)} ({t(r.status)}{t(", simulated).")} </p>
        ))}

        {b.cancellable && b.status === 'confirmed' && !quote && (
          <p><button className="secondary" onClick={startCancel}>{t("Cancel this journey…")}</button></p>
        )}
        {msg && <p className="status-bad" role="alert">{t(msg)}</p>}
        {quote && (
          <div className="card" role="region" aria-label={t("Cancellation and refund")}>
            <h2>{t("Cancel and refund")}</h2>
            {quote.disrupted && <p className="warn">{t("Because your journey is disrupted, unused legs are refunded in full.")}</p>}
            <table className="legs">
              <thead><tr><th scope="col">{t("Leg")}</th><th scope="col">{t("Paid")}</th><th scope="col">{t("Refund")}</th><th scope="col">{t("Why")}</th></tr></thead>
              <tbody>
                {quote.lines.map((l) => (
                  <tr key={l.sequence}><th scope="row">{l.route_code}</th><td>{money(l.paid, b.currency)}</td><td>{money(l.refund, b.currency)} ({l.percent}%)</td><td>{t(l.reason)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="price-line">{t("You will receive:")} <strong data-testid="quote-total">{money(quote.total_refund, b.currency)}</strong>  {t("(simulated refund)")}</p>
            <div className="actions">
              <button className="primary danger" disabled={busy} onClick={confirmCancel}>{t("Confirm cancellation")}</button>
              <button className="secondary" disabled={busy} onClick={() => setQuote(null)}>{t("Keep my booking")}</button>
            </div>
          </div>
        )}

        {b.payments.length > 0 && (
          <>
            <h2>{t("Payment attempts (simulated)")}</h2>
            <ul>{b.payments.map((p, i) => <li key={i}>{p.purpose === 'replacement' ? t("Replacement top-up: ") : ''}{t(p.status)} — {money(p.amount, b.currency)}{p.failure_reason && ` — ${t(p.failure_reason)}`}</li>)}</ul>
          </>
        )}
      </section>
    </>
  )
}
