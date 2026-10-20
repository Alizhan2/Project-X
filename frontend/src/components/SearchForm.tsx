import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useState, type FormEvent } from 'react'
import type { SetURLSearchParams } from 'react-router-dom'
import type { Stop } from '../api'
import { regionToday as today } from '../format'

export default function SearchForm({ params, setParams, stops, fieldErr }: { params: URLSearchParams; setParams: SetURLSearchParams; stops: Stop[] | null; fieldErr: Record<string, string> }) {
  useLanguage()
  const [origin, setOrigin] = useState(params.get('origin') ?? '')
  const [destination, setDestination] = useState(params.get('destination') ?? '')
  const [date, setDate] = useState(params.get('date') ?? today())
  const [time, setTime] = useState(params.get('time') ?? '06:00')
  const [passengers, setPassengers] = useState(params.get('passengers') ?? '1')
  const [timeMode, setTimeMode] = useState(params.get('time_mode') === 'arrival' ? 'arrival' : 'departure')
  const timeField = timeMode === 'arrival' ? 'arrive_by' : 'depart_after'

  function submit(e: FormEvent) {
    e.preventDefault()
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries({ origin, destination, date, time, passengers, time_mode: timeMode })) next.set(key, value)
    if ((params.get('time_mode') ?? 'departure') !== timeMode) next.delete('sort')
    next.delete('repeat')
    setParams(next)
  }
  const err = (name: string) => fieldErr[name] && <span id={`${name}-err`} className="field-error">{t(fieldErr[name])}</span>
  const aria = (name: string) => fieldErr[name] ? { 'aria-invalid': true, 'aria-describedby': `${name}-err` } : {}
  return (
      <form className="card search-form" onSubmit={submit} noValidate>
        <div className="field time-mode-field">
          <label htmlFor="time-mode">{t("Journey time")}</label>
          <select id="time-mode" value={timeMode} onChange={e => setTimeMode(e.target.value)}>
            <option value="departure">{t("Depart after")}</option>
            <option value="arrival">{t("Arrive by")}</option>
          </select>
          <span className="muted small">{t("All times use Europe/Berlin.")}</span>
        </div>
        <div className="field search-origin">
          <label htmlFor="origin">{t("From")}</label>
          <select id="origin" required value={origin} onChange={(e) => setOrigin(e.target.value)} {...aria('origin')}>
            <option value="">{t("Choose a stop…")}</option>
            {stops?.map((s) => <option key={s.code} value={s.code}>{placeName(s.name)}</option>)}
          </select>
          {err('origin')}
        </div>
        <div className="field search-destination">
          <label htmlFor="destination">{t("To")}</label>
          <select id="destination" required value={destination} onChange={(e) => setDestination(e.target.value)} {...aria('destination')}>
            <option value="">{t("Choose a stop…")}</option>
            {stops?.map((s) => <option key={s.code} value={s.code}>{placeName(s.name)}</option>)}
          </select>
          {err('destination')}
        </div>
        <div className="field">
          <label htmlFor="date">{timeMode === 'arrival' ? t("Arrival date") : t("Date")}</label>
          <input id="date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} {...aria(timeField)} />
          {err(timeField)}
        </div>
        <div className="field">
          <label htmlFor="time">{timeMode === 'arrival' ? t("Arrive no later than") : t("Earliest departure")}</label>
          <input id="time" type="time" required value={time} onChange={(e) => setTime(e.target.value)} {...aria(timeField)} />
        </div>
        <div className="field">
          <label htmlFor="passengers">{t("Passengers")}</label>
          <input id="passengers" type="number" min={1} max={9} required value={passengers} onChange={(e) => setPassengers(e.target.value)} {...aria('passengers')} />
          {err('passengers')}
        </div>
        <button type="submit" className="primary" disabled={!origin || !destination}>{t("Search journeys")}</button>
      </form>
  )
}
