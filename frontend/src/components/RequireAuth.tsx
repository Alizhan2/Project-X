import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

export default function RequireAuth() {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <p>Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return <Outlet />
}
