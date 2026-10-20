import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'

interface Leg { mode: string; from: string; to: string }

/**
 * Plain-language answer to "what if a connection breaks?". Every sentence describes behaviour that exists:
 * the spare time per change is arithmetic on the timetable (not a punctuality forecast), notifications and
 * non-reserving replacement offers come from the disruption pipeline, and a disrupted journey refunds unused
 * legs in full. All money is simulated in the demonstration.
 */
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
      <p>{t('If a delay or cancellation breaks a connection after you have booked, we notify you, search replacements for the rest of your trip and show the exact price difference before you decide. Offers do not hold places until you accept. If nothing suitable exists, you can cancel for a full refund of the unused legs. In this demonstration all payments and refunds are simulated.')}</p>
    </section>
  )
}
