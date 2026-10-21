import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Browser, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Requires seeded demo data. Follow a line: notices about services leaving within 48 hours, without a booking.
const PASSWORD = process.env.DEMO_USER_PASSWORD ?? 'doedu-demo-2026'
const reverseSearch = `/?origin=RV-BUS&destination=NG-BUS&date=${demoDayIso()}&time=07:00&passengers=1&modes=bus`

async function register(page: Page, name: string) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill(name)
  await page.getByLabel('Email').fill(`fl-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/journeys/)
}

/** The Valley operator delays (or clears) the next VC1R service that leaves within the 48 hour horizon, via the real operator API. */
async function operatorDelaysNextVc1r(browser: Browser, minutes: number): Promise<number> {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill('ops.valley@doedu.test')
  await page.getByLabel('Password').fill(PASSWORD)
  await Promise.all([page.waitForResponse(r => r.url().includes('/api/auth/login/')), page.getByRole('button', { name: 'Sign in' }).click()])
  const list = await (await page.request.get('/api/operator/services/?route=VC1R')).json()
  const soon = list.results.find((s: { departs_at: string; status: string }) => Date.parse(s.departs_at) > Date.now() + 3600_000 && Date.parse(s.departs_at) < Date.now() + 40 * 3600_000 && s.status !== 'cancelled')
  expect(soon, 'a VC1R service within the next 40 hours').toBeTruthy()
  const token = (await ctx.cookies()).find(c => c.name === 'csrftoken')!.value
  const res = await page.request.post(`/api/operator/services/${soon.id}/change/`, { data: { action: 'delay', minutes }, headers: { 'X-CSRFToken': token } })
  expect(res.ok()).toBeTruthy()
  await ctx.close()
  return soon.id
}

test('follow a line from the journey, hear about a delay without a booking, then unfollow', async ({ page, browser }) => {
  await register(page, 'Fay Follower')
  await page.goto(reverseSearch)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  const follow = page.getByRole('region', { name: 'Follow these lines' })
  await expect(follow).toContainText('within 48 hours')
  const button = follow.getByRole('button', { name: 'Follow VC1R' })
  await button.click()
  await expect(follow.getByRole('button', { name: 'Following VC1R' })).toHaveAttribute('aria-pressed', 'true')
  await page.reload()                                                             // persisted on the server
  await expect(page.getByRole('region', { name: 'Follow these lines' }).getByRole('button', { name: 'Following VC1R' })).toBeVisible()

  try {
    await operatorDelaysNextVc1r(browser, 20)
    await page.goto('/notifications')
    await expect(page.getByText('Line VC1R: delayed by 20 min')).toBeVisible()
    await page.getByRole('link', { name: 'Open alerts' }).first().click()
    const followed = page.getByRole('region', { name: 'Followed lines' })
    await expect(followed).toContainText('VC1R')
    await expect(followed).toContainText('Valley Coaches')
    await followed.getByRole('button', { name: 'Unfollow VC1R' }).click()
    await expect(followed).toContainText('No followed lines yet.')
    await page.reload()
    await expect(page.getByRole('region', { name: 'Followed lines' })).toContainText('No followed lines yet.')
  } finally {
    await operatorDelaysNextVc1r(browser, 0)                                        // leave the shared demo data as found
  }
})

test('signed-out visitors are asked to sign in; the follow and alerts screens pass the accessibility scan', async ({ page }) => {
  await page.goto(reverseSearch)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await expect(page.getByRole('region', { name: 'Follow these lines' }).getByRole('link', { name: 'Sign in to follow lines' })).toBeVisible()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { document.documentElement.dataset.theme = t }, theme)
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(r.violations.map(v => `${v.id}: ${v.nodes[0]?.target.join(' ')}`), `axe on journey details (${theme})`).toEqual([])
  }
  await register(page, 'Axe Follower')
  await page.goto(reverseSearch)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await page.getByRole('button', { name: 'Follow VC1R' }).click()
  await page.goto('/alerts')
  await expect(page.getByRole('region', { name: 'Followed lines' })).toContainText('VC1R')
  for (const theme of ['light', 'dark']) {
    await page.evaluate(t => { document.documentElement.dataset.theme = t }, theme)
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(r.violations.map(v => `${v.id}: ${v.nodes[0]?.target.join(' ')}`), `axe on alerts with follows (${theme})`).toEqual([])
  }
})
