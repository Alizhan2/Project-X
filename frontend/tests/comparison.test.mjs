import test from 'node:test'
import assert from 'node:assert/strict'
import { explainDifference } from '../src/comparison.ts'

const base = { total_price: '10.10', currency: 'EUR', passengers: 2, duration_minutes: 80, arrives_at: '2026-10-20T23:50:00+02:00', transfers: 1, min_transfer_buffer_minutes: 15 }

test('cent-accurate prices and longer duration are distinguished from arrival time', () => {
  const facts = explainDifference({ ...base, total_price: '10.20', duration_minutes: 100, arrives_at: '2026-10-20T23:40:00+02:00' }, base)
  assert.ok(facts.includes('EUR 0.10 more expensive in total.'))
  assert.ok(facts.includes('20 min longer journey.'))
  assert.ok(facts.includes('Arrives 10 min earlier.'))
})
test('next-day arrivals and connection margins do not imply reliability', () => {
  const facts = explainDifference({ ...base, arrives_at: '2026-10-21T00:20:00+02:00', min_transfer_buffer_minutes: 20 }, base)
  assert.ok(facts.includes('Arrives 30 min later.'))
  assert.ok(facts.includes('5 min more spare time at the tightest connection.'))
  assert.ok(!facts.some(f => /reliable|safe|guarantee/i.test(f)))
})
test('direct journeys have no synthetic connection buffer', () => {
  const facts = explainDifference({ ...base, transfers: 0, min_transfer_buffer_minutes: null }, base)
  assert.ok(facts.includes('Direct, with no changes.'))
  assert.ok(!facts.some(f => /spare|buffer/.test(f)))
})
test('different currencies or party sizes are not compared', () => {
  for (const change of [{ currency: 'USD' }, { passengers: 1 }]) {
    assert.match(explainDifference({ ...base, ...change }, base)[0], /cannot be compared/)
  }
})
test('equal and cheaper prices remain exact', () => {
  assert.equal(explainDifference(base, base)[0], 'The same total price.')
  assert.equal(explainDifference({ ...base, total_price: '9.99' }, base)[0], 'EUR 0.11 cheaper in total.')
})
