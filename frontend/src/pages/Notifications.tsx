import { Link } from 'react-router-dom'
import { useNotifications } from '../notifications'
import { clock, dayLabel } from '../format'

export default function Notifications() {
  const { items, unread, read, readAll } = useNotifications()
  return (
    <>
      <h1>Notifications</h1>
      <div className="actions">
        <p aria-live="polite">{unread} unread</p>
        <button className="secondary" disabled={unread === 0} onClick={() => readAll()}>Mark all as read</button>
      </div>
      {items.length === 0 && <div className="card empty"><p><strong>No notifications yet.</strong></p><p className="muted">We will tell you here if a service on one of your journeys changes.</p></div>}
      <ul className="result-list">
        {items.map((n) => (
          <li key={n.id} className={`card notif ${n.read ? '' : 'unread'}`}>
            <p><strong>{n.title}</strong> {!n.read && <span className="badge">New</span>}</p>
            <p>{n.body}</p>
            <p className="muted small">{dayLabel(n.created_at)} {clock(n.created_at)}</p>
            <p>
              {n.booking && <Link to={`/booking/${n.booking}`}>Open booking {n.booking}</Link>}{' '}
              {!n.read && <button className="link" onClick={() => read(n.id)}>Mark as read</button>}
            </p>
          </li>
        ))}
      </ul>
    </>
  )
}
