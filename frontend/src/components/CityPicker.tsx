import { useEffect, useRef, useState } from 'react'
import { cityMatches, type City } from '../kazakhstan'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'

export default function CityPicker({ name, cities, value, query, error, onQuery, onSelect }: {
  name: 'origin' | 'destination'
  cities: City[]
  value: string
  query: string | null
  error?: string
  onQuery: (query: string) => void
  onSelect: (id: string) => void
}) {
  const language = useLanguage()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const list = useRef<HTMLUListElement>(null)
  const matches = cities.filter(city => cityMatches(city, query ?? ''))
  const options = matches.slice(0, 8)
  const selected = cities.find(city => city.id === value)
  const id = `kz-city-${name}`
  useEffect(() => {
    if (open) list.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active, open])
  function choose(city: City) {
    onSelect(city.id)
    setOpen(false)
    setActive(-1)
  }
  return <div className="field city-picker" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }}>
    <label htmlFor={id}>{t(name === 'origin' ? 'From' : 'To')}</label>
    <input id={id} name={name} role="combobox" autoComplete="off" spellCheck={false}
      value={query ?? selected?.name[language] ?? ''} placeholder={t('City or region in any of three languages')}
      aria-expanded={open} aria-controls={`${id}-options`} aria-autocomplete="list"
      aria-activedescendant={open && active >= 0 && options[active] ? `${id}-${options[active].id}` : undefined}
      aria-invalid={!!error} aria-describedby={error ? `kz-${name}-error` : undefined}
      onFocus={event => { setOpen(true); event.currentTarget.select() }}
      onClick={() => setOpen(true)}
      onChange={event => { onQuery(event.target.value); setOpen(true); setActive(-1) }}
      onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); setOpen(true)
          setActive(index => event.key === 'ArrowDown' ? Math.min(index + 1, options.length - 1) : Math.max(index - 1, 0))
        } else if (event.key === 'Enter' && open && (query !== null || active >= 0)) {
          event.preventDefault()
          const city = options[Math.max(0, active)]
          if (city) choose(city)
        } else if (event.key === 'Escape') {
          event.preventDefault(); setOpen(false); setActive(-1)
        }
      }} />
    <div className="city-options" hidden={!open}>
    <ul ref={list} id={`${id}-options`} role="listbox" aria-label={t(name === 'origin' ? 'Departure city suggestions' : 'Arrival city suggestions')}>
      {options.map((city, index) => <li key={city.id} role="option" id={`${id}-${city.id}`}
        aria-selected={city.id === value} data-active={index === active}
        onMouseDown={event => event.preventDefault()} onClick={() => choose(city)}>
        <strong>{city.name[language]}</strong><span>{city.region[language]}</span>
      </li>)}
    </ul>
    <p className="small muted" role="status">{options.length
      ? t('{0} matching cities. Choose a suggestion to confirm your city.', { 0: matches.length })
      : t('No matching cities. Try another spelling or region.')}</p>
    </div>
    {error && <span className="field-error" id={`kz-${name}-error`}>{t(error)}</span>}
  </div>
}
