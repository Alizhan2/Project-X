import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, createBooking, fetchSavedTravellers, saveTraveller, type SavedTraveller } from '../api'
import SavedTravellers from '../components/SavedTravellers'
import { useAuth } from '../auth'
import LegSummary from '../components/LegSummary'
import { useItinerary } from '../hooks'
import { money } from '../format'

export default function Book() {
  useLanguage()
  const [p] = useSearchParams()
  const legs = p.get('legs') ?? '', passengers = p.get('passengers') ?? '1'
  const [expected, setExpected] = useState(p.get('total') ?? '')
  const { user } = useAuth()
  const nav = useNavigate()
  const arriveBy = p.get('arrive_by') || undefined
  const st = useItinerary(legs, passengers, arriveBy)
  const n = Number(passengers)
  const [names, setNames] = useState<string[]>(() => Array.from({ length: n }, (_, i) => (i === 0 ? (user?.name ?? '') : '')))
  const [email, setEmail] = useState(user?.email ?? '')
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<SavedTraveller[]>([])
  const [keepNames, setKeepNames] = useState(false)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchSavedTravellers(ctrl.signal).then(setSaved).catch(() => undefined)   // a convenience: failure just hides the shortcuts
    return () => ctrl.abort()
  }, [])
  const savedKeys = new Set(saved.map(s => s.full_name.toLowerCase()))
  const newNames = names.map(x => x.trim()).filter(x => x && !savedKeys.has(x.toLowerCase()))
  const useSaved = (name: string) => setNames(old => { const i = old.findIndex(x => x.trim() === ''); return i < 0 ? old : old.map((x, j) => (j === i ? name : x)) })
  // One key per form instance: a double click or retry replays the same checkout instead of booking twice.
  const key = useRef(crypto.randomUUID())

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (st.kind !== 'ready') return
    setBusy(true); setErr(null)
    try {
      const booking = await createBooking({
        passengers: n, contact_email: email, travellers: names, expected_total: expected || undefined,
        legs: st.data.selection, arrive_by: arriveBy,
      }, key.current)
      if (keepNames) await Promise.allSettled(newNames.map(saveTraveller))   // optional; never blocks or fails the booking
      nav(`/booking/${booking.reference}/pay`, { replace: true })
    } catch (x) {
      setErr(x instanceof ApiError ? x : new ApiError(t("Something went wrong.")))
    } finally { setBusy(false) }
  }

  const changedTotal = err?.code === 'offer_changed' ? String(err.data.new_total) : null
  return (
    <>
      <h1>{t("Traveller details")}</h1>
      {arriveBy && <p>{t("Arrive by")} {arriveBy.replace('T', ' ')}  {t("(Europe/Berlin). The deadline is checked again when reserving.")}</p>}
      {st.kind === 'loading' && <p>{t("Loading journey…")}</p>}
      {st.kind === 'error' && <div className="card" role="alert"><p className="status-bad">{st.error.message}</p><Link to="/">{t("Search again")}</Link></div>}
      {st.kind === 'ready' && (
        <div className="two-col">
          <form className="card" onSubmit={submit} noValidate>
            {err && !changedTotal && (
              <div role="alert" className="status-bad">
                <p>{t(err.message)}</p>
                {['unavailable', 'no_capacity', 'invalid_leg', 'arrival_deadline_missed'].includes(err.code ?? '') && <p><Link to="/">{t("Search again")}</Link></p>}
              </div>
            )}
            {changedTotal && (
              <div role="alert" className="warn">
                <p>{t("The price changed to")} {money(changedTotal, st.data.currency)}.</p>
                <button type="button" className="primary" onClick={() => { setExpected(changedTotal); setErr(null) }}>{t("Accept new price")}</button>
              </div>
            )}
            <div className="field">
              <label htmlFor="contact">{t("Contact email")}</label>
              <input id="contact" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!err?.fields.contact_email} />
              {err?.fields.contact_email && <span className="field-error">{t(err.fields.contact_email)}</span>}
            </div>
            <SavedTravellers saved={saved} names={names} onUse={useSaved} />
            {names.map((v, i) => (
              <div className="field" key={i}>
                <label htmlFor={`t${i}`}>{t("Passenger")} {i + 1}  {t("full name")}</label>
                <input id={`t${i}`} required value={v} onChange={(e) => setNames(names.map((x, j) => (j === i ? e.target.value : x)))} />
              </div>
            ))}
            {newNames.length > 0 && (
              <label className="check"><input type="checkbox" checked={keepNames} onChange={e => setKeepNames(e.target.checked)} /> {t('Save new names to my account for faster checkout (names only; you can remove them in My journeys).')}</label>
            )}
            {err?.fields.travellers && <p className="field-error">{t(err.fields.travellers)}</p>}
            <p className="muted small">{t("We only keep names and a contact email. No documents or card details are collected.")}</p>
            <button className="primary" type="submit" disabled={busy}>{t("Reserve and continue to payment")}</button>
          </form>
          <aside className="card" aria-label={t("Order summary")}>
            <h2>{t("Summary")}</h2>
            <LegSummary it={st.data} />
            <p className="price-line">{t("Total:")} <strong>{money(st.data.total_price, st.data.currency)}</strong></p>
          </aside>
        </div>
      )}
    </>
  )
}
