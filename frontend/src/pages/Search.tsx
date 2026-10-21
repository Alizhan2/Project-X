import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, fetchStops, searchJourneys, type SearchResponse, type Stop } from '../api'
import ResultCard from '../components/ResultCard'
import SearchForm from '../components/SearchForm'
import FavoriteRoutes from '../components/FavoriteRoutes'
import JourneyComparison from '../components/JourneyComparison'
import UpcomingJourney from '../components/UpcomingJourney'
import JourneyHero, { JourneyBenefits } from '../components/JourneyHero'
import DayStrip from '../components/DayStrip'
import WatchPrompt from '../components/WatchPrompt'
import { regionToday } from '../format'

type Results =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; data: SearchResponse }
  | { kind: 'error'; message: string; fields: Record<string, string> }

const today = regionToday

export default function Search() {
  useLanguage()
  const [params, setParams] = useSearchParams()
  const [editing, setEditing] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [stops, setStops] = useState<Stop[] | null>(null)
  const [stopsError, setStopsError] = useState<string | null>(null)
  const scope = params.toString()
  const [response, setResponse] = useState<{ key: string; value: Results } | null>(null)

  const arrivalMode = params.get('time_mode') === 'arrival'
  const arriveBy = arrivalMode ? `${params.get('date') ?? today()}T${params.get('time') ?? '06:00'}` : undefined
  const sort = params.get('sort') ?? (arrivalMode ? 'latest_departure' : 'departure')
  const maxTransfers = params.get('max_transfers') ?? 'any'
  const modes = params.get('modes') ?? 'bus,train,taxi'
  const maxConnection = params.get('max_connection_minutes') ?? ''
  const [selection, setSelection] = useState<{ key: string; ids: string[] }>({ key: scope, ids: [] })
  // Reset on a new search, including history navigation; never restore a stale comparison.
  if (selection.key !== scope) setSelection({ key: scope, ids: [] })
  const compared = selection.key === scope ? selection.ids : []
  const setCompared = (update: (old: string[]) => string[]) => setSelection(old => ({ key: scope, ids: update(old.key === scope ? old.ids : []) }))

  useEffect(() => {
    const ctrl = new AbortController()
    fetchStops(ctrl.signal)
      .then(setStops)
      .catch((e: unknown) => { if (!ctrl.signal.aborted) setStopsError(e instanceof Error ? e.message : String(e)) })
    return () => ctrl.abort()
  }, [])

  // The URL is the source of truth for an executed search, so results are linkable and survive reload.
  const query = useMemo(() => {
    const o = params.get('origin'), d = params.get('destination')
    if (!o || !d) return null
    return {
      origin: o, destination: d,
      ...(params.get('time_mode') === 'arrival' ? { arrive_by: `${params.get('date') ?? today()}T${params.get('time') ?? '06:00'}` } : { depart_after: `${params.get('date') ?? today()}T${params.get('time') ?? '06:00'}` }),
      passengers: params.get('passengers') ?? '1',
      sort: params.get('sort') ?? (params.get('time_mode') === 'arrival' ? 'latest_departure' : 'departure'),
      modes: params.get('modes') ?? 'bus,train,taxi',
      max_transfers: params.get('max_transfers') ?? 'any',
      max_connection_minutes: params.get('max_connection_minutes') ?? '',
    }
  }, [params])

  useEffect(() => {
    if (!query) return
    const ctrl = new AbortController()
    searchJourneys(query, ctrl.signal)
      .then((data) => { if (!ctrl.signal.aborted) setResponse({ key: scope, value: { kind: 'done', data } }) })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        if (e instanceof ApiError) setResponse({ key: scope, value: { kind: 'error', message: e.message, fields: e.fields } })
        else setResponse({ key: scope, value: { kind: 'error', message: t("Could not reach the server."), fields: {} } })
      })
    return () => ctrl.abort()
  }, [query, scope])

  const results: Results = response?.key === scope ? response.value : { kind: query ? 'loading' : 'idle' }
  const shown = results.kind === 'done'
    ? results.data.results
    : []
  // The alert is described by the same server-side parameters the search used, with modes in canonical order.
  const MODE_ORDER = ['bus', 'train', 'taxi']
  const watchSearch = query && {
    origin: query.origin, destination: query.destination, date: params.get('date') ?? today(), time: params.get('time') ?? '06:00',
    passengers: Number(query.passengers), modes: query.modes.split(',').sort((a, b) => MODE_ORDER.indexOf(a) - MODE_ORDER.indexOf(b)).join(','),
  }
  const cheapest = results.kind === 'done' && results.data.results.length
    ? results.data.results.reduce((best, r) => (Number(r.total_price) < Number(best.total_price) ? r : best))
    : null
  const fieldErr = results.kind === 'error' ? results.fields : {}

  function changeParam(name: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(name, value)
    setParams(next)
  }

  const err = (name: string) => fieldErr[name] && <span id={`${name}-err`} className="field-error">{t(fieldErr[name])}</span>
  const aria = (name: string) => (fieldErr[name] ? { 'aria-invalid': true, 'aria-describedby': `${name}-err` } : {})

  return (
    <>
      {!query ? <JourneyHero /> : <header className="search-results-heading"><h1>{t('Choose your journey')}</h1>{results.kind === 'done' && <span className="badge">{t('{0} journeys', {0: shown.length})}</span>}</header>}
      <UpcomingJourney />
      {params.get("repeat") === "1" && <p className="email-notice">{t("A new search for this direction. Choose your travel date; prices and availability are current. No previous booking is changed.")}</p>}
      {stopsError && <p className="status-bad" role="alert">{t("Could not load stops:")} {t(stopsError)}</p>}
      {query && <div className="search-summary"><div><strong>{placeName(stops?.find(s => s.code === params.get('origin'))?.name ?? params.get('origin') ?? '')} → {placeName(stops?.find(s => s.code === params.get('destination'))?.name ?? params.get('destination') ?? '')}</strong><p>{params.get('date')} · {arrivalMode ? t('Arrive by') : t('Depart after')} {params.get('time') ?? '06:00'} · {t('For {0} passenger(s)', {0: params.get('passengers') ?? '1'})}</p></div><button type="button" className="secondary" aria-expanded={editing} aria-controls="journey-search" onClick={() => setEditing(!editing)}>{t('Change search')}</button></div>}
      <div id="journey-search" hidden={!!query && !editing && results.kind !== 'error'}>
      <SearchForm key={JSON.stringify(['origin', 'destination', 'date', 'time', 'passengers', 'time_mode'].map(k => params.get(k)))} params={params} setParams={setParams} stops={stops} fieldErr={fieldErr} />
      </div>
      {!query && <JourneyBenefits />}

      {query && <>
      {!arrivalMode && <DayStrip origin={query.origin} destination={query.destination} date={params.get('date') ?? today()} time={params.get('time') ?? '06:00'} passengers={query.passengers} modes={query.modes} onPick={date => changeParam('date', date)} />}
      {!arrivalMode && results.kind === 'done' && <WatchPrompt search={watchSearch!} cheapest={cheapest ? { price: cheapest.total_price, currency: cheapest.currency } : null} />}
      <JourneyComparison arriveBy={arriveBy} options={compared.flatMap(key => shown.filter(it => it.legs_param === key))} remove={key => setCompared(old => old.filter(k => k !== key))} clear={() => setCompared(() => [])} />

      <div className="search-workspace">
      <section id="journey-filters" data-open={filtersOpen} className="search-filters" aria-label={t("Journey filters")}>
        <h2>{t('Filters')}</h2>
        <fieldset><legend>{t("Transport")}</legend><div className="mode-options">{['bus', 'train', 'taxi'].map(mode => <label key={mode}>
          <input type="checkbox" checked={modes.split(',').includes(mode)} disabled={modes === mode} onChange={e => {
            const next = e.target.checked ? [...modes.split(','), mode] : modes.split(',').filter(m => m !== mode)
            changeParam('modes', next.sort().join(','))
          }} />{t(mode[0].toUpperCase() + mode.slice(1))}
        </label>)}</div>{err('modes')}</fieldset>
        <div className="field"><label htmlFor="max-transfers">{t("Transfers")}</label>
          <select id="max-transfers" value={maxTransfers} onChange={e => changeParam('max_transfers', e.target.value)} {...aria('max_transfers')}>
            <option value="any">{t("Any number (up to 2)")}</option><option value="0">{t("Direct only")}</option><option value="1">{t("At most 1")}</option><option value="2">{t("At most 2")}</option>
          </select>{err('max_transfers')}
        </div>
        <div className="field"><label htmlFor="max-connection">{t("Maximum connection time")}</label>
          <select id="max-connection" value={maxConnection} onChange={e => changeParam('max_connection_minutes', e.target.value)} {...aria('max_connection_minutes')}>
            <option value="">{t("Any available")}</option><option value="15">{t("15 minutes")}</option><option value="30">{t("30 minutes")}</option><option value="60">{t("1 hour")}</option><option value="120">{t("2 hours")}</option><option value="180">{t("3 hours")}</option>
          </select><span className="muted small">{t("From arrival to next departure, including walking.")}</span>{err('max_connection_minutes')}
        </div>
      </section>
      <section aria-labelledby="results-h" aria-live="polite" aria-busy={results.kind === 'loading'} className="results">
        <div className="results-bar">
          <button type="button" className="secondary mobile-filter-toggle" aria-expanded={filtersOpen} aria-controls="journey-filters" onClick={() => setFiltersOpen(!filtersOpen)}>{t('Filters')}</button>
          <h2 id="results-h" className="sr-only">{t("Results")}</h2>
          <div className="sort-tabs" aria-label={t('Sort results')}>{[['departure', 'Earliest departure'], ['price', 'Lowest price'], ['duration', 'Shortest duration'], ['buffer', 'Largest transfer buffer']].map(([value, label]) => <button type="button" key={value} aria-pressed={sort === value} onClick={() => changeParam('sort', value)}>{t(label)}</button>)}</div>
          {query && <div className="field">
            <label htmlFor="sort">{t("Sort by")}</label>
            <select id="sort" value={sort} onChange={e => changeParam('sort', e.target.value)}>
              <option value="departure">{t("Earliest departure")}</option>
              <option value="latest_departure">{t("Latest departure")}</option>
              <option value="price">{t("Lowest price")}</option>
              <option value="duration">{t("Shortest duration")}</option>
              <option value="buffer">{t("Largest transfer buffer")}</option>
            </select>
          </div>}
        </div>
        {results.kind === 'idle' && <p className="muted">{t("Choose where you are travelling and search.")}</p>}
        {results.kind === 'loading' && <><p role="status">{t("Searching…")}</p><ul className="result-list" aria-hidden="true">{[0, 1, 2].map(i => <li key={i} className="card result-skeleton"><span className="skeleton" /><span className="skeleton" /><span className="skeleton" /></li>)}</ul></>}
        {results.kind === 'error' && <p className="status-bad" role="alert">{t(results.message)}</p>}
        {results.kind === 'done' && (
          <>
            <div className="results-bar">
              <p>
                {shown.length}  {t("matching journey(s).")} {arrivalMode ? t("Arriving by {0} at {1} (Europe/Berlin); departures within the preceding {2} hours. Some journeys may start the previous day.", {0: params.get('date'), 1: params.get('time') ?? '06:00', 2: results.data.window_hours}) : t("Departing in the next {0} hours.", {0: results.data.window_hours})}{' '}
                <span className="badge">{t("Simulated data")}</span>
              </p>
            </div>
            {shown.length === 0 ? (
              <div className="card empty">
                <p><strong>{t("No journeys found.")}</strong></p>
                <p className="muted">
                  {arrivalMode ? t("Try a later arrival deadline, ") : t("Try another date or time, ")}{t("fewer passengers, relaxing the transfer filter, or a different stop. Cancelled services, services without enough free places, and impossible connections are not shown.")} </p>
              </div>
            ) : (
              <ul className="result-list">
                {shown.map((it, index) => <ResultCard key={it.legs_param} it={it} arriveBy={arriveBy} comparison={{
                  label: t("Compare journey {0}", {0: index + 1}), selected: compared.includes(it.legs_param), disabled: compared.length >= 3 && !compared.includes(it.legs_param),
                  toggle: () => setCompared(old => old.includes(it.legs_param) ? old.filter(k => k !== it.legs_param) : old.length < 3 ? [...old, it.legs_param] : old),
                }} />)}
              </ul>
            )}
          </>
        )}
      </section>
      </div>
      <p className="results-explanation muted small">{t('Connection buffer is spare time beyond the minimum transfer, including walking. It is not a punctuality prediction. Taxi prices are per vehicle.')}</p>
      <FavoriteRoutes origin={params.get('origin') ?? ''} destination={params.get('destination') ?? ''} />
      </>}
    </>
  )
}
