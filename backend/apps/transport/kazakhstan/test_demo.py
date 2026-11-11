from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
import threading
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.services import cancel_booking, create_booking
from apps.core.models import AuditRecord
from apps.payments.services import pay_booking, process_refund
from apps.transport.models import CancellationPolicy, Departure, Fare, Hub, Operator, Route, RouteStop, Stop, TransferLink

from .catalog import TIMEZONE
from .demo import DemoUnavailable, POLICY_NAME, SCHEDULE_ACTION, ensure_network, search_demo, stop_code
from .providers import SearchQuery


def query(passengers=1, modes=('bus', 'train')):
    day = timezone.now().astimezone(ZoneInfo(TIMEZONE)).date() + timedelta(days=2)
    return SearchQuery('kz-temirtau', 'kz-alatau', datetime.combine(day, time(6), tzinfo=ZoneInfo(TIMEZONE)),
                       passengers, modes)


@override_settings(SIMULATION_ENABLED=True)
class KazakhstanDemoTests(TestCase):
    def test_network_is_additive_idempotent_and_does_not_create_accounts_or_mesh(self):
        legacy = Stop.objects.create(code='EXISTING', name='Existing stop', kind='bus', step_free=False)
        operators = ensure_network()
        ensure_network()
        self.assertEqual(set(operators), {'kz-demo-bus', 'kz-demo-rail'})
        self.assertEqual(Hub.objects.filter(code__startswith='KZ-').count(), 90)
        self.assertEqual(Stop.objects.filter(code__startswith='KZ-').count(), 180)
        self.assertEqual(TransferLink.objects.count(), 180)
        self.assertEqual(CancellationPolicy.objects.filter(name=POLICY_NAME).count(), 1)
        self.assertEqual((Route.objects.count(), Departure.objects.count(), User.objects.count()), (0, 0, 0))
        legacy.refresh_from_db()
        self.assertEqual((legacy.name, legacy.step_free), ('Existing stop', False))
        bus, rail = (Stop.objects.get(code=stop_code('kz-temirtau', mode)) for mode in ('bus', 'train'))
        self.assertEqual((bus.name, rail.name), ('Temirtau', 'Temirtau'))
        walking = TransferLink.objects.get(from_stop=bus, to_stop=rail)
        self.assertEqual((walking.minutes, walking.boarding_buffer_minutes, walking.step_free), (10, 5, True))

    def test_noncapital_pair_returns_bookable_kzt_party_prices_in_local_time(self):
        search = query(passengers=3)
        results = search_demo(search)
        self.assertEqual(len(results), 6)
        self.assertEqual({it.legs[0].mode for it in results}, {'bus', 'train'})
        for itinerary in results:
            leg = itinerary.legs[0]
            self.assertEqual((itinerary.currency, itinerary.passengers, itinerary.transfers), ('KZT', 3, 0))
            self.assertEqual(itinerary.total_price, leg.unit_price * 3)
            self.assertGreater(leg.unit_price, Decimal('0'))
            self.assertEqual(leg.departs_at.utcoffset(), timedelta(hours=5))
            self.assertGreaterEqual(leg.departs_at, search.depart_after)
            self.assertLess(leg.departs_at, search.depart_after + timedelta(hours=24))
            self.assertTrue(leg.wheelchair_accessible)
            self.assertTrue(leg.from_stop.step_free)
            self.assertTrue(leg.to_stop.step_free)
            self.assertEqual(leg.selection['departure_id'], leg.departure.pk)

    def test_mode_filters_and_pair_only_generation_keep_the_mesh_small(self):
        bus_results = search_demo(query(modes=('bus',)))
        self.assertEqual(len(bus_results), 3)
        self.assertTrue(all(it.legs[0].mode == 'bus' for it in bus_results))
        self.assertEqual((Route.objects.count(), RouteStop.objects.count(), Fare.objects.count(), Departure.objects.count()),
                         (1, 2, 1, 6))
        search_demo(query(modes=('bus',)))
        self.assertEqual(Departure.objects.count(), 6)
        trains = search_demo(query(modes=('train',)))
        self.assertEqual(len(trains), 3)
        self.assertEqual({it.legs[0].mode for it in trains}, {'train'})
        self.assertEqual((Route.objects.count(), Departure.objects.count()), (2, 12))
        routes = Route.objects.all()
        self.assertTrue(all(len(route.code) <= 16 for route in routes))
        self.assertEqual({rs.stop.code for rs in RouteStop.objects.select_related('stop')},
                         {stop_code(city, mode) for city in ('kz-temirtau', 'kz-alatau') for mode in ('bus', 'train')})

    def test_search_respects_live_delays_cancellations_capacity_and_operator_fare(self):
        original = query(passengers=2, modes=('bus',))
        results = search_demo(original)
        delayed, cancelled = (results[index].legs[0].departure for index in (0, 1))
        Departure.objects.filter(pk=delayed.pk).update(status='delayed', delay_minutes=20,
                                                      capacity=5, places_taken=3, baseline_places=3)
        Departure.objects.filter(pk=cancelled.pk).update(status='cancelled')
        Fare.objects.update(price=Decimal('9876.54'))
        later = replace(original, depart_after=original.depart_after + timedelta(minutes=10))
        current = search_demo(later)
        matching = next(it for it in current if it.legs[0].departure.pk == delayed.pk)
        self.assertEqual(matching.departs_at, original.depart_after + timedelta(minutes=20))
        self.assertEqual(matching.total_price, Decimal('19753.08'))
        self.assertNotIn(cancelled.pk, [it.legs[0].departure.pk for it in current])
        self.assertNotIn(delayed.pk, [it.legs[0].departure.pk for it in search_demo(replace(later, passengers=3))])
        delayed.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual((delayed.status, delayed.delay_minutes, delayed.capacity, delayed.places_taken),
                         ('delayed', 20, 5, 3))
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(Fare.objects.get().price, Decimal('9876.54'))

    def test_repeated_search_preserves_rescheduled_and_deleted_template_slots(self):
        original = query(modes=('bus',))
        results = search_demo(original)
        moved, removed = (results[index].legs[0].departure for index in (0, 1))
        original_time = moved.departs_at
        moved.departs_at += timedelta(hours=2)
        moved.save(update_fields=['departs_at'])
        current = search_demo(original)
        self.assertFalse(Departure.objects.filter(route=moved.route, departs_at=original_time).exists())
        self.assertEqual(Departure.objects.count(), 6)
        live = next(it for it in current if it.legs[0].departure.pk == moved.pk)
        self.assertEqual(live.departs_at, moved.departs_at)
        removed_time = removed.departs_at
        removed.delete()
        search_demo(original)
        search_demo(original)
        self.assertFalse(Departure.objects.filter(route=moved.route, departs_at=removed_time).exists())
        self.assertEqual(Departure.objects.count(), 5)
        self.assertEqual(AuditRecord.objects.filter(action=SCHEDULE_ACTION).count(), 2)

    def test_new_local_day_extends_only_that_route_day_once(self):
        original = query(modes=('bus',))
        search_demo(original)
        tomorrow = replace(original, depart_after=original.depart_after + timedelta(days=1))
        self.assertEqual(len(search_demo(tomorrow)), 3)
        self.assertEqual(len(search_demo(tomorrow)), 3)
        self.assertEqual(Departure.objects.count(), 9)
        self.assertEqual(AuditRecord.objects.filter(action=SCHEDULE_ACTION).count(), 3)

    def test_current_prices_and_duration_sorting(self):
        prices = [it.total_price for it in search_demo(query(), sort='price')]
        self.assertEqual(prices, sorted(prices))
        durations = [it.duration_minutes for it in search_demo(query(), sort='duration')]
        self.assertEqual(durations, sorted(durations))

    def test_generated_selection_uses_existing_booking_payment_and_refund_lifecycle(self):
        itinerary = search_demo(query(passengers=2, modes=('train',)))[0]
        user = User.objects.create_user('kz-demo@example.test', 'Kazakhstan Demo', password=None)
        booking, created = create_booking(user=user, selection=[itinerary.legs[0].selection], passengers=2,
            traveller_names=['Demo One', 'Demo Two'], contact_email=user.email,
            idempotency_key='kazakhstan-demo-booking', expected_total=itinerary.total_price)
        self.assertTrue(created)
        self.assertEqual((booking.currency, booking.total_amount), ('KZT', itinerary.total_price))
        attempt, _ = pay_booking(user=user, reference=booking.reference,
                                idempotency_key='kazakhstan-demo-payment', outcome='success')
        booking.refresh_from_db()
        self.assertEqual((booking.status, attempt.status, attempt.currency), ('confirmed', 'succeeded', 'KZT'))
        search_demo(query(modes=('train',)))
        departure = Departure.objects.get(pk=itinerary.legs[0].departure.pk)
        self.assertEqual(departure.places_taken, 2)
        _booking, refund = cancel_booking(booking.pk, user, expected_refund=itinerary.total_price)
        process_refund(refund.pk)
        booking.refresh_from_db()
        refund.refresh_from_db()
        departure.refresh_from_db()
        self.assertEqual((booking.status, refund.status, refund.currency, departure.places_taken),
                         ('cancelled', 'completed', 'KZT', 0))

    @override_settings(SIMULATION_ENABLED=False)
    def test_simulation_disabled_refuses_before_writing(self):
        for action in (ensure_network, lambda: search_demo(query())):
            with self.assertRaises(DemoUnavailable):
                action()
        self.assertEqual((Hub.objects.count(), Stop.objects.count(), Route.objects.count(), Operator.objects.count()),
                         (0, 0, 0, 0))

    def test_invalid_search_and_seed_failure_do_not_leave_partial_data(self):
        for changes in ({'origin': 'NG-BUS'}, {'destination': 'kz-temirtau'}, {'passengers': 0},
                        {'currency': 'EUR'}, {'modes': ('taxi',)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                search_demo(replace(query(), **changes))
        self.assertEqual(Stop.objects.count(), 0)
        with patch('apps.transport.kazakhstan.demo.Departure.objects.bulk_create', side_effect=RuntimeError('seed failed')):
            with self.assertRaisesMessage(RuntimeError, 'seed failed'):
                search_demo(query())
        self.assertEqual((Hub.objects.count(), Stop.objects.count(), Route.objects.count(), CancellationPolicy.objects.count()),
                         (0, 0, 0, 0))
        self.assertEqual(AuditRecord.objects.filter(action=SCHEDULE_ACTION).count(), 0)


@override_settings(SIMULATION_ENABLED=True)
class KazakhstanDemoConcurrencyTests(TransactionTestCase):
    def test_simultaneous_first_searches_create_one_policy_and_no_duplicates(self):
        barrier = threading.Barrier(2)
        outcomes, errors = [], []

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                outcomes.append(len(search_demo(query())))
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(outcomes), [6, 6])
        self.assertEqual(CancellationPolicy.objects.filter(name=POLICY_NAME).count(), 1)
        self.assertEqual((Hub.objects.count(), Stop.objects.count(), Route.objects.count(), Departure.objects.count()),
                         (90, 180, 2, 12))
        self.assertEqual(AuditRecord.objects.filter(action=SCHEDULE_ACTION).count(), 4)
