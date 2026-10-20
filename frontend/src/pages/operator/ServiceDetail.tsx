import { placeName, t } from '../../i18n'
import { useLanguage } from '../../useLanguage'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, opChange, opEdit, opFare, opImpact, opRoutes, opService, type Impact, type OpRoute, type OpService } from '../../api'
import { clock, dayLabel } from '../../format'

const REASON: Record<string, string> = { service_cancelled: 'service cancelled', connection_missed: 'connection missed', taxi_unavailable: 'taxi outside service hours' }

export default function ServiceDetail() {
  useLanguage()
  const { id = '' } = useParams()
  const [s, setS] = useState<OpService | null>(null)
  const [route, setRoute] = useState<OpRoute | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [capacity, setCapacity] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [action, setAction] = useState<'delay' | 'cancel'>('delay')
  const [minutes, setMinutes] = useState('15')
  const [impact, setImpact] = useState<Impact | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const svc = await opService(id)
      setS(svc); setCapacity(String(svc.capacity))
      const routes = await opRoutes()
      setRoute(routes.results.find((r) => r.code === svc.route_code) ?? null)
    } catch (e) { setErr(e instanceof ApiError ? e : new ApiError(t("Unexpected error."))) }
  }, [id])
  useEffect(() => { load() }, [load])

  if (err) return <p className="status-bad" role="alert">{err.status === 404 ? t("Service not found (it may belong to another operator).") : t(err.message)}</p>
  if (!s) return <p>{t("Loading…")}</p>

  async function saveCapacity(e: FormEvent) {
    e.preventDefault(); setMsg(null)
    try { await opEdit(s!.id, { capacity: Number(capacity) }); setMsg(t("Capacity saved.")); load() }
    catch (x) { setMsg(x instanceof ApiError ? (x.fields.capacity ?? x.message) : t("Unexpected error.")) }
  }
  async function preview() {
    setMsg(null); setImpact(null)
    try { setImpact(await opImpact(s!.id, action, action === 'delay' ? Number(minutes) : 0)) }
    catch (x) { setMsg(x instanceof ApiError ? x.message : t("Unexpected error.")) }
  }
  async function apply() {
    setBusy(true); setMsg(null)
    try {
      const r = await opChange(s!.id, action, action === 'delay' ? Number(minutes) : 0)
      setMsg(r.noop ? t("No change: the service was already in that state.") : t("Applied. {0} booking(s) were notified.", {0: r.affected_bookings}))
      setImpact(null); load()
    } catch (x) { setMsg(x instanceof ApiError ? x.message : t("Unexpected error.")) } finally { setBusy(false) }
  }
  async function saveFare(fareId: number, price: string) {
    try { await opFare(fareId, price); setMsg(t("Fare saved. Existing bookings keep the price they paid.")); load() }
    catch (x) { setMsg(x instanceof ApiError ? (x.fields.price ?? x.message) : t("Unexpected error.")) }
  }

  const closed = s.status === 'cancelled'
  return (
    <>
      <p><Link to="/operator">{t("← All services")}</Link></p>
      <h1>{s.route_code} · {dayLabel(s.departs_at)} {clock(s.departs_at)}</h1>
      <p className="muted">{placeName(s.first_stop)} → {placeName(s.last_stop)} · <span className={`badge status-${s.status}`}>{t(s.status)}{s.status === 'delayed' ? t(" +{0} min", {0: s.delay_minutes}) : ''}</span></p>
      {msg && <p role="status" className="card">{t(msg)}</p>}

      <section className="card" aria-labelledby="cap-h">
        <h2 id="cap-h">{t("Capacity")}</h2>
        <p>{s.places_taken}  {t("of")} {s.capacity}  {t("places booked or held.")}</p>
        <form onSubmit={saveCapacity} className="inline-form">
          <div className="field"><label htmlFor="capacity">{t("Capacity")}</label><input id="capacity" type="number" min={s.places_taken || 1} value={capacity} onChange={(e) => setCapacity(e.target.value)} /></div>
          <button className="secondary" type="submit">{t("Save capacity")}</button>
        </form>
      </section>

      <section className="card" aria-labelledby="chg-h">
        <h2 id="chg-h">{t("Delay or cancel")}</h2>
        {closed ? <p>{t("This service is cancelled.")}</p> : (
          <>
            <div className="inline-form">
              <div className="field"><label htmlFor="action">{t("Change")}</label>
                <select id="action" value={action} onChange={(e) => { setAction(e.target.value as 'delay' | 'cancel'); setImpact(null) }}>
                  <option value="delay">{t("Set delay")}</option><option value="cancel">{t("Cancel service")}</option>
                </select></div>
              {action === 'delay' && (
                <div className="field"><label htmlFor="minutes">{t("Total delay (minutes, 0 clears)")}</label>
                  <input id="minutes" type="number" min={0} max={720} value={minutes} onChange={(e) => { setMinutes(e.target.value); setImpact(null) }} /></div>
              )}
              <button className="secondary" onClick={preview}>{t("Preview consequences")}</button>
            </div>
            {impact && (
              <div role="region" aria-label={t("Consequences")} className="card">
                <h3>{t("Consequences")}</h3>
                <p data-testid="impact-summary">{impact.affected.length}  {t("booking(s),")} {impact.passengers}  {t("passenger(s) affected;")} {impact.broken}  {t("journey(s) would be broken.")}</p>
                {impact.affected.length > 0 && (
                  <table className="legs">
                    <thead><tr><th scope="col">{t("Booking")}</th><th scope="col">{t("Passengers")}</th><th scope="col">{t("Effect")}</th></tr></thead>
                    <tbody>{impact.affected.map((a) => (
                      <tr key={a.reference}><th scope="row">{a.reference}</th><td>{a.passengers}</td>
                        <td>{a.after === 'broken' ? t("Journey broken: {0}", {0: t(REASON[a.reason] ?? a.reason)}) : a.after === 'delayed' ? t("Delayed, connections hold") : t("No effect")}</td></tr>
                    ))}</tbody>
                  </table>
                )}
                <p className="muted small">{t("Affected passengers are notified and offered cancellation with refund. Passenger contact details are not shown.")}</p>
                <button className={`primary ${action === 'cancel' ? 'danger' : ''}`} disabled={busy} onClick={apply}>
                  {action === 'cancel' ? t("Confirm cancellation of service") : t("Confirm delay of {0} min", {0: minutes})}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {route && (
        <section className="card" aria-labelledby="fare-h">
          <h2 id="fare-h">{t("Fares (per passenger)")}</h2>
          <table className="legs">
            <thead><tr><th scope="col">{t("From → to")}</th><th scope="col">{t("Price (")}{route.fares[0]?.currency})</th><th scope="col"><span className="sr-only">{t("Save")}</span></th></tr></thead>
            <tbody>{route.fares.map((f) => <FareRow key={f.id} fare={f} onSave={saveFare} />)}</tbody>
          </table>
        </section>
      )}

      {s.events && s.events.length > 0 && (
        <section className="card" aria-labelledby="hist-h">
          <h2 id="hist-h">{t("Change history")}</h2>
          <ul>{s.events.map((e, i) => <li key={i}>{dayLabel(e.created_at)} {clock(e.created_at)} — {t(e.kind)}{e.kind === 'delay' ? t(" {0} min", {0: e.delay_minutes}) : ''}, {e.affected_bookings}  {t("booking(s) affected")}</li>)}</ul>
        </section>
      )}
    </>
  )
}

function FareRow({ fare, onSave }: { fare: OpRoute['fares'][number]; onSave: (id: number, price: string) => void }) {
  useLanguage()
  const [price, setPrice] = useState(fare.price)
  return (
    <tr>
      <th scope="row">{placeName(fare.from)} → {placeName(fare.to)}</th>
      <td><label className="sr-only" htmlFor={`fare-${fare.id}`}>{t("Price")} {placeName(fare.from)}  {t("to")} {placeName(fare.to)}</label>
        <input id={`fare-${fare.id}`} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></td>
      <td><button className="secondary" onClick={() => onSave(fare.id, price)}>{t("Save")}<span className="sr-only">  {t("fare")} {placeName(fare.from)}  {t("to")} {placeName(fare.to)}</span></button></td>
    </tr>
  )
}
