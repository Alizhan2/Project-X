import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, fetchFollows, followLine, unfollowLine, type LineFollow } from '../api'
import { useAuth } from '../authContext'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'

interface Line { route_code: string; route_name: string; mode: string }

/** Follow the bus/train lines of a journey: delay and cancellation notices for services leaving soon, without a booking. */
export default function FollowLines({ lines }: { lines: Line[] }) {
  useLanguage()
  const { user } = useAuth()
  const [follows, setFollows] = useState<LineFollow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => {
    if (!user) return
    const ctrl = new AbortController()
    fetchFollows(ctrl.signal).then(r => setFollows(r.results)).catch(() => undefined)   // a convenience: failure just hides state
    return () => ctrl.abort()
  }, [user])
  const unique = lines.filter((l, i) => l.mode !== 'taxi' && lines.findIndex(x => x.route_code === l.route_code) === i)
  if (unique.length === 0) return null

  async function toggle(line: Line) {
    const existing = follows?.find(f => f.route_code === line.route_code)
    setBusy(line.route_code); setError(null)
    try {
      if (existing) { await unfollowLine(existing.id); setFollows(f => (f ?? []).filter(x => x.id !== existing.id)) }
      else { const created = await followLine(line.route_code); setFollows(f => [...(f ?? []), created]) }
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.detail ?? e.fields.route_code ?? e.message) : t('Unexpected error.'))
    } finally { setBusy(null) }
  }

  return (
    <section className="follow-lines" aria-labelledby="follow-h">
      <h2 id="follow-h">{t('Follow these lines')}</h2>
      <p className="muted small">{t('You will be told about delays and cancellations on services of a followed line that leave within 48 hours, even without a booking.')}</p>
      {!user ? <p><Link to="/login">{t('Sign in to follow lines')}</Link></p> : (
        <ul>
          {unique.map(l => {
            const on = follows?.some(f => f.route_code === l.route_code) ?? false
            return (
              <li key={l.route_code}>
                <button type="button" className="secondary" aria-pressed={on} disabled={follows === null || busy === l.route_code} onClick={() => toggle(l)}>
                  {on ? t('Following {0}', { 0: l.route_code }) : t('Follow {0}', { 0: l.route_code })}
                </button>
                <span className="muted small">{l.route_name}</span>
              </li>
            )
          })}
        </ul>
      )}
      {error && <p role="alert" className="status-bad">{t(error)}</p>}
    </section>
  )
}
