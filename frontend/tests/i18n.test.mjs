import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { t, setLanguage, getLanguage } from '../src/i18n.ts'
import { dayLabel, clock } from '../src/format.ts'
import { explainDifference } from '../src/comparison.ts'
const catalog = JSON.parse(readFileSync(new URL('../src/messages.json', import.meta.url)))

test('catalogs shipped to browser and worker agree', () => {
  const backend = JSON.parse(readFileSync(new URL('../../backend/apps/core/locales/messages.json', import.meta.url)))
  assert.deepEqual(backend, catalog)
  for (const [key, translations] of Object.entries(catalog)) {
    for (const language of ['ru', 'kk']) {
      assert.ok(translations[language]?.trim(), `${key}: missing ${language}`)
      const placeholders = [...translations[language].matchAll(/\{(\w+)\}/g)].map(m => m[1])
      const expected = [...key.matchAll(/\{(\w+)\}/g)].map(m => m[1])
      assert.ok(placeholders.every(name => expected.includes(name)), key)
      // The unused English plural suffix is intentionally omitted in Russian/Kazakh.
      if (key !== '{0} transfer{1}') assert.deepEqual(placeholders.sort(), expected.sort(), key)
    }
  }
})
test('switches static, interpolated and previously rendered messages without modifying references', () => {
  setLanguage('ru')
  assert.equal(t('Search'), 'Поиск')
  assert.equal(t('Only {0} place(s) left on {1}. ', { 0: 2, 1: 'VC1' }), 'На VC1 осталось мест: 2. ')
  const previous = t('Booking DD-ABC cancelled')
  setLanguage('kk')
  assert.equal(t(previous), 'DD-ABC брондауы тоқтатылды')
  assert.equal(t('Search'), 'Іздеу')
  assert.equal(t('DD-ABC'), 'DD-ABC')
  assert.equal(t('<img>'), '<img>')
  setLanguage('zz')
  assert.equal(getLanguage(), 'kk')
  setLanguage('en')
  assert.equal(t(previous), 'Booking DD-ABC cancelled')
})
test('all generated comparison facts translate including singular transfers', () => {
  const base = { total_price: '10.00', currency: 'EUR', passengers: 1, duration_minutes: 80, arrives_at: '2026-10-20T10:00:00Z', transfers: 1, min_transfer_buffer_minutes: 15 }
  for (const language of ['ru', 'kk']) {
    setLanguage(language)
    for (const transfers of [0, 2, 3]) {
      for (const sign of [-1, 1]) {
        const option = { ...base, transfers, total_price: sign < 0 ? '9.00' : '11.00', duration_minutes: 80 + sign * 5, arrives_at: sign < 0 ? '2026-10-20T09:55:00Z' : '2026-10-20T10:05:00Z', min_transfer_buffer_minutes: 15 + sign * 5 }
        for (const fact of explainDifference(option, base)) { assert.notEqual(t(fact), fact, fact); assert.doesNotMatch(t(fact), /shorter|longer|fewer|more|later|earlier|transfer|journey|total/, fact) }
      }
    }
  }
  setLanguage('en')
})

test('regional date labels are deterministic even without Kazakh ICU data', () => {
  const iso = '2026-10-21T00:05:00+02:00'
  setLanguage('kk')
  assert.equal(dayLabel(iso), 'ср, 21 қаз.')
  setLanguage('ru')
  assert.equal(dayLabel(iso), 'ср, 21 окт.')
  assert.equal(clock(iso), '00:05')
  setLanguage('en')
})
