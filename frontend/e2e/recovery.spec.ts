import { demoDayLabel } from './demo-day'
import { expect, test, type Browser, type Page } from '@playwright/test'

// Requires `manage.py seed_demo` (synthetic demo accounts + pre-booked journeys). Each scenario is consumed once per seed.
const PASSWORD = process.env.DEMO_USER_PASSWORD ?? 'doedu-demo-2026'

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: /Sign out/ })).toBeVisible()
}

/** The operator changes a service through the real operator UI. */
async function operatorChange(browser: Browser, email: string, route: string, time: string, action: 'delay' | 'cancel', minutes = 0) {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await signIn(page, email)
  await page.getByRole('link', { name: 'Operator' }).click()
  await page.locator('tr').filter({ hasText: route }).filter({ hasText: `${demoDayLabel()} ${time}` }).first().getByRole('link', { name: /Manage/ }).click()
  if (action === 'delay') {
    await page.getByLabel('Total delay (minutes, 0 clears)').fill(String(minutes))
    await page.getByRole('button', { name: 'Preview consequences' }).click()
    await page.getByRole('button', { name: `Confirm delay of ${minutes} min` }).click()
  } else {
    await page.getByLabel('Change', { exact: true }).selectOption('cancel')
    await page.getByRole('button', { name: 'Preview consequences' }).click()
    await page.getByRole('button', { name: 'Confirm cancellation of service' }).click()
  }
  await expect(page.getByText(/Applied\. \d+ booking\(s\) were notified/)).toBeVisible()
  await ctx.close()
}

async function openDisruptedBooking(page: Page, email: string) {
  await signIn(page, email)
  await page.goto('/notifications')
  await expect(page.getByText(/needs attention/).first()).toBeVisible()
  await page.getByRole('link', { name: /Open booking/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Your journey is disrupted' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Replacement options' })).toBeVisible()
}

test('delay breaks the connection; an offer made stale by another service change is refused, then a fresh one is accepted', async ({ browser }) => {
  await operatorChange(browser, 'ops.valley@doedu.test', 'VC1', '14:00', 'delay', 45)
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await openDisruptedBooking(page, 'demo.passenger@doedu.test')

  await expect(page.getByText('Kept as booked')).toBeVisible()
  const offers = page.getByTestId('offer')
  await expect(offers.first()).toBeVisible()
  await expect(offers.first()).toContainText('Places are not held until you accept')
  await expect(offers.first()).toContainText(/wheelchair vehicle/i)

  // The first offered service gets cancelled by its operator behind the passenger's back.
  const ref = (await page.locator('[data-testid="reference"]').innerText()).trim()
  const data = await (await page.request.get(`/api/bookings/${ref}/replacements/`)).json()
  const svc = data.offers[0].legs.find((l: { departure_id: number | null }) => l.departure_id)
  const opEmail = svc.route_code.startsWith('DR') ? 'ops.rail@doedu.test' : svc.route_code.startsWith('GL') ? 'ops.greenline@doedu.test' : 'ops.valley@doedu.test'
  const octx = await browser.newContext()
  const op = await octx.newPage()
  await signIn(op, opEmail)
  const token = (await octx.cookies()).find((c) => c.name === 'csrftoken')!.value
  const res = await op.request.post(`/api/operator/services/${svc.departure_id}/change/`, { data: { action: 'cancel', minutes: 0 }, headers: { 'X-CSRFToken': token } })
  expect(res.ok()).toBeTruthy()
  await octx.close()

  await offers.first().getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('group', { name: 'Confirm replacement' }).getByRole('button', { name: /Confirm replacement|and confirm/ }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Options were refreshed' })).toBeVisible()

  // A fresh option works.
  await page.getByTestId('offer').first().getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('group', { name: 'Confirm replacement' }).getByRole('button', { name: /Confirm replacement|and confirm/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Replacement options' })).toHaveCount(0)
  await expect(page.getByText('Original legs that were replaced (history)')).toBeVisible()
  await ctx.close()
})

test('replacement that costs more: failed simulated top-up changes nothing, retry succeeds', async ({ browser }) => {
  await operatorChange(browser, 'ops.valley@doedu.test', 'VC1', '12:00', 'cancel')
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await openDisruptedBooking(page, 'demo.pay@doedu.test')
  const pay = page.getByTestId('offer').filter({ hasText: 'Extra to pay' }).first()
  await expect(pay).toContainText('EUR 0.10')
  await pay.getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('button', { name: 'Simulate failed payment' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Nothing was changed' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your journey is disrupted' })).toBeVisible() // original still intact
  await page.getByRole('button', { name: /Pay EUR 0.10 \(simulated\) and confirm/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByText(/Replacement top-up: succeeded/)).toBeVisible()
  await ctx.close()
})

test('cheaper replacement: simulated refund of the difference', async ({ browser }) => {
  await operatorChange(browser, 'ops.greenline@doedu.test', 'GL1', '12:30', 'cancel')
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await openDisruptedBooking(page, 'demo.refund@doedu.test')
  const cheaper = page.getByTestId('offer').filter({ hasText: 'You get back' }).first()
  await expect(cheaper).toContainText('EUR 0.10')
  await cheaper.getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('button', { name: /Confirm replacement and receive refund/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByTestId('refund')).toContainText('Cheaper replacement journey')
  await ctx.close()
})

test('no alternative: clear explanation and full-refund cancellation', async ({ browser }) => {
  await operatorChange(browser, 'ops.rail@doedu.test', 'DR1', '18:10', 'delay', 60)
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await signIn(page, 'demo.noalt@doedu.test')
  await page.goto('/notifications')
  await page.getByRole('link', { name: /Open booking/ }).first().click()
  await expect(page.getByRole('heading', { name: 'No replacement found' })).toBeVisible()
  await expect(page.getByTestId('offer')).toHaveCount(0)
  await page.getByRole('button', { name: 'Review cancellation and refund' }).click()
  await expect(page.getByText('refunded in full')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm cancellation' }).click()
  await expect(page.getByTestId('refund')).toContainText('Cancelled after disruption')
  await expect(page.getByTestId('status')).toContainText('Cancelled')
  await ctx.close()
})
