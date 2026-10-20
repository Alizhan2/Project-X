import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../authContext'
import { offlineCopies } from '../offline'

export default function RequireAuth() {
  useLanguage()
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <p>{t("Loading…")}</p>
  // Offline, the session cannot be checked: still allow the pages that can show on-device copies (never payment or booking forms).
  const offlineView = !navigator.onLine && offlineCopies().length > 0 && (loc.pathname === '/journeys' || /^\/booking\/[^/]+$/.test(loc.pathname))
  if (!user && offlineView) return <Outlet />
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return <Outlet />
}
