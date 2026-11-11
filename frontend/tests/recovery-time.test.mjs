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
test('Kazakhstan recovery fields and repeat links use the booking market', () => {
  assert.equal(demoDateTimeInput('2026-11-10T23:30:00Z', 'Asia/Almaty'), '2026-11-11T04:30')
  const url = new URL(repeatSearchUrl('KZ-751000000-B', 'KZ-711000000-B', 2, false, 'kz-almaty', 'kz-astana'), 'https://doedu.test')
  assert.equal(url.pathname, '/')
  assert.equal(url.searchParams.get('origin'), 'kz-almaty')
  assert.equal(url.searchParams.get('destination'), 'kz-astana')
  assert.equal(url.searchParams.get('passengers'), '2')
  assert.equal(url.searchParams.get('modes'), 'bus,train')
})
