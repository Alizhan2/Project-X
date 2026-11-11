import { demoDayIso, demoDayLabel } from './demo-day'
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

  // Ask for a future replacement starting at the original origin; this fixture needs a
  // scheduled service to exercise an operator invalidating an already displayed offer.
  await page.getByLabel('Earliest departure', { exact: true }).fill(`${demoDayIso()}T14:00`)
  await page.getByLabel('Latest acceptable arrival').fill(`${demoDayIso()}T23:30`)
  await page.getByLabel('Maximum payment now', { exact: false }).fill('30')
  const optionsResponse = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/replacements/') && new URL(r.url()).searchParams.has('max_payment_now') && r.ok())
  await page.getByRole('button', { name: 'Find replacement journeys' }).click()
  const data = await (await optionsResponse).json()
  const serviceOffer = data.offers.find((o: { legs: { departure_id: number | null }[] }) => o.legs.some(l => l.departure_id))
  expect(serviceOffer, 'fixture must offer a scheduled service for operator invalidation').toBeTruthy()
  const offers = page.getByTestId('offer')
  await expect(offers.first()).toBeVisible()
  await expect(offers.first()).toContainText('Places are not held until you accept')
  await expect(offers.first()).toContainText(/wheelchair vehicle/i)

  // The first offered service gets cancelled by its operator behind the passenger's back.
  const svc = serviceOffer.legs.find((l: { departure_id: number | null }) => l.departure_id)
  const opEmail = svc.route_code.startsWith('DR') ? 'ops.rail@doedu.test' : svc.route_code.startsWith('GL') ? 'ops.greenline@doedu.test' : 'ops.valley@doedu.test'
  const octx = await browser.newContext()
  const op = await octx.newPage()
  await signIn(op, opEmail)
  const token = (await octx.cookies()).find((c) => c.name === 'csrftoken')!.value
  const res = await op.request.post(`/api/operator/services/${svc.departure_id}/change/`, { data: { action: 'cancel', minutes: 0 }, headers: { 'X-CSRFToken': token } })
  expect(res.ok()).toBeTruthy()
  await octx.close()

  await page.locator(`[data-offer-id="${serviceOffer.id}"]`).getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('group', { name: 'Confirm replacement' }).getByRole('button', { name: /Pay full replacement price and confirm/ }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Options were refreshed' })).toBeVisible()

  // A fresh option works.
  await page.getByTestId('offer').first().getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('group', { name: 'Confirm replacement' }).getByRole('button', { name: /Pay full replacement price and confirm/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Replacement options' })).toHaveCount(0)
  await expect(page.getByText('Original legs that were replaced (history)')).toBeVisible()
  const ref = await page.getByTestId('reference').innerText()
  const current = await (await page.request.get(`/api/bookings/${ref}/`)).json()
  const cached = await page.evaluate(reference => JSON.parse(localStorage.getItem('doedu.offline.v1')!).items.find((item: { booking: { reference: string } }) => item.booking.reference === reference).booking, ref)
  expect(cached.legs).toEqual(current.legs)
  expect(cached.legs.some((leg: { status: string }) => leg.status === 'replaced')).toBe(true)
  await ctx.close()
})

test('replacement charges full price: failed payment preserves original, retry succeeds', async ({ browser }) => {
  await operatorChange(browser, 'ops.valley@doedu.test', 'VC1', '12:00', 'cancel')
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await openDisruptedBooking(page, 'demo.pay@doedu.test')
  const pay = page.getByTestId('offer').filter({ hasText: 'Pay now:' }).first()
  await expect(pay).toContainText('Eligible old-leg refund (separate):')
  await pay.getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('button', { name: 'Simulate failed payment' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Nothing was changed' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your journey is disrupted' })).toBeVisible() // original still intact
  await page.getByRole('button', { name: /Pay full replacement price and confirm/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByText(/Replacement payment: succeeded/)).toBeVisible()
  await ctx.close()
})

test('replacement payment and old-leg refund are recorded separately', async ({ browser }) => {
  await operatorChange(browser, 'ops.greenline@doedu.test', 'GL1', '12:30', 'cancel')
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await openDisruptedBooking(page, 'demo.refund@doedu.test')
  const cheaper = page.getByTestId('offer').filter({ hasText: 'Eligible old-leg refund (separate):' }).first()
  await expect(cheaper).toContainText('Pay now:')
  await cheaper.getByRole('button', { name: 'Choose this journey' }).click()
  await page.getByRole('button', { name: /Pay full replacement price and confirm/ }).click()
  await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
  await expect(page.getByTestId('refund')).toContainText('Refund for replaced legs')
  await ctx.close()
})

test('no alternative: constraints are explained and policy-based cancellation is available', async ({ browser }) => {
  await operatorChange(browser, 'ops.rail@doedu.test', 'DR1', '18:10', 'delay', 60)
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await signIn(page, 'demo.noalt@doedu.test')
  await page.goto('/notifications')
  await page.getByRole('link', { name: /Open booking/ }).first().click()
  await page.getByLabel('Maximum payment now', { exact: false }).fill('0')
  await page.getByRole('button', { name: 'Find replacement journeys' }).click()
  await expect(page.getByRole('heading', { name: 'No replacement found' })).toBeVisible()
  await expect(page.getByTestId('offer')).toHaveCount(0)
  await page.getByRole('button', { name: 'Review cancellation policy' }).click()
  await expect(page.getByRole('region', { name: 'Cancellation and refund' }).getByText('A delay alone does not guarantee a full refund. The cancellation policy saved at purchase applies.')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm cancellation' }).click()
  await expect(page.getByTestId('refund')).toContainText('Cancelled after disruption')
  await expect(page.getByTestId('status')).toContainText('Cancelled')
  await ctx.close()
})
