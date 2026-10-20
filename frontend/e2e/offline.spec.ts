import { expect, test, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Requires seeded demo data. On-device copies of confirmed journeys (client-side offline view).
async function registerAndBook(page: Page) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Olive Offline')
  await page.getByLabel('Email').fill(`off-${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('button', { name: /Sign out|Menu/ }).first()).toBeVisible()
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=16:00&passengers=1&sort=departure`)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await page.getByRole('link', { name: 'Continue to traveller details' }).click()
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await page.getByRole('button', { name: 'Simulate successful payment' }).click()
  await expect(page.getByRole('heading', { name: /Booking confirmed/ })).toBeVisible()
  return (await page.getByTestId('reference').innerText()).trim()
}

test('a confirmed journey stays viewable offline, stores no e-mail, hides actions, and recovers when back online', async ({ page, context }) => {
  const ref = await registerAndBook(page)
  const stored = await page.evaluate(() => localStorage.getItem('doedu.offline.v1') ?? '')
  expect(stored).toContain(ref)
  expect(stored).not.toContain('@')                      // no e-mail address on the device
  expect(JSON.parse(stored).items[0].booking.payments).toEqual([])

  await context.setOffline(true)
  await expect(page.getByText('You are offline. Some features need a connection.')).toBeVisible()
  await page.getByRole('link', { name: 'My journeys' }).click()
  const saved = page.getByRole('region', { name: 'Saved on this device' })
  await expect(saved).toContainText(ref)
  await saved.getByRole('link', { name: ref }).click()
  await expect(page.getByTestId('offline-copy')).toContainText('not a valid travel ticket')
  await expect(page.getByRole('list', { name: 'Journey timeline' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Cancel this journey/ })).toHaveCount(0)    // actions need the server

  await context.setOffline(false)
  await expect(page.getByTestId('offline-copy')).toHaveCount(0, { timeout: 25000 })        // the quiet refresh replaces the copy
  await expect(page.getByRole('button', { name: /Cancel this journey/ })).toBeVisible()
})

test('signing out removes the on-device copies', async ({ page }) => {
  await registerAndBook(page)
  expect(await page.evaluate(() => localStorage.getItem('doedu.offline.v1'))).not.toBeNull()
  const menu = page.getByRole('button', { name: 'Menu' })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('button', { name: /Sign out/ }).click()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('doedu.offline.v1'))).toBeNull()
})
