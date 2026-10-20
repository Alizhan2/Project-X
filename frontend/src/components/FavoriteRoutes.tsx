import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, deleteFavorite, fetchFavorites, saveFavorite, type FavoriteRoute } from '../api'
import { useAuth } from '../auth'
import { repeatSearchUrl } from '../format'

interface Props { origin: string; destination: string }
export default function FavoriteRoutes(props: Props) {
  const { user } = useAuth()
  return user ? <SavedDirections key={user.id} {...props} /> : <p className="muted small"><Link to="/login">Sign in</Link> to save your favourite directions.</p>
}

function SavedDirections({ origin, destination }: Props) {
  const [routes, setRoutes] = useState<FavoriteRoute[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchFavorites(ctrl.signal).then(data => { if (!ctrl.signal.aborted) setRoutes(data) }).catch(() => {
      if (!ctrl.signal.aborted) setError('Could not load saved directions. Refresh to try again.')
    })
    return () => ctrl.abort()
  }, [])
  const saved = routes?.some(r => r.origin === origin && r.destination === destination)
  async function change(id?: number) {
    setBusy(true); setError('')
    try {
      if (id !== undefined) {
        await deleteFavorite(id)
        setRoutes(old => old?.filter(r => r.id !== id) ?? [])
      } else {
        const favorite = await saveFavorite(origin, destination)
        setRoutes(old => [favorite, ...(old ?? []).filter(r => r.id !== favorite.id)])
      }
    } catch (e) {
      setError(e instanceof ApiError ? Object.values(e.fields).join(' ') || e.message : 'Could not update saved directions. Try again.')
    } finally { setBusy(false) }
  }
  return <section className="saved-directions" aria-labelledby="saved-heading">
    <div className="saved-heading"><h2 id="saved-heading">Saved directions</h2>
      {origin && destination && origin !== destination && <button className="secondary" disabled={busy || routes === null || saved} onClick={() => change()}>{saved ? 'Direction saved' : 'Save this direction'}</button>}
    </div>
    {error && <p role="alert" className="status-bad">{error}</p>}
    {!routes && !error && <p className="muted">Loading saved directions…</p>}
    {routes?.length === 0 && <p className="muted small">Save a direction after searching, then find new departures whenever you need it.</p>}
    {!!routes?.length && <ul className="saved-list">{routes.map(r => <li key={r.id}>
      <Link to={repeatSearchUrl(r.origin, r.destination)}>{r.origin_name} → {r.destination_name}</Link>
      <button className="link" disabled={busy} aria-label={`Remove ${r.origin_name} to ${r.destination_name}`} onClick={() => change(r.id)}>Remove</button>
    </li>)}</ul>}
  </section>
}
