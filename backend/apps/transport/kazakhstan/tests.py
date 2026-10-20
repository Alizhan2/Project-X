from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from .catalog import CITIES
from .providers import Offer, OneTR, ProviderUnavailable
from .views import SearchInput, catalog, search


class KazakhstanTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.params = {'origin': 'kz-almaty', 'destination': 'kz-astana',
                       'date': (self.now + timedelta(days=2)).date().isoformat(), 'time': '06:00'}

    def test_catalog_is_multilingual_geography_not_inventory(self):
        response = catalog(APIRequestFactory().get('/'))
        self.assertEqual(len(CITIES), 20)
        self.assertEqual(len({c['id'] for c in CITIES}), 20)
        self.assertFalse(response.data['booking_enabled'])
        self.assertEqual(response.data['currency'], 'KZT')
        self.assertEqual(response.data['timezone'], 'Asia/Almaty')
        for city in CITIES:
            self.assertEqual(set(city['name']), {'en', 'ru', 'kk'})
            self.assertEqual(set(city['region']), {'en', 'ru', 'kk'})

    def test_input_uses_kazakhstan_timezone_and_default_time(self):
        for params in (self.params, {k: v for k, v in self.params.items() if k != 'time'}):
            data = SearchInput(data=params)
            self.assertTrue(data.is_valid(), data.errors)
            dt = data.validated_data['depart_after']
            self.assertEqual(dt.utcoffset(), timedelta(hours=5))
            self.assertEqual(dt.hour, 6)

    def test_invalid_input_never_reaches_supplier(self):
        for changes in ({'destination': 'kz-almaty'}, {'origin': 'NG-BUS'}, {'passengers': 0},
                        {'passengers': 10}, {'modes': 'taxi'}, {'time': '24:00'},
                        {'date': '2000-01-01'}, {'date': (self.now + timedelta(days=367)).date().isoformat()}):
            with self.subTest(changes=changes):
                serializer = SearchInput(data={**self.params, **changes})
                self.assertFalse(serializer.is_valid())

    def test_unconnected_supplier_cannot_return_fake_inventory(self):
        with self.assertRaises(ProviderUnavailable):
            OneTR().search(None)
        response = search(APIRequestFactory().get('/', self.params))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'provider_not_connected')
        self.assertNotIn('results', response.data)
        self.assertFalse(response.data['booking_enabled'])

    def offer(self):
        query = SearchInput(data=self.params)
        query.is_valid(raise_exception=True)
        departure = query.validated_data['depart_after']
        return Offer('1tr', 'test-only-offer', 'kz-almaty', 'kz-astana', departure,
                     departure + timedelta(hours=20), Decimal('12345.67'), 'KZT',
                     self.now, self.now + timedelta(minutes=10), 'train', 1)

    def test_boundary_filters_expired_wrong_route_currency_party_and_long_journeys(self):
        valid = self.offer()
        rejected = [replace(valid, checked_at=self.now - timedelta(hours=2), expires_at=self.now - timedelta(hours=1)),
                    replace(valid, origin='kz-aktobe'), replace(valid, passengers=2),
                    replace(valid, provider='other'), replace(valid, checked_at=self.now + timedelta(minutes=1)),
                    replace(valid, arrives_at=valid.departs_at + timedelta(hours=73))]
        with patch('apps.transport.kazakhstan.views.get_provider') as supplier:
            supplier.return_value.search.return_value = [valid, *rejected]
            response = search(APIRequestFactory().get('/', self.params))
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['total_price'], '12345.67')
        self.assertFalse(response.data['booking_enabled'])

    def test_offer_contract_rejects_invalid_money_and_naive_dates(self):
        for changes in ({'total_price': Decimal('NaN')}, {'total_price': Decimal('-1')},
                        {'total_price': Decimal('1.001')}, {'currency': 'EUR'},
                        {'departs_at': self.now.replace(tzinfo=None)}, {'provider_offer_id': ''},
                        {'passengers': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.offer(), **changes)
