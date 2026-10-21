import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, createWatch, type Watch, type WatchBody } from '../api'
import { useAuth } from '../authContext'
import { money } from '../format'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'

interface Props { search: Omit<WatchBody, 'kind'>; cheapest: { price: string; currency: string } | null }

/**
 * "Notify me" under the results: a price alert when journeys exist, an availability alert when none do.
 * It only creates a notification request: it holds no seats and no price (stated next to the button).
 */
export default function WatchPrompt({ search, cheapest }: Props) {
  useLanguage()
  const { user } = useAuth()
  const [state, setState] = useState<{ kind: 'idle' } | { kind: 'saving' } | { kind: 'saved'; watch: Watch } | { kind: 'error'; message: string }>({ kind: 'idle' })
  const key = JSON.stringify(search)
  const [forKey, setForKey] = useState(key)
  if (forKey !== key) { setForKey(key); setState({ kind: 'idle' }) }        // a new search starts with a clean prompt

  async function save() {
    setState({ kind: 'saving' })
    try { setState({ kind: 'saved', watch: await createWatch({ ...search, kind: cheapest ? 'price' : 'availability' }) }) }
    catch (e) {
      const fields = e instanceof ApiError ? e.fields : {}
      setState({ kind: 'error', message: fields.kind ?? fields.detail ?? fields.date ?? (e instanceof ApiError ? e.message : t('Unexpected error.')) })
    }
  }

  return (
    <section className="watch-prompt card" aria-labelledby="watch-h">
      <h2 id="watch-h">{t('Get notified')}</h2>
      {!user ? <p><Link to="/login" state={{ from: `/?${new URLSearchParams({ ...search, passengers: String(search.passengers) })}` }}>{t('Sign in to get alerts')}</Link></p> : state.kind === 'saved' ? (
        <p role="status">{t('Alert saved.')} <Link to="/alerts">{t('See your alerts')}</Link></p>
      ) : (
        <>
          <button type="button" className="secondary" disabled={state.kind === 'saving'} onClick={save}>
            {cheapest ? t('Notify me if the price drops (now from {0})', { 0: money(cheapest.price, cheapest.currency) }) : t('Notify me when a journey becomes available')}
          </button>
          {state.kind === 'error' && <p role="alert" className="status-bad">{t(state.message)}</p>}
        </>
      )}
      <p className="muted small">{t('Alerts only notify you. They do not hold places or prices, and everything here is simulated.')}</p>
    </section>
  )
}
