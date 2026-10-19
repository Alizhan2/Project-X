import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, fetchStops, searchJourneys, type SearchResponse, type Stop } from '../api'
import ResultCard from '../components/ResultCard'

type Results =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; data: SearchResponse }
  | { kind: 'error'; message: string; fields: Record<string, string> }

const today = () => new Date().toLocaleDateString('en-CA')

export default function Search() {
  const [params, setParams] = useSearchParams()
  const [stops, setStops] = useState<Stop[] | null>(null)
  const [stopsError, setStopsError] = useState<string | null>(null)
  const [results, setResults] = useState<Results>({ kind: 'idle' })

  const [origin, setOrigin] = useState(params.get('origin') ?? '')
  const [destination, setDestination] = useState(params.get('destination') ?? '')
  const [date, setDate] = useState(params.get('date') ?? today())
  const [time, setTime] = useState(params.get('time') ?? '06:00')
  const [passengers, setPassengers] = useState(params.get('passengers') ?? '1')
  const sort = params.get('sort') ?? 'departure'
  const maxTransfers = params.get('max_transfers') ?? 'any'

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
    }
  }, [params])

  useEffect(() => {
    if (!query) return
    const ctrl = new AbortController()
    setResults({ kind: 'loading' })
    searchJourneys(query, ctrl.signal)
      .then((data) => setResults({ kind: 'done', data }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        if (e instanceof ApiError) setResults({ kind: 'error', message: e.message, fields: e.fields })
        else setResults({ kind: 'error', message: 'Could not reach the server.', fields: {} })
      })
    return () => ctrl.abort()
  }, [query])

  const shown = results.kind === 'done'
    ? results.data.results.filter((it) => maxTransfers === 'any' || it.transfers <= Number(maxTransfers))
    : []
  const fieldErr = results.kind === 'error' ? results.fields : {}

  function submit(e: FormEvent) {
    e.preventDefault()
    setParams({ origin, destination, date, time, passengers, sort })
  }

  function changeParam(name: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(name, value)
    setParams(next)
  }

  const err = (name: string) => fieldErr[name] && <span id={`${name}-err`} className="field-error">{fieldErr[name]}</span>
  const aria = (name: string) => (fieldErr[name] ? { 'aria-invalid': true, 'aria-describedby': `${name}-err` } : {})

  return (
    <>
      <h1>Plan your journey</h1>
      {stopsError && <p className="status-bad" role="alert">Could not load stops: {stopsError}</p>}
      <form className="card search-form" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="origin">From</label>
          <select id="origin" required value={origin} onChange={(e) => setOrigin(e.target.value)} {...aria('origin')}>
            <option value="">Choose a stop…</option>
            {stops?.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
          {err('origin')}
        </div>
        <div className="field">
          <label htmlFor="destination">To</label>
          <select id="destination" required value={destination} onChange={(e) => setDestination(e.target.value)} {...aria('destination')}>
            <option value="">Choose a stop…</option>
            {stops?.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
          {err('destination')}
        </div>
        <div className="field">
          <label htmlFor="date">Date</label>
          <input id="date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} {...aria('depart_after')} />
          {err('depart_after')}
        </div>
        <div className="field">
          <label htmlFor="time">Earliest departure</label>
          <input id="time" type="time" required value={time} onChange={(e) => setTime(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="passengers">Passengers</label>
          <input id="passengers" type="number" min={1} max={9} required value={passengers} onChange={(e) => setPassengers(e.target.value)} {...aria('passengers')} />
          {err('passengers')}
        </div>
        <button type="submit" className="primary" disabled={!origin || !destination}>Search journeys</button>
      </form>

      <section aria-labelledby="results-h" aria-live="polite" className="results">
        <h2 id="results-h">Results</h2>
        {results.kind === 'idle' && <p className="muted">Choose where you are travelling and search.</p>}
        {results.kind === 'loading' && <p>Searching…</p>}
        {results.kind === 'error' && <p className="status-bad" role="alert">{results.message}</p>}
        {results.kind === 'done' && (
          <>
            <div className="results-bar">
              <p>
                {shown.length} of {results.data.count} journey(s) shown, departing in the next {results.data.window_hours} hours{' '}
                <span className="badge">Simulated data</span>
              </p>
              <div className="field">
                <label htmlFor="max-transfers">Transfers</label>
                <select id="max-transfers" value={maxTransfers} onChange={(e) => changeParam('max_transfers', e.target.value)}>
                  <option value="any">Any number</option>
                  <option value="0">Direct only</option>
                  <option value="1">At most 1</option>
                </select>
              </div>
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
                {shown.map((it) => <ResultCard key={it.legs_param} it={it} />)}
              </ul>
            )}
          </>
        )}
      </section>
    </>
  )
}
