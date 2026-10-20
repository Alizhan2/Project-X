import { useState } from 'react'
import { t } from '../i18n'
import { useLanguage } from '../useLanguage'
import { currentTheme, setTheme, type Theme } from '../theme'

export default function ThemeToggle() {
  useLanguage()
  const [theme, setCurrent] = useState<Theme>(currentTheme)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  return (
    <button type="button" className="theme-toggle" aria-pressed={theme === 'dark'} onClick={() => { setTheme(next); setCurrent(next) }}
      aria-label={t('Dark theme')} title={theme === 'dark' ? t('Switch to light theme') : t('Switch to dark theme')}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {theme === 'dark' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> : <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />}
      </svg>
    </button>
  )
}
