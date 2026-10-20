import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchUpcoming, type TravelPlan } from '../api'
import { useAuth } from '../authContext'
import { clock, dayLabel } from '../format'

export default function UpcomingJourney() {
  useLanguage()
  const { user } = useAuth()
  return user ? <Upcoming key={user.id} /> : null
}

function Upcoming() {
  useLanguage()
  const [plan, setPlan] = useState<TravelPlan | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try {
        const data = await fetchUpcoming(controller.signal)
        if (!controller.signal.aborted) { setPlan(data.journey); setError(false); setLoaded(true) }
      } catch {
        if (!controller.signal.aborted) { setError(true); setLoaded(true) }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 15000)
      }
    }
    void refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [])
  if (!loaded) return <p className="muted">{t("Checking your next journey…")}</p>
  if (error) return <p role="status" className="warn">{t("Could not refresh your next journey.")} <Link to="/journeys">{t("Open My journeys")}</Link></p>
  if (!plan) return <p className="muted small">{t("Your next confirmed journey will appear here.")}</p>
  const first = plan.legs[0], last = plan.legs[plan.legs.length - 1]
  const next = plan.legs.find(leg => leg.sequence === plan.next_sequence)
  return <section className="card upcoming-journey" aria-labelledby="upcoming-title">
    <div>
      <p className="eyebrow">{t("YOUR NEXT JOURNEY")}</p>
      <h2 id="upcoming-title">{placeName(first.from)} → {placeName(last.to)}</h2>
      <p className="upcoming-time">{clock(first.departs_at)} <span>{dayLabel(first.departs_at)}</span></p>
      {plan.status === 'broken' ? <p className="status-bad">{t("Journey disrupted. Review a replacement or cancellation.")}</p> :
        <p>{plan.progress === 'in_progress' ? t("Journey in progress according to the timetable.") : t("Upcoming departure.")}{plan.status === 'delayed' ? t(" Times updated after a delay.") : ''}</p>}
      {next && plan.status !== 'broken' && <p className="muted">{next.state === 'travelling' ? t("Current leg") : t("Next leg")}: {t(next.mode)} {next.route_code} · {placeName(next.from)} → {placeName(next.to)} · {clock(next.departs_at)}</p>}
      <p className="small muted">{t("Timetable estimate, not GPS. Updated at")} {clock(plan.generated_at)}  {t("· Europe/Berlin")}</p>
    </div>
    <Link className="button primary" to={`/booking/${plan.reference}`}>{plan.status === 'broken' ? t("Review disruption") : t("Open journey & downloads")}</Link>
  </section>
}
