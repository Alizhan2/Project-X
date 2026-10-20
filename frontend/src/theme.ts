export type Theme = 'light' | 'dark'
export const currentTheme = (): Theme => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try { localStorage.setItem('doedu.theme', theme) } catch { /* Storage may be unavailable: the choice then lasts for this visit only. */ }
}
