import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, acceptReplacement, declineReplacement, fetchReplacements, type Booking, type PaymentOutcome, type RecoveryPreferences, type ReplacementOffer, type Replacements } from '../api'
import { clock, dayLabel, money, demoDateTimeInput } from '../format'
import { useNow } from '../hooks'
import Timeline from './Timeline'

function Settlement({ offer: o }: { offer: ReplacementOffer }) {
  return <div className="price-line">
    <p>{t('Pay now:')} <strong>{money(o.payment_now, o.currency)}</strong></p>
    <p>{t('Eligible old-leg refund (separate):')} <strong>{money(o.eligible_refund, o.currency)}</strong></p>
    <p>{t('Net extra cost after a successful refund:')} <strong>{money(o.net_extra_cost, o.currency)}</strong></p>
    <p className="muted small">{t('The refund is not available to pay for this replacement. The budget limit applies to the full payment now.')}</p>
  </div>
}

const formValues = (data: Replacements, timeZone = 'Europe/Berlin'): RecoveryPreferences => ({
  origin: data.constraints?.origin ?? '',
  earliest_departure: demoDateTimeInput(data.constraints?.earliest_departure ?? '', data.timezone ?? timeZone),
  latest_arrival: demoDateTimeInput(data.constraints?.latest_arrival ?? '', data.timezone ?? timeZone),
  max_payment_now: data.constraints?.max_payment_now == null ? '' : String(data.constraints.max_payment_now),
  wheelchair_required: String(data.constraints?.wheelchair_required ?? 'false'),
})

export default function RecoveryPanel({ booking, onChanged, onCancel }: { booking: Booking; onChanged: (b: Booking, message: string) => void; onCancel: () => void }) {
  useLanguage()
  const [data, setData] = useState<Replacements | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [choice, setChoice] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<RecoveryPreferences>({})
  const [active, setActive] = useState<RecoveryPreferences>({})
  const key = useRef(crypto.randomUUID())
  const now = useNow()
  const ref = booking.reference
  const pending = booking.payments.find(p => p.purpose === 'replacement' && ['pending', 'created'].includes(p.status))

  useEffect(() => {
    const ctrl = new AbortController()
    fetchReplacements(ref, ctrl.signal)
      .then(d => { if (!ctrl.signal.aborted) { setData(d); setDraft(formValues(d, booking.timezone)); setError(null) } })
      .catch(e => { if (!ctrl.signal.aborted) setError(e instanceof ApiError ? e.message : t('Could not load replacement options.')) })
    return () => ctrl.abort()
  }, [ref, booking.timezone])

  async function refresh(preferences = active) {
    const d = await fetchReplacements(ref, undefined, preferences)
    setData(d)
    return d
  }
  async function search(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null); setFields({}); setChoice(null)
    const preferences = Object.fromEntries(Object.entries(draft).filter(([, value]) => value !== ''))
    try { await refresh(preferences); setActive(preferences) }
    catch (e) { const err = e instanceof ApiError ? e : new ApiError(t('Unexpected error.')); setError(err.message); setFields(err.fields) }
    finally { setBusy(false) }
  }
  async function accept(o: ReplacementOffer, outcome: PaymentOutcome, reconcile = false) {
    setBusy(true); setError(null)
    try {
      const r = await acceptReplacement(ref, o.id, outcome, reconcile && pending ? pending.idempotency_key : key.current, reconcile)
      const waiting = r.booking.payments.some(p => p.purpose === 'replacement' && ['pending', 'created'].includes(p.status))
      onChanged(r.booking, t(waiting ? 'Payment result pending. Your original booking is retained.' : r.offer.status === 'accepted' ? 'Your replacement journey is booked (simulated).' : 'The replacement was not confirmed. Check the separately recorded refund; your original booking is retained.'))
      if (!waiting) { setChoice(null); await refresh() }
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(t('Unexpected error.'))
      setError(err.code === 'payment_failed' ? t('The simulated payment failed. Nothing was changed; your original booking and places are intact. You can try again.') : t('{0} Options were refreshed.', {0: err.message}))
      if (err.code === 'payment_failed') key.current = crypto.randomUUID()
      else if (!['payment_pending', 'payment_unknown'].includes(err.code ?? '')) {
        setChoice(null)
        await refresh().catch(() => undefined)
      }
    } finally { setBusy(false) }
  }
  const update = (name: keyof RecoveryPreferences, value: string) => setDraft(old => ({ ...old, [name]: value }))
  const fieldError = (name: string) => fields[name] && <span className="field-error">{t(fields[name])}</span>

  if (error && !data) return <p role="alert" className="status-bad">{t(error)}</p>
  if (!data) return <p>{t('Looking for replacement options…')}</p>
  return <section className="recovery-panel" aria-labelledby="rec-h">
    <h2 id="rec-h">{t('Replacement options')}</h2>
    {error && <p role="alert" className="status-bad">{t(error)}</p>}
    <form className="card" onSubmit={search}>
      <h3>{t('Your recovery requirements')}</h3>
      <p className="small muted">{t('Choose your current reachable stop. All times use {0}. Used legs remain unchanged.', { 0: data.timezone ?? booking.timezone ?? 'Europe/Berlin' })}</p>
      <fieldset disabled={busy || !!pending}>
        <div className="field"><label htmlFor="recovery-origin">{t('Current reachable location')}</label>
          <select id="recovery-origin" value={draft.origin ?? ''} onChange={e => update('origin', e.target.value)} required>
            <option value="">{t('Choose a stop…')}</option>
            {data.locations?.filter(stop => stop.code.startsWith('KZ-') === (booking.timezone === 'Asia/Almaty')).map(stop => <option key={stop.code} value={stop.code}>{placeName(stop.name)}</option>)}
          </select>{fieldError('origin')}
        </div>
        <div className="field"><label htmlFor="recovery-earliest">{t('Earliest departure')}</label><input id="recovery-earliest" type="datetime-local" value={draft.earliest_departure ?? ''} onChange={e => update('earliest_departure', e.target.value)} required />{fieldError('earliest_departure')}</div>
        <div className="field"><label htmlFor="recovery-latest">{t('Latest acceptable arrival')}</label><input id="recovery-latest" type="datetime-local" value={draft.latest_arrival ?? ''} onChange={e => update('latest_arrival', e.target.value)} required />{fieldError('latest_arrival')}</div>
        <div className="field"><label htmlFor="recovery-budget">{t('Maximum payment now')} ({booking.currency})</label><input id="recovery-budget" type="number" min="0" step="1" value={draft.max_payment_now ?? ''} onChange={e => update('max_payment_now', e.target.value)} placeholder={t('No limit')} />{fieldError('max_payment_now')}</div>
        <label className="check"><input type="checkbox" checked={!!booking.wheelchair_required || draft.wheelchair_required === 'true'} disabled={!!booking.wheelchair_required} onChange={e => update('wheelchair_required', String(e.target.checked))} />{t('Require a fully step-free journey')}</label>
        <button type="submit" className="secondary">{t('Find replacement journeys')}</button>
      </fieldset>
    </form>
    {pending && <div className="card warn-card" role="status"><strong>{t('Payment result pending')}</strong><p>{t('We are checking the original payment. A new payment is blocked until its result is known.')}</p></div>}
    <div className="recovery-layout"><div className="recovery-options">
      <div className="card recovery-original"><h3>{t('What changes')}</h3>
        {data.retained_legs.length > 0 && <><h3>{t('Kept as booked')}</h3><ul className="recovery-retained">{data.retained_legs.map(l => <li key={l.sequence}><strong>{t(l.mode)} {l.route_code}</strong><p>{placeName(l.from)} → {placeName(l.to)}</p></li>)}</ul></>}
        <h3>{t('Legs to replace')}</h3><ul>{data.affected_legs.map(l => <li key={l.sequence}>{t(l.mode)} {l.route_code}: {placeName(l.from)} → {placeName(l.to)}, {clock(l.departs_at)} ({dayLabel(l.departs_at)})</li>)}</ul>
        {data.original_arrival && <p className="muted">{t('Originally you would arrive at')} {clock(data.original_arrival)}.</p>}
      </div>
      {data.state === 'none' && <div className="card warn-card" role="status"><h3>{t('No replacement found')}</h3><p>{t('No journey meets the selected location, deadline, payment budget and accessibility requirements. Your booking has not changed.')}</p>{data.cancellation && <p>{t('Refund if you cancel now:')} <strong>{money(data.cancellation.total_refund, booking.currency)}</strong></p>}<button className="secondary" onClick={onCancel}>{t('Review cancellation policy')}</button></div>}
      {data.offers.map(o => {
        const isPending = pending?.offer_id === o.id
        const selected = choice === o.id || isPending
        const expired = new Date(o.expires_at).getTime() <= now
        return <article key={o.id} className="card recovery-offer" data-testid="offer" data-offer-id={o.id}>
          <h3>{t('Arrival')} {clock(o.arrives_at)} <span className="muted small">{dayLabel(o.arrives_at)}</span></h3>
          {o.retained_legs && o.retained_legs.length > 0 && <p className="small">{t('Kept as booked')}: {o.retained_legs.map(l => `${l.route_code} ${placeName(l.from)} → ${placeName(l.to)}`).join('; ')}</p>}
          {o.affected_legs && <p className="small">{t('Legs to replace')}: {o.affected_legs.map(l => l.route_code).join(', ')}</p>}
          <Timeline connections={o.connections} legs={o.legs.map(l => ({ ...l, from: l.from.name, to: l.to.name }))} />
          <p className="small muted">{t('Wheelchair vehicle:')} {o.legs.some(l => l.accessibility.wheelchair_vehicle === 'no') ? t('no') : o.legs.every(l => l.accessibility.wheelchair_vehicle === 'yes') ? t('yes') : t('not known')}</p>
          <Settlement offer={o} />
          <p className="muted small">{t('Places are not held until you accept. Availability and price are checked again at that moment.')}</p>
          <p className="small">{t('Offer expires at')} {clock(o.expires_at)}</p>
          {isPending ? <div className="actions">
            <button className="primary" disabled={busy} onClick={() => accept(o, 'success', true)}>{t('Reconcile as successful (simulated)')}</button>
            <button className="secondary" disabled={busy} onClick={() => accept(o, 'failure', true)}>{t('Reconcile as failed (simulated)')}</button>
          </div> : selected ? <div className="sim-panel" role="group" aria-label={t("Confirm replacement")}><h4>{t('Payment simulator')}</h4><p>{t('Your original booking remains until the replacement is confirmed.')}</p><div className="actions">
            <button className="primary" disabled={busy || expired || !!pending} onClick={() => accept(o, 'success')}>{t('Pay full replacement price and confirm (simulated)')}</button>
            <button className="secondary" disabled={busy || expired || !!pending} onClick={() => accept(o, 'failure')}>{t('Simulate failed payment')}</button>
            <button className="secondary" disabled={busy || expired || !!pending} onClick={() => accept(o, 'pending')}>{t('Simulate unknown payment result')}</button>
            <button className="link" disabled={busy || !!pending} onClick={() => setChoice(null)}>{t('Back')}</button>
          </div></div> : <div className="actions"><button className="primary" disabled={busy || expired || !!pending} onClick={() => { key.current = crypto.randomUUID(); setChoice(o.id) }}>{expired ? t('This offer has expired.') : t('Choose this journey')}</button><button className="link" disabled={busy || !!pending} onClick={async () => { setBusy(true); try { await declineReplacement(ref, o.id); await refresh() } catch (e) { setError(e instanceof Error ? e.message : t('Unexpected error.')) } finally { setBusy(false) } }}>{t('Decline')}</button></div>}
        </article>
      })}
    </div><aside className="card recovery-summary"><h3>{t('Separate payment and refund')}</h3><p>{t('The full replacement fare is paid now. Any eligible refund is processed separately and may fail or remain pending.')}</p><p className="small muted">{t('A delay alone does not guarantee a full refund. The cancellation policy saved at purchase applies.')}</p></aside></div>
  </section>
}
