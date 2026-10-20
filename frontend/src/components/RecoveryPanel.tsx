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
  if (o.settlement === 'pay') return <p className="price-line">Extra to pay: <strong>{money(o.difference, o.currency)}</strong> <span className="muted small">(simulated additional payment)</span></p>
  if (o.settlement === 'refund') return <p className="price-line">You get back: <strong>{money(String(Math.abs(Number(o.difference)).toFixed(2)), o.currency)}</strong> <span className="muted small">(simulated refund)</span></p>
  return <p className="price-line">No price difference.</p>
}

export default function RecoveryPanel({ booking, onChanged, onCancel }: { booking: Booking; onChanged: (b: Booking, message: string) => void; onCancel: () => void }) {
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
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load replacement options.') }
  }, [ref])
  useEffect(() => { load() }, [load])

  async function accept(o: ReplacementOffer, outcome: 'success' | 'failure') {
    setBusy(true); setError(null)
    try {
      const r = await acceptReplacement(ref, o.id, outcome, key.current)
      onChanged(r.booking, 'Your replacement journey is booked (simulated).')
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('Unexpected error.')
      if (err.code === 'payment_failed') {
        key.current = crypto.randomUUID() // a retry is a new attempt, not a replay
        setError('The simulated payment failed. Nothing was changed; your original booking and places are intact. You can try again.')
      } else {
        setError(`${WHY[err.code ?? ''] ?? err.message} Options were refreshed.`)
        setChoice(null); await load(true)
      }
    } finally { setBusy(false) }
  }

  async function decline(o: ReplacementOffer) {
    await declineReplacement(ref, o.id).catch(() => undefined)
    setChoice(null); await load()
  }

  if (error && !data) return <p role="alert" className="status-bad">{error}</p>
  if (!data) return <p>Looking for replacement options…</p>
  return (
    <section className="card" aria-labelledby="rec-h">
      <h2 id="rec-h">Replacement options</h2>
      {error && <p role="alert" className="status-bad">{error}</p>}

      {data.retained_legs.length > 0 && (
        <>
          <h3>Kept as booked</h3>
          <Timeline legs={data.retained_legs.map((l) => ({ ...l, operator: '', note: undefined }))} />
        </>
      )}
      <h3>Cannot be used</h3>
      <ul>{data.affected_legs.map((l) => <li key={l.sequence}>{l.mode} {l.route_code}: {l.from} → {l.to}, {clock(l.departs_at)} ({dayLabel(l.departs_at)})</li>)}</ul>
      {data.original_arrival && <p className="muted">Originally you would arrive at {clock(data.original_arrival)}.</p>}

      {data.state === 'none' && (
        <div className="card warn-card" role="status">
          <h3>No replacement found</h3>
          <p>We could not find a suitable alternative for the rest of your journey within the next few hours. You can cancel the journey and get a full refund of the legs you have not used (simulated).</p>
          {data.cancellation && <p>Refund if you cancel now: <strong>{money(data.cancellation.total_refund, booking.currency)}</strong></p>}
          <button className="primary danger" onClick={onCancel}>Review cancellation and refund</button>
        </div>
      )}

      {data.offers.map((o, n) => {
        const left = Math.max(0, Math.floor((new Date(o.expires_at).getTime() - now) / 1000))
        const open = choice === o.id
        return (
          <article key={o.id} className="card" aria-label={`Option ${n + 1}`} data-testid="offer">
            <h3>Option {n + 1}: arrive {clock(o.arrives_at)}{data.original_arrival && ` (planned ${clock(data.original_arrival)})`}</h3>
            <Timeline legs={o.legs.map((l) => ({ departs_at: l.departs_at, arrives_at: l.arrives_at, from: l.from.name, to: l.to.name, mode: l.mode, operator: l.operator, route_code: l.route_code,
              note: l.status === 'delayed' ? `Delayed ${l.delay_minutes} min` : undefined }))} />
            <ul className="muted small">
              {o.legs.map((l, i) => (
                <li key={i}>{l.route_code}: wheelchair vehicle {l.accessibility.wheelchair_vehicle === 'unknown' ? 'not known' : l.accessibility.wheelchair_vehicle}, step-free boarding {l.accessibility.origin_step_free === 'unknown' ? 'not known' : l.accessibility.origin_step_free}</li>
              ))}
            </ul>
            <p>Replaces journey parts worth {money(o.replaced_value, o.currency)} with new parts costing {money(o.replacement_price, o.currency)}.</p>
            <Settlement o={o} />
            <p className="warn small" role="note">{o.availability_warning}</p>
            <p className="muted small">Offer expires in {left > 0 ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}` : 'moments (refresh for new options)'}.</p>
            {!open && <button className="primary" disabled={busy || left === 0} onClick={() => setChoice(o.id)}>Choose this journey</button>}
            {open && (
              <div className="sim-panel" role="group" aria-label="Confirm replacement">
                {o.settlement === 'pay' ? (
                  <>
                    <p>Simulator: an additional payment of <strong>{money(o.difference, o.currency)}</strong> is needed. No real money or card details are used.</p>
                    <div className="actions">
                      <button className="primary" disabled={busy} onClick={() => accept(o, 'success')}>Pay {money(o.difference, o.currency)} (simulated) and confirm</button>
                      <button className="secondary" disabled={busy} onClick={() => accept(o, 'failure')}>Simulate failed payment</button>
                    </div>
                  </>
                ) : (
                  <button className="primary" disabled={busy} onClick={() => accept(o, 'success')}>
                    Confirm replacement{o.settlement === 'refund' ? ' and receive refund (simulated)' : ''}
                  </button>
                )}
                <p><button className="link" disabled={busy} onClick={() => setChoice(null)}>Back to options</button> <button className="link" disabled={busy} onClick={() => decline(o)}>Decline this option</button></p>
              </div>
            )}
          </article>
        )
      })}
      <p><button className="secondary" disabled={busy} onClick={() => load()}>Refresh options</button></p>
    </section>
  )
}
