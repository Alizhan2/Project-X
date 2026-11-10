import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test.describe('help centre', () => {
  for (const [name, size] of Object.entries({ desktop: { width: 1100, height: 900 }, mobile: { width: 390, height: 800 } })) {
    test(`opens, expands and is accessible (${name})`, async ({ page }) => {
      await page.setViewportSize(size)
      await page.goto('/demo')
      const menu = page.getByRole('button', { name: 'Menu' })
      if (await menu.isVisible()) await menu.click()
      await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Help' }).click()
      await expect(page.getByRole('heading', { name: 'Help', level: 1 })).toBeVisible()
      await page.getByText('What does "simulated" mean?').click()
      await expect(page.getByText('no money is ever charged')).toBeVisible()
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
      expect(r.violations.map((v) => v.id)).toEqual([])
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    })
  }
})
