import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Automated WCAG 2.1 A/AA scan (axe-core). This finds many, not all, accessibility problems: it does not replace
// manual keyboard/screen-reader testing. Requires `manage.py seed_demo`.
const PASSWORD = process.env.DEMO_USER_PASSWORD ?? 'doedu-demo-2026'
const VIEWPORTS = { desktop: { width: 1100, height: 900 }, mobile: { width: 390, height: 800 } }

async function scan(page: Page, where: string) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const summary = r.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`)
  expect(summary, `axe violations on ${where}`).toEqual([])
}

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // On narrow screens the account controls live in the collapsed menu: open it before looking for them.
  const menu = page.getByRole('button', { name: 'Menu' })
  if (await menu.isVisible()) await menu.click()
  await expect(page.getByRole('button', { name: /Sign out/ })).toBeVisible()
}

for (const [name, size] of Object.entries(VIEWPORTS)) {
  test.describe(`accessibility (${name})`, () => {
    test.use({ viewport: size })

    test('public pages', async ({ page }) => {
      await page.goto('/'); await scan(page, 'search (empty)')
      await page.goto(`/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=11:00&passengers=1&sort=price`)
      await expect(page.locator('.result').first()).toBeVisible(); await scan(page, 'search results')
      await page.goto(`/?origin=LK-BUS&destination=NG-BUS&date=${demoDayIso()}&time=06:00&passengers=9`)
      await expect(page.getByText('No journeys found.')).toBeVisible(); await scan(page, 'search empty state')
      await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=06:00&passengers=12`)
      await expect(page.getByText('Must be a whole number from 1 to 9.')).toBeVisible(); await scan(page, 'search validation error')
      await page.goto(`/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=11:00&passengers=1`)
      await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
      await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible(); await scan(page, 'journey details')
      for (const path of ['/login', '/register', '/status']) { await page.goto(path); await scan(page, path) }
    })

    test('passenger pages', async ({ page }) => {
      await signIn(page, 'demo.refund@doedu.test')
      await page.goto('/journeys'); await expect(page.getByRole('heading', { name: 'My journeys' })).toBeVisible(); await scan(page, 'my journeys')
      await page.goto('/notifications'); await scan(page, 'notifications')
      await page.goto('/journeys'); await page.getByRole('link', { name: /DD-/ }).first().click()
      await expect(page.getByTestId('status')).toBeVisible(); await scan(page, 'booking details')
      await page.getByRole('button', { name: 'Cancel this journey…' }).click()
      await expect(page.getByTestId('quote-total')).toBeVisible(); await scan(page, 'cancellation quote')
    })

    test('traveller, payment and operator pages', async ({ page, browser }) => {
      await signIn(page, 'demo.passenger@doedu.test')
      await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=16:00&passengers=1`)
      await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
      await page.getByRole('link', { name: 'Continue to traveller details' }).click()
      await expect(page.getByRole('heading', { name: 'Traveller details' })).toBeVisible(); await scan(page, 'traveller details')
      await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
      await expect(page.getByTestId('countdown')).toBeVisible(); await scan(page, 'payment simulator')
      await page.getByRole('button', { name: 'Simulate failed payment' }).click()
      await expect(page.getByText(/Payment failed/)).toBeVisible(); await scan(page, 'payment failed')

      const ctx = await browser.newContext({ viewport: size })
      const op = await ctx.newPage()
      await signIn(op, 'ops.valley@doedu.test')
      await op.goto('/operator'); await expect(op.getByTestId('services-table')).toBeVisible(); await scan(op, 'operator services')
      await op.goto('/operator/new'); await scan(op, 'operator create service')
      await op.goto('/operator'); await op.getByRole('link', { name: /Manage/ }).first().click()
      await op.getByRole('button', { name: 'Preview consequences' }).click()
      await expect(op.getByTestId('impact-summary')).toBeVisible(); await scan(op, 'operator service + impact')
      await ctx.close()
    })
  })
}
