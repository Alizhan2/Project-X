import { demoDayIso, demoDayLabel } from './demo-day'
import { expect, test } from '@playwright/test'

// Requires freshly seeded demo data (`manage.py seed_demo`): the delay applied here persists.
const DEMO_PASSWORD = process.env.DEMO_USER_PASSWORD ?? 'doedu-demo-2026'

test('operator delay breaks a passenger connection; passenger is notified and cancels with a full refund', async ({ browser }) => {
  // ---- passenger books Bus VC1 12:00 -> Train DR1 -> Taxi (40 min to spare at the tight connection)
  const pCtx = await browser.newContext()
  const passenger = await pCtx.newPage()
  await passenger.goto('/register')
  await passenger.getByLabel('Full name').fill('Dana Disrupted')
  await passenger.getByLabel('Email').fill(`dd-${Date.now()}@example.com`)
  await passenger.getByLabel('Password').fill('correct-horse-42')
  await passenger.getByRole('button', { name: 'Create account' }).click()
  await expect(passenger.getByRole('heading', { name: 'My journeys' })).toBeVisible()

  await passenger.goto(`/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=12:00&passengers=1&sort=departure`)
  const card = passenger.locator('.result').filter({ hasText: '12:00 →' }).filter({ hasText: 'Bus VC1' })
    .filter({ hasText: 'Train DR1' }).filter({ hasText: 'Taxi: Portmouth Harbour' }).filter({ hasText: '40 min' }).first()
  await card.getByRole('link', { name: /^Select/ }).click()
  await passenger.getByRole('link', { name: 'Continue to traveller details' }).click()
  await passenger.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await passenger.getByRole('button', { name: 'Simulate successful payment' }).click()
  await expect(passenger.getByRole('heading', { name: /Booking confirmed/ })).toBeVisible()
  const ref = await passenger.getByTestId('reference').innerText()

  // ---- operator previews, then applies, a 45 minute delay
  const oCtx = await browser.newContext()
  const operator = await oCtx.newPage()
  await operator.goto('/login')
  await operator.getByLabel('Email').fill('ops.valley@doedu.test')
  await operator.getByLabel('Password').fill(DEMO_PASSWORD)
  await operator.getByRole('button', { name: 'Sign in' }).click()
  await operator.getByRole('link', { name: 'Operator' }).click()
  await expect(operator.getByRole('heading', { name: 'My services' })).toBeVisible()
  const row = operator.locator('tr').filter({ hasText: 'VC1' }).filter({ hasText: `${demoDayLabel()} 12:00` }).first()
  await row.getByRole('link', { name: /Manage/ }).click()
  await operator.getByLabel('Total delay (minutes, 0 clears)').fill('45')
  await operator.getByRole('button', { name: 'Preview consequences' }).click()
  await expect(operator.getByTestId('impact-summary')).toContainText('would be broken')
  await expect(operator.getByRole('row', { name: new RegExp(ref) })).toContainText('Journey broken: connection missed')
  await expect(operator.getByText(/@example\.com/)).toHaveCount(0) // no passenger contact data
  await operator.getByRole('button', { name: 'Confirm delay of 45 min' }).click()
  await expect(operator.getByText(/Applied\. \d+ booking\(s\) were notified/)).toBeVisible()

  // ---- passenger sees the notification and the disrupted booking, then cancels for a full refund
  await passenger.goto('/notifications')
  await expect(passenger.getByText(`Your journey ${ref} needs attention`)).toBeVisible()
  await passenger.getByRole('link', { name: `Open booking ${ref}` }).first().click()
  await expect(passenger.getByRole('heading', { name: 'Your journey is disrupted' })).toBeVisible()
  await passenger.getByRole('button', { name: 'Cancel this journey…' }).click()
  await expect(passenger.getByText('refunded in full')).toBeVisible()
  const total = (await passenger.getByTestId('quote-total').innerText())
  await passenger.getByRole('button', { name: 'Confirm cancellation' }).click()
  await expect(passenger.getByTestId('refund')).toContainText('Cancelled after disruption')
  await expect(passenger.getByTestId('refund')).toContainText(total.replace('EUR ', ''))
  await expect(passenger.getByTestId('status')).toContainText('Cancelled')
  await pCtx.close(); await oCtx.close()
})

test('a passenger cannot use the operator area', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Nosy Passenger')
  await page.getByLabel('Email').fill(`np-${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'My journeys' })).toBeVisible()
  await page.goto('/operator')
  await expect(page.getByRole('alert')).toContainText('only for operator accounts')
  const res = await page.request.get('/api/operator/services/')
  expect(res.status()).toBe(403)
})
