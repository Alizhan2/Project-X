import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

export default function RequireRole({ role }: { role: string }) {
  useLanguage()
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <p>{t("Loading…")}</p>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  if (user.role !== role) return <p role="alert" className="status-bad">{t("This area is only for")} {t(role)}  {t("accounts.")}</p>
  return <Outlet />
}
