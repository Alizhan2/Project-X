import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { Link } from 'react-router-dom'
import { useNotifications } from '../notificationsContext'
import { clock, dayLabel } from '../format'

export default function Notifications() {
  useLanguage()
  const { items, unread, read, readAll } = useNotifications()
  return (
    <>
      <h1>{t("Notifications")}</h1>
      <div className="actions">
        <p aria-live="polite">{unread}  {t("unread")}</p>
        <button className="secondary" disabled={unread === 0} onClick={() => readAll()}>{t("Mark all as read")}</button>
      </div>
      {items.length === 0 && <div className="card empty"><p><strong>{t("No notifications yet.")}</strong></p><p className="muted">{t("We will tell you here if a service on one of your journeys changes.")}</p></div>}
      <ul className="result-list">
        {items.map((n) => (
          <li key={n.id} className={`card notif ${n.read ? '' : 'unread'}`}>
            <p><strong>{t(n.title)}</strong> {!n.read && <span className="badge">{t("New")}</span>}</p>
            <p>{t(n.body)}</p>
            <p className="muted small">{dayLabel(n.created_at)} {clock(n.created_at)}</p>
            <p>
              {n.booking && <Link to={`/booking/${n.booking}`}>{t("Open booking")} {n.booking}</Link>}{' '}
              {!n.read && <button className="link" onClick={() => read(n.id)}>{t("Mark as read")}</button>}
            </p>
          </li>
        ))}
      </ul>
    </>
  )
}
