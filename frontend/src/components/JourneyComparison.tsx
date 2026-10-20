import { Link } from 'react-router-dom'
import type { Itinerary } from '../api'
import { explainDifference } from '../comparison'
import { clock, dayLabel, duration, money } from '../format'

export default function JourneyComparison({ options, remove, clear, arriveBy }: { options: Itinerary[]; remove: (key: string) => void; clear: () => void; arriveBy?: string }) {
  if (!options.length) return null
  return <section className="comparison card" aria-labelledby="comparison-heading">
    <div className="saved-heading"><h2 id="comparison-heading">Compare journeys ({options.length}/3)</h2><button className="link" onClick={clear}>Clear comparison</button></div>
    <p className="muted">{options.length === 1 ? 'Choose one or two more journeys below to compare.' : 'Differences are relative to the first selected journey. Prices cover everyone in your search.'}</p>
    <div className="comparison-grid">{options.map((it, index) => <article className="comparison-option" key={it.legs_param}>
      <h3>Option {index + 1}{index === 0 ? ' · Reference' : ''}</h3>
      <p className="comparison-price">{money(it.total_price, it.currency)}</p>
      <dl>
        <dt>Departure</dt><dd>{dayLabel(it.departs_at)}, {clock(it.departs_at)}</dd>
        <dt>Arrival</dt><dd>{dayLabel(it.arrives_at)}, {clock(it.arrives_at)}</dd>
        <dt>Journey time</dt><dd>{duration(it.duration_minutes)}</dd>
        <dt>Transport</dt><dd>{it.legs.map(l => l.mode).join(' → ')}</dd>
        <dt>Transfers</dt><dd>{it.transfers === 0 ? 'Direct' : it.transfers}</dd>
        <dt>Tightest connection buffer</dt><dd>{it.min_transfer_buffer_minutes === null ? 'No transfer' : `${it.min_transfer_buffer_minutes} min`}</dd>
        <dt>Cancellation policies</dt><dd>{[...new Set(it.legs.map(l => l.cancellation_policy))].join('; ')}</dd>
      </dl>
      {index > 0 && <ul className="comparison-facts" aria-label={`Option ${index + 1} differences`}>{explainDifference(it, options[0]).map(fact => <li key={fact}>{fact}</li>)}</ul>}
      <div className="actions"><Link className="button primary" to={`/journey?${new URLSearchParams({ legs: it.legs_param, passengers: String(it.passengers), total: it.total_price, ...(arriveBy ? { arrive_by: arriveBy } : {}) })}`}>View option {index + 1}</Link><button className="link" onClick={() => remove(it.legs_param)}>Remove option {index + 1}</button></div>
    </article>)}</div>
    <p className="small muted">Connection buffers are timetable margins, not predictions of punctuality. Prices and availability are checked again before booking. Changing the search clears this comparison.</p>
  </section>
}
