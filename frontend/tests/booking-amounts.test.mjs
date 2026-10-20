import test from 'node:test'
import assert from 'node:assert/strict'
import { netPaid } from '../src/bookingAmounts.ts'

test('cancelled demo journey shows 6.05 after its 20.05 refund; failed payment is excluded', () => {
  assert.equal(netPaid({ payments: [
    { status: 'failed', amount: '26.10' },
    { status: 'succeeded', amount: '26.10' },
  ], refunds: [{ status: 'completed', amount: '20.05' }] }), '6.05')
})

test('replacement top-ups and cheaper-journey refunds are each counted once', () => {
  assert.equal(netPaid({ payments: [
    { status: 'succeeded', amount: '26.10' },
    { status: 'failed', amount: '0.10' },
    { status: 'succeeded', amount: '0.10' },
  ], refunds: [
    { status: 'completed', amount: '0.20' },
    { status: 'completed', amount: '20.05' },
  ] }), '5.95')
})

test('pending transfers do not change net paid; unpaid and fully refunded bookings show zero', () => {
  assert.equal(netPaid({ payments: [{ status: 'created', amount: '26.10' }], refunds: [] }), '0.00')
  assert.equal(netPaid({ payments: [{ status: 'succeeded', amount: '26.10' }], refunds: [{ status: 'pending', amount: '20.05' }] }), '26.10')
  assert.equal(netPaid({ payments: [{ status: 'succeeded', amount: '26.10' }], refunds: [{ status: 'completed', amount: '26.10' }] }), '0.00')
})
