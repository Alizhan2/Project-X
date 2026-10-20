import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import type { SavedTraveller } from '../api'

/** One-tap fill of passenger names from the account's saved list. Only names; nothing is saved without the checkbox. */
export default function SavedTravellers({ saved, names, onUse }: { saved: SavedTraveller[]; names: string[]; onUse: (name: string) => void }) {
  useLanguage()
  if (saved.length === 0) return null
  const used = new Set(names.map(n => n.trim().toLowerCase()))
  const full = names.every(n => n.trim() !== '')
  return (
    <div className="saved-travellers" role="group" aria-labelledby="saved-tr-h">
      <p id="saved-tr-h" className="muted small">{t('Saved travellers')}</p>
      <ul>
        {saved.map(s => (
          <li key={s.id}>
            <button type="button" className="secondary" disabled={used.has(s.full_name.toLowerCase()) || full} onClick={() => onUse(s.full_name)}
              aria-label={t('Use {0} as a passenger', { 0: s.full_name })}>{s.full_name}</button>
          </li>
        ))}
      </ul>
    </div>
  )
}
