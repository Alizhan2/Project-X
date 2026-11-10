from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.transport.models import CancellationPolicy, Departure, Fare, Operator, Route, RouteStop, Stop, TransferLink

from . import services
from .transfers import TransferRules, assess_connection


class ConnectionBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.bus = Stop(pk=1, code="C-BUS", step_free=True)
        self.rail = Stop(pk=2, code="C-RAIL", step_free=True)
        self.rules = TransferRules([TransferLink(from_stop=self.bus, to_stop=self.rail, minutes=8,
                                                boarding_buffer_minutes=10, step_free=True)])
        self.departure = datetime(2026, 11, 20, 9, tzinfo=dt_timezone.utc)

    def test_ex01_exact_boundaries(self):
        for minute, margin, status in [(42, 0, "at_risk"), (38, 4, "at_risk"),
                                       (37, 5, "feasible"), (50, -8, "infeasible")]:
            with self.subTest(arrival_minute=minute):
                arrival = self.departure.replace(hour=8, minute=minute)
                result = assess_connection(self.bus, self.rail, arrival, self.departure, self.rules)
                self.assertEqual((result["walking_minutes"], result["boarding_buffer_minutes"]), (8, 10))
                self.assertEqual((result["margin_minutes"], result["status"]), (margin, status))

    def test_full_dates_and_fractional_minute_boundaries(self):
        departure = self.departure.replace(hour=0, minute=5)
        arrival = departure - timedelta(minutes=23)
        self.assertEqual(assess_connection(self.bus, self.rail, arrival, departure, self.rules)["status"], "feasible")
        arrival += timedelta(seconds=1)
        self.assertEqual(assess_connection(self.bus, self.rail, arrival, departure, self.rules)["status"], "at_risk")
        arrival = departure - timedelta(minutes=18) + timedelta(seconds=1)
        self.assertEqual(assess_connection(self.bus, self.rail, arrival, departure, self.rules)["status"], "infeasible")

    def test_booking_disruption_check_uses_the_same_margin(self):
        from apps.bookings.models import BookingLeg
        from apps.disruptions.services import LiveLeg, assess

        for minute, expected in [(42, "ok"), (38, "ok"), (37, "ok"), (50, "broken")]:
            arrival = self.departure.replace(hour=8, minute=minute)
            first = BookingLeg(sequence=0, from_stop=self.bus, to_stop=self.bus,
                               departure_id=1, departs_at=arrival-timedelta(minutes=30), arrives_at=arrival)
            second = BookingLeg(sequence=1, from_stop=self.rail, to_stop=self.rail,
                                departure_id=2, departs_at=self.departure, arrives_at=self.departure+timedelta(hours=1))
            live = [LiveLeg(first, first.departs_at, first.arrives_at),
                    LiveLeg(second, second.departs_at, second.arrives_at)]
            with self.subTest(minute=minute), patch("apps.disruptions.services.live_legs", return_value=live):
                result = assess(None, transfers=self.rules)
                self.assertEqual(result.status, expected)
                self.assertEqual(result.connections[0], assess_connection(self.bus, self.rail, arrival, self.departure, self.rules))

    def test_fall_back_clock_uses_elapsed_time(self):
        zone = ZoneInfo("Europe/Berlin")
        arrival = datetime(2026, 10, 25, 2, 37, tzinfo=zone, fold=0)
        departure = datetime(2026, 10, 25, 2, 0, tzinfo=zone, fold=1)
        result = assess_connection(self.bus, self.rail, arrival, departure, self.rules)
        self.assertEqual((result["margin_minutes"], result["status"]), (5, "feasible"))

    def test_missing_path_is_never_feasible(self):
        result = assess_connection(self.rail, self.bus, self.departure-timedelta(hours=1), self.departure, self.rules)
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["path_step_free"], "unknown")

    def test_on_demand_pickup_does_not_claim_connection_safety(self):
        result = assess_connection(self.bus, self.rail, self.departure-timedelta(minutes=28),
                                   self.departure, self.rules, on_demand=True)
        self.assertEqual(result["status"], "on_demand")
        self.assertIsNone(result["margin_minutes"])


class AccessibleTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.start = (timezone.now() + timedelta(days=2)).replace(hour=8, minute=0, second=0, microsecond=0)
        cls.a, cls.b, cls.c, cls.d = [Stop.objects.create(code=code, name=code, kind="bus", step_free=True)
                                     for code in ["A", "B", "C", "D"]]
        operator = Operator.objects.create(code="EX", name="Example")
        policy = CancellationPolicy.objects.create(name="Flexible", full_refund_hours_before=0,
                                                    partial_refund_hours_before=0, partial_refund_percent=100)
        cls.departures = []
        for index, (origin, destination, at) in enumerate([(cls.a, cls.b, cls.start),
                                                         (cls.c, cls.d, cls.start+timedelta(hours=1))]):
            route = Route.objects.create(operator=operator, policy=policy, code=f"R{index}", name="Example", mode="bus")
            for sequence, (stop, offset) in enumerate([(origin, 0), (destination, 30)]):
                RouteStop.objects.create(route=route, sequence=sequence, stop=stop,
                                         arrival_offset_min=offset, departure_offset_min=offset)
            Fare.objects.create(route=route, from_stop=origin, to_stop=destination, price=Decimal("400"), currency="KZT")
            cls.departures.append(Departure.objects.create(route=route, departs_at=at, capacity=10,
                                                           wheelchair_accessible=True))
        cls.path = TransferLink.objects.create(from_stop=cls.b, to_stop=cls.c, minutes=8,
                                               boarding_buffer_minutes=10, step_free=True)

    def selection(self):
        return [{"departure_id": dep.pk, "from_stop": origin.code, "to_stop": dest.code}
                for dep, origin, dest in [(self.departures[0], self.a, self.b), (self.departures[1], self.c, self.d)]]

    def find(self, **kwargs):
        return services.search(self.a, self.d, self.start, 1, now=self.start-timedelta(hours=1),
                               wheelchair_required=True, **kwargs)

    def test_strict_search_and_checkout_share_full_path_check(self):
        self.assertEqual(len(self.find()), 1)
        it = services.build_itinerary(self.selection(), 1, self.start-timedelta(hours=1), wheelchair_required=True)
        self.assertEqual(it.connections[0]["margin_minutes"], 12)
        self.assertEqual(it.connections[0]["path_step_free"], "yes")
        for value in [None, False]:
            self.path.step_free = value
            self.path.save()
            self.assertEqual(self.find(), [])
            with self.assertRaisesMessage(services.OfferError, "not confirmed accessible"):
                services.build_itinerary(self.selection(), 1, self.start-timedelta(hours=1), wheelchair_required=True)
        self.assertTrue(services.search(self.a, self.d, self.start, 1, now=self.start-timedelta(hours=1)))

    def test_arrive_by_excludes_unknown_path(self):
        params = dict(now=self.start-timedelta(hours=1), wheelchair_required=True)
        self.assertTrue(services.search_arrive_by(self.a, self.d, self.start+timedelta(hours=2), 1, **params))
        self.path.step_free = None
        self.path.save()
        self.assertEqual(services.search_arrive_by(self.a, self.d, self.start+timedelta(hours=2), 1, **params), [])

    def test_unknown_vehicle_or_stop_is_excluded(self):
        for model, pk, field in [(Departure, self.departures[0].pk, "wheelchair_accessible"),
                                 (Stop, self.b.pk, "step_free"), (Stop, self.a.pk, "step_free")]:
            with self.subTest(field=field, pk=pk):
                model.objects.filter(pk=pk).update(**{field: None})
                self.assertEqual(self.find(), [])
                model.objects.filter(pk=pk).update(**{field: True})

    def test_recovery_first_walk_requires_accessible_path(self):
        now = self.start-timedelta(hours=1)
        self.assertTrue(services.search(self.b, self.d, self.start, 1, now=now,
                                        walk_from_start=True, wheelchair_required=True))
        self.path.step_free = None
        self.path.save()
        self.assertEqual(services.search(self.b, self.d, self.start, 1, now=now,
                                         walk_from_start=True, wheelchair_required=True), [])

    def test_boarding_buffer_is_enforced_in_search_and_revalidation(self):
        self.path.boarding_buffer_minutes = 23
        self.path.save()
        self.assertEqual(self.find(), [])
        with self.assertRaisesMessage(services.OfferError, "no longer possible"):
            services.build_itinerary(self.selection(), 1, self.start-timedelta(hours=1))

    def test_api_strict_flag_validation_and_current_details(self):
        params = {"origin": self.a.code, "destination": self.d.code, "depart_after": self.start.isoformat(),
                  "wheelchair_required": "true"}
        result = self.client.get("/api/search/", params)
        self.assertEqual(result.status_code, 200)
        self.assertIs(result.json()["results"][0]["wheelchair_required"], True)
        self.assertEqual(result.json()["results"][0]["connections"][0]["boarding_buffer_minutes"], 10)
        self.assertEqual(self.client.get("/api/search/", {**params, "wheelchair_required": "maybe"}).status_code, 400)
        legs = ",".join(f"d{s['departure_id']}:{s['from_stop']}:{s['to_stop']}" for s in self.selection())
        self.path.step_free = None
        self.path.save()
        result = self.client.get("/api/itinerary/", {"legs": legs, "wheelchair_required": "true"})
        self.assertEqual((result.status_code, result.json()["code"]), (409, "accessibility_unavailable"))
