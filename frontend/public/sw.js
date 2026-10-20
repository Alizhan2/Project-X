/* Doedu service worker: offline app shell only.
 * - NEVER caches /api/, /admin/ or any non-GET request: no personal or booking data ever enters this cache.
 * - Static, content-hashed files (/assets, /fonts, /design, /icons) are cache-first; they never change under one URL.
 * - Page navigations are network-first; the last good index.html is the offline fallback (the SPA then shows its own offline state).
 * Bump VERSION to drop old caches. */
const VERSION = 'doedu-shell-v1'
const STATIC_PREFIXES = ['/assets/', '/fonts/', '/design/', '/icons/']

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== VERSION) await caches.delete(key)
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', event => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/')) return        // never intercepted

  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(VERSION)
      try {
        const fresh = await fetch(req)
        if (fresh.ok && fresh.headers.get('content-type')?.includes('text/html')) await cache.put('/index.html', fresh.clone())
        return fresh
      } catch {
        return (await cache.match('/index.html')) ?? Response.error()
      }
    })())
    return
  }
  if (STATIC_PREFIXES.some(p => url.pathname.startsWith(p)) || url.pathname === '/theme-init.js' || url.pathname === '/manifest.webmanifest') {
    event.respondWith((async () => {
      const cache = await caches.open(VERSION)
      const hit = await cache.match(req)
      if (hit) return hit
      const fresh = await fetch(req)
      if (fresh.ok) await cache.put(req, fresh.clone())
      return fresh
    })())
  }
})
