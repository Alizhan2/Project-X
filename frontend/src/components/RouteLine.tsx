import { placeName, t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { clock, duration } from '../format'
import { layoutRoute, type RouteLeg } from '../routeLine'

const MODE: Record<string, string> = { bus: 'Bus', train: 'Train', taxi: 'Taxi' }

function ModeIcon({ mode }: { mode: string }) {
  const common = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
  if (mode === 'train') return <svg {...common}><rect x="5" y="3" width="14" height="14" rx="3" /><path d="M5 11h14M9 21l2-4M15 21l-2-4" /><circle cx="9" cy="14" r=".6" /><circle cx="15" cy="14" r=".6" /></svg>
  if (mode === 'taxi') return <svg {...common}><path d="M5 16l1.5-5.5A2 2 0 0 1 8.4 9h7.2a2 2 0 0 1 1.9 1.5L19 16" /><rect x="3" y="16" width="18" height="4" rx="1.5" /><path d="M10 6h4v3h-4z" /></svg>
  return <svg {...common}><rect x="4" y="3" width="16" height="14" rx="3" /><path d="M4 11h16M8 21v-4M16 21v-4" /><circle cx="8" cy="14" r=".6" /><circle cx="16" cy="14" r=".6" /></svg>
}

/**
 * Schematic overview of a journey: one coloured block per leg (width ~ duration), dashed connectors for changes,
 * delayed legs highlighted. No map service is used. `decorative` hides it from assistive technology when the same
 * information follows as text (the Timeline); otherwise it exposes one summary sentence per route.
 */
export default function RouteLine({ legs, compact = false, decorative = false }: { legs: RouteLeg[]; compact?: boolean; decorative?: boolean }) {
  useLanguage()
  const segments = layoutRoute(legs)
  const label = `${t('Route overview')}: ` + legs.map((l, i) => {
    const next = legs[i + 1]
    const leg = `${l.mode === 'taxi' ? t(MODE.taxi) : `${t(MODE[l.mode] ?? l.mode)} ${l.route_code}`} ${placeName(l.from)} → ${placeName(l.to)}, ${clock(l.departs_at)}–${clock(l.arrives_at)}${l.note ? ` (${t(l.note)})` : ''}`
    return next ? `${leg}; ${t('Change:')} ${segments.find(s => s.kind === 'change' && s.index === i)?.minutes} ${t('min')}` : leg
  }).join('; ')
  return (
    <div className={`route-line${compact ? ' route-line-compact' : ''}`} {...(decorative ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label })}>
      {segments.map((s, k) => {
        const leg = legs[s.index]
        if (s.kind === 'change') {
          return <div key={k} className="rl-col rl-change" style={{ flexGrow: s.weight }}><div className="rl-bar"><span>{s.minutes} {t('min')}</span></div></div>
        }
        const last = s.index === legs.length - 1
        return (
          <div key={k} className="rl-col rl-leg" style={{ flexGrow: s.weight }}>
            <div className={`rl-bar rl-${leg.mode}${leg.note ? ' rl-warn' : ''}`}>
              <ModeIcon mode={leg.mode} />
              <span className="rl-code">{leg.mode === 'taxi' ? t(MODE.taxi) : leg.route_code}</span>
              {!compact && <span className="rl-min">{duration(s.minutes)}</span>}
            </div>
            {!compact && (
              <div className="rl-stops">
                <span className="rl-stop"><strong>{clock(leg.departs_at)}</strong> {placeName(leg.from)}</span>
                {last && <span className="rl-stop rl-stop-end"><strong>{clock(leg.arrives_at)}</strong> {placeName(leg.to)}</span>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
