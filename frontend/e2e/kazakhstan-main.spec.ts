import { expect, test } from '@playwright/test'
import { demoDayIso } from './demo-day'

test('Kazakhstan is the home scenario and synthetic booking is clearly separate', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Doedu Kazakhstan', exact: true })).toBeVisible()
  await expect(page.getByText('Real ticket sales are not yet available.', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Real cities · saved plans · KZT · Kazakhstan time')).toBeVisible()
  await page.getByRole('link', { name: 'Try demo booking with fictional routes (EUR, Europe/Berlin)' }).click()
  await expect(page).toHaveURL(/\/demo$/)
  await expect(page.getByText('Fictional stops, EUR and Europe/Berlin time. No real tickets.')).toBeVisible()
  await expect(page.getByLabel('From', { exact: true })).toBeVisible()
})

test('legacy synthetic search links stay usable and strict access follows selection', async ({ page }) => {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=06:00&passengers=1`)
  await expect(page).toHaveURL(/\/demo\?origin=NG-BUS/)
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/search/' && new URL(r.url()).searchParams.get('wheelchair_required') === 'true' && r.ok())
  await page.locator('#journey-filters').getByLabel('Require a fully step-free journey').check()
  await expect(page).toHaveURL(/wheelchair_required=true/)
  const results = await response
  // The selected fixture may have zero accessible paths; unknown paths must never be offered.
  {
    const data = await results.json()
    for (const it of data.results) {
      for (const leg of it.legs) expect(Object.values(leg.accessibility)).toEqual(['yes', 'yes', 'yes'])
      for (const connection of it.connections) expect(connection.path_step_free).toBe('yes')
    }
    if (data.results.length) {
      await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
      await expect(page).toHaveURL(/wheelchair_required=true/)
    }
  }
})
