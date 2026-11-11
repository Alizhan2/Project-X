import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cityMatches, readShared, sharePath, defaults, normalizePrice } from '../src/kazakhstan.ts'
const cities = [{id:'kz-almaty',name:{en:'Almaty',ru:'Алматы',kk:'Алматы'},region:{en:'Almaty City',ru:'город Алматы',kk:'Алматы қаласы'}}, {id:'kz-aktobe',name:{en:'Aktobe',ru:'Актобе',kk:'Ақтөбе'},region:{en:'Aktobe Region',ru:'Актюбинская область',kk:'Ақтөбе облысы'}}]
test('city filtering accepts all three languages and regions', () => {
  for (const query of ['aktobe', ' АКТОБЕ ', 'Ақтөбе', 'Актюбинская']) assert.equal(cityMatches(cities[1], query), true)
  assert.equal(cityMatches(cities[0], 'aktobe'), false)
})
test('city filtering accepts historical aliases without changing stable city identifiers', () => {
  const city = { ...cities[0], aliases: ['Алма-Ата', 'Alma-Ata', 'Алма-Ата қаласы', 'Верный'] }
  assert.equal(cityMatches(city, 'alma-ata'), true)
  assert.equal(cityMatches(city, 'ВЕРНЫЙ'), true)
  assert.equal(city.id, 'kz-almaty')
  assert.equal(cityMatches({ ...city, aliases: ['Берёзовка'] }, 'березов'), true)
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

test('arrival, accessibility and whole-party price roundtrip without floating point rounding', () => {
  const values = { ...defaults(), destination: 'kz-aktobe', time_mode: 'arrival', wheelchair_required: 'true', max_price: '9999999999.99' }
  const path = sharePath(values, true, 'latest_departure')
  const parsed = readShared(path.split('?')[1], cities)
  assert.equal(parsed.executed, true)
  assert.equal(parsed.invalid, false)
  assert.deepEqual(parsed.values, values)
  assert.equal(parsed.sort, 'latest_departure')
  assert.equal(path.includes('max_price=9999999999.99'), true)
})
test('old links only prefill; executed links validate every public parameter before fetching', () => {
  const old = readShared('?origin=kz-almaty&destination=kz-aktobe', cities)
  assert.equal(old.executed, false)
  assert.equal(old.values.time_mode, 'departure')
  assert.equal(old.values.wheelchair_required, 'false')
  assert.equal(old.values.max_price, '')
  assert.equal(old.sort, 'departure')
  for (const extra of ['wheelchair_required=maybe', 'time_mode=before', 'max_price=-1', 'max_price=1.234', 'max_price=1e4', 'sort=buffer', 'origin=unknown', 'search=2']) {
    const parsed = readShared(`?search=1&${extra}`, cities)
    assert.equal(parsed.invalid, true, extra)
    assert.equal(parsed.executed, false, extra)
  }
})
test('decimal budgets accept zero and a localized comma while rejecting excess precision and overflow', () => {
  assert.equal(normalizePrice('0'), '0.00')
  assert.equal(normalizePrice('00012,3'), '12.30')
  assert.equal(normalizePrice(' 1200.50 '), '1200.50')
  assert.equal(normalizePrice(''), '')
  assert.equal(normalizePrice('9999999999.99'), '9999999999.99')
  for (const bad of ['10000000000', '1.001', '-0.01', 'NaN', 'Infinity', '1e3', '0x10', '.50']) assert.equal(normalizePrice(bad), null, bad)
  assert.equal(new URL(sharePath({ ...defaults(), max_price: '' }), 'https://doedu.test').searchParams.has('max_price'), false)
  assert.equal(readShared('?max_price=12,3', cities).values.max_price, '12.30')
})
test('arrival default sorting and explicit sorting survive an executed search URL', () => {
  const values = { ...defaults(), destination: 'kz-aktobe', time_mode: 'arrival' }
  assert.equal(readShared(sharePath(values, true).split('?')[1], cities).sort, 'latest_departure')
  for (const sort of ['departure', 'latest_departure', 'price', 'duration']) assert.equal(readShared(sharePath(values, true, sort).split('?')[1], cities).sort, sort)
})
