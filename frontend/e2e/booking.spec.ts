import { demoDayIso } from './demo-day'
import { expect, test } from '@playwright/test'

// Requires seeded demo data (`manage.py seed_demo`); each run consumes 1 place on VC1 12:00 (demo day).

test('passenger registers, books, survives a failed payment, confirms, and sees the booking', async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`

  await page.goto(`/?origin=NG-BUS&destination=RV-BUS&date=${demoDayIso()}&time=12:00&passengers=1&sort=departure`)
  await page.getByRole('link', { name: /^Select/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Journey details' })).toBeVisible()
  await expect(page.getByText('Simulated data')).toBeVisible()
  await page.getByRole('link', { name: 'Continue to traveller details' }).click()

  // Not signed in: redirected to login, then register and come back.
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.getByRole('link', { name: 'Create one' }).click()
  await page.getByLabel('Full name').fill('Eva Example')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('correct-horse-42')
  await page.getByRole('button', { name: 'Create account' }).click()

  await expect(page.getByRole('heading', { name: 'Traveller details' })).toBeVisible()
  await page.getByRole('button', { name: 'Reserve and continue to payment' }).click()

  await expect(page.getByRole('heading', { name: 'Payment', exact: true })).toBeVisible()
  await expect(page.getByTestId('countdown')).toBeVisible()
  await expect(page.getByText('No real payment is taken')).toBeVisible()

  await page.getByRole('button', { name: 'Simulate failed payment' }).click()
  await expect(page.getByText(/Payment failed/)).toBeVisible()
  await page.getByRole('button', { name: 'Simulate successful payment' }).click()

  await expect(page.getByRole('heading', { name: /Booking confirmed \(simulated\)/ })).toBeVisible()
  const ref = await page.getByTestId('reference').innerText()
  expect(ref).toMatch(/^DD-/)
  await expect(page.getByText('Not a valid travel ticket')).toBeVisible()

  await page.getByRole('link', { name: 'My journeys' }).click()
  await expect(page.getByRole('link', { name: ref })).toBeVisible()
})

test('another passenger cannot open a booking they do not own', async ({ page, request }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('nobody@example.com')
  await page.getByLabel('Password').fill('wrong-password-1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Email or password is incorrect.')).toBeVisible()
  const res = await request.get('/api/bookings/DD-NOTMINE1/')
  expect([401, 403]).toContain(res.status())
})
