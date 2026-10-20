import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cityMatches, readShared, sharePath, defaults } from '../src/kazakhstan.ts'
const cities = [{id:'kz-almaty',name:{en:'Almaty',ru:'Алматы',kk:'Алматы'},region:{en:'Almaty City',ru:'город Алматы',kk:'Алматы қаласы'}}, {id:'kz-aktobe',name:{en:'Aktobe',ru:'Актобе',kk:'Ақтөбе'},region:{en:'Aktobe Region',ru:'Актюбинская область',kk:'Ақтөбе облысы'}}]
test('city filtering accepts all three languages and regions', () => {
  for (const query of ['aktobe', ' АКТОБЕ ', 'Ақтөбе', 'Актюбинская']) assert.equal(cityMatches(cities[1], query), true)
  assert.equal(cityMatches(cities[0], 'aktobe'), false)
})
test('shared links whitelist only public trip fields and roundtrip', () => {
  const values = {...defaults(), destination:'kz-aktobe', note:'SECRET NOTE', id:42, user:9}
  const path = sharePath(values)
  assert.equal(path.includes('SECRET'), false)
  assert.equal(path.includes('note'), false)
  assert.equal(path.includes('user'), false)
  const parsed = readShared(path.split('?')[1], cities)
  assert.equal(parsed.invalid, false)
  for (const key of ['origin','destination','date','time','passengers','modes']) assert.equal(parsed.values[key], values[key])
})
test('malformed external links cannot supply invalid cities or arbitrary form values', () => {
  const parsed = readShared('?origin=evil&date=2026-02-31&time=99:00&passengers=100&modes=flight&note=secret', cities)
  assert.equal(parsed.invalid, true)
  assert.equal(parsed.values.origin, 'kz-almaty')
  assert.equal(parsed.values.passengers, '1')
  assert.equal('note' in parsed.values, false)
})
