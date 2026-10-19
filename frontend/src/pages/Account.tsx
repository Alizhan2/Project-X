import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { useConfig } from '../config'

export default function Account({ mode }: { mode: 'login' | 'register' }) {
  const { login, register } = useAuth()
  const cfg = useConfig()
  const nav = useNavigate()
  const loc = useLocation()
  const to = (loc.state as { from?: string } | null)?.from ?? '/journeys'
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, name, password)
      nav(to, { replace: true })
    } catch (x) {
      setErr(x instanceof ApiError ? x : new ApiError('Something went wrong.'))
    } finally { setBusy(false) }
  }
  const f = (n: string) => err?.fields[n]
  if (mode === 'register' && !cfg.registration_enabled) {
    return <section className="card narrow"><h1>Registration is closed</h1><p>New accounts cannot be created on this deployment. <Link to="/login">Sign in</Link></p></section>
  }
  return (
    <section className="card narrow">
      <h1>{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
      {err && !Object.keys(err.fields).length && <p className="status-bad" role="alert">{err.message}</p>}
      {f('detail') && <p className="status-bad" role="alert">{f('detail')}</p>}
      <form onSubmit={submit} noValidate>
        {mode === 'register' && (
          <div className="field">
            <label htmlFor="name">Full name</label>
            <input id="name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!f('full_name')} />
            {f('full_name') && <span className="field-error">{f('full_name')}</span>}
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!f('email')} />
          {f('email') && <span className="field-error">{f('email')}</span>}
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!f('password')} />
          {f('password') && <span className="field-error">{f('password')}</span>}
        </div>
        <button className="primary" type="submit" disabled={busy}>{mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <p>
        {mode === 'login' ? (cfg.registration_enabled ? <>No account? <Link to="/register" state={loc.state}>Create one</Link></> : null) : <>Already registered? <Link to="/login" state={loc.state}>Sign in</Link></>}
      </p>
    </section>
  )
}
