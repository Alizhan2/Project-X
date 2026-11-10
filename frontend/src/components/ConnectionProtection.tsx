import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'

interface Leg { mode: string; from: string; to: string }

export default function ConnectionProtection({ legs, buffers }: { legs: Leg[]; buffers?: number[] }) {
  useLanguage()
  if (legs.length < 2) {
    return (
      <section className="protection" aria-labelledby="protection-h">
        <h2 id="protection-h">{t('How this journey is protected')}</h2>
        <p>{t('Direct journey: there is no connection to miss.')}</p>
      </section>
    )
  }
  // `buffers` only has entries for changes into fixed-time services (bus/train); a taxi leaves when you are ready.
  let next = 0
  return (
    <section className="protection" aria-labelledby="protection-h">
      <h2 id="protection-h">{t('How this journey is protected')}</h2>
      {buffers && <ul>
        {legs.slice(1).map((leg, i) => {
          const place = placeName(legs[i].to)
          if (leg.mode === 'taxi') return <li key={i}>{t('Taxi after {0}: it is dispatched when you arrive, so there is no connection to miss.', { 0: place })}</li>
          const spare = buffers[next++]
          return <li key={i}>{t('Change at {0}: {1} min to spare. If the earlier service arrives more than {1} min late, this connection breaks.', { 0: place, 1: spare })}</li>
        })}
      </ul>}
      {buffers && <p className="muted small">{t('Spare time is the extra time beyond the minimum needed to change. It is not a prediction of punctuality.')}</p>}
      <p>{t('If a connection breaks, review replacement routes, the full payment required now and any separate eligible refund. Your original booking stays intact until replacement confirmation succeeds. Cancellation follows each saved fare policy; a delay alone does not guarantee a full refund. All payments and refunds are simulated.')}</p>
    </section>
  )
}
