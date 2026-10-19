import { expect, test } from '@playwright/test'

test('shell loads and reports backend + database connected', async ({ page }) => {
  await page.goto('/status')
  await expect(page.getByText('all transport data, payments and booking confirmations are simulated')).toBeVisible()
  await expect(page.getByTestId('system-status')).toContainText('Backend and database connected')
})

test('backend health endpoint responds through the same origin', async ({ request }) => {
  const res = await request.get('/api/health/')
  expect(res.ok()).toBeTruthy()
  expect((await res.json()).database).toBe('ok')
})

test('deep links survive a hard refresh (SPA fallback) and unknown API paths are JSON 404s', async ({ page, request }) => {
  await page.goto('/journeys')                        // protected deep link, signed out: must reach the login screen
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.goto('/status')
  await page.reload()
  await expect(page.getByTestId('system-status')).toContainText('Backend and database connected')
  const res = await request.get('/api/definitely-not-here/')
  expect(res.status()).toBe(404)
  // Django's DEBUG page (dev only) is HTML; deployed environments return the sanitised JSON error.
  if ((res.headers()['content-type'] ?? '').includes('json')) expect((await res.json()).code).toBe('not_found')
})

test('runtime config drives the simulation banner and release footer', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('note')).toContainText('not valid travel tickets')
  await expect(page.locator('footer')).toContainText('release')
})
