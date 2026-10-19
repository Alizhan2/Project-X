import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useConfig } from '../config'
import { useNotifications } from '../notifications'

export default function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const cfg = useConfig()
  const { unread } = useNotifications()
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      {cfg.simulated && (
        <div className="sim-banner" role="note">
          {cfg.launch_mode === 'demo' ? 'Demonstration' : 'Development build'} — all transport data, payments and booking confirmations are simulated.
          Confirmations are not valid travel tickets.
        </div>
      )}
      <header className="site-header">
        <span className="brand">Doedu</span>
        <nav aria-label="Main">
          <NavLink to="/" end>Search</NavLink>
          {user && <NavLink to="/journeys">My journeys</NavLink>}
          {user && (
            <NavLink to="/notifications">
              Notifications{unread > 0 && <span className="count" aria-label={`${unread} unread`}> {unread}</span>}
            </NavLink>
          )}
          {user?.role === 'operator' && <NavLink to="/operator">Operator</NavLink>}
          <NavLink to="/status">System status</NavLink>
          {user ? (
            <button className="link" onClick={async () => { await logout(); nav('/') }}>Sign out ({user.name})</button>
          ) : (
            <NavLink to="/login">Sign in</NavLink>
          )}
        </nav>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="site-footer">Doedu · {cfg.launch_mode} · release {cfg.release}</footer>
    </>
  )
}
