import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ApiError, request } from '../api'
import { useAuth } from '../auth'

export default function EmailAccount({ mode }: { mode: 'forgot' | 'reset' | 'verify' }) {
  const { hash } = useLocation()
  const { user, refresh } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const token = new URLSearchParams(hash.slice(1))
  const hasToken = !!token.get('uid') && !!token.get('token')
  const title = mode === 'forgot' ? 'Forgot your password?' : mode === 'reset' ? 'Choose a new password' : 'Verify your email'

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(''); setMessage('')
    if (mode === 'reset' && password !== confirmation) { setError('The passwords do not match.'); return }
    setBusy(true)
    try {
      const path = mode === 'forgot' ? 'password-reset/' : mode === 'reset' ? 'password-reset/confirm/' : hasToken ? 'email-verification/confirm/' : 'email-verification/'
      const body = mode === 'forgot' ? { email } : hasToken ? { uid: token.get('uid'), token: token.get('token'), ...(mode === 'reset' ? { password } : {}) } : undefined
      const response = await request<{ detail: string }>('POST', `/api/auth/${path}`, body)
      setMessage(response.detail)
      setDone(true)
      if (hasToken) {
        window.history.replaceState(null, '', window.location.pathname)
        await refresh().catch(() => undefined)
      }
    } catch (e) {
      setError(e instanceof ApiError ? Object.values(e.fields).join(' ') || e.message : 'Could not reach the server. Try again.')
    } finally { setBusy(false) }
  }
  return <section className="card narrow account-card">
    <h1>{title}</h1>
    <p className="muted">{mode === 'forgot' ? 'Enter your account email. We’ll send a link to set a new password.' : mode === 'reset' ? 'Use a unique password with at least 8 characters.' : hasToken ? 'Confirm that this email address belongs to you.' : 'Request a link to confirm the email address on your account.'}</p>
    {error && <p className="status-bad" role="alert">{error}</p>}
    {message && <p className="status-ok" role="status">{message}</p>}
    {mode === 'reset' && !hasToken && !done ? <p>This link is incomplete. <Link to="/forgot-password">Request a new link</Link>.</p>
      : mode === 'verify' && !hasToken && !user ? <p><Link to="/login" state={{ from: '/verify-email' }}>Sign in to request a verification email</Link>.</p>
      : !done && <form onSubmit={submit}>
        {mode === 'forgot' && <div className="field"><label htmlFor="reset-email">Email</label><input id="reset-email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>}
        {mode === 'reset' && <><div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} /></div><div className="field"><label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></div></>}
        <button className="primary" disabled={busy}>{busy ? 'Please wait…' : mode === 'forgot' ? 'Send reset link' : mode === 'reset' ? 'Update password' : hasToken ? 'Confirm email' : 'Send verification link'}</button>
      </form>}
    <p><Link to="/login">Back to sign in</Link> · <Link to="/journeys">My journeys</Link></p>
    {mode === 'reset' && error && <Link to="/forgot-password">Request a new reset link</Link>}
  </section>
}
