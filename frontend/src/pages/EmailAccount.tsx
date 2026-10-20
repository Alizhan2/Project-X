import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ApiError, request } from '../api'
import { useAuth } from '../authContext'

export default function EmailAccount({ mode }: { mode: 'forgot' | 'reset' | 'verify' }) {
  useLanguage()
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
  const title = mode === 'forgot' ? t("Forgot your password?") : mode === 'reset' ? t("Choose a new password") : t("Verify your email")

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(''); setMessage('')
    if (mode === 'reset' && password !== confirmation) { setError(t("The passwords do not match.")); return }
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
      setError(e instanceof ApiError ? Object.values(e.fields).join(' ') || e.message : t("Could not reach the server. Try again."))
    } finally { setBusy(false) }
  }
  return <section className="card narrow account-card">
    <h1>{title}</h1>
    <p className="muted">{mode === 'forgot' ? t("Enter your account email. We’ll send a link to set a new password.") : mode === 'reset' ? t("Use a unique password with at least 8 characters.") : hasToken ? t("Confirm that this email address belongs to you.") : t("Request a link to confirm the email address on your account.")}</p>
    {error && <p className="status-bad" role="alert">{t(error)}</p>}
    {message && <p className="status-ok" role="status">{t(message)}</p>}
    {mode === 'reset' && !hasToken && !done ? <p>{t("This link is incomplete.")} <Link to="/forgot-password">{t("Request a new link")}</Link>.</p>
      : mode === 'verify' && !hasToken && !user ? <p><Link to="/login" state={{ from: '/verify-email' }}>{t("Sign in to request a verification email")}</Link>.</p>
      : !done && <form onSubmit={submit}>
        {mode === 'forgot' && <div className="field"><label htmlFor="reset-email">{t("Email")}</label><input id="reset-email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>}
        {mode === 'reset' && <><div className="field"><label htmlFor="new-password">{t("New password")}</label><input id="new-password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} /></div><div className="field"><label htmlFor="confirm-password">{t("Confirm new password")}</label><input id="confirm-password" type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></div></>}
        <button className="primary" disabled={busy}>{busy ? t("Please wait…") : mode === 'forgot' ? t("Send reset link") : mode === 'reset' ? t("Update password") : hasToken ? t("Confirm email") : t("Send verification link")}</button>
      </form>}
    <p><Link to="/login">{t("Back to sign in")}</Link> · <Link to="/journeys">{t("My journeys")}</Link></p>
    {mode === 'reset' && error && <Link to="/forgot-password">{t("Request a new reset link")}</Link>}
  </section>
}
