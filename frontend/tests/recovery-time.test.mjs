import test from 'node:test'
import assert from 'node:assert/strict'
import { demoDateTimeInput, repeatSearchUrl } from '../src/format.ts'

test('recovery form uses demo-region wall time from absolute timestamps, including midnight and DST', () => {
  assert.equal(demoDateTimeInput('2026-11-10T23:30:00Z'), '2026-11-11T00:30')
  assert.equal(demoDateTimeInput('2026-07-10T08:00:00Z'), '2026-07-10T10:00')
  assert.equal(demoDateTimeInput('invalid'), '')
})
test('repeat demo searches stay in the demo area after Kazakhstan becomes home', () => {
  assert.ok(repeatSearchUrl('NG-BUS', 'RV-BUS').startsWith('/demo?'))
  assert.ok(repeatSearchUrl('NG-BUS', 'RV-BUS', 1, true).includes('wheelchair_required=true'))
})
