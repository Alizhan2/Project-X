import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth'
import { ConfigProvider } from './config'
import { NotificationsProvider } from './notifications'
import './index.css'
import './design.css'
import './theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* URL-backed controls must commit synchronously; API requests have their own loading states. */}
    <BrowserRouter useTransitions={false}>
      <ConfigProvider>
        <AuthProvider>
          <NotificationsProvider>
            <App />
          </NotificationsProvider>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  </StrictMode>,
)

// Installable app + offline app shell. Production builds only: a service worker would get in the way of the dev server.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => undefined) })
}
