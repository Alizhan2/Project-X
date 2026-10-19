import type { Itinerary, Tri } from '../api'
import { money } from '../format'
import Timeline from './Timeline'

const tri = (v: Tri) => (v === 'yes' ? 'yes' : v === 'no' ? 'no' : 'not known')

export default function LegSummary({ it }: { it: Itinerary }) {
  return (
    <>
      <Timeline buffers={it.transfer_buffers} legs={it.legs.map((l) => ({
        departs_at: l.departs_at, arrives_at: l.arrives_at, from: l.from.name, to: l.to.name, mode: l.mode,
        operator: l.operator, route_code: l.route_code,
        note: l.status === 'delayed' ? `Delayed by ${l.delay_minutes} min (times include the delay)` : undefined,
      }))} />
      <table className="legs">
        <caption className="sr-only">Fare and accessibility per leg</caption>
        <thead><tr><th scope="col">Leg</th><th scope="col">Fare</th><th scope="col">Accessibility</th><th scope="col">Cancellation</th></tr></thead>
        <tbody>
          {it.legs.map((l) => (
            <tr key={`${l.route_code}-${l.departs_at}`}>
              <th scope="row">{l.route_code} {l.from.name} → {l.to.name}</th>
              <td>{money(l.unit_price, it.currency)} {l.price_basis === 'vehicle' ? 'per taxi (up to 4 passengers)' : 'per passenger'}</td>
              <td>Wheelchair vehicle: {tri(l.accessibility.wheelchair_vehicle)}<br />Step-free at boarding: {tri(l.accessibility.origin_step_free)}<br />Step-free at arrival: {tri(l.accessibility.destination_step_free)}</td>
              <td>{l.cancellation_policy}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
