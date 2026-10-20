import { expect, test, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

// Requires seeded demo data. Saved travellers, connection-protection wording, trip activity.
async function register(page: Page, name: string) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill(name)
  await page.getByLabel('Email').fill(`cp-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('button', { name: /Sign out|Menu/ }).first()).toBeVisible()
}

async function startBooking(page: Page, passengers: number, time = '12:00') {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=${time}&passengers=${passengers}&sort=departure`)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await page.getByRole('link', { name: 'Continue to traveller details' }).click()
  await expect(page.getByRole('heading', { name: 'Traveller details' })).toBeVisible()
}

test('saved travellers: opt-in saving, one-tap reuse, and removal', async ({ page }) => {
  await register(page, 'Pat Example')
  await startBooking(page, 2)
  await expect(page.getByRole('group', { name: 'Saved travellers' })).toHaveCount(0)      // nothing saved yet
  await page.getByLabel('Passenger 2 full name').fill('Max Example')
  await page.getByLabel(/Save new names to my account/).check()
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await expect(page.getByRole('heading', { name: 'Payment', exact: true })).toBeVisible()

  // A second booking: the saved names appear as shortcuts, and a used name cannot be added twice.
  await startBooking(page, 2, '14:00')
  const group = page.getByRole('group', { name: 'Saved travellers' })
  await expect(group.getByRole('button', { name: 'Use Max Example as a passenger' })).toBeVisible()
  await page.getByLabel('Passenger 2 full name').fill('')
  await group.getByRole('button', { name: 'Use Max Example as a passenger' }).click()
  await expect(page.getByLabel('Passenger 2 full name')).toHaveValue('Max Example')
  await expect(group.getByRole('button', { name: 'Use Max Example as a passenger' })).toBeDisabled()

  // Management and deletion in My journeys.
  await page.goto('/journeys')
  const manage = page.getByRole('region', { name: 'Saved travellers' })
  await expect(manage).toContainText('Max Example')
  await manage.getByRole('button', { name: 'Remove Max Example' }).click()
  await expect(manage).not.toContainText('Max Example')
  await page.reload()
  await expect(page.getByRole('region', { name: 'Saved travellers' }).getByText('Max Example')).toHaveCount(0)
})

test('without the checkbox nothing is saved', async ({ page }) => {
  await register(page, 'Quiet Person')
  await startBooking(page, 1)
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await expect(page.getByRole('heading', { name: 'Payment', exact: true })).toBeVisible()
  const res = await page.request.get('/api/travellers/')
  expect(await res.json()).toEqual([])
})

test('a multimodal journey explains what protects each change; the booking shows its activity', async ({ page }) => {
  await register(page, 'Mia Protected')
  await page.goto(`/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=11:00&passengers=1&sort=buffer`)
  const card = page.locator('.result').filter({ hasText: 'Bus VC1' }).filter({ hasText: 'Train DR1' }).filter({ hasText: 'Taxi: Portmouth Harbour' }).first()
  await card.getByRole('link', { name: /^Select/ }).click()
  const protection = page.getByRole('region', { name: 'How this journey is protected' })
  await expect(protection).toContainText(/Change at .*: \d+ min to spare\. If the earlier service arrives more than \d+ min late/)
  await expect(protection).toContainText('Taxi after')
  await expect(protection).toContainText('not a prediction of punctuality')
  await expect(protection).toContainText('exact price difference')
  await expect(protection).toContainText('simulated')

  await page.getByRole('link', { name: 'Continue to traveller details' }).click()
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await page.getByRole('button', { name: 'Simulate failed payment' }).click()
  await expect(page.getByText(/Payment failed/)).toBeVisible()
  await page.getByRole('button', { name: 'Simulate successful payment' }).click()
  await expect(page.getByRole('heading', { name: /Booking confirmed/ })).toBeVisible()

  const activity = page.getByRole('region', { name: 'Trip activity' })
  await expect(activity.getByRole('listitem')).toHaveCount(3)
  await expect(activity.getByRole('listitem').nth(0)).toContainText('Places reserved')
  await expect(activity.getByRole('listitem').nth(1)).toContainText('Payment failed (simulated)')
  await expect(activity.getByRole('listitem').nth(2)).toContainText('Payment confirmed (simulated)')
  await expect(page.getByRole('region', { name: 'How this journey is protected' })).toBeVisible()   // also on the booking
})

test('direct journeys say there is no connection to miss', async ({ page }) => {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=12:00&passengers=1&max_transfers=0`)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await expect(page.getByRole('region', { name: 'How this journey is protected' })).toContainText('no connection to miss')
})
