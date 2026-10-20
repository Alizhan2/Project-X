import { getLanguage, languages, localeNames, setLanguage, t, type Language } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../authContext'
import { useConfig } from '../configContext'
import { useNotifications } from '../notificationsContext'
import { useOnline } from '../hooks'
import ThemeToggle from './ThemeToggle'

export default function Layout() {
  const language = useLanguage()
  useEffect(() => {
    const invalid = (event: Event) => {
      const input = event.target
      if (!(input instanceof HTMLInputElement || input instanceof HTMLSelectElement)) return
      input.setCustomValidity('')
      const validity = input.validity
      if (!validity.valid) input.setCustomValidity(t(validity.valueMissing ? 'This field is required.' : validity.typeMismatch && input instanceof HTMLInputElement && input.type === 'email' ? 'Enter a valid email address.' : 'Enter a valid value.'))
    }
    const clear = (event: Event) => {
      const input = event.target
      if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement) input.setCustomValidity('')
    }
    document.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select').forEach(input => input.setCustomValidity(''))
    document.addEventListener('invalid', invalid, true)
    document.addEventListener('input', clear, true)
    return () => { document.removeEventListener('invalid', invalid, true); document.removeEventListener('input', clear, true) }
  }, [language])
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const cfg = useConfig()
  const [menuOpen, setMenuOpen] = useState(false)
  const isKazakhstan = useLocation().pathname === '/kazakhstan'
  const { unread } = useNotifications()
  const online = useOnline()
  return (
    <>
      <a className="skip-link" href="#main">{t("Skip to content")}</a>
      {!online && <div className="offline-banner" role="status">{t('You are offline. Some features need a connection.')}</div>}
      <header className="site-header">
        <NavLink to="/" className="brand" aria-label="Doedu"><img src="/design/doedu-mark.svg" width="28" height="28" alt="" />doedu</NavLink>
        <button className="mobile-menu-toggle" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{t('Menu')}</button>
        <label className="language-switch"><span className="sr-only">{t('Language')}</span>
          <select aria-label={t('Language')} value={getLanguage()} onChange={e => setLanguage(e.target.value as Language)}>
            {languages.map(code => <option key={code} value={code} lang={code}>{localeNames[code]}</option>)}
          </select>
        </label>
        <ThemeToggle />
        <nav id="main-navigation" aria-label={t("Main")} data-open={menuOpen} onClick={e => { if (e.target instanceof Element && e.target.closest('a')) setMenuOpen(false) }}>
          <NavLink to="/" end>{t("Search")}</NavLink>
          <NavLink to="/kazakhstan">{t("Kazakhstan")}</NavLink>
          <NavLink to="/journeys">{t("My journeys")}</NavLink>
          {user && (
            <NavLink to="/notifications">
               {t("Notifications")}{unread > 0 && <span className="count" aria-label={t("{0} unread", {0: unread})}> {unread}</span>}
            </NavLink>
          )}
          {user?.role === 'operator' && <NavLink to="/operator">{t("Operator")}</NavLink>}
          <NavLink to="/status">{t("System status")}</NavLink>
          {user ? (
            <button className="link" onClick={async () => { await logout(); nav('/') }}>{t("Sign out (")}{user.name})</button>
          ) : (
            <NavLink to="/login" className="sign-in-link">{t("Sign in")}</NavLink>
          )}
        </nav>
      </header>
      <main id="main">
        {user && !user.email_verified && <aside className="email-notice">{t("Keep access to your account.")} <NavLink to="/verify-email">{t("Verify your email")}</NavLink></aside>}
        <Outlet />
      </main>
      <footer className="site-footer">
        {cfg.simulated && <div className="sim-banner" role="note">{isKazakhstan ? t('Kazakhstan directory. Real ticket sales are not yet available.') : <>{cfg.launch_mode === 'demo' ? t("Demonstration") : t("Development build")} {t("— all transport data, payments and booking confirmations are simulated. Confirmations are not valid travel tickets.")}</>}</div>}
        <p className="release-label">Doedu · {t(cfg.launch_mode)} {t("· release")} {cfg.release}</p>
      </footer>
    </>
  )
}
