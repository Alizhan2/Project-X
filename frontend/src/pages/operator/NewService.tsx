import { placeName, t } from '../../i18n'
import { useLanguage } from '../../useLanguage'
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, opCreate, opRoutes, type OpRoute } from '../../api'

export default function NewService() {
  useLanguage()
  const nav = useNavigate()
  const [routes, setRoutes] = useState<OpRoute[]>([])
  const [routeId, setRouteId] = useState('')
  const [when, setWhen] = useState('')
  const [capacity, setCapacity] = useState('40')
  const [wheelchair, setWheelchair] = useState('unknown')
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => { opRoutes().then((r) => setRoutes(r.results)).catch(() => undefined) }, [])

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null)
    try {
      const s = await opCreate({
        route_id: Number(routeId), departs_at: new Date(when).toISOString(), capacity: Number(capacity),
        wheelchair_accessible: wheelchair === 'unknown' ? null : wheelchair === 'yes',
      })
      nav(`/operator/services/${s.id}`)
    } catch (x) { setErr(x instanceof ApiError ? x : new ApiError(t("Unexpected error."))) }
  }
  const f = (n: string) => err?.fields[n] ? t(err.fields[n]) : undefined
  return (
    <section className="card narrow">
      <h1>{t("Create a service")}</h1>
      {err && !Object.keys(err.fields).length && <p className="status-bad" role="alert">{t(err.message)}</p>}
      <form onSubmit={submit} noValidate>
        <div className="field"><label htmlFor="route">{t("Route")}</label>
          <select id="route" required value={routeId} onChange={(e) => setRouteId(e.target.value)}>
            <option value="">{t("Choose a route…")}</option>
            {routes.map((r) => <option key={r.id} value={r.id}>{r.code} — {placeName(r.name)}</option>)}
          </select></div>
        <div className="field"><label htmlFor="when">{t("Departure (your local time)")}</label>
          <input id="when" type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} aria-invalid={!!f('departs_at')} />
          {f('departs_at') && <span className="field-error">{f('departs_at')}</span>}</div>
        <div className="field"><label htmlFor="cap">{t("Capacity (passengers)")}</label>
          <input id="cap" type="number" min={1} max={500} required value={capacity} onChange={(e) => setCapacity(e.target.value)} aria-invalid={!!f('capacity')} />
          {f('capacity') && <span className="field-error">{f('capacity')}</span>}</div>
        <div className="field"><label htmlFor="wc">{t("Wheelchair-accessible vehicle")}</label>
          <select id="wc" value={wheelchair} onChange={(e) => setWheelchair(e.target.value)}>
            <option value="unknown">{t("Not known")}</option><option value="yes">{t("Yes")}</option><option value="no">{t("No")}</option>
          </select></div>
        {f('detail') && <p className="field-error">{f('detail')}</p>}
        <button className="primary" type="submit" disabled={!routeId || !when}>{t("Create service")}</button>
      </form>
    </section>
  )
}
