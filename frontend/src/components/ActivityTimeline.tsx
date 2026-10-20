import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import type { ActivityEvent } from '../api'
import { clock, dayLabel, money } from '../format'

/** What happened to this booking, oldest first. Texts are fixed phrases from the server and are translated here. */
export default function ActivityTimeline({ events }: { events: ActivityEvent[] }) {
  useLanguage()
  if (events.length === 0) return null
  return (
    <section aria-labelledby="activity-h" className="activity">
      <h2 id="activity-h">{t('Trip activity')}</h2>
      <ol className="activity-list">
        {events.map((e, i) => (
          <li key={i} className={`activity-${e.kind}`}>
            <span className="activity-dot" aria-hidden="true" />
            <div>
              <p><strong>{t(e.title)}</strong>{e.amount && e.currency ? <> · {money(e.amount, e.currency)}</> : null}</p>
              <p className="muted small"><time dateTime={e.at}>{dayLabel(e.at)} {clock(e.at)}</time></p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
