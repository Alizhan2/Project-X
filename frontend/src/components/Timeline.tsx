import { clock, dayLabel } from '../format'

interface Item {
  departs_at: string; arrives_at: string; from: string; to: string; mode: string; operator: string
  route_code: string; note?: string
}

const gap = (a: string, b: string) => Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)

export default function Timeline({ legs, buffers }: { legs: Item[]; buffers?: number[] }) {
  return (
    <ol className="timeline" aria-label="Journey timeline">
      {legs.map((l, i) => (
        <li key={i}>
          <p><strong>{clock(l.departs_at)}</strong> {l.from} <span className="muted">({dayLabel(l.departs_at)})</span></p>
          <p className="muted small">{[l.mode === 'taxi' ? 'Taxi (simulated)' : `${l.mode} ${l.route_code}`, l.operator].filter(Boolean).join(' · ')}</p>
          {l.note && <p className="warn">{l.note}</p>}
          <p><strong>{clock(l.arrives_at)}</strong> {l.to} <span className="muted">({dayLabel(l.arrives_at)})</span></p>
          {i < legs.length - 1 && (
            <p className="transfer small">
              Change: {gap(l.arrives_at, legs[i + 1].departs_at)} min between arrival and next departure
              {buffers && buffers[i] !== undefined && legs[i + 1].mode !== 'taxi' ? ` (${buffers[i]} min to spare)` : ''}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}
