import { expect, test, type Page } from '@playwright/test'
import { demoDayIso } from './demo-day'

async function reserve(page: Page) {
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Reservation Test')
  await page.getByLabel('Email').fill(`reservation-${crypto.randomUUID()}@example.test`)
  await page.getByLabel('Password').fill(`Test!${crypto.randomUUID()}`)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My journeys' })).toBeVisible()
  await page.goto(`/demo?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=16:00&passengers=1`)
  await page.locator('.result').first().getByRole('link', { name: /^Select/ }).click()
  await page.getByRole('link', { name: 'Continue to traveller details' }).click()
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()
  await expect(page.getByTestId('countdown')).toBeVisible()
  return page.url().split('/').at(-2)!
}

test('a failed cancellation stays on payment and offers a retry for the active reservation', async ({ page }) => {
  const ref = await reserve(page)
  await page.route('**/abandon/', route => route.abort('internetdisconnected'))
  await page.getByRole('button', { name: 'Cancel this reservation' }).click()
  await expect(page.getByRole('alert')).toContainText('The reservation is still active')
  await expect(page).toHaveURL(new RegExp(`/booking/${ref}/pay$`))
  expect((await (await page.request.get(`/api/bookings/${ref}/`)).json()).status).toBe('pending_payment')
  await page.unroute('**/abandon/')
  await page.getByRole('button', { name: 'Cancel this reservation' }).click()
  await expect(page).toHaveURL(/\/journeys$/)
  expect((await (await page.request.get(`/api/bookings/${ref}/`)).json()).status).toBe('cancelled')
})

test('a lost cancellation response is reconciled before allowing another payment', async ({ page }) => {
  const ref = await reserve(page)
  await page.route('**/abandon/', async route => {
    const response = await route.fetch()
    expect(response.ok()).toBe(true) // server cancelled it, but the browser loses the reply
    await route.abort('internetdisconnected')
  })
  await page.route(`**/api/bookings/${ref}/`, route => route.abort('internetdisconnected'))
  await page.getByRole('button', { name: 'Cancel this reservation' }).click()
  await expect(page.getByRole('alert')).toContainText('We could not confirm the cancellation')
  await expect(page.getByRole('button', { name: 'Simulate successful payment', exact: true })).toBeDisabled()
  await expect(page).toHaveURL(new RegExp(`/booking/${ref}/pay$`))
  await page.unroute(`**/api/bookings/${ref}/`)
  await page.getByRole('button', { name: 'Check reservation status' }).click()
  await expect(page).toHaveURL(/\/journeys$/)
  const booking = await (await page.request.get(`/api/bookings/${ref}/`)).json()
  expect(booking.status).toBe('cancelled')
  expect(booking.payments).toEqual([])
})
