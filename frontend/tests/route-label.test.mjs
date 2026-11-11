import test from 'node:test'
import assert from 'node:assert/strict'
import { isDemoRouteCode, passengerRouteLabel } from '../src/format.ts'
import { setLanguage } from '../src/i18n.ts'

test('generated Kazakhstan bus and train identifiers become readable labels in all three languages', () => {
  const expected = {
    en: ['Bus · Almaty → Astana', 'Train · Almaty → Astana'],
    ru: ['Автобус · Алматы → Астана', 'Поезд · Алматы → Астана'],
    kk: ['Автобус · Алматы → Астана', 'Пойыз · Алматы → Астана'],
  }
  try {
    for (const [language, labels] of Object.entries(expected)) {
      setLanguage(language)
      assert.equal(passengerRouteLabel('KZBf03a59d60372', 'bus', 'Almaty', 'Astana'), labels[0])
      assert.equal(passengerRouteLabel('KZT123456abcdef', 'train', 'Almaty', 'Astana'), labels[1])
      assert.equal(passengerRouteLabel('VC1', 'bus', 'Northgate Bus Station', 'Riverton Bus Station'), 'VC1')
    }
  } finally { setLanguage('en') }
})

test('only the exact generated namespace is reformatted; authored route codes stay unchanged', () => {
  assert.equal(isDemoRouteCode('KZBf03a59d60372'), true)
  assert.equal(isDemoRouteCode('KZT123456abcdef'), true)
  for (const code of ['VC1', 'DR1', 'KZBAlmaty', 'KZBF03A59D60372', 'KZBf03a59d6037', 'KZBf03a59d603720', 'KZXf03a59d60372', 'KZBf03a59d60372-extra']) {
    assert.equal(isDemoRouteCode(code), false, code)
    assert.equal(passengerRouteLabel(code, 'bus', 'Almaty', 'Astana'), code)
  }
})
