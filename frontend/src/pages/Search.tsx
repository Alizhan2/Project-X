import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, fetchStops, searchJourneys, type SearchResponse, type Stop } from '../api'
import ResultCard from '../components/ResultCard'
import SearchForm from '../components/SearchForm'
import FavoriteRoutes from '../components/FavoriteRoutes'
import JourneyComparison from '../components/JourneyComparison'
import { regionToday } from '../format'

type Results =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; data: SearchResponse }
  | { kind: 'error'; message: string; fields: Record<string, string> }

const today = regionToday

export default function Search() {
  const [params, setParams] = useSearchParams()
  const [stops, setStops] = useState<Stop[] | null>(null)
  const [stopsError, setStopsError] = useState<string | null>(null)
  const scope = params.toString()
  const [response, setResponse] = useState<{ key: string; value: Results } | null>(null)

  const sort = params.get('sort') ?? 'departure'
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
      depart_after: `${params.get('date') ?? today()}T${params.get('time') ?? '06:00'}`,
      passengers: params.get('passengers') ?? '1',
      sort: params.get('sort') ?? 'departure',
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
        else setResponse({ key: scope, value: { kind: 'error', message: 'Could not reach the server.', fields: {} } })
      })
    return () => ctrl.abort()
  }, [query, scope])

  const results: Results = response?.key === scope ? response.value : { kind: query ? 'loading' : 'idle' }
  const shown = results.kind === 'done'
    ? results.data.results
    : []
  const fieldErr = results.kind === 'error' ? results.fields : {}

  function changeParam(name: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(name, value)
    setParams(next)
  }

  const err = (name: string) => fieldErr[name] && <span id={`${name}-err`} className="field-error">{fieldErr[name]}</span>
  const aria = (name: string) => (fieldErr[name] ? { 'aria-invalid': true, 'aria-describedby': `${name}-err` } : {})

  return (
    <>
      <section className="journey-intro">
        <div><h1>Plan your journey</h1><p>From your first stop to your final destination.<br />Find buses, trains and taxis that connect.</p></div>
        <div className="route-ribbon" aria-label="Travel by bus, train and taxi"><span>Bus</span><i aria-hidden="true" /><span>Train</span><i aria-hidden="true" /><span>Taxi</span></div>
      </section>
      {params.get("repeat") === "1" && <p className="email-notice">A new search for this direction. Choose your travel date; prices and availability are current. No previous booking is changed.</p>}
      {stopsError && <p className="status-bad" role="alert">Could not load stops: {stopsError}</p>}
      <SearchForm key={JSON.stringify(['origin', 'destination', 'date', 'time', 'passengers'].map(k => params.get(k)))} params={params} setParams={setParams} stops={stops} fieldErr={fieldErr} />

      <section className="search-filters" aria-label="Journey filters">
        <fieldset><legend>Transport</legend><div className="mode-options">{['bus', 'train', 'taxi'].map(mode => <label key={mode}>
          <input type="checkbox" checked={modes.split(',').includes(mode)} disabled={modes === mode} onChange={e => {
            const next = e.target.checked ? [...modes.split(','), mode] : modes.split(',').filter(m => m !== mode)
            changeParam('modes', next.sort().join(','))
          }} />{mode[0].toUpperCase() + mode.slice(1)}
        </label>)}</div>{err('modes')}</fieldset>
        <div className="field"><label htmlFor="max-transfers">Transfers</label>
          <select id="max-transfers" value={maxTransfers} onChange={e => changeParam('max_transfers', e.target.value)} {...aria('max_transfers')}>
            <option value="any">Any number (up to 2)</option><option value="0">Direct only</option><option value="1">At most 1</option><option value="2">At most 2</option>
          </select>{err('max_transfers')}
        </div>
        <div className="field"><label htmlFor="max-connection">Maximum connection time</label>
          <select id="max-connection" value={maxConnection} onChange={e => changeParam('max_connection_minutes', e.target.value)} {...aria('max_connection_minutes')}>
            <option value="">Any available</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">1 hour</option><option value="120">2 hours</option><option value="180">3 hours</option>
          </select><span className="muted small">From arrival to next departure, including walking.</span>{err('max_connection_minutes')}
        </div>
      </section>
      <FavoriteRoutes origin={params.get('origin') ?? ''} destination={params.get('destination') ?? ''} />
      <JourneyComparison options={compared.flatMap(key => shown.filter(it => it.legs_param === key))} remove={key => setCompared(old => old.filter(k => k !== key))} clear={() => setCompared(() => [])} />
      <section aria-labelledby="results-h" aria-live="polite" className="results">
        <h2 id="results-h">Results</h2>
        {results.kind === 'idle' && <p className="muted">Choose where you are travelling and search.</p>}
        {results.kind === 'loading' && <p>Searching…</p>}
        {results.kind === 'error' && <p className="status-bad" role="alert">{results.message}</p>}
        {results.kind === 'done' && (
          <>
            <div className="results-bar">
              <p>
                {shown.length} matching journey(s), departing in the next {results.data.window_hours} hours{' '}
                <span className="badge">Simulated data</span>
              </p>
              <div className="field">
                <label htmlFor="sort">Sort by</label>
                <select id="sort" value={sort} onChange={(e) => changeParam('sort', e.target.value)}>
                  <option value="departure">Earliest departure</option>
                  <option value="price">Lowest price</option>
                  <option value="duration">Shortest duration</option>
                  <option value="buffer">Largest transfer buffer</option>
                </select>
              </div>
            </div>
            {shown.length === 0 ? (
              <div className="card empty">
                <p><strong>No journeys found.</strong></p>
                <p className="muted">
                  Try another date or time, fewer passengers, relaxing the transfer filter, or a different stop. Cancelled
                  services, services without enough free places, and impossible connections are not shown.
                </p>
              </div>
            ) : (
              <ul className="result-list">
                {shown.map((it, index) => <ResultCard key={it.legs_param} it={it} comparison={{
                  label: `Compare journey ${index + 1}`, selected: compared.includes(it.legs_param), disabled: compared.length >= 3 && !compared.includes(it.legs_param),
                  toggle: () => setCompared(old => old.includes(it.legs_param) ? old.filter(k => k !== it.legs_param) : old.length < 3 ? [...old, it.legs_param] : old),
                }} />)}
              </ul>
            )}
          </>
        )}
      </section>
    </>
  )
}
