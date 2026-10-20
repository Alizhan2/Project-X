import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Requires seeded demo data. Covers the route overview, the nearby-days strip and the dark theme.
const results = (extra = '') => `/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=06:00&passengers=1${extra}`

async function scan(page: Page, where: string) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(r.violations.map(v => `${v.id}: ${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ')}`), `axe on ${where}`).toEqual([])
}

test('results show a route overview for each journey and the same overview inside the timeline', async ({ page }) => {
  await page.goto(results('&sort=duration'))
  const first = page.locator('.result').first()
  await expect(first).toBeVisible()
  const overview = first.getByRole('img', { name: /Route overview/ })
  await expect(overview).toBeVisible()
  await expect(overview).toHaveAttribute('aria-label', /→/)
  await first.getByRole('link', { name: /^Select/ }).click()
  await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible()
  await expect(page.locator('.route-line:not(.route-line-compact)').first()).toBeVisible()
  await expect(page.locator('.route-line .rl-stops').first()).toContainText('Northgate')
})

test('nearby days strip: shows seven days, marks the chosen one, and switching a day re-runs the search', async ({ page }) => {
  await page.goto(results())
  const strip = page.getByRole('region', { name: 'Nearby days' })
  await expect(strip.getByRole('button')).toHaveCount(7)
  await expect(strip.locator('[aria-current=date]')).toHaveCount(1)
  await expect(strip.locator('[aria-current=date] strong')).toContainText('EUR')
  const other = strip.locator('button:not([aria-current]):not(:disabled)').first()
  await expect(other).toBeVisible()
  await other.click()
  await expect(page).not.toHaveURL(new RegExp(`date=${demoDayIso()}`))
  await expect(page.locator('.result').first()).toBeVisible()
  await expect(strip.locator('[aria-current=date]')).toHaveCount(1)
})

test('nearby days strip is not shown for arrive-by searches', async ({ page }) => {
  await page.goto(results('&time_mode=arrival'))
  await expect(page.locator('.result, .empty').first()).toBeVisible()
  await expect(page.getByRole('region', { name: 'Nearby days' })).toHaveCount(0)
})

for (const [name, viewport] of [['desktop', { width: 1100, height: 900 }], ['mobile', { width: 390, height: 800 }]] as const) {
  test(`dark theme (${name}): toggle persists across reload and passes the accessibility scan`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('doedu.theme'))
    await page.reload()
    const menu = page.getByRole('button', { name: 'Menu' })
    if (await menu.isVisible()) await menu.click()
    await page.getByRole('button', { name: 'Dark theme' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await scan(page, `home (dark, ${name})`)
    await page.goto(results())
    await expect(page.locator('.result').first()).toBeVisible()
    await scan(page, `results (dark, ${name})`)
    await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
    await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible()
    await scan(page, `journey details (dark, ${name})`)
    await page.evaluate(() => localStorage.removeItem('doedu.theme'))
  })
}

test('"Lowest price" badge appears only when day prices differ', async ({ page }) => {
  await page.goto(results())
  const strip = page.getByRole('region', { name: 'Nearby days' })
  await expect(strip.getByRole('button')).toHaveCount(7)
  const prices = await strip.locator('.day-chip strong').allInnerTexts()
  const badges = await strip.locator('.day-chip-badge').count()
  if (new Set(prices).size > 1) {
    expect(badges).toBeGreaterThan(0)
    expect(badges).toBeLessThan(prices.length)   // not every day can be "the lowest"
  } else {
    expect(badges).toBe(0)                        // all prices equal: a badge would be meaningless
  }
})

test.describe('mobile layout regressions', () => {
  test.use({ viewport: { width: 390, height: 800 } })

  test('no page scrolls sideways on a phone (wide tables scroll inside their own region)', async ({ page }) => {
    const overflow = async (where: string) => {
      await page.waitForTimeout(400)
      const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
      expect(scroll, `horizontal overflow on ${where}`).toBeLessThanOrEqual(width)
    }
    await page.goto('/'); await overflow('home')
    await page.goto(results()); await expect(page.locator('.result').first()).toBeVisible(); await overflow('results')
    await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
    await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible(); await overflow('journey details')
    await expect(page.getByRole('region', { name: 'Fare and accessibility per leg' })).toBeVisible()   // the table sits in a scroll region
    await page.goto('/kazakhstan'); await overflow('kazakhstan')
  })

  test('booking form and an unpaid booking read correctly on a phone', async ({ page }) => {
    await page.goto('/register')
    await page.getByLabel('Full name').fill('Mobile Mia')
    await page.getByLabel('Email').fill(`mm-${Date.now()}@example.com`)
    await page.getByLabel('Password').fill('correct-horse-42')
    await page.getByRole('button', { name: 'Create account' }).click()
    await expect(page).toHaveURL(/\/journeys/)                  // registration finished (the Menu button exists before sign-in on phones)
    await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=18:00&passengers=1`)
    await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
    await page.getByRole('link', { name: 'Continue to traveller details' }).click()
    await expect(page.getByRole('heading', { name: 'Traveller details' })).toBeVisible()
    await page.waitForTimeout(400)
    const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
    expect(scroll).toBeLessThanOrEqual(width)
    await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
    await expect(page.getByTestId('countdown')).toBeVisible()
    await page.goBack()
    await page.goto('/journeys')
    await page.getByRole('link', { name: /DD-/ }).first().click()
    await expect(page.getByTestId('status')).toContainText('Awaiting payment')
    await expect(page.getByTestId('net-paid')).toHaveCount(0)                       // nothing has been paid yet
    await expect(page.locator('footer .sim-banner')).toContainText(/^(Development build|Demonstration) — all transport data/)
  })
})
