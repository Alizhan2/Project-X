import { placeName, t } from '../../i18n'
import { useLanguage } from '../../useLanguage'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, opServices, type OpService } from '../../api'
import { clock, dayLabel } from '../../format'
import ScrollTable from '../../components/ScrollTable'

export default function Services() {
  useLanguage()
  const [rows, setRows] = useState<OpService[] | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => { opServices().then((r) => setRows(r.results)).catch((e: unknown) => setErr(e instanceof ApiError ? e : new ApiError(t("Unexpected error.")))) }, [])
  return (
    <>
      <h1>{t("My services")}</h1>
      <p><Link className="button primary" to="/operator/new">{t("Create a service")}</Link></p>
      {err && <p className="status-bad" role="alert">{t(err.message)}</p>}
      {!rows && !err && <p>{t("Loading…")}</p>}
      {rows && rows.length === 0 && <div className="card empty"><p>{t("You have no upcoming services.")}</p></div>}
      {rows && rows.length > 0 && (
        <ScrollTable label={t("Services table")}>
        <table className="legs card" data-testid="services-table">
          <caption className="sr-only">{t("Upcoming services of your operator")}</caption>
          <thead><tr><th scope="col">{t("Service")}</th><th scope="col">{t("Departs")}</th><th scope="col">{t("Status")}</th><th scope="col">{t("Booked / capacity")}</th><th scope="col"><span className="sr-only">{t("Actions")}</span></th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <th scope="row">{s.route_code} <span className="muted small">{placeName(s.first_stop)} → {placeName(s.last_stop)}</span></th>
                <td>{dayLabel(s.departs_at)} {clock(s.departs_at)}</td>
                <td><span className={`badge status-${s.status}`}>{t(s.status)}{s.status === 'delayed' ? t(" +{0} min", {0: s.delay_minutes}) : ''}</span></td>
                <td>{s.places_taken} / {s.capacity}</td>
                <td><Link to={`/operator/services/${s.id}`}>{t("Manage")}<span className="sr-only"> {s.route_code} {clock(s.departs_at)}</span></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
        </ScrollTable>
      )}
    </>
  )
}
