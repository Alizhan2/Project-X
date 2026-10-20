import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, request } from '../api'
import { useAuth } from '../auth'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { cityMatches, readShared, sharePath, type City, type Plan, type PlanValues } from '../kazakhstan'

export default function KazakhstanPlanner({ cities, search, today }: { cities: City[]; search: string; today: string }) {
  const language = useLanguage()
  const { user } = useAuth()
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
  }
  function handleError(error: unknown) {
    if (error instanceof ApiError) {
      setFields(error.fields)
      setMessage(error.code === 'provider_not_connected' ? 'Real ticket search is awaiting provider access. No prices or availability have been checked.' : error.fields.detail ?? error.message)
    } else setMessage('Could not reach the server. Check your connection and try again.')
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const action = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') ?? 'save'
    if (values.origin === values.destination) { setFields({ destination: 'Origin and destination must differ.' }); return }
    setFields({}); setMessage(''); setShared('')
    if (action === 'share') {
      const url = new URL(sharePath(values), window.location.origin).href
      setShared(url)
      try { await navigator.clipboard.writeText(url); setMessage('Link copied. Private notes are not included.') }
      catch { setMessage('Copy the link below. Private notes are not included.') }
      return
    }
    if (action === 'save' && !user) { setMessage('Sign in to save your plans.'); return }
    const ctrl = new AbortController(); controller.current = ctrl; setBusy(true)
    try {
      if (action === 'search') {
        await request('GET', `/api/kazakhstan/search/${sharePath(values).slice('/kazakhstan'.length)}`, undefined, { signal: ctrl.signal })
        setMessage('Real ticket sales are not yet available.')
      } else {
        const plan = await request<Plan>(editing ? 'PUT' : 'POST', `/api/kazakhstan/plans/${editing ? `${editing}/` : ''}`, { ...values, note }, { signal: ctrl.signal })
        setPlans(old => [plan, ...old.filter(p => p.id !== plan.id)])
        setEditing(null); setNote(''); setMessage('Plan saved. This is not a booking.')
      }
    } catch (error) { if (!ctrl.signal.aborted) handleError(error) }
    finally { if (!ctrl.signal.aborted) setBusy(false) }
  }
  function load(plan: Plan, edit: boolean) {
    setValues({ origin: plan.origin, destination: plan.destination, date: plan.date, time: plan.time.slice(0, 5), passengers: String(plan.passengers), modes: plan.modes })
    setNote(edit ? plan.note : ''); setEditing(edit ? plan.id : null)
    setQueries({ origin: '', destination: '' }); setFields({}); setShared('')
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
  const cityName = (id: string) => cities.find(c => c.id === id)?.name[language] ?? id
  return <>
    {initial.invalid && <p className="kz-notice">{t('Some link parameters were invalid and have been reset. Check the form before continuing.')}</p>}
    <form ref={form} className="card" onSubmit={submit} aria-label={t('Kazakhstan journey search')}>
      <h2>{t(editing ? 'Edit plan' : 'Plan a journey')}</h2>
      <p>{t('A plan is not a booking. No seats, fares or departure times are confirmed.')}</p>
      <fieldset disabled={busy} className="kz-fields search-form">
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
        <button type="button" className="button" onClick={() => { setValues(v => ({ ...v, origin: v.destination, destination: v.origin })); setQueries({ origin: '', destination: '' }); setFields({}); setShared('') }}>{t('Swap cities')}</button>
        <label className="field">{t('Date')}<input name="date" type="date" required value={values.date} onChange={e => change('date', e.target.value)} {...fieldProps('date')} />{errorFor('date')}</label>
        <label className="field">{t('Departure time (UTC+5)')}<input name="time" type="time" required value={values.time} onChange={e => change('time', e.target.value)} {...fieldProps('time')} />{errorFor('time')}</label>
        <label className="field">{t('Passengers')}<input name="passengers" type="number" min="1" max="9" required value={values.passengers} onChange={e => change('passengers', e.target.value)} {...fieldProps('passengers')} />{errorFor('passengers')}</label>
        <label className="field">{t('Transport')}<select name="modes" value={values.modes} onChange={e => change('modes', e.target.value)}><option value="bus,train">{t('Bus and train')}</option><option value="bus">{t('Bus')}</option><option value="train">{t('Train')}</option></select></label>
        {user && <label className="field kz-note">{t('Private note')}<textarea maxLength={1000} value={note} onChange={e => setNote(e.target.value)} {...fieldProps('note')} />{errorFor('note')}<span className="small muted">{t('Only you can see this note. It is never included in shared links.')}</span></label>}
      </fieldset>
      <div className="kz-actions">
        {user ? <button className="primary" value="save" disabled={busy}>{t(editing ? 'Save changes' : 'Save plan')}</button> : <Link to="/login" state={{ from: sharePath(values) }}>{t('Sign in to save your plans.')}</Link>}
        <button type="submit" value="share" disabled={busy}>{t('Share journey')}</button>
        <button type="submit" value="search" disabled={busy}>{t('Check search availability')}</button>
        {editing && <button type="button" disabled={busy} onClick={() => { setEditing(null); setNote(''); setFields({}); setMessage('') }}>{t('Cancel editing')}</button>}
      </div>
    </form>
    {message && <p role="status" className="kz-notice">{t(message)}</p>}
    {shared && <label className="field">{t('Journey link')}<input readOnly value={shared} onFocus={e => e.currentTarget.select()} /></label>}
    {user && <section className="kz-plans" aria-label={t('My plans')}><h2>{t('My plans')}</h2>
      {loadingPlans && <p role="status">{t('Loading…')}</p>}
      {listError && <p role="alert">{t(listError)}</p>}
      {!loadingPlans && !listError && !plans.length && <p>{t('No plans yet. Save your first journey above.')}</p>}
      <ul className="result-list">{plans.map(plan => <li className="card" key={plan.id}>
        <h3>{cityName(plan.origin)} → {cityName(plan.destination)}</h3>
        <p>{plan.date} · {plan.time.slice(0, 5)} UTC+5 · {t('Passengers')}: {plan.passengers} · {t(plan.modes === 'bus,train' ? 'Bus and train' : plan.modes === 'bus' ? 'Bus' : 'Train')}</p>
        <p className="muted">{t('Not a booking')}{plan.date < today ? ` · ${t('Past date — choose a new date to reuse this plan.')}` : ''}</p>
        {plan.note && <p className="kz-private-note">{plan.note}</p>}
        <div className="kz-actions"><button disabled={busy} onClick={() => load(plan, true)}>{t('Edit plan')}</button><button disabled={busy} onClick={() => load(plan, false)}>{t('Repeat plan')}</button>
          <button disabled={busy} onClick={() => setDeleting(plan.id)}>{t('Delete plan')}</button></div>
        {deleting === plan.id && <div className="kz-actions"><span>{t('Delete this saved plan?')}</span><button disabled={busy} onClick={() => void remove(plan.id)}>{t('Confirm deletion')}</button><button disabled={busy} onClick={() => setDeleting(null)}>{t('Cancel')}</button></div>}
      </li>)}</ul>
    </section>}
  </>
}
