import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, request, type SearchResponse } from '../api'
import { useAuth } from '../authContext'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { cityMatches, defaultSort, normalizePrice, readShared, sharePath, type City, type Plan, type PlanValues, type Sort } from '../kazakhstan'
import ResultCard from './ResultCard'
import JourneyComparison from './JourneyComparison'

export default function KazakhstanPlanner({ cities, search, today, demo = false }: { cities: City[]; search: string; today: string; demo?: boolean }) {
  const language = useLanguage()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [initial] = useState(() => readShared(search, cities))
  const [values, setValues] = useState(initial.values)
  const [queries, setQueries] = useState({ origin: '', destination: '' })
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [plans, setPlans] = useState<Plan[]>([])
  const [listError, setListError] = useState('')
  const [loadingPlans, setLoadingPlans] = useState(!!user)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [shared, setShared] = useState('')
  const [deleting, setDeleting] = useState<number | null>(null)
  const [results, setResults] = useState<SearchResponse | null>(null)
  const sort = initial.sort
  const [refresh, setRefresh] = useState(0)
  const [searching, setSearching] = useState(initial.executed)
  const pending = busy || searching
  const [compared, setCompared] = useState<string[]>([])
  const controller = useRef<AbortController | null>(null)
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    if (user) request<Plan[]>('GET', '/api/kazakhstan/plans/', undefined, { signal: ctrl.signal })
      .then(setPlans).catch(() => { if (!ctrl.signal.aborted) setListError('Could not load your plans. Reload the page to try again.') })
      .finally(() => { if (!ctrl.signal.aborted) setLoadingPlans(false) })
    return () => { ctrl.abort(); controller.current?.abort() }
  }, [user])
  function change(key: keyof PlanValues, value: string) {
    setValues(v => ({ ...v, [key]: value })); setShared(''); setFields({}); setMessage('')
    setResults(null); setCompared([])
  }
  const handleError = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      setFields(error.fields)
      setMessage(error.code === 'provider_not_connected' ? 'Real ticket search is awaiting provider access. No prices or availability have been checked.' : error.fields.detail ?? error.message)
    } else setMessage('Could not reach the server. Check your connection and try again.')
  }, [])
  useEffect(() => {
    if (!initial.executed) return
    const ctrl = new AbortController()
    request<SearchResponse>('GET', `/api/kazakhstan/search/${sharePath(initial.values, true, initial.sort).slice(1)}`, undefined, { signal: ctrl.signal })
      .then(data => { if (!ctrl.signal.aborted) setResults(data) })
      .catch(error => { if (!ctrl.signal.aborted) handleError(error) })
      .finally(() => { if (!ctrl.signal.aborted) setSearching(false) })
    return () => ctrl.abort()
  }, [initial, refresh, handleError])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const action = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') ?? (demo ? 'search' : 'save')
    if (values.origin === values.destination) {
      setFields({ destination: 'Origin and destination must differ.' }); setMessage('Please check the highlighted fields.')
      form.current?.querySelector<HTMLSelectElement>('select[name="destination"]')?.focus()
      return
    }
    setFields({}); setMessage(''); setShared('')
    if (normalizePrice(values.max_price) === null) {
      setFields({ max_price: 'Enter a non-negative amount with at most 10 digits before the decimal point and 2 after.' }); setMessage('Please check the highlighted fields.')
      form.current?.querySelector<HTMLInputElement>('input[name="max_price"]')?.focus()
      return
    }
    if (action === 'share') {
      const url = new URL(sharePath(values, demo, defaultSort(values)), window.location.origin).href
      setShared(url)
      try { await navigator.clipboard.writeText(url); setMessage('Link copied. Private notes are not included.') }
      catch { setMessage('Copy the link below. Private notes are not included.') }
      return
    }
    if (action === 'save' && !user) { setMessage('Sign in to save your plans.'); return }
    if (action === 'search') {
      if (editing !== null) { setMessage('Save or cancel editing before running a new search.'); return }
      setResults(null); setCompared([]); setSearching(true)
      const path = sharePath(values, true)
      if (path.slice(1) === search) setRefresh(value => value + 1)
      else navigate(path)
      return
    }
    const ctrl = new AbortController(); controller.current = ctrl; setBusy(true)
    try {
      const plan = await request<Plan>(editing ? 'PUT' : 'POST', `/api/kazakhstan/plans/${editing ? `${editing}/` : ''}`, { ...values, note, wheelchair_required: values.wheelchair_required === 'true', max_price: normalizePrice(values.max_price) || null }, { signal: ctrl.signal })
      setPlans(old => [plan, ...old.filter(p => p.id !== plan.id)])
      setEditing(null); setNote(''); setMessage('Plan saved. This is not a booking.')
    } catch (error) { if (!ctrl.signal.aborted) handleError(error) }
    finally { if (!ctrl.signal.aborted) setBusy(false) }
  }
  function load(plan: Plan, edit: boolean) {
    setValues({ origin: plan.origin, destination: plan.destination, date: plan.date, time: plan.time.slice(0, 5), passengers: String(plan.passengers), modes: plan.modes, time_mode: plan.time_mode ?? 'departure', wheelchair_required: String(plan.wheelchair_required ?? false), max_price: plan.max_price ?? '' })
    setNote(edit ? plan.note : ''); setEditing(edit ? plan.id : null)
    setQueries({ origin: '', destination: '' }); setFields({}); setShared('')
    setResults(null); setCompared([])
    setMessage(edit ? 'Editing your plan. Update the date if it has passed.' : 'Choose a new date before saving another plan.')
    form.current?.scrollIntoView({ behavior: 'instant', block: 'start' })
    form.current?.querySelector<HTMLInputElement>('input')?.focus()
  }
  async function remove(id: number) {
    setBusy(true); setMessage('')
    const ctrl = new AbortController(); controller.current = ctrl
    try {
      await request('DELETE', `/api/kazakhstan/plans/${id}/`, undefined, { signal: ctrl.signal })
      setPlans(old => old.filter(p => p.id !== id)); setDeleting(null)
      if (editing === id) { setEditing(null); setNote('') }
      setMessage('Plan deleted.')
    } catch (error) { if (!ctrl.signal.aborted) handleError(error) }
    finally { if (!ctrl.signal.aborted) setBusy(false) }
  }
  const errorFor = (name: string) => fields[name] ? <span className="field-error" id={`kz-${name}-error`}>{t(fields[name])}</span> : null
  const fieldProps = (name: string) => ({ 'aria-invalid': !!fields[name], 'aria-describedby': fields[name] ? `kz-${name}-error` : undefined })
  const arriveBy = results?.arrive_by ?? (initial.values.time_mode === 'arrival' ? `${initial.values.date}T${initial.values.time}:00+05:00` : undefined)
  const wheelchairRequired = initial.values.wheelchair_required === 'true'
  const cityName = (id: string) => cities.find(c => c.id === id)?.name[language] ?? id
  return <>
    {initial.invalid && <p className="kz-notice">{t('Some link parameters were invalid and have been reset. Check the form before continuing.')}</p>}
    <form ref={form} className="card" onSubmit={submit} aria-label={t('Kazakhstan journey search')} aria-busy={pending}>
      <h2>{t(editing ? 'Edit plan' : 'Plan a journey')}</h2>
      <p>{t(demo ? 'Search simulated journeys between Kazakhstan cities, then reserve and try the payment simulator. A saved plan does not hold a place.' : 'A plan is not a booking. No seats, fares or departure times are confirmed.')}</p>
      <fieldset disabled={pending} className="kz-fields search-form">
        {(['origin', 'destination'] as const).map((name, index) => {
          const matches = cities.filter(city => cityMatches(city, queries[name]))
          const options = cities.filter(city => city.id === values[name] || matches.includes(city))
          return <div className="field" key={name}>
            <label htmlFor={`kz-filter-${name}`}>{t(index === 0 ? 'Find departure city' : 'Find arrival city')}</label>
            <input id={`kz-filter-${name}`} type="search" value={queries[name]} placeholder={t('City or region in any of three languages')} onChange={e => setQueries(q => ({ ...q, [name]: e.target.value }))} />
            {queries[name] && <span className="small muted" role="status">{t('{0} matching cities. Your selection stays until you change it.', { 0: matches.length })}</span>}
            <label htmlFor={`kz-select-${name}`}>{t(index === 0 ? 'From' : 'To')}</label>
            <select id={`kz-select-${name}`} name={name} value={values[name]} onChange={e => change(name, e.target.value)} {...fieldProps(name)}>
              {options.map(city => <option value={city.id} key={city.id}>{city.name[language]} — {city.region[language]}</option>)}
            </select>{errorFor(name)}
          </div>
        })}
        <button type="button" className="button" onClick={() => { setValues(v => ({ ...v, origin: v.destination, destination: v.origin })); setQueries({ origin: '', destination: '' }); setFields({}); setShared(''); setResults(null); setCompared([]) }}>{t('Swap cities')}</button>
        <label className="field">{t('Time preference')}<select name="time_mode" value={values.time_mode} onChange={e => change('time_mode', e.target.value)} {...fieldProps('time_mode')}><option value="departure">{t('Depart after')}</option><option value="arrival">{t('Arrive by')}</option></select>{errorFor('time_mode')}</label>
        <label className="field">{t('Date')}<input name="date" type="date" required value={values.date} onChange={e => change('date', e.target.value)} {...fieldProps('date')} />{errorFor('date')}</label>
        <label className="field">{t(values.time_mode === 'arrival' ? 'Arrival deadline (UTC+5)' : 'Departure time (UTC+5)')}<input name="time" type="time" required value={values.time} onChange={e => change('time', e.target.value)} {...fieldProps('time')} />{errorFor('time')}</label>
        <label className="field">{t('Passengers')}<input name="passengers" type="number" min="1" max="9" required value={values.passengers} onChange={e => change('passengers', e.target.value)} {...fieldProps('passengers')} />{errorFor('passengers')}</label>
        <label className="field">{t('Transport')}<select name="modes" value={values.modes} onChange={e => change('modes', e.target.value)} {...fieldProps('modes')}><option value="bus,train">{t('Bus and train')}</option><option value="bus">{t('Bus')}</option><option value="train">{t('Train')}</option></select>{errorFor('modes')}</label>
        <label className="field">{t('Maximum total price (KZT)')}<input name="max_price" type="text" inputMode="decimal" maxLength={13} value={values.max_price} placeholder={t('No maximum')} onChange={e => change('max_price', e.target.value.replace(',', '.'))} {...fieldProps('max_price')} aria-describedby={`kz-price-help${fields.max_price ? ' kz-max_price-error' : ''}`} /><span className="small muted" id="kz-price-help">{t('Optional limit for all passengers together, not per person.')}</span>{errorFor('max_price')}</label>
        <label className="check"><input name="wheelchair_required" type="checkbox" checked={values.wheelchair_required === 'true'} onChange={e => change('wheelchair_required', String(e.target.checked))} {...fieldProps('wheelchair_required')} aria-describedby={`kz-access-help${fields.wheelchair_required ? ' kz-wheelchair_required-error' : ''}`} />{t('Require a fully step-free journey')}{errorFor('wheelchair_required')}</label>
        <p className="small muted" id="kz-access-help">{t('Only confirmed accessible vehicles, stops and transfer paths. Unknown accessibility is excluded.')}</p>
        {user && <label className="field kz-note">{t('Private note')}<textarea maxLength={1000} value={note} onChange={e => setNote(e.target.value)} {...fieldProps('note')} />{errorFor('note')}<span className="small muted">{t('Only you can see this note. It is never included in shared links.')}</span></label>}
      </fieldset>
      <div className="kz-actions">
        <button type="submit" className={demo ? 'primary' : undefined} value="search" disabled={pending || editing !== null} aria-describedby={editing !== null ? 'kz-edit-search-help' : undefined}>{t(pending ? 'Please wait…' : demo ? 'Search demo journeys' : 'Check search availability')}</button>
        {user ? <button value="save" disabled={pending}>{t(editing ? 'Save changes' : 'Save plan')}</button> : <Link to="/login" state={{ from: sharePath(values) }}>{t('Sign in to save your plans.')}</Link>}
        <button type="submit" value="share" disabled={pending}>{t('Share journey')}</button>
        {editing && <button type="button" disabled={pending} onClick={() => { setEditing(null); setNote(''); setFields({}); setMessage('') }}>{t('Cancel editing')}</button>}
      </div>
      {editing !== null && <p id="kz-edit-search-help" className="small muted">{t('Save or cancel editing before running a new search.')}</p>}
    </form>
    {searching && <p role="status">{t('Searching…')}</p>}
    {message && <p role={Object.keys(fields).length ? 'alert' : 'status'} className="kz-notice">{t(message)}</p>}
    {shared && <label className="field">{t('Journey link')}<input readOnly value={shared} onFocus={e => e.currentTarget.select()} /></label>}
    {results && <section aria-labelledby="kz-results-heading">
      <h2 id="kz-results-heading" aria-live="polite">{t('Results')} · {results.results.length}</h2>
      <p className="muted">{t('Demo journeys · KZT · Kazakhstan time (UTC+5). No real tickets.')}</p>
      {initial.values.time_mode === 'arrival' && <p className="muted">{t('Arriving by {0} at {1} (UTC+5); departures within the preceding 24 hours. Some journeys may start the previous day.', { 0: initial.values.date, 1: initial.values.time })}</p>}
      {!results.results.length ? <p role="status">{t('No demo journeys match your time, transport, accessibility and price limit. Try another time or a higher price limit.')}</p> : <>
        <label className="field">{t('Sort by')}<select value={sort} onChange={e => navigate(sharePath(initial.values, true, e.target.value as Sort))}><option value="departure">{t('Earliest departure')}</option><option value="latest_departure">{t('Latest departure')}</option><option value="price">{t('Lowest price')}</option><option value="duration">{t('Shortest duration')}</option></select></label>
        <JourneyComparison arriveBy={arriveBy} wheelchairRequired={wheelchairRequired} options={compared.flatMap(key => { const it = results.results.find(value => value.legs_param === key); return it ? [it] : [] })} clear={() => setCompared([])} remove={key => setCompared(old => old.filter(k => k !== key))} />
        <ul className="result-list">{results.results.map((it, index) => <ResultCard key={it.legs_param} it={it} arriveBy={arriveBy} wheelchairRequired={wheelchairRequired} comparison={{ label: t('Compare journey {0}', { 0: index + 1 }), selected: compared.includes(it.legs_param), disabled: compared.length >= 3 && !compared.includes(it.legs_param), toggle: () => setCompared(old => old.includes(it.legs_param) ? old.filter(key => key !== it.legs_param) : old.length < 3 ? [...old, it.legs_param] : old) }} />)}</ul>
      </>}
    </section>}
    {user && <section className="kz-plans" id="my-plans" aria-label={t('My plans')}><h2>{t('My plans')}</h2>
      {loadingPlans && <p role="status">{t('Loading…')}</p>}
      {listError && <p role="alert">{t(listError)}</p>}
      {!loadingPlans && !listError && !plans.length && <p>{t('No plans yet. Save your first journey above.')}</p>}
      <ul className="result-list">{plans.map(plan => <li className="card" key={plan.id}>
        <h3>{cityName(plan.origin)} → {cityName(plan.destination)}</h3>
        <p>{plan.date} · {t(plan.time_mode === 'arrival' ? 'Arrive by' : 'Depart after')} {plan.time.slice(0, 5)} UTC+5 · {t('Passengers')}: {plan.passengers} · {t(plan.modes === 'bus,train' ? 'Bus and train' : plan.modes === 'bus' ? 'Bus' : 'Train')}</p>
        {plan.wheelchair_required && <p className="small">{t('Require a fully step-free journey')}</p>}
        {plan.max_price != null && <p className="small">{t('Maximum total price (KZT)')}: {plan.max_price}</p>}
        <p className="muted">{t('Not a booking')}{plan.date < today ? ` · ${t('Past date — choose a new date to reuse this plan.')}` : ''}</p>
        {plan.note && <p className="kz-private-note">{plan.note}</p>}
        <div className="kz-actions"><button disabled={pending} onClick={() => load(plan, true)}>{t('Edit plan')}</button><button disabled={pending} onClick={() => load(plan, false)}>{t('Repeat plan')}</button>
          <button disabled={pending} onClick={() => setDeleting(plan.id)}>{t('Delete plan')}</button></div>
        {deleting === plan.id && <div className="kz-actions"><span>{t('Delete this saved plan?')}</span><button disabled={pending} onClick={() => void remove(plan.id)}>{t('Confirm deletion')}</button><button disabled={pending} onClick={() => setDeleting(null)}>{t('Cancel')}</button></div>}
      </li>)}</ul>
    </section>}
  </>
}
