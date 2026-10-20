import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { clock, dayLabel } from '../format'

interface Item {
  departs_at: string; arrives_at: string; from: string; to: string; mode: string; operator: string
  route_code: string; note?: string
}

const gap = (a: string, b: string) => Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)

export default function Timeline({ legs, buffers }: { legs: Item[]; buffers?: number[] }) {
  useLanguage()
  return (
    <ol className="timeline" aria-label={t("Journey timeline")}>
      {legs.map((l, i) => (
        <li key={i}>
          <p><strong>{clock(l.departs_at)}</strong> {placeName(l.from)} <span className="muted">({dayLabel(l.departs_at)})</span></p>
          <p className="muted small">{[l.mode === 'taxi' ? t("Taxi (simulated)") : `${t(l.mode)} ${l.route_code}`, l.operator].filter(Boolean).join(' · ')}</p>
          {l.note && <p className="warn">{t(l.note)}</p>}
          <p><strong>{clock(l.arrives_at)}</strong> {placeName(l.to)} <span className="muted">({dayLabel(l.arrives_at)})</span></p>
          {i < legs.length - 1 && (
            <p className="transfer small">
               {t("Change:")} {gap(l.arrives_at, legs[i + 1].departs_at)}  {t("min between arrival and next departure")} {buffers && buffers[i] !== undefined && legs[i + 1].mode !== 'taxi' ? t(" ({0} min to spare)", {0: buffers[i]}) : ''}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}
