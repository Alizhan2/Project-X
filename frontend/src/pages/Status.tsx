import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from '../api'

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; health: Health }
  | { kind: 'error'; message: string }

export default function Status() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const ctrl = new AbortController()
    fetchHealth(ctrl.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setState({ kind: 'error', message: String(e) })
      })
    return () => ctrl.abort()
  }, [])

  return (
    <section aria-labelledby="status-h" className="card">
      <h1 id="status-h">System status</h1>
      <div aria-live="polite" data-testid="system-status">
        {state.kind === 'loading' && <p>Checking backend…</p>}
        {state.kind === 'error' && <p className="status-bad">Backend unreachable: {state.message}</p>}
        {state.kind === 'ready' && state.health.status === 'ok' && (
          <p className="status-ok">Backend and database connected.</p>
        )}
        {state.kind === 'ready' && state.health.status !== 'ok' && (
          <p className="status-bad">Backend reports a database problem.</p>
        )}
      </div>
    </section>
  )
}
