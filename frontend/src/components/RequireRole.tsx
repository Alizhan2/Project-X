import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

export default function RequireRole({ role }: { role: string }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <p>Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  if (user.role !== role) return <p role="alert" className="status-bad">This area is only for {role} accounts.</p>
  return <Outlet />
}
