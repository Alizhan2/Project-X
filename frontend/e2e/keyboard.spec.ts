import { expect, test } from '@playwright/test'
import { demoDayIso } from './demo-day'

test('search and selection work by keyboard alone, with visible focus', async ({ page }) => {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=16:00&passengers=1`)
  await expect(page.locator('.result').first()).toBeVisible()

  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()

  // Walk the tab order until the first result's Select link; it must be reachable and show a focus outline.
  let reached = false
  for (let i = 0; i < 40 && !reached; i++) {
    await page.keyboard.press('Tab')
    reached = await page.evaluate(() => document.activeElement?.textContent?.startsWith('Select') ?? false)
  }
  expect(reached).toBe(true)
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle)
  expect(outline).not.toBe('none')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible()

  // The sort control is operable with the keyboard and updates the URL.
  await page.goBack()
  await page.getByLabel('Sort by').focus()
  await page.keyboard.type('Lowest')
  await expect(page).toHaveURL(/sort=price/)
})
