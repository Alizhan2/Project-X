import { Link } from 'react-router-dom'
import type { Itinerary, Leg, Tri } from '../api'
import { clock, dayLabel, duration, money, sameDay } from '../format'

const MODE: Record<string, string> = { bus: 'Bus', train: 'Train', taxi: 'Taxi' }
const triText = (label: string, v: Tri) => `${label}: ${v === 'yes' ? 'yes' : v === 'no' ? 'no' : 'not known'}`

function accessSummary(legs: Leg[]) {
  const chair = legs.map((l) => l.accessibility.wheelchair_vehicle)
  const v: Tri = chair.includes('no') ? 'no' : chair.includes('unknown') ? 'unknown' : 'yes'
  return triText(legs.length > 1 ? 'Wheelchair-accessible vehicles (all legs)' : 'Wheelchair-accessible vehicle', v)
}

export default function ResultCard({ it }: { it: Itinerary }) {
  const nextDay = !sameDay(it.departs_at, it.arrives_at)
  const delayed = it.legs.filter((l) => l.status === 'delayed')
  const scarce = it.legs.find((l) => l.places_left !== null && l.places_left <= it.passengers + 2)
  return (
    <li className="card result">
      <div className="result-main">
        <p className="times">
          <strong>{clock(it.departs_at)}</strong> → <strong>{clock(it.arrives_at)}</strong>
          {nextDay && <span className="badge"> +1 day ({dayLabel(it.arrives_at)})</span>}
        </p>
        <p className="muted">
          {dayLabel(it.departs_at)} · {duration(it.duration_minutes)} ·{' '}
          {it.transfers === 0 ? 'Direct' : `${it.transfers} transfer${it.transfers > 1 ? 's' : ''}`}
        </p>
        <ol className="chips" aria-label="Legs">
          {it.legs.map((l, i) => (
            <li key={i} className={`chip chip-${l.mode}`}>
              {l.mode === 'taxi' ? MODE.taxi : `${MODE[l.mode]} ${l.route_code}`}: {l.from.name} → {l.to.name}
            </li>
          ))}
        </ol>
        {it.min_transfer_buffer_minutes !== null && (
          <p className="small">
            Tightest connection: <strong>{it.min_transfer_buffer_minutes} min</strong> to spare
            <span className="muted"> (extra time beyond the minimum needed to change; not a prediction of punctuality)</span>
          </p>
        )}
        {delayed.map((l) => (
          <p key={l.route_code + l.departs_at} className="warn" role="status">
            {l.route_code} is delayed by {l.delay_minutes} min — times shown include the delay.
          </p>
        ))}
        <p className="muted small">
          {scarce ? `Only ${scarce.places_left} place(s) left on ${scarce.route_code}. ` : ''}
          {accessSummary(it.legs)}
        </p>
      </div>
      <div className="result-price">
        <p className="price">{money(it.total_price, it.currency)}</p>
        <p className="muted small">for {it.passengers} passenger(s)</p>
        <Link className="button primary" to={`/journey?${new URLSearchParams({ legs: it.legs_param, passengers: String(it.passengers), total: it.total_price })}`}>
          Select<span className="sr-only"> {clock(it.departs_at)} departure</span>
        </Link>
      </div>
    </li>
  )
}
