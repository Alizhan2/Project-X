import test from 'node:test'
import assert from 'node:assert/strict'
import { layoutRoute, minutesBetween } from '../src/routeLine.ts'

const leg = (from, to, departs_at, arrives_at, mode = 'bus') => ({ from, to, departs_at, arrives_at, mode, route_code: 'X1' })

test('one leg has one segment and no change', () => {
  const s = layoutRoute([leg('A', 'B', '2026-10-21T12:00:00+02:00', '2026-10-21T12:55:00+02:00')])
  assert.deepEqual(s.map(x => [x.kind, x.minutes]), [['leg', 55]])
})

test('legs and changes alternate, in order, with the real minutes', () => {
  const s = layoutRoute([
    leg('A', 'B', '2026-10-21T12:00:00+02:00', '2026-10-21T12:55:00+02:00'),
    leg('B', 'C', '2026-10-21T14:45:00+02:00', '2026-10-21T15:30:00+02:00', 'train'),
    leg('C', 'D', '2026-10-21T15:43:00+02:00', '2026-10-21T15:55:00+02:00', 'taxi'),
  ])
  assert.deepEqual(s.map(x => [x.kind, x.index, x.minutes]), [['leg', 0, 55], ['change', 0, 110], ['leg', 1, 45], ['change', 1, 13], ['leg', 2, 12]])
})

test('a short taxi leg stays visible next to a long train leg (square-root scaling, minimum width)', () => {
  const s = layoutRoute([
    leg('A', 'B', '2026-10-21T08:00:00+02:00', '2026-10-21T11:00:00+02:00', 'train'),
    leg('B', 'C', '2026-10-21T11:10:00+02:00', '2026-10-21T11:12:00+02:00', 'taxi'),
  ])
  const [train, , taxi] = s
  assert.ok(taxi.weight >= 4, 'minimum weight keeps the label readable')
  assert.ok(train.weight / taxi.weight < 4, 'a 90x longer leg is not drawn 90x wider')
  assert.ok(train.weight > taxi.weight)
})

test('midnight crossing and negative gaps never produce negative minutes', () => {
  assert.equal(minutesBetween('2026-10-21T23:30:00+02:00', '2026-10-22T00:40:00+02:00'), 70)
  assert.equal(minutesBetween('2026-10-21T12:00:00+02:00', '2026-10-21T11:00:00+02:00'), 0)
})
