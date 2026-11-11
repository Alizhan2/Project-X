"""Kazakhstan search preferences use the same live offer rules as checkout."""
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import transaction
from django.test import TestCase, override_settings

from apps.bookings.models import Booking, Reservation
from apps.bookings.tests import checkout, client_for, make_user
from apps.transport.models import Departure, Fare, RouteStop, Stop

from .demo import search_demo, stop_code
from .providers import SearchQuery
from .views import SearchInput


ZONE = ZoneInfo('Asia/Almaty')


@override_settings(SIMULATION_ENABLED=True)
class KazakhstanSearchPreferencesTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, tzinfo=ZONE)
        self.enterContext(patch('django.utils.timezone.now', return_value=self.now))
        self.day = self.now.date() + timedelta(days=2)
        self.start = datetime.combine(self.day, time(6), tzinfo=ZONE)
        self.query = SearchQuery('kz-almaty', 'kz-astana', self.start, 2, ('bus',))
        self.params = {'origin': self.query.origin, 'destination': self.query.destination,
                       'date': self.day.isoformat(), 'time': '06:00', 'passengers': 2, 'modes': 'bus'}

    def arrival_query(self, deadline, **changes):
        return replace(self.query, depart_after=deadline - timedelta(hours=24), **changes)

    def test_arrival_input_uses_local_deadline_and_prior_24_hour_window(self):
        data = SearchInput(data={**self.params, 'time_mode': 'arrival', 'time': '07:30',
                                 'wheelchair_required': 'true', 'max_price': '10000.00'})
        self.assertTrue(data.is_valid(), data.errors)
        values = data.validated_data
        deadline = datetime.combine(self.day, time(7, 30), tzinfo=ZONE)
        self.assertEqual(values['arrive_by'], deadline)
        self.assertEqual(values['depart_after'], deadline - timedelta(hours=24))
        self.assertEqual(values['arrive_by'].utcoffset(), timedelta(hours=5))
        self.assertIs(values['wheelchair_required'], True)
        self.assertEqual(values['max_price'], Decimal('10000.00'))

    def test_defaults_preserve_departure_search_and_unlimited_budget(self):
        data = SearchInput(data=self.params)
        self.assertTrue(data.is_valid(), data.errors)
        self.assertEqual(data.validated_data['depart_after'], self.start)
        self.assertEqual(data.validated_data['time_mode'], 'departure')
        self.assertNotIn('arrive_by', data.validated_data)
        self.assertIsNone(data.validated_data['max_price'])
        self.assertIs(data.validated_data['wheelchair_required'], False)

    def test_arrival_is_inclusive_and_defaults_to_latest_departure(self):
        original = search_demo(self.query)[0]
        deadline = original.arrives_at
        results = search_demo(self.arrival_query(deadline), arrive_by=deadline)
        self.assertTrue(results)
        self.assertEqual(results[0].departs_at, self.start)
        self.assertEqual(results[0].arrives_at, deadline)
        self.assertTrue(all(it.arrives_at <= deadline for it in results))
        self.assertEqual([it.departs_at for it in results], sorted((it.departs_at for it in results), reverse=True))
        self.assertTrue(any(it.departs_at.date() == self.day - timedelta(days=1) for it in results))

    def test_arrival_window_generates_previous_day_and_handles_midnight(self):
        search_demo(self.query)
        RouteStop.objects.filter(sequence=1).update(arrival_offset_min=390, departure_offset_min=390)
        deadline = datetime.combine(self.day + timedelta(days=1), time(0, 30), tzinfo=ZONE)
        results = search_demo(self.arrival_query(deadline), arrive_by=deadline)
        self.assertTrue(results)
        self.assertEqual(results[0].departs_at, datetime.combine(self.day, time(18), tzinfo=ZONE))
        self.assertEqual(results[0].arrives_at, deadline)
        self.assertTrue(all(deadline - timedelta(hours=24) <= it.departs_at < deadline for it in results))

    def test_nearby_arrival_deadline_never_returns_departed_services(self):
        expired = replace(self.query, depart_after=self.now - timedelta(hours=24))
        self.assertEqual(search_demo(expired, arrive_by=self.now), [])
        self.assertEqual(Stop.objects.count(), 0)
        deadline = self.now + timedelta(hours=8)
        data = SearchInput(data={**self.params, 'date': self.now.date().isoformat(),
                                 'time': '20:00', 'time_mode': 'arrival'})
        self.assertTrue(data.is_valid(), data.errors)
        self.assertEqual(data.validated_data['depart_after'], self.now)
        results = search_demo(self.arrival_query(deadline), arrive_by=deadline)
        self.assertTrue(results)
        self.assertTrue(all(self.now < it.departs_at and it.arrives_at <= deadline for it in results))
        self.assertFalse(any(it.departs_at.hour == 12 for it in results))

    def test_live_delays_and_cancellations_are_rechecked_against_deadline(self):
        deadline = search_demo(self.query)[0].arrives_at
        arrival_query = self.arrival_query(deadline)
        results = search_demo(arrival_query, arrive_by=deadline)
        delayed, cancelled = results[0].legs[0].departure, results[1].legs[0].departure
        Departure.objects.filter(pk=delayed.pk).update(status='delayed', delay_minutes=10)
        Departure.objects.filter(pk=cancelled.pk).update(status='cancelled')
        current = search_demo(arrival_query, arrive_by=deadline)
        ids = {it.legs[0].departure.pk for it in current}
        self.assertNotIn(delayed.pk, ids)
        self.assertNotIn(cancelled.pk, ids)
        self.assertTrue(all(it.arrives_at <= deadline for it in current))
        delayed.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual((delayed.status, delayed.delay_minutes, cancelled.status), ('delayed', 10, 'cancelled'))

    def test_strict_accessibility_excludes_unknown_and_inaccessible_vehicles(self):
        initial = search_demo(self.query)
        Departure.objects.filter(pk=initial[0].legs[0].departure.pk).update(wheelchair_accessible=None)
        Departure.objects.filter(pk=initial[1].legs[0].departure.pk).update(wheelchair_accessible=False)
        strict = search_demo(self.query, wheelchair_required=True)
        self.assertEqual([it.legs[0].departure.pk for it in strict], [initial[2].legs[0].departure.pk])
        self.assertTrue(all(it.wheelchair_required for it in strict))
        self.assertEqual(len(search_demo(self.query)), 3)

    def test_strict_accessibility_requires_both_stops_to_be_confirmed_step_free(self):
        search_demo(self.query)
        for city in (self.query.origin, self.query.destination):
            for value in (False, None):
                with self.subTest(city=city, step_free=value):
                    Stop.objects.filter(code=stop_code(city, 'bus')).update(step_free=value)
                    self.assertEqual(search_demo(self.query, wheelchair_required=True), [])
                    self.assertEqual(len(search_demo(self.query)), 3)
                    Stop.objects.filter(code=stop_code(city, 'bus')).update(step_free=True)

    def test_budget_is_inclusive_whole_party_price_and_zero_is_a_real_cap(self):
        query = replace(self.query, passengers=3)
        search_demo(query)
        Fare.objects.update(price=Decimal('10.00'))
        self.assertEqual(len(search_demo(query, max_price=Decimal('30.00'))), 3)
        self.assertEqual(search_demo(query, max_price=Decimal('29.99')), [])
        self.assertEqual(search_demo(query, max_price=Decimal('0')), [])

    def test_api_returns_arrival_and_accessibility_context_without_supplier_calls(self):
        deadline = search_demo(self.query)[0].arrives_at
        with patch('apps.transport.kazakhstan.views.get_provider') as supplier:
            response = self.client.get('/api/kazakhstan/search/', {**self.params,
                'date': deadline.date().isoformat(), 'time': deadline.strftime('%H:%M'),
                'time_mode': 'arrival', 'wheelchair_required': 'true', 'max_price': '10000.00'})
        supplier.assert_not_called()
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['time_mode'], 'arrival')
        self.assertEqual(payload['arrive_by'], deadline.isoformat())
        self.assertTrue(payload['results'])
        for result in payload['results']:
            self.assertTrue(result['wheelchair_required'])
            self.assertLessEqual(datetime.fromisoformat(result['arrives_at']), deadline)
            self.assertLessEqual(Decimal(result['total_price']), Decimal('10000.00'))
        self.assertEqual(payload['results'][0]['departs_at'], self.start.isoformat())

    def test_arrival_deadline_is_rechecked_at_itinerary_and_checkout_after_delay(self):
        deadline = search_demo(self.query)[0].arrives_at
        response = self.client.get('/api/kazakhstan/search/', {**self.params, 'time_mode': 'arrival',
                                    'time': deadline.strftime('%H:%M'), 'wheelchair_required': 'true'})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        itinerary = payload['results'][0]
        self.assertEqual(payload['arrive_by'], deadline.isoformat())
        self.assertTrue(payload['arrive_by'].endswith('+05:00'))
        self.assertEqual(itinerary['arrives_at'], payload['arrive_by'])
        user = make_user('arrival-preferences@example.test')
        client = client_for(user)
        params = {'legs': itinerary['legs_param'], 'passengers': 2, 'wheelchair_required': 'true',
                  'arrive_by': payload['arrive_by']}
        detail = client.get('/api/itinerary/', params)
        self.assertEqual(detail.status_code, 200, detail.content)
        body = {'legs': itinerary['selection'], 'passengers': 2, 'travellers': ['Demo One', 'Demo Two'],
                'contact_email': user.email, 'expected_total': itinerary['total_price'],
                'arrive_by': payload['arrive_by'], 'wheelchair_required': True}
        # Prove equality is bookable, then roll back this private probe before testing stale search results.
        with transaction.atomic():
            accepted = checkout(client, body)
            self.assertEqual(accepted.status_code, 201, accepted.content)
            self.assertEqual(accepted.json()['legs'][0]['arrives_at'], payload['arrive_by'])
            transaction.set_rollback(True)
        self.assertEqual((Booking.objects.count(), Reservation.objects.count()), (0, 0))
        departure_id = itinerary['selection'][0]['departure_id']
        from apps.disruptions.services import apply_change
        apply_change(actor=user, departure_id=departure_id, action='delay', minutes=10)
        for rejected in (client.get('/api/itinerary/', params), checkout(client, body)):
            self.assertEqual(rejected.status_code, 409, rejected.content)
            self.assertEqual(rejected.json()['code'], 'arrival_deadline_missed')
        self.assertEqual((Booking.objects.count(), Reservation.objects.count()), (0, 0))
        self.assertEqual(Departure.objects.get(pk=departure_id).places_taken, 0)

    def test_strict_accessibility_is_rechecked_after_search_without_holding_places(self):
        response = self.client.get('/api/kazakhstan/search/', {**self.params, 'wheelchair_required': 'true'})
        self.assertEqual(response.status_code, 200, response.content)
        itinerary = response.json()['results'][0]
        self.assertTrue(itinerary['wheelchair_required'])
        user = make_user('accessible-preferences@example.test')
        client = client_for(user)
        params = {'legs': itinerary['legs_param'], 'passengers': 2, 'wheelchair_required': 'true'}
        self.assertEqual(client.get('/api/itinerary/', params).status_code, 200)
        body = {'legs': itinerary['selection'], 'passengers': 2, 'travellers': ['Demo One', 'Demo Two'],
                'contact_email': user.email, 'expected_total': itinerary['total_price'], 'wheelchair_required': True}
        departure_id = itinerary['selection'][0]['departure_id']
        for unavailable in ('vehicle_unknown', 'origin_not_step_free'):
            with self.subTest(unavailable=unavailable):
                if unavailable == 'vehicle_unknown':
                    Departure.objects.filter(pk=departure_id).update(wheelchair_accessible=None)
                else:
                    Departure.objects.filter(pk=departure_id).update(wheelchair_accessible=True)
                    Stop.objects.filter(code=stop_code(self.query.origin, 'bus')).update(step_free=False)
                for rejected in (client.get('/api/itinerary/', params), checkout(client, body)):
                    self.assertEqual(rejected.status_code, 409, rejected.content)
                    self.assertEqual(rejected.json()['code'], 'accessibility_unavailable')
                self.assertEqual((Booking.objects.count(), Reservation.objects.count()), (0, 0))
                self.assertEqual(Departure.objects.get(pk=departure_id).places_taken, 0)

    def test_invalid_preferences_are_rejected_before_supplier_or_generation(self):
        for changes in ({'time_mode': 'other'}, {'wheelchair_required': 'maybe'}, {'max_price': '-0.01'},
                        {'max_price': 'NaN'}, {'max_price': 'Infinity'}, {'max_price': '1.001'},
                        {'max_price': '10000000000.00'}, {'sort': 'buffer'}, {'sort': 'bad'},
                        {'time': '24:00'}, {'time_mode': 'arrival', 'date': '2000-01-01'},
                        {'date': (self.day + timedelta(days=366)).isoformat()}):
            with self.subTest(changes=changes), patch('apps.transport.kazakhstan.views.get_provider') as supplier:
                response = self.client.get('/api/kazakhstan/search/', {**self.params, **changes})
                self.assertEqual(response.status_code, 400, response.content)
                supplier.assert_not_called()
        self.assertEqual((Stop.objects.count(), Departure.objects.count()), (0, 0))

    def test_invalid_helper_preferences_do_not_create_inventory(self):
        for preferences in ({'max_price': Decimal('-1')}, {'max_price': Decimal('NaN')},
                            {'max_price': 1000.0}, {'wheelchair_required': 'false'},
                            {'arrive_by': self.start - timedelta(minutes=1)},
                            {'arrive_by': self.start.replace(tzinfo=None)}):
            with self.subTest(preferences=preferences), self.assertRaises(ValueError):
                search_demo(self.query, **preferences)
        self.assertEqual((Stop.objects.count(), Departure.objects.count()), (0, 0))
