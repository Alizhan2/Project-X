import { useEffect, useState } from 'react'
import { fetchSearchDays, type SearchDay } from '../api'
import { dayLabel, duration, money } from '../format'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'

interface Props { origin: string; destination: string; date: string; time: string; passengers: string; modes: string; onPick: (date: string) => void }

/** Cheapest and fastest journey for the days around the chosen one (a price calendar). Failure is silent: it is a convenience. */
export default function DayStrip({ origin, destination, date, time, passengers, modes, onPick }: Props) {
  useLanguage()
  const key = [origin, destination, date, time, passengers, modes].join('|')
  const [state, setState] = useState<{ key: string; days: SearchDay[] } | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchSearchDays({ origin, destination, date, time, passengers, modes }, ctrl.signal)
      .then(r => { if (!ctrl.signal.aborted) setState({ key, days: r.days }) })
      .catch(() => undefined)
    return () => ctrl.abort()
  }, [key, origin, destination, date, time, passengers, modes])

  const days = state?.key === key ? state.days : null
  const prices = (days ?? []).filter(d => d.cheapest_price !== null).map(d => Number(d.cheapest_price))
  // A "lowest price" badge only means something when prices differ between days.
  const lowest = prices.length > 1 && Math.min(...prices) < Math.max(...prices) ? Math.min(...prices) : null
  return (
    <section className="day-strip" aria-labelledby="days-h">
      <h2 id="days-h" className="sr-only">{t('Nearby days')}</h2>
      {!days ? (
        <ul className="day-strip-list" aria-hidden="true">{Array.from({ length: 7 }, (_, i) => <li key={i}><span className="skeleton day-skeleton" /></li>)}</ul>
      ) : (
        <ul className="day-strip-list">
          {days.map(d => {
            const selected = d.date === date
            const isLowest = lowest !== null && d.cheapest_price !== null && Number(d.cheapest_price) === lowest
            return (
              <li key={d.date}>
                <button type="button" className="day-chip" aria-current={selected ? 'date' : undefined} disabled={d.count === 0 && !selected} onClick={() => onPick(d.date)}>
                  <span className="day-chip-date">{dayLabel(d.date)}</span>
                  {d.cheapest_price !== null && d.currency
                    ? <><strong>{money(d.cheapest_price, d.currency)}</strong><span className="day-chip-meta">{t('Fastest {0}', { 0: duration(d.fastest_minutes ?? 0) })}</span></>
                    : <span className="day-chip-meta">{t('No journeys')}</span>}
                  {isLowest && <span className="day-chip-badge">{t('Lowest price')}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
