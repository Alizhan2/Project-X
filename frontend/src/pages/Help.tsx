import { Link } from 'react-router-dom'
import { t } from '../i18n'

const TOPICS: [string, string][] = [
  ['What does "simulated" mean?', 'Everything in Doedu is a demonstration. Timetables, prices, payments, refunds and confirmations are made up. A confirmation is not a travel ticket and no money is ever charged. Do not use it to travel.'],
  ['What happens if a connection breaks?', 'If a service is cancelled or delayed so that you can no longer make the next leg, you get a notification. Doedu then looks for replacement journeys to your destination and shows the exact price difference. Nothing is booked or held until you accept one; if none exists, you can cancel the unused legs for a full refund.'],
  ['How long is a place held while I pay?', 'Places are held for a short time after checkout (10 minutes in this demo). If you do not pay in time, the booking expires and the places go back on sale.'],
  ['How do refunds work?', 'Each leg has its own cancellation policy, shown before you book and saved with your booking. The refund depends on how long before departure you cancel; a service cancelled by the operator is refunded in full. Refunds here are simulated.'],
  ['What is a change buffer?', 'The spare minutes between arriving and the next departure, after the minimum change time. It is a plain time difference, not a prediction that a service will be on time. Taxis leave when you are ready, so there is nothing to miss.'],
  ['Why does a search show no journeys?', 'Services may not run at that time, may be cancelled or full, or the connection may be impossible. Try another date or time, the nearby-days strip, or fewer filters. When nothing matches, Doedu shows the next journey that does.'],
  ['What are alerts and followed lines?', 'Alerts tell you when a journey gets cheaper or a full service has places again. Following a line tells you about delays and cancellations without a booking. They only notify you: no place or price is held.'],
  ['Who can I contact?', 'This demo has no support team yet, so there is nobody to answer messages. Your bookings, notices and replacement offers are always available under My journeys and Notifications.'],
]

export default function Help() {
  return (
    <section className="help" aria-labelledby="help-title">
      <h1 id="help-title">{t('Help')}</h1>
      <p className="muted">{t('Short answers about booking, delays and refunds. All data is simulated.')}</p>
      <div className="help-list">
        {TOPICS.map(([q, a]) => (
          <details key={q} className="card help-item">
            <summary>{t(q)}</summary>
            <p>{t(a)}</p>
          </details>
        ))}
      </div>
      <p><Link to="/">{t('Back to search')}</Link></p>
    </section>
  )
}
