import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { demoDayIso } from './demo-day'

const messages = JSON.parse(readFileSync(new URL('../src/messages.json', import.meta.url), 'utf8')) as Record<string, { ru: string; kk: string }>

test('Kazakhstan demo covers the official city directory and keeps the fictional region separate', async ({ page, request }) => {
  const response = await request.get('/api/kazakhstan/catalog/')
  expect(response.ok()).toBeTruthy()
  const catalog = await response.json()
  expect(catalog.cities).toHaveLength(90)
  expect(catalog.geography.as_of).toBe('2026-11-04')
  expect(catalog.simulated).toBe(true)
  expect(catalog.booking_enabled).toBe(true)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Doedu Kazakhstan', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Kazakhstan booking demo' })).toBeVisible()
  await expect(page.getByText('Real cities · saved plans · KZT · Kazakhstan time')).toBeVisible()
  await page.locator('#kz-filter-origin').fill('Капчагай')
  await expect(page.locator('#kz-select-origin option[value="kz-konaev"]')).toHaveCount(1)
  await page.getByRole('link', { name: 'Other demo scenarios (fictional region, EUR)' }).click()
  await expect(page).toHaveURL(/\/demo$/)
  await expect(page.getByText('Fictional stops, EUR and Europe/Berlin time. No real tickets.')).toBeVisible()
  await expect(page.getByLabel('From', { exact: true })).toBeVisible()
  await expect(page.locator('#origin option[value^="KZ-"]')).toHaveCount(0)
})

for (const language of ['en', 'ru', 'kk'] as const) {
  test(`Kazakhstan ${language}: new city, KZT booking, local time and downloads`, async ({ page }) => {
    test.setTimeout(60_000)
    const label = (key: string) => language === 'en' ? key : messages[key][language]
    const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })
    await page.goto(`/?lang=${language}`)
    await page.locator('#kz-select-origin').selectOption('kz-almaty')
    await page.locator('#kz-select-destination').selectOption('kz-kosshy')
    const form = page.locator('form').first()
    await form.locator('input[name="date"]').fill(tomorrow)
    await form.locator('input[name="time"]').fill('06:00')
    const search = page.waitForResponse(r => new URL(r.url()).pathname === '/api/kazakhstan/search/' && r.ok())
    await form.locator('button[value="search"]').click()
    const results = await (await search).json()
    expect(results.currency).toBe('KZT')
    expect(results.timezone).toBe('Asia/Almaty')
    expect(results.results.length).toBeGreaterThan(0)
    expect(results.results.every((it: { departs_at: string; timezone: string }) => it.timezone === 'Asia/Almaty' && it.departs_at.endsWith('+05:00'))).toBe(true)
    await expect(page.locator('.result').first()).toContainText('KZT')
    if (language === 'en') {
      await page.getByLabel('Sort by').selectOption('price')
      const cheapest = [...results.results].sort((a, b) => { const aa = BigInt(a.total_price.replace('.', '')), bb = BigInt(b.total_price.replace('.', '')); return aa === bb ? 0 : aa < bb ? -1 : 1 })[0]
      await expect(page.locator('.result').first().locator('.price')).toHaveText(`KZT ${cheapest.total_price}`)
      await page.locator('.result').nth(0).getByRole('checkbox').check()
      await page.locator('.result').nth(1).getByRole('checkbox').check()
      await expect(page.locator('.comparison-option')).toHaveCount(2)
      await page.getByLabel('Sort by').selectOption('duration')
      const shortest = [...results.results].sort((a, b) => a.duration_minutes - b.duration_minutes)[0]
      const target = await page.locator('.result').first().getByRole('link', { name: /^Select/ }).getAttribute('href')
      expect(new URL(target!, 'https://doedu.test').searchParams.get('legs')).toBe(shortest.legs_param)
    }
    await page.locator('.result').first().getByRole('link', { name: new RegExp('^' + label('Select')) }).click()
    await page.getByRole('link', { name: label('Continue to traveller details') }).click()
    await page.getByRole('link', { name: label('Create one') }).click()
    await page.locator('#name').fill('Kazakhstan Demo Traveller')
    await page.locator('#email').fill(`kz-${language}-${Date.now()}@example.test`)
    await page.locator('#password').fill('KzTest!' + crypto.randomUUID())
    await page.getByRole('button', { name: label('Create account'), exact: true }).click()
    await expect(page.getByRole('heading', { name: label('Traveller details'), exact: true })).toBeVisible()
    if (language === 'ru') {
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 900 })
        if (width === 390) await page.getByRole('button', { name: label('Menu'), exact: true }).click()
        const size = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth, header: document.querySelector('.site-header')!.getBoundingClientRect().right }))
        expect(size.page).toBeLessThanOrEqual(size.viewport)
        expect(size.header).toBeLessThanOrEqual(size.viewport)
        await expect(page.locator('.language-switch')).toBeInViewport()
        await expect(page.locator('.theme-toggle')).toBeInViewport()
        if (width === 390) await page.getByRole('button', { name: label('Menu'), exact: true }).click()
      }
      await page.setViewportSize({ width: 1280, height: 900 })
    }
    await page.getByRole('button', { name: label('Reserve and continue to payment') }).click()
    await expect(page.getByTestId('countdown')).toBeVisible()
    await page.getByRole('button', { name: label('Simulate successful payment') }).click()
    await expect(page.getByRole('heading', { name: label('Booking confirmed (simulated)') })).toBeVisible()
    await expect(page.locator('main')).toContainText('Asia/Almaty')
    const reference = await page.getByTestId('reference').innerText()
    const calendarEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: label('Add to calendar (.ics)') }).click()
    const calendar = await calendarEvent
    expect(calendar.suggestedFilename()).toBe(`doedu-${reference}.ics`)
    const calendarText = readFileSync((await calendar.path())!, 'utf8').replace(/\r?\n /g, '')
    expect(calendarText).toContain('BEGIN:VEVENT')
    expect(calendarText).toContain(language === 'en' ? 'Kosshy' : language === 'ru' ? 'Косшы' : 'Қосшы')
    const pdfEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: label('Download journey PDF') }).click()
    const pdf = await pdfEvent
    expect(pdf.suggestedFilename()).toBe(`doedu-${reference}.pdf`)
    expect(readFileSync((await pdf.path())!).subarray(0, 5).toString()).toBe('%PDF-')
    await page.reload()
    await expect(page.getByTestId('reference')).toHaveText(reference)
    await expect(page.locator('main')).toContainText('Asia/Almaty')
    await page.getByRole('link', { name: label('My journeys'), exact: true }).click()
    await page.getByRole('link', { name: label('Repeat journey') }).first().click()
    await expect(page).toHaveURL(/\/?\?origin=kz-almaty&destination=kz-kosshy/)
    await expect(page.locator('#kz-select-destination')).toHaveValue('kz-kosshy')
  })
}

test('legacy synthetic search links stay usable and strict access follows selection', async ({ page }) => {
  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=06:00&passengers=1`)
  await expect(page).toHaveURL(/\/demo\?origin=NG-BUS/)
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/search/' && new URL(r.url()).searchParams.get('wheelchair_required') === 'true' && r.ok())
  await page.locator('#journey-filters').getByLabel('Require a fully step-free journey').check()
  await expect(page).toHaveURL(/wheelchair_required=true/)
  const results = await response
  const data = await results.json()
  for (const it of data.results) {
    for (const leg of it.legs) expect(Object.values(leg.accessibility)).toEqual(['yes', 'yes', 'yes'])
    for (const connection of it.connections) expect(connection.path_step_free).toBe('yes')
  }
  if (data.results.length) {
    await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
    await expect(page).toHaveURL(/wheelchair_required=true/)
  }
})
