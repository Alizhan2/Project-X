import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { clock, dayLabel } from '../format'
import RouteLine from './RouteLine'
import type { Connection } from '../api'

interface Item {
  departs_at: string; arrives_at: string; from: string; to: string; mode: string; operator: string
  route_code: string; note?: string
}

const gap = (a: string, b: string) => Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)

export default function Timeline({ legs, buffers, connections }: { legs: Item[]; buffers?: number[]; connections?: Connection[] }) {
  useLanguage()
  return (
    <>
    {legs.length > 0 && <RouteLine legs={legs} decorative />}
    <ol className="timeline" aria-label={t("Journey timeline")}>
      {legs.map((l, i) => (
        <li key={i}>
          <p><strong>{clock(l.departs_at)}</strong> {placeName(l.from)} <span className="muted">({dayLabel(l.departs_at)})</span></p>
          <p className="muted small">{[l.mode === 'taxi' ? t("Taxi (simulated)") : `${t(l.mode)} ${l.route_code}`, t(l.operator)].filter(Boolean).join(' · ')}</p>
          {l.note && <p className="warn">{t(l.note)}</p>}
          <p><strong>{clock(l.arrives_at)}</strong> {placeName(l.to)} <span className="muted">({dayLabel(l.arrives_at)})</span></p>
          {i < legs.length - 1 && (
            <p className="transfer small">
               {t("Change:")} {gap(l.arrives_at, legs[i + 1].departs_at)} {t("min between arrival and next departure")}
               {connections?.[i] ? <ConnectionDetails connection={connections[i]} /> : buffers && buffers[i] !== undefined && legs[i + 1].mode !== 'taxi' ? t(" ({0} min to spare)", {0: buffers[i]}) : ''}
            </p>
          )}
        </li>
      ))}
    </ol>
    </>
  )
}

function ConnectionDetails({ connection: c }: { connection: Connection }) {
  const status = { infeasible: 'Connection cannot be made', at_risk: 'Connection at risk', feasible: 'Feasible connection', on_demand: 'On-demand taxi pickup' }[c.status]
  return <><br /><strong>{t(status)}</strong> · {t("Walk: {0} min", {0: c.walking_minutes ?? t("not known")})} · {t("Boarding buffer: {0} min", {0: c.boarding_buffer_minutes})}
    {c.margin_minutes !== null && <> · {t("Spare time: {0} min", {0: c.margin_minutes})}</>}
    <br />{t("Step-free transfer path:")} {c.path_step_free === 'yes' ? t('yes') : c.path_step_free === 'no' ? t('no') : t('not known')}
    {c.status === 'on_demand' && <> · {t("Taxi pickup waiting time is included in the displayed departure.")}</>}
  </>
}
