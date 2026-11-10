import { expect, test } from '@playwright/test'

test('an unknown initial payment is reconciled with the same key and cannot create a new charge', async ({ page }) => {
  const ref = 'DD-PENDING'
  const time = new Date(Date.now() + 240_000).toISOString()
  let booking = {
    reference: ref, status: 'pending_payment', status_label: 'Awaiting payment', passengers: 1,
    total_amount: '7.00', currency: 'EUR', contact_email: 'demo@example.test', expires_at: time,
    created_at: new Date().toISOString(), confirmed_at: null, simulated_notice: 'Simulated booking.',
    travellers: ['Demo passenger'], travel_plan: null, legs: [], refunds: [], payments: [] as object[], cancellable: true, disruption: null,
  }
  const chargeKeys: string[] = []
  const reconciliationKeys: string[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me/') return route.fulfill({ json: { user: { id: 1, email: 'demo@example.test', name: 'Demo passenger', role: 'passenger', email_verified: true, operator: null } } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: {} })
    if (path === '/api/notifications/') return route.fulfill({ json: { unread: 0, results: [] } })
    if (path === '/api/config/') return route.fulfill({ json: { launch_mode: 'demo', simulated: true, release: 'test', registration_enabled: true } })
    if (path === `/api/bookings/${ref}/`) return route.fulfill({ json: booking })
    if (path === `/api/bookings/${ref}/pay/`) {
      expect(route.request().postDataJSON()).toEqual({ outcome: 'pending' })
      const key = route.request().headers()['idempotency-key']
      chargeKeys.push(key)
      booking = { ...booking, payments: [{ id: 1, purpose: 'initial', idempotency_key: key, amount: '7.00', status: 'pending', failure_reason: '', created_at: time }] }
      return route.fulfill({ json: { replayed: false, payment: { status: 'pending', failure_reason: '' }, booking } })
    }
    if (path === `/api/bookings/${ref}/pay/reconcile/`) {
      reconciliationKeys.push(route.request().headers()['idempotency-key'])
      booking = { ...booking, status: 'confirmed', status_label: 'Confirmed (simulated)', payments: [{ ...(booking.payments[0]), status: 'succeeded' }] }
      return route.fulfill({ json: { replayed: false, payment: { status: 'succeeded', failure_reason: '' }, booking } })
    }
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto(`/booking/${ref}/pay`)
  await page.getByRole('button', { name: 'Simulate unknown payment result' }).click()
  await expect(page.getByText('Payment result pending', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Simulate successful payment', exact: true })).toHaveCount(0)
  await page.reload()
  await page.getByRole('button', { name: 'Reconcile as successful (simulated)' }).click()
  await expect(page).toHaveURL(new RegExp(`/booking/${ref}$`))
  expect(chargeKeys).toHaveLength(1)
  expect(reconciliationKeys).toEqual(chargeKeys)
})
