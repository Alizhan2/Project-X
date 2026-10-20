import test from 'node:test'
import assert from 'node:assert/strict'

// Minimal localStorage so the module runs under node.
const store = new Map()
globalThis.localStorage = { getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) }
const { saveOfflineCopy, offlineCopies, getOfflineCopy, clearOfflineCopies, pruneOfflineCopies } = await import('../src/offline.ts')

const NOW = Date.parse('2026-10-21T10:00:00Z')
const booking = (ref, arrives = '2026-10-21T15:00:00Z', status = 'confirmed') => ({
  reference: ref, status, contact_email: 'pat@example.com', travellers: ['Pat Example'],
  payments: [{ status: 'succeeded', amount: '7.00' }], refunds: [{ amount: '1.00' }], activity: [{ title: 'x' }],
  legs: [{ status: 'booked', departs_at: '2026-10-21T12:00:00Z', arrives_at: arrives }],
})
const reset = () => { store.clear() }

test('stores a confirmed upcoming booking without e-mail, payments, refunds or activity', () => {
  reset()
  saveOfflineCopy(1, booking('DD-A'), NOW)
  const copy = getOfflineCopy('DD-A')
  assert.equal(copy.booking.contact_email, '')
  assert.deepEqual([copy.booking.payments, copy.booking.refunds, copy.booking.activity], [[], [], undefined])
  assert.ok(!store.get('doedu.offline.v1').includes('pat@example.com'))
  assert.deepEqual(copy.booking.travellers, ['Pat Example'])
})

test('does not keep unconfirmed, cancelled or long-finished journeys, and drops a copy that became ineligible', () => {
  reset()
  saveOfflineCopy(1, booking('DD-P', undefined, 'pending_payment'), NOW)
  saveOfflineCopy(1, booking('DD-C', undefined, 'cancelled'), NOW)
  saveOfflineCopy(1, booking('DD-OLD', '2026-10-19T10:00:00Z'), NOW)       // arrived two days ago
  assert.equal(offlineCopies().length, 0)
  saveOfflineCopy(1, booking('DD-A'), NOW)
  assert.equal(offlineCopies().length, 1)
  saveOfflineCopy(1, booking('DD-A', undefined, 'cancelled'), NOW)          // cancelled later: the copy is removed
  assert.equal(offlineCopies().length, 0)
})

test('keeps a journey for one day after arrival, newest first, at most five', () => {
  reset()
  saveOfflineCopy(1, booking('DD-JUST', '2026-10-20T20:00:00Z'), NOW)        // arrived 14 h ago
  assert.ok(getOfflineCopy('DD-JUST'))
  for (let i = 0; i < 6; i++) saveOfflineCopy(1, booking(`DD-${i}`), NOW + i * 1000)
  const refs = offlineCopies().map(c => c.booking.reference)
  assert.equal(refs.length, 5)
  assert.equal(refs[0], 'DD-5')
})

test('saving the same booking again replaces it instead of duplicating', () => {
  reset()
  saveOfflineCopy(1, booking('DD-A'), NOW)
  saveOfflineCopy(1, booking('DD-A'), NOW + 5000)
  assert.equal(offlineCopies().length, 1)
})

test('another account never sees or inherits copies; sign-out clears everything', () => {
  reset()
  saveOfflineCopy(1, booking('DD-A'), NOW)
  pruneOfflineCopies(1)
  assert.equal(offlineCopies().length, 1)         // same account: kept
  pruneOfflineCopies(2)
  assert.equal(offlineCopies().length, 0)         // different account: wiped
  saveOfflineCopy(1, booking('DD-A'), NOW)
  saveOfflineCopy(2, booking('DD-B'), NOW)        // saving as another account replaces the store
  assert.deepEqual(offlineCopies().map(c => c.booking.reference), ['DD-B'])
  clearOfflineCopies()
  assert.equal(store.has('doedu.offline.v1'), false)
})

test('corrupt storage is ignored, not fatal', () => {
  reset()
  store.set('doedu.offline.v1', '{not json')
  assert.deepEqual(offlineCopies(), [])
  saveOfflineCopy(1, booking('DD-A'), NOW)
  assert.equal(offlineCopies().length, 1)
})
