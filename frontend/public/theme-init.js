// Runs before first paint (external file: the CSP forbids inline scripts). Chooses the theme from the saved
// choice, else from the operating-system preference, and records it on <html data-theme>.
try {
  var saved = localStorage.getItem('doedu.theme')
  var dark = saved === 'dark' || (saved !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
} catch { document.documentElement.dataset.theme = 'light' }
