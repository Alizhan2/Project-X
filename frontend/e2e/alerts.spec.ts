import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Browser, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Requires seeded demo data. Alerts ("watches"): price drop and availability.
const PASSWORD = process.env.DEMO_USER_PASSWORD ?? 'doedu-demo-2026'
const busSearch = (extra = '') => `/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=11:30&passengers=1&modes=bus${extra}`

async function register(page: Page, name: string) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill(name)
  await page.getByLabel('Email').fill(`al-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/journeys/)
}

/** The Valley operator changes a fare through the real operator API (same session cookies and CSRF as the UI). */
async function operatorSetsFare(browser: Browser, price: string) {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill('ops.valley@doedu.test')
  await page.getByLabel('Password').fill(PASSWORD)
  await Promise.all([page.waitForResponse(r => r.url().includes('/api/auth/login/')), page.getByRole('button', { name: 'Sign in' }).click()])
  const routes = await (await page.request.get('/api/operator/routes/')).json()
  const fare = routes.results.find((r: { code: string }) => r.code === 'VC1').fares.find((f: { from: string; to: string }) => f.from === 'Northgate Bus Station' && f.to === 'Riverton Bus Station')
  const token = (await ctx.cookies()).find(c => c.name === 'csrftoken')!.value
  const res = await page.request.patch(`/api/operator/fares/${fare.id}/`, { data: { price }, headers: { 'X-CSRFToken': token } })
  expect(res.ok()).toBeTruthy()
  await ctx.close()
}

test('price alert: saved from the results, notifies when the operator lowers the fare, and the link reopens the search', async ({ page, browser }) => {
  await register(page, 'Alex Alert')
  await page.goto(busSearch())
  await expect(page.locator('.result').first()).toBeVisible()
  const prompt = page.getByRole('region', { name: 'Get notified' })
  await expect(prompt).toContainText('they do not hold places'.replace('they', 'They'))
  await prompt.getByRole('button', { name: /Notify me if the price drops \(now from EUR 7\.00\)/ }).click()
  await expect(prompt.getByRole('status')).toContainText('Alert saved.')

  await operatorSetsFare(browser, '3.00')
  try {
    await page.goto('/alerts')                                              // listing checks the alert, even without a running worker
    await expect(page.getByText('Cheapest when you last looked: EUR 3.00')).toBeVisible()
    await page.goto('/notifications')
    await expect(page.getByText('Price dropped: Northgate Bus Station → Riverton Bus Station')).toBeVisible()
    await page.getByRole('link', { name: 'Open search' }).first().click()
    await expect(page).toHaveURL(/origin=NG-BUS/)
    await expect(page.locator('.result').first()).toContainText('EUR 3.00')
  } finally {
    await operatorSetsFare(browser, '7.00')          // leave the shared demo data as found: other specs rely on the seeded fare
  }
})

test('availability alert when nothing matches; it can be listed, scanned for accessibility and removed', async ({ page }) => {
  await register(page, 'Wendy Waiting')
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=11:30&passengers=1&modes=taxi`)
  await expect(page.getByText('No journeys found.')).toBeVisible()
  const prompt = page.getByRole('region', { name: 'Get notified' })
  await prompt.getByRole('button', { name: 'Notify me when a journey becomes available' }).click()
  await expect(prompt.getByRole('status')).toContainText('Alert saved.')
  await prompt.getByRole('link', { name: 'See your alerts' }).click()
  const item = page.locator('.alert-item')
  await expect(item).toContainText('Journey becomes available')
  await expect(item.locator('.badge')).toHaveText('Active')
  await page.emulateMedia({ reducedMotion: 'reduce' })               // no colour transitions mid-scan when the theme is switched
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { document.documentElement.dataset.theme = t }, theme)
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(r.violations.map(v => `${v.id}: ${v.nodes[0]?.target.join(' ')}`), `axe on alerts (${theme})`).toEqual([])
  }
  await item.getByRole('button', { name: /Remove alert/ }).click()
  await expect(page.getByText('No alerts yet.')).toBeVisible()
  await page.reload()
  await expect(page.getByText('No alerts yet.')).toBeVisible()
})

test('a price alert is not offered when no journey exists, and signed-out visitors are asked to sign in', async ({ page }) => {
  await page.goto(busSearch())
  await expect(page.locator('.result').first()).toBeVisible()
  await expect(page.getByRole('region', { name: 'Get notified' }).getByRole('link', { name: 'Sign in to get alerts' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Get notified' }).getByRole('button')).toHaveCount(0)
})

test('arrive-by searches do not offer alerts', async ({ page }) => {
  await page.goto(busSearch('&time_mode=arrival'))
  await expect(page.locator('.result, .empty').first()).toBeVisible()
  await expect(page.getByRole('region', { name: 'Get notified' })).toHaveCount(0)
})
