import { expect, test } from '@playwright/test'
import type { Booking, ReplacementOffer } from '../src/api'

// Isolated UI contract: exercise confirmation without consuming shared demo bookings.
for (const settlement of ['none', 'pay', 'refund'] as const) {
  test(`redesigned recovery keeps ${settlement} settlement behind explicit confirmation`, async ({ page }) => {
    await page.setViewportSize({ width: settlement === 'pay' ? 390 : 1440, height: 1000 })
    const ref = 'DD-DESIGN-TEST'
    const departure = '2026-10-21T14:00:00+02:00'
    const arrival = '2026-10-21T18:55:00+02:00'
    const booking: Booking = {
      reference: ref, status: 'confirmed', status_label: 'Confirmed', passengers: 1,
      total_amount: '26.10', currency: 'EUR', contact_email: 'demo.passenger@doedu.test',
      expires_at: arrival, created_at: departure, confirmed_at: departure,
      simulated_notice: 'Simulated booking.', travellers: ['Demo passenger'],
      travel_plan: null, legs: [], refunds: [], payments: [], cancellable: true,
      disruption: { status: 'broken', reason: 'missed_connection', problem_sequence: 1, arrival_delay_minutes: 120 },
    }
    const offer: ReplacementOffer = {
      id: 1, status: 'proposed', expires_at: new Date(Date.now() + 600_000).toISOString(),
      arrives_at: arrival, currency: 'EUR', replacement_price: '10.00', replaced_value: '10.00',
      difference: settlement === 'pay' ? '0.10' : settlement === 'refund' ? '-0.10' : '0.00',
      settlement, reserves_capacity: false, availability_warning: 'Places are not held until you accept.',
      legs: [{ mode: 'train', route_code: 'DR2', operator: 'Demo Rail', from: { name: 'Riverton Station' },
        to: { name: 'Portmouth Harbour Station' }, departs_at: departure, arrives_at: arrival,
        status: 'scheduled', delay_minutes: 0, unit_price: '10.00', price_basis: 'passenger', places_left: 12,
        accessibility: { wheelchair_vehicle: 'yes', origin_step_free: 'yes', destination_step_free: 'yes' } }],
    }
    const accepted: unknown[] = []
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/auth/me/') return route.fulfill({ json: { user: { id: 1, email: booking.contact_email, name: 'Demo passenger', role: 'passenger', email_verified: true, operator: null } } })
      if (path === '/api/auth/csrf/') return route.fulfill({ json: {} })
      if (path === '/api/notifications/') return route.fulfill({ json: { unread: 0, results: [] } })
      if (path === '/api/config/') return route.fulfill({ json: { launch_mode: 'demo', simulated: true, release: 'test', registration_enabled: true } })
      if (path === `/api/bookings/${ref}/`) return route.fulfill({ json: booking })
      if (path === `/api/bookings/${ref}/replacements/`) return route.fulfill({ json: {
        state: 'options', offers: [offer], retained_legs: [], original_arrival: departure,
        affected_legs: [{ sequence: 1, mode: 'train', route_code: 'DR1', from: 'Riverton Station', to: 'Portmouth Harbour Station', from_code: 'RV-RAIL', to_code: 'PM-RAIL', departs_at: departure, arrives_at: arrival }],
      } })
      if (path.endsWith('/accept/')) {
        const body = route.request().postDataJSON()
        accepted.push(body)
        if (body.outcome === 'failure') return route.fulfill({ status: 409, json: { code: 'payment_failed', message: 'Simulated failure.' } })
        return route.fulfill({ json: { replayed: false, booking: { ...booking, disruption: null } } })
      }
      return route.fulfill({ status: 404, json: { message: 'Unexpected test request.' } })
    })
    await page.goto(`/booking/${ref}?lang=en`)
    const option = page.getByTestId('offer')
    await expect(option).toBeVisible()
    await expect(page.getByRole('group', { name: 'Confirm replacement', exact: true })).toHaveCount(0)
    await option.getByRole('button', { name: 'Choose this journey' }).click()
    const confirmation = page.getByRole('group', { name: 'Confirm replacement', exact: true })
    await expect(confirmation).toBeVisible()
    expect(accepted).toHaveLength(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath('recovery.png'), fullPage: true })
    if (settlement === 'pay') {
      await confirmation.getByRole('button', { name: 'Simulate failed payment' }).click()
      await expect(page.getByRole('alert').filter({ hasText: 'Nothing was changed' })).toBeVisible()
      await expect(option).toBeVisible()
    }
    await confirmation.getByRole('button', { name: settlement === 'pay' ? /Pay.*and confirm/ : /^Confirm replacement/ }).click()
    await expect(page.getByText('Your replacement journey is booked (simulated).')).toBeVisible()
    expect(accepted.at(-1)).toEqual({ outcome: 'success' })
    await expect(page.getByTestId('offer')).toHaveCount(0)
  })
}
