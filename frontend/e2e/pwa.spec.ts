import { expect, test } from '@playwright/test'

// Service worker behaviour exists only in a production build: run against `vite preview` with PWA_PREVIEW=1
// (see README "PWA"). Skipped on the dev server.
test.skip(!process.env.PWA_PREVIEW, 'needs a production build (vite preview)')

test('manifest is valid and installable metadata is present', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.locator('link[rel=manifest]')).toHaveAttribute('href', '/manifest.webmanifest')
  const manifest = await (await request.get('/manifest.webmanifest')).json()
  expect(manifest.display).toBe('standalone')
  expect(manifest.start_url).toBe('/')
  for (const icon of manifest.icons) expect((await request.get(icon.src)).ok(), icon.src).toBeTruthy()
  expect(manifest.icons.some((i: { purpose?: string }) => i.purpose === 'maskable')).toBe(true)
  expect(manifest.name).toMatch(/demonstration/i)
})

test('the app shell loads offline, and no API data is ever cached', async ({ page, context }) => {
  await page.goto('/')
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()                                           // now controlled by the worker
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await page.goto('/status')                                    // makes API calls while online
  await expect(page.getByTestId('system-status')).toContainText('connected')

  const cached = await page.evaluate(async () => {
    const urls: string[] = []
    for (const key of await caches.keys()) for (const r of await (await caches.open(key)).keys()) urls.push(new URL(r.url).pathname)
    return urls
  })
  expect(cached.length).toBeGreaterThan(0)
  expect(cached.filter(u => u.startsWith('/api/') || u.startsWith('/admin/'))).toEqual([])

  await context.setOffline(true)
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()               // served from the cache
  await expect(page.getByText('You are offline. Some features need a connection.')).toBeVisible()
})
