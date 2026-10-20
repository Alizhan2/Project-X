import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, acceptReplacement, declineReplacement, fetchReplacements, type Booking, type ReplacementOffer, type Replacements } from '../api'
import { clock, dayLabel, money } from '../format'
import { useNow } from '../hooks'
import Timeline from './Timeline'

const WHY: Record<string, string> = {
  offer_expired: 'This offer has expired.',
  offer_outdated: 'Something changed since this offer was made (price, times or availability).',
  offer_unavailable: 'This offer is no longer available.',
  no_capacity: 'The replacement no longer has enough free places.',
  booking_not_active: 'This booking is no longer active.',
}

function Settlement({ o }: { o: ReplacementOffer }) {
  useLanguage()
  if (o.settlement === 'pay') return <p className="price-line">{t("Extra to pay:")} <strong>{money(o.difference, o.currency)}</strong> <span className="muted small">{t("(simulated additional payment)")}</span></p>
  if (o.settlement === 'refund') return <p className="price-line">{t("You get back:")} <strong>{money(String(Math.abs(Number(o.difference)).toFixed(2)), o.currency)}</strong> <span className="muted small">{t("(simulated refund)")}</span></p>
  return <p className="price-line">{t("No price difference.")}</p>
}

export default function RecoveryPanel({ booking, onChanged, onCancel }: { booking: Booking; onChanged: (b: Booking, message: string) => void; onCancel: () => void }) {
  useLanguage()
  const [data, setData] = useState<Replacements | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [choice, setChoice] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const key = useRef(crypto.randomUUID())
  const now = useNow()
  const ref = booking.reference

  const load = useCallback(async (preserveError = false) => {
    try {
      setData(await fetchReplacements(ref))
      if (!preserveError) setError(null)
    }
    catch (e) { setError(e instanceof ApiError ? e.message : t("Could not load replacement options.")) }
  }, [ref])
  useEffect(() => {
    // Initial load: guarded so a slow response for a previous booking can never overwrite the current one.
    let current = true
    fetchReplacements(ref)
      .then(d => { if (current) { setData(d); setError(null) } })
      .catch(e => { if (current) setError(e instanceof ApiError ? e.message : t("Could not load replacement options.")) })
    return () => { current = false }
  }, [ref])

  async function accept(o: ReplacementOffer, outcome: 'success' | 'failure') {
    setBusy(true); setError(null)
    try {
      const r = await acceptReplacement(ref, o.id, outcome, key.current)
      onChanged(r.booking, t("Your replacement journey is booked (simulated)."))
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(t("Unexpected error."))
      if (err.code === 'payment_failed') {
        key.current = crypto.randomUUID() // a retry is a new attempt, not a replay
        setError(t("The simulated payment failed. Nothing was changed; your original booking and places are intact. You can try again."))
      } else {
        setError(t("{0} Options were refreshed.", {0: t(WHY[err.code ?? ''] ?? err.message)}))
        setChoice(null); await load(true)
      }
    } finally { setBusy(false) }
  }

  async function decline(o: ReplacementOffer) {
    await declineReplacement(ref, o.id).catch(() => undefined)
    setChoice(null); await load()
  }

  if (error && !data) return <p role="alert" className="status-bad">{t(error)}</p>
  if (!data) return <p>{t("Looking for replacement options…")}</p>
  return (
    <section className="recovery-panel" aria-labelledby="rec-h">
      <h2 id="rec-h">{t("Replacement options")}</h2>
      {error && <p role="alert" className="status-bad">{t(error)}</p>}

      <div className="recovery-layout"><div className="recovery-options">
      <div className="card recovery-original"><h3>{t('What changes')}</h3>
      {data.retained_legs.length > 0 && (
        <>
          <h3>{t("Kept as booked")}</h3>
          <ul className="recovery-retained">{data.retained_legs.map(l => <li key={l.sequence}><strong>{t(l.mode)} {l.route_code}</strong><p>{placeName(l.from)} → {placeName(l.to)}</p></li>)}</ul>
        </>
      )}
      <h3>{t("Cannot be used")}</h3>
      <ul>{data.affected_legs.map((l) => <li key={l.sequence}>{t(l.mode)} {l.route_code}: {placeName(l.from)} → {placeName(l.to)}, {clock(l.departs_at)} ({dayLabel(l.departs_at)})</li>)}</ul>
      {data.original_arrival && <p className="muted">{t("Originally you would arrive at")} {clock(data.original_arrival)}.</p>}

      </div>
      {data.state === 'none' && (
        <div className="card warn-card" role="status">
          <h3>{t("No replacement found")}</h3>
          <p>{t("We could not find a suitable alternative for the rest of your journey within the next few hours. You can cancel the journey and get a full refund of the legs you have not used (simulated).")}</p>
          {data.cancellation && <p>{t("Refund if you cancel now:")} <strong>{money(data.cancellation.total_refund, booking.currency)}</strong></p>}
          <button className="primary danger" onClick={onCancel}>{t("Review cancellation and refund")}</button>
        </div>
      )}

      {data.offers.map((o, n) => {
        const left = Math.max(0, Math.floor((new Date(o.expires_at).getTime() - now) / 1000))
        const open = choice === o.id
        return (
          <article key={o.id} className={`card recovery-offer${open ? ' is-selected' : ''}`} aria-label={t("Option {0}", {0: n + 1})} data-testid="offer">
            <h3>{t("Option")} {n + 1}{t(": arrive")} {clock(o.arrives_at)}{data.original_arrival && t(" (planned {0})", {0: clock(data.original_arrival)})}</h3>
            <p className="offer-chain">{o.legs.map(l => l.mode === 'taxi' ? t('Taxi') : `${t(l.mode)} ${l.route_code}`).join(' → ')}</p>
            <details className="offer-details"><summary>{t('Journey information')}</summary>
            <Timeline legs={o.legs.map((l) => ({ departs_at: l.departs_at, arrives_at: l.arrives_at, from: l.from.name, to: l.to.name, mode: l.mode, operator: l.operator, route_code: l.route_code,
              note: l.status === 'delayed' ? t("Delayed {0} min", {0: l.delay_minutes}) : undefined }))} />
            <ul className="muted small">
              {o.legs.map((l, i) => (
                <li key={i}>{l.route_code}{t(": wheelchair vehicle")} {l.accessibility.wheelchair_vehicle === 'unknown' ? t("not known") : l.accessibility.wheelchair_vehicle}{t(", step-free boarding")} {l.accessibility.origin_step_free === 'unknown' ? t("not known") : l.accessibility.origin_step_free}</li>
              ))}
            </ul>
            <p>{t("Replaces journey parts worth")} {money(o.replaced_value, o.currency)}  {t("with new parts costing")} {money(o.replacement_price, o.currency)}.</p>
            </details>
            <Settlement o={o} />
            <p className="warn small" role="note">{o.availability_warning}</p>
            <p className="muted small">{t("Offer expires in")} {left > 0 ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}` : t("moments (refresh for new options)")}.</p>
            {!open && <button className="primary" disabled={busy || left === 0} onClick={() => setChoice(o.id)}>{t("Choose this journey")}</button>}
            {open && <span className="badge selected-badge">{t('Selected')}</span>}
          </article>
        )
      })}
      </div>
      {data.offers.length > 0 && <aside className="card recovery-confirm" aria-label={t('Your new plan')}>
        <h3>{t('Your new plan')}</h3>
        {!data.offers.some(o => o.id === choice) ? <p className="muted">{t('Choose a replacement to review its arrival time and price before confirming.')}</p> : data.offers.filter(o => o.id === choice).map(o => <div key={o.id}>
          <p><strong>{dayLabel(o.arrives_at)}, {clock(o.arrives_at)}</strong></p>
          <Settlement o={o} />
          <p className="muted small">{t('Your original booking changes only after successful confirmation.')}</p>
          <div className="sim-panel" role="group" aria-label={t("Confirm replacement")}>
                {o.settlement === 'pay' ? (
                  <>
                    <p>{t("Simulator: an additional payment of")} <strong>{money(o.difference, o.currency)}</strong>  {t("is needed. No real money or card details are used.")}</p>
                    <div className="actions">
                      <button className="primary" disabled={busy} onClick={() => accept(o, 'success')}>{t("Pay")} {money(o.difference, o.currency)}  {t("(simulated) and confirm")}</button>
                      <button className="secondary" disabled={busy} onClick={() => accept(o, 'failure')}>{t("Simulate failed payment")}</button>
                    </div>
                  </>
                ) : (
                  <button className="primary" disabled={busy} onClick={() => accept(o, 'success')}>
                     {t("Confirm replacement")}{o.settlement === 'refund' ? t(" and receive refund (simulated)") : ''}
                  </button>
                )}
                <p><button className="link" disabled={busy} onClick={() => setChoice(null)}>{t("Back to options")}</button> <button className="link" disabled={busy} onClick={() => decline(o)}>{t("Decline this option")}</button></p>
              </div>
        </div>)}
        <button type="button" className="link" disabled={busy} onClick={onCancel}>{t('Review cancellation and refund')}</button>
      </aside>}</div>
      <p><button className="secondary" disabled={busy} onClick={() => load()}>{t("Refresh options")}</button></p>
    </section>
  )
}
