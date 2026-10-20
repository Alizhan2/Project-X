import { demoDayIso } from './demo-day'
import { expect, test } from '@playwright/test'
import type { SearchResponse } from '../src/api'

// Requires seeded demo data: `python manage.py seed_demo` (demo day = reference date + 1).

test('search shows database-backed direct bus journeys with prices and simulated label', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('From', { exact: true }).selectOption({ label: 'Northgate Bus Station' })
  await page.getByLabel('To', { exact: true }).selectOption({ label: 'Riverton Bus Station' })
  await page.getByLabel('Date').fill(demoDayIso())
  await page.getByLabel('Earliest departure').fill('06:00')
  const searchResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/search/' && r.ok())
  await page.getByRole('button', { name: 'Search journeys' }).click()
  const data: SearchResponse = await (await searchResponse).json()

  await expect(page.getByText('Simulated data')).toBeVisible()
  const cards = page.locator('.result')
  await expect(cards.first()).toBeVisible()
  await expect(cards.first()).toContainText('EUR')
  await expect(cards).toHaveCount(data.results.length)
  // Additive demo schedules may have no disruption on tomorrow's date.
  // Check actual API delays rather than requiring an unrelated, consumed scenario.
  for (const leg of data.results.flatMap(it => it.legs).filter(l => l.status === 'delayed')) {
    await expect(page.getByText(`${leg.route_code}: Delayed by ${leg.delay_minutes} min`).first()).toBeVisible()
  }

  await page.getByLabel('Sort by').selectOption('price')
  await expect(page).toHaveURL(/sort=price/)
})

test('a party too large for the only taxi link gets a helpful empty state', async ({ page }) => {
  await page.goto(`/?origin=LK-BUS&destination=NG-BUS&date=${demoDayIso()}&time=06:00&passengers=9`)
  await expect(page.getByText('No journeys found.')).toBeVisible()
})

test('server validation errors are shown next to the field', async ({ page }) => {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=06:00&passengers=12`)
  await expect(page.getByText('Must be a whole number from 1 to 9.')).toBeVisible()
})
