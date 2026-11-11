from collections import Counter

from django.test import SimpleTestCase

from .catalog import CITIES, CITY_IDS, GEOGRAPHY_SOURCE


class KazakhstanCityCatalogTests(SimpleTestCase):
    def setUp(self):
        self.cities = {city['id']: city for city in CITIES}

    def test_complete_city_coverage_matches_official_region_totals(self):
        # BNS administrative-territorial statistics, 1 July 2026; current KATO agrees.
        expected = {'10': 4, '11': 11, '15': 8, '19': 5, '23': 2, '27': 2,
                    '31': 4, '33': 6, '35': 8, '39': 6, '43': 4, '47': 3,
                    '55': 3, '59': 5, '61': 7, '62': 3, '63': 6,
                    '71': 1, '75': 1, '79': 1}
        self.assertEqual(Counter(city['region_code'] for city in CITIES), expected)
        self.assertEqual(len(CITIES), GEOGRAPHY_SOURCE['city_count'])
        self.assertEqual((len(CITIES), len(set(CITY_IDS))), (90, 90))
        self.assertEqual(GEOGRAPHY_SOURCE['as_of'], '2026-11-04')

    def test_city_identity_language_and_geography_contract(self):
        codes = set()
        for city in CITIES:
            with self.subTest(city=city['id']):
                self.assertRegex(city['kato'], r'^\d{9}$')
                self.assertNotIn(city['kato'], codes)
                codes.add(city['kato'])
                self.assertEqual(city['region_code'], city['kato'][:2])
                self.assertEqual((city['country'], city['timezone'], city['status']),
                                 ('KZ', 'Asia/Almaty', 'city'))
                for field in ('name', 'region'):
                    self.assertEqual(set(city[field]), {'en', 'ru', 'kk'})
                    self.assertTrue(all(value and value == value.strip() for value in city[field].values()))
                self.assertNotIn('Г.А.', city['name']['ru'])
                self.assertTrue(all(isinstance(alias, str) and alias.strip() for alias in city['aliases']))
                self.assertEqual(len(city['aliases']), len(set(city['aliases'])))
        self.assertNotIn('634820000', codes)  # Алтай city administration, not an additional city.

    def test_original_saved_plan_city_ids_keep_their_identity(self):
        expected = {
            'astana': '710000000', 'almaty': '750000000', 'shymkent': '790000000',
            'kokshetau': '111010000', 'aktobe': '151010000', 'atyrau': '231010000',
            'oral': '271010000', 'aktau': '471010000', 'kostanay': '391010000',
            'petropavl': '591010000', 'pavlodar': '551010000', 'karaganda': '351010000',
            'zhezkazgan': '621010000', 'oskemen': '631010000', 'semey': '101010000',
            'taldykorgan': '331010000', 'konaev': '191010000', 'taraz': '311010000',
            'kyzylorda': '431010000', 'turkistan': '611010000',
        }
        for slug, code in expected.items():
            self.assertEqual(self.cities['kz-' + slug]['kato'], code)
        self.assertEqual(self.cities['kz-konaev']['name']['ru'], 'Конаев')
        konaev = self.cities['kz-konaev']
        self.assertIn('Қонаев', [*konaev['name'].values(), *konaev['aliases']])

    def test_non_capitals_and_common_search_names_are_included(self):
        for slug in ('alatau', 'kosshy', 'temirtau', 'shchuchinsk', 'saryagash',
                     'zaisan', 'baikonur', 'fort-shevchenko', 'zharkent', 'rudny'):
            self.assertIn('kz-' + slug, self.cities)
        for slug, alias in (('astana', 'Нур-Султан'), ('konaev', 'Капшагай'),
                            ('konaev', 'Kapchagay'), ('oskemen', 'Ust-Kamenogorsk'),
                            ('aktau', 'Шевченко'), ('semey', 'Семипалатинск'),
                            ('ridder', 'Лениногорск'), ('altai', 'Зыряновск'),
                            ('baikonur', 'Байконур'), ('arys', 'Арыс'), ('saran', 'Саран')):
            city = self.cities['kz-' + slug]
            self.assertIn(alias, [*city['name'].values(), *city['aliases']])
