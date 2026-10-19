import { demoDayIso } from './demo-day'
import { expect, test } from '@playwright/test'

// Requires seeded demo data. Books a Bus -> Train -> Taxi journey end to end.

test('passenger finds, compares and books a Bus → Train → Taxi journey', async ({ page }) => {
  await page.goto(`/register`)
  await page.getByLabel('Full name').fill('Mia Multimodal')
  await page.getByLabel('Email').fill(`mm-${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'My journeys' })).toBeVisible()

  await page.goto(`/?origin=NG-BUS&destination=PM-MARINA&date=${demoDayIso()}&time=11:00&passengers=2&sort=buffer`)
  const first = page.locator('.result').filter({ hasText: 'Bus VC1' }).filter({ hasText: 'Train DR1' }).filter({ hasText: 'Taxi: Portmouth Harbour Station' }).first()
  await expect(first).toBeVisible()
  await expect(first).toContainText('Bus VC1')
  await expect(first).toContainText('Train DR1')
  await expect(first).toContainText('2 transfers')
  await expect(first).toContainText('not a prediction of punctuality')

  // Sorting by buffer is reflected in the URL and keeps results stable.
  await expect(page.getByLabel('Sort by')).toHaveValue('buffer')
  await page.getByLabel('Transfers').selectOption('1')
  await expect(page.locator('.result').filter({ hasText: '2 transfers' })).toHaveCount(0)
  await page.getByLabel('Transfers').selectOption('any')

  await first.getByRole('link', { name: /^Select/ }).click()
  await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible()
  await expect(page.getByText('per taxi (up to 4 passengers)')).toBeVisible()
  await page.getByRole('link', { name: 'Continue to traveller details' }).click()
  await page.getByLabel('Passenger 2 full name').fill('Max Multimodal')
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await page.getByRole('button', { name: 'Simulate successful payment' }).click()

  await expect(page.getByRole('heading', { name: /Booking confirmed/ })).toBeVisible()
  await expect(page.getByText('Taxi (simulated)')).toBeVisible()
  await expect(page.getByText(/bus VC1/)).toBeVisible()
  await expect(page.getByText(/train DR1/)).toBeVisible()
})
