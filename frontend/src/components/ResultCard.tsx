import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { Link } from 'react-router-dom'
import type { Itinerary, Leg, Tri } from '../api'
import { clock, dayLabel, duration, money, sameDay } from '../format'

const MODE: Record<string, string> = { bus: 'Bus', train: 'Train', taxi: 'Taxi' }
const triText = (label: string, v: Tri) => `${label}: ${v === 'yes' ? t('yes') : v === 'no' ? t('no') : t("not known")}`

function accessSummary(legs: Leg[]) {
  const chair = legs.map((l) => l.accessibility.wheelchair_vehicle)
  const v: Tri = chair.includes('no') ? 'no' : chair.includes('unknown') ? 'unknown' : 'yes'
  return triText(legs.length > 1 ? t("Wheelchair-accessible vehicles (all legs)") : t("Wheelchair-accessible vehicle"), v)
}

export default function ResultCard({ it, comparison, arriveBy }: { it: Itinerary; arriveBy?: string; comparison?: { label: string; selected: boolean; disabled: boolean; toggle: () => void } }) {
  useLanguage()
  const nextDay = !sameDay(it.departs_at, it.arrives_at)
  const delayed = it.legs.filter((l) => l.status === 'delayed')
  const scarce = it.legs.find((l) => l.places_left !== null && l.places_left <= it.passengers + 2)
  return (
    <li className="card result">
      <div className="result-main">
        <p className="times">
          <strong>{clock(it.departs_at)}</strong> → <strong>{clock(it.arrives_at)}</strong>
          {nextDay && <span className="badge">  {t("+1 day (")}{dayLabel(it.arrives_at)})</span>}
        </p>
        <p className="muted">
          {dayLabel(it.departs_at)} · {duration(it.duration_minutes)} ·{' '}
          {it.transfers === 0 ? t("Direct") : t("{0} transfer{1}", {0: it.transfers, 1: it.transfers > 1 ? 's' : ''})}
        </p>
      </div>
      <div className="result-price">
        <p className="price">{money(it.total_price, it.currency)}</p>
        <p className="muted small">{t("For {0} passenger(s)", {0: it.passengers})}</p>
      </div>
      <ol className="route-segments" aria-label={t('Legs')}>{it.legs.map((l, i) => <li className={`route-segment route-segment-${l.mode}`} key={i}><span>{l.mode === 'taxi' ? t(MODE.taxi) : `${t(MODE[l.mode])} ${l.route_code}`}</span></li>)}</ol>
      <div className="result-bottom"><div className="connection-buffer">{it.min_transfer_buffer_minutes !== null && <p>{t('Connection buffer: {0} min', {0: it.min_transfer_buffer_minutes})}</p>}
        {scarce && <p className="warn small">{t('Only {0} place(s) left on {1}. ', {0: scarce.places_left, 1: scarce.route_code})}</p>}
        {delayed.map(l => <p className="warn small" role="status" key={l.route_code + l.departs_at}>{l.route_code}: {t('Delayed by {0} min', {0: l.delay_minutes})}</p>)}
      </div><div className="result-actions">        <Link className="button primary" to={`/journey?${new URLSearchParams({ legs: it.legs_param, passengers: String(it.passengers), total: it.total_price, ...(arriveBy ? { arrive_by: arriveBy } : {}) })}`}>
           {t("Select")}<span className="sr-only"> {clock(it.departs_at)}  {t("departure")}</span>
        </Link>
        {comparison && <label className="compare-choice"><input type="checkbox" aria-label={comparison.label} checked={comparison.selected} disabled={comparison.disabled} onChange={comparison.toggle} />{t("Compare")}{comparison.disabled && <span className="sr-only">  {t("(maximum three selected)")}</span>}</label>}
</div></div>
      <details className="result-details"><summary>{t('Journey information')}</summary>        <ol className="chips" aria-label={t("Legs")}>
          {it.legs.map((l, i) => (
            <li key={i} className={`chip chip-${l.mode}`}>
              {l.mode === 'taxi' ? t(MODE.taxi) : `${t(MODE[l.mode])} ${l.route_code}`}: {placeName(l.from.name)} → {placeName(l.to.name)}
            </li>
          ))}
        </ol>
        {it.min_transfer_buffer_minutes !== null && (
          <p className="small">
             {t("Tightest connection:")} <strong>{it.min_transfer_buffer_minutes}  {t("min")}</strong>  {t("to spare")} <span className="muted">  {t("(extra time beyond the minimum needed to change; not a prediction of punctuality)")}</span>
          </p>
        )}
        {delayed.map((l) => (
          <p key={l.route_code + l.departs_at} className="warn" role="status">
            {l.route_code}  {t("is delayed by")} {l.delay_minutes}  {t("min — times shown include the delay.")} </p>
        ))}
        <p className="muted small">
          {scarce ? t("Only {0} place(s) left on {1}. ", {0: scarce.places_left, 1: scarce.route_code}) : ''}
          {accessSummary(it.legs)}
        </p>
</details>
    </li>
  )
}
