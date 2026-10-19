import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Same-origin in dev: the browser talks only to Vite, which proxies /api and /admin
// to Django. This keeps session cookies and CSRF identical to production.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
    },
  },
})
