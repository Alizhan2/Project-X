from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.transport import demo_data

REF = demo_data.reference_date()          # today in the demo timezone
DAY = REF + timedelta(days=1)             # demo day: carries the special scenarios
NEXT = REF + timedelta(days=2)


def at(hhmm, day=DAY):
    """'YYYY-MM-DDTHH:MM' local string for the demo day (tests stay valid as the calendar moves)."""
    return f"{day.isoformat()}T{hhmm}"


def get(client, **params):
    base = {"origin": "NG-BUS", "destination": "RV-BUS", "depart_after": at("07:00"), "passengers": 1}
    base.update(params)
    return client.get("/api/search/", {k: v for k, v in base.items() if v is not None})


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        demo_data.reset_transport_data(REF)

    def routes(self, res):
        """(route, local departure 'YYYY-MM-DDTHH:MM') pairs of *direct* journeys; full date avoids next-day collisions."""
        return [(r["legs"][0]["route_code"], r["departs_at"][:16]) for r in res.json()["results"] if r["transfers"] == 0]

    def test_returns_real_database_results_with_simulated_flag(self):
        res = get(self.client)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["simulated"])
        self.assertGreater(res.json()["count"], 0)

    def test_cancelled_service_excluded(self):
        self.assertNotIn(("VC1", at("10:00")), self.routes(get(self.client)))

    def test_delay_shifts_times_and_is_reported(self):
        r = next(x for x in get(self.client).json()["results"] if x["legs"][0]["delay_minutes"] == 45)
        self.assertEqual(r["departs_at"][11:16], "08:45")
        self.assertEqual(r["arrives_at"][11:16], "09:40")

    def test_time_boundaries_inclusive_start(self):
        def departures(after):
            return [r["departs_at"][:16] for r in get(self.client, depart_after=after).json()["results"]]
        self.assertIn(at("07:30"), departures(at("07:30")))
        self.assertNotIn(at("07:30"), departures(at("07:31")))

    def test_window_is_24_hours(self):
        res = self.routes(get(self.client, depart_after=at("07:00")))
        self.assertIn(("VC1", at("06:00", NEXT)), res)  # next day 06:00, within the window
        res2 = get(self.client, depart_after=at("07:00")).json()["results"]
        self.assertTrue(all(r["departs_at"][:16] <= at("07:00", NEXT) for r in res2))

    def test_wrong_direction_has_no_results_for_one_way_route(self):
        res = get(self.client, origin="LK-BUS", destination="RV-BUS")
        self.assertEqual(self.routes(res), [])  # no direct bus Lakeside -> Riverton (a taxi + walk connection exists)

    def test_reverse_direction_uses_reverse_route(self):
        res = get(self.client, origin="RV-BUS", destination="NG-BUS")
        self.assertEqual({r[0] for r in self.routes(res)}, {"VC1R"})

    def test_capacity_filter_last_place(self):
        one = get(self.client, depart_after=at("07:30"), passengers=1)
        two = get(self.client, depart_after=at("07:30"), passengers=2)
        self.assertIn(("GL1", at("07:30")), self.routes(one))
        self.assertNotIn(("GL1", at("07:30")), self.routes(two))
        leg = next(r for r in one.json()["results"] if r["legs"][0]["route_code"] == "GL1")["legs"][0]
        self.assertEqual(leg["places_left"], 1)

    def test_sold_out_service_excluded(self):
        res = get(self.client, origin="RV-BUS", destination="PM-BUS", depart_after=at("11:00"))
        self.assertNotIn(("GL2", at("11:30")), self.routes(res))

    def test_midnight_crossing_arrives_next_day(self):
        res = get(self.client, depart_after=at("23:00"))
        night = next(r for r in res.json()["results"] if r["legs"][0]["route_code"] == "GL3")
        self.assertEqual(night["departs_at"][:16], at("23:30"))
        self.assertEqual(night["arrives_at"][:16], at("00:40", NEXT))
        self.assertEqual(night["duration_minutes"], 70)

    def test_total_price_scales_with_passengers_exactly(self):
        one = get(self.client, depart_after=at("12:00")).json()["results"][0]
        three = get(self.client, depart_after=at("12:00"), passengers=3).json()["results"][0]
        self.assertEqual(one["total_price"], "7.00")
        self.assertEqual(three["total_price"], "21.00")
        self.assertEqual(three["currency"], "EUR")

    def test_sorting(self):
        by_price = [float(r["total_price"]) for r in get(self.client, sort="price").json()["results"]]
        self.assertEqual(by_price, sorted(by_price))
        by_dur = [r["duration_minutes"] for r in get(self.client, sort="duration").json()["results"]]
        self.assertEqual(by_dur, sorted(by_dur))

    def test_unknown_accessibility_is_unknown_not_no(self):
        res = get(self.client, origin="RV-BUS", destination="LK-BUS", depart_after=at("07:00"))
        leg = res.json()["results"][0]["legs"][0]
        self.assertEqual(leg["accessibility"]["wheelchair_vehicle"], "unknown")
        self.assertEqual(leg["accessibility"]["destination_step_free"], "unknown")

    def test_validation(self):
        for params in (
            {"passengers": 0}, {"passengers": 10}, {"passengers": "x"}, {"depart_after": "nope"},
            {"origin": "ZZZ"}, {"destination": "NG-BUS"}, {"sort": "cheapest"},
        ):
            self.assertEqual(get(self.client, **params).status_code, 400, params)

    def test_stops_endpoint(self):
        res = self.client.get("/api/stops/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("NG-BUS", [s["code"] for s in res.json()])


class SeedTests(TestCase):
    def test_seed_is_deterministic_and_resettable(self):
        from apps.transport.models import Departure
        with override_settings(ALLOW_DEMO_TOOLS=True):
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            first = list(Departure.objects.order_by("route__code", "departs_at").values_list("route__code", "departs_at", "status", "places_taken"))
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            second = list(Departure.objects.order_by("route__code", "departs_at").values_list("route__code", "departs_at", "status", "places_taken"))
        self.assertEqual(first, second)

    def test_seed_command_creates_the_recovery_demo_bookings(self):
        from apps.bookings.models import Booking
        with override_settings(ALLOW_DEMO_TOOLS=True):
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)   # reset is repeatable
        self.assertEqual(sorted(Booking.objects.values_list("user__username", "status")), [
            ("demo.noalt@doedu.test", "confirmed"), ("demo.passenger@doedu.test", "confirmed"),
            ("demo.pay@doedu.test", "confirmed"), ("demo.refund@doedu.test", "confirmed")])

    def test_seed_refuses_outside_debug(self):
        with override_settings(ALLOW_DEMO_TOOLS=False), self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)


class ItineraryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.transport.models import Departure
        demo_data.reset_transport_data(REF)
        cls.dep = Departure.objects.get(route__code="VC1", departs_at=demo_data._local(DAY, "12:00"))
        cls.last = Departure.objects.get(route__code="GL1", departs_at=demo_data._local(DAY, "07:30"))

    def test_returns_fresh_details(self):
        r = self.client.get("/api/itinerary/", {"legs": f"d{self.dep.pk}:NG-BUS:RV-BUS", "passengers": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_price"], "14.00")
        self.assertEqual(r.json()["legs_param"], f"d{self.dep.pk}:NG-BUS:RV-BUS")

    def test_bare_numeric_leg_token_still_accepted(self):
        r = self.client.get("/api/itinerary/", {"legs": f"{self.dep.pk}:NG-BUS:RV-BUS"})
        self.assertEqual(r.status_code, 200)

    def test_conflicts_and_validation(self):
        r = self.client.get("/api/itinerary/", {"legs": f"d{self.last.pk}:NG-BUS:RV-BUS", "passengers": 2})
        self.assertEqual((r.status_code, r.json()["code"]), (409, "no_capacity"))
        r = self.client.get("/api/itinerary/", {"legs": f"d{self.dep.pk}:RV-BUS:NG-BUS"})
        self.assertEqual((r.status_code, r.json()["code"]), (409, "invalid_leg"))
        self.assertEqual(self.client.get("/api/itinerary/", {"legs": "junk"}).status_code, 400)
        self.assertEqual(self.client.get("/api/itinerary/", {"legs": f"d{self.dep.pk}:NG-BUS:RV-BUS", "passengers": 99}).status_code, 400)
        too_many = ",".join([f"d{self.dep.pk}:NG-BUS:RV-BUS"] * 4)
        self.assertEqual(self.client.get("/api/itinerary/", {"legs": too_many}).status_code, 400)


class MultimodalSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        demo_data.reset_transport_data(REF)

    def search(self, o, d, hhmm="11:00", **kw):
        return get(self.client, origin=o, destination=d, depart_after=at(hhmm), **kw).json()["results"]

    def modes(self, it):
        return [l["mode"] for l in it["legs"]]

    def test_bus_train_taxi_itinerary_exists_with_correct_pricing(self):
        res = self.search("NG-BUS", "PM-MARINA")
        chain = [r for r in res if self.modes(r) == ["bus", "train", "taxi"]]
        self.assertTrue(chain)
        it = chain[0]
        self.assertEqual([l["from"]["code"] for l in it["legs"]], ["NG-BUS", "RV-RAIL", "PM-RAIL"])
        self.assertEqual(it["transfers"], 2)
        taxi = it["legs"][2]
        self.assertEqual((taxi["unit_price"], taxi["price_basis"]), ("14.00", "vehicle"))
        total = sum(float(l["leg_total"]) for l in it["legs"])
        self.assertAlmostEqual(float(it["total_price"]), total)

    def test_taxi_is_priced_per_vehicle_not_per_passenger(self):
        one = next(r for r in self.search("NG-BUS", "PM-MARINA") if self.modes(r) == ["bus", "train", "taxi"])
        three = next(r for r in self.search("NG-BUS", "PM-MARINA", passengers=3) if self.modes(r) == ["bus", "train", "taxi"])
        self.assertEqual(three["legs"][2]["leg_total"], "14.00")
        self.assertEqual(three["legs"][0]["leg_total"], f"{float(one['legs'][0]['unit_price']) * 3:.2f}")

    def test_more_passengers_than_a_taxi_holds_gives_no_taxi_journeys(self):
        self.assertEqual(self.search("NG-BUS", "PM-MARINA", passengers=5), [])

    def test_connections_respect_transfer_times_and_delays(self):
        # VC1 08:00 is delayed 45 min => arrives Riverton 09:40, +10 min walk = 09:50: the 09:45 train is missed.
        res = self.search("NG-BUS", "PM-RAIL", "07:30")
        delayed = [r for r in res if r["legs"][0]["status"] == "delayed" and len(r["legs"]) == 2]
        self.assertTrue(delayed)
        for r in delayed:
            train = r["legs"][1]
            self.assertGreaterEqual(train["departs_at"][11:16], "10:45")  # earliest feasible train
            self.assertGreaterEqual(r["min_transfer_buffer_minutes"], 0)

    def test_every_connection_is_physically_possible(self):
        for r in self.search("NG-BUS", "PM-MARINA", "06:00") + self.search("NG-BUS", "LK-BUS", "06:00"):
            self.assertLessEqual(len(r["legs"]), 3)
            stops = [r["legs"][0]["from"]["code"]] + [l["to"]["code"] for l in r["legs"]]
            self.assertEqual(len(stops), len(set(stops)), "stop visited twice")
            for a, b in zip(r["legs"], r["legs"][1:]):
                self.assertGreater(b["departs_at"], a["arrives_at"])

    def dep(self, code, hhmm):
        from apps.transport.models import Departure
        return Departure.objects.get(route__code=code, departs_at=demo_data._local(DAY, hhmm))

    def itinerary(self, legs):
        return self.client.get("/api/itinerary/", {"legs": ",".join(legs)})

    def test_connection_needs_an_explicit_transfer_link(self):
        bus = self.dep("VC1", "12:00")           # arrives Riverton Bus Station
        train = self.dep("DR1", "13:10")         # leaves Northgate Central Station: no link from RV-BUS to NG-RAIL
        r = self.itinerary([f"d{bus.pk}:NG-BUS:RV-BUS", f"d{train.pk}:NG-RAIL:RV-RAIL"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "invalid_connection"))

    def test_connection_missed_when_previous_service_is_delayed(self):
        delayed_bus = self.dep("VC1", "08:00")   # +45 min: arrives Riverton 09:40, walk 10 => 09:50
        train = self.dep("DR1", "09:10")         # leaves Riverton Station 09:45
        legs = [f"d{delayed_bus.pk}:NG-BUS:RV-BUS", f"d{train.pk}:RV-RAIL:PM-RAIL"]
        r = self.itinerary(legs)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "connection_missed"))
        delayed_bus.delay_minutes, delayed_bus.status = 0, "scheduled"   # on time: arrives 08:55 => 40 min spare
        delayed_bus.save()
        ok = self.itinerary(legs)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["transfer_buffers"], [40])

    def test_sort_by_buffer_puts_largest_minimum_buffer_first(self):
        res = get(self.client, origin="NG-BUS", destination="PM-RAIL", depart_after=at("06:00"), sort="buffer").json()["results"]
        with_conn = [r["min_transfer_buffer_minutes"] for r in res if r["min_transfer_buffer_minutes"] is not None]
        self.assertEqual(with_conn, sorted(with_conn, reverse=True))
        directs = [r for r in res if r["min_transfer_buffer_minutes"] is None]
        if directs:
            self.assertIsNone(res[0]["min_transfer_buffer_minutes"])  # direct = nothing to miss, listed first

    def test_taxi_not_offered_outside_service_hours(self):
        # Last train arrives Portmouth 00:30; a taxi pickup would be after 23:59 => no taxi continuation.
        res = self.search("RV-RAIL", "PM-MARINA", "23:30")
        self.assertEqual([r for r in res if r["departs_at"][:10] == DAY.isoformat()], [])

    def test_train_journey_crossing_midnight(self):
        res = self.search("NG-RAIL", "PM-RAIL", "23:00")
        night = [r for r in res if r["legs"][0]["departs_at"][:16] == at("23:10")]
        self.assertTrue(night)
        self.assertEqual(night[0]["arrives_at"][:10], NEXT.isoformat())
        self.assertEqual(night[0]["duration_minutes"], 80)

    def test_departed_services_are_not_offered(self):
        res = get(self.client, origin="NG-BUS", destination="RV-BUS", depart_after=at("06:00", REF - timedelta(days=1))).json()
        self.assertTrue(all(r["departs_at"] > (REF - timedelta(days=1)).isoformat() for r in res["results"]))
        from django.utils import timezone
        self.assertTrue(all(r["departs_at"] >= timezone.localtime().isoformat()[:16] for r in res["results"]))


class SeedTests(TestCase):
    def test_seed_is_deterministic_and_resettable(self):
        from apps.transport.models import Departure
        q = lambda: list(Departure.objects.order_by("route__code", "departs_at").values_list("route__code", "departs_at", "status", "places_taken"))
        with override_settings(ALLOW_DEMO_TOOLS=True):
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            first = q()
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            second = q()
        self.assertEqual(first, second)

    def test_seed_command_creates_the_recovery_demo_bookings(self):
        from apps.bookings.models import Booking
        with override_settings(ALLOW_DEMO_TOOLS=True):
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)
            call_command("seed_demo", reference_date=REF.isoformat(), verbosity=0)   # reset is repeatable
        self.assertEqual(sorted(Booking.objects.values_list("user__username", "status")), [
            ("demo.noalt@doedu.test", "confirmed"), ("demo.passenger@doedu.test", "confirmed"),
            ("demo.pay@doedu.test", "confirmed"), ("demo.refund@doedu.test", "confirmed")])

    def test_seed_refuses_outside_debug(self):
        with override_settings(ALLOW_DEMO_TOOLS=False), self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)


class SyncDemoScheduleTests(TestCase):
    def run_sync(self, days=5):
        call_command("sync_demo_schedule", days=days, verbosity=0)

    def test_creates_network_and_timetable_without_accounts(self):
        from apps.accounts.models import User
        from apps.transport.models import Departure, Route
        self.run_sync()
        self.assertEqual(Route.objects.count(), 8)
        self.assertGreater(Departure.objects.count(), 100)
        self.assertEqual(User.objects.count(), 0)               # never creates demo accounts

    def test_is_additive_and_idempotent_and_never_touches_existing_data(self):
        from apps.transport.models import Departure
        self.run_sync(3)
        n = Departure.objects.count()
        dep = Departure.objects.first()
        Departure.objects.filter(pk=dep.pk).update(places_taken=2, status="delayed", delay_minutes=15)
        self.run_sync(3)
        self.assertEqual(Departure.objects.count(), n)           # same range: nothing new
        dep.refresh_from_db()
        self.assertEqual((dep.places_taken, dep.status, dep.delay_minutes), (2, "delayed", 15))   # untouched
        self.run_sync(6)
        self.assertGreater(Departure.objects.count(), n)         # extended further ahead

    def test_works_in_production_demo_mode_but_not_when_simulation_is_off(self):
        with override_settings(ALLOW_DEMO_TOOLS=False, ENVIRONMENT="production"):
            self.run_sync(2)                                    # additive loading is allowed for the hosted demo
        with override_settings(SIMULATION_ENABLED=False), self.assertRaises(CommandError):
            call_command("sync_demo_schedule", verbosity=0)

    def test_demo_accounts_need_an_explicit_password_when_deployed(self):
        import os
        from unittest import mock
        with override_settings(IS_DEPLOYED=True), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEMO_USER_PASSWORD", None)
            with self.assertRaises(RuntimeError):
                demo_data.demo_password()
        with override_settings(IS_DEPLOYED=True), mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": "custom-secret-1"}):
            self.assertEqual(demo_data.demo_password(), "custom-secret-1")

    def test_reset_still_rebuilds_the_same_network(self):
        from apps.transport.models import Departure, Route
        demo_data.reset_transport_data(REF)
        self.assertEqual(Route.objects.count(), 8)
        self.assertEqual(Departure.objects.count(), 7 * sum(len(t) for t in demo_data.TIMETABLE.values()))


class SearchFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        demo_data.reset_transport_data(REF)

    def test_train_only_and_forbidden_taxi_leg(self):
        trains = get(self.client, origin='NG-RAIL', destination='PM-RAIL', modes='train').json()['results']
        self.assertTrue(trains)
        self.assertTrue(all(leg['mode'] == 'train' for it in trains for leg in it['legs']))
        mixed = get(self.client, destination='PM-MARINA', modes='bus,train,taxi').json()['results']
        self.assertTrue(mixed)
        excluded = get(self.client, destination='PM-MARINA', modes='bus,train').json()['results']
        self.assertEqual(excluded, [])

    def test_transfer_limits_and_connection_duration(self):
        from datetime import datetime
        direct = get(self.client, max_transfers='0').json()['results']
        self.assertTrue(direct)
        self.assertTrue(all(it['transfers'] == 0 for it in direct))
        self.assertEqual(get(self.client, destination='PM-MARINA', max_transfers='0').json()['results'], [])
        bounded = get(self.client, destination='PM-MARINA', max_connection_minutes=30).json()['results']
        self.assertTrue(bounded)
        for it in bounded:
            for a, b in zip(it['legs'], it['legs'][1:]):
                self.assertLessEqual(datetime.fromisoformat(b['departs_at']) - datetime.fromisoformat(a['arrives_at']), timedelta(minutes=30))

    def test_invalid_filters_are_rejected(self):
        for query in [{'modes': ''}, {'modes': 'plane'}, {'max_transfers': '-1'}, {'max_transfers': '3'}, {'max_connection_minutes': 'four'}, {'max_connection_minutes': '181'}]:
            response = get(self.client, **query)
            self.assertEqual(response.status_code, 400, query)
            self.assertIn(next(iter(query)), response.json())

    def test_filtering_precedes_result_cap(self):
        from unittest.mock import patch
        from decimal import Decimal
        from apps.transport.models import Departure, Fare, Route, RouteStop, Stop
        rail = Route.objects.filter(mode='train').first()
        origin, destination = Stop.objects.get(code='NG-RAIL'), Stop.objects.get(code='PM-RAIL')
        bus = Route.objects.create(code='FILTERBUS', name='Cheaper bus', mode='bus', operator=rail.operator, policy=rail.policy)
        RouteStop.objects.create(route=bus, stop=origin, sequence=0, arrival_offset_min=0, departure_offset_min=0)
        RouteStop.objects.create(route=bus, stop=destination, sequence=1, arrival_offset_min=60, departure_offset_min=60)
        Fare.objects.create(route=bus, from_stop=origin, to_stop=destination, price=Decimal('0.01'))
        Departure.objects.create(route=bus, departs_at=demo_data._local(DAY, '08:00'), capacity=10)
        with patch('apps.planning.services.MAX_RESULTS', 1):
            unfiltered = get(self.client, origin='NG-RAIL', destination='PM-RAIL', sort='price').json()['results']
            filtered = get(self.client, origin='NG-RAIL', destination='PM-RAIL', modes='train', sort='price').json()['results']
        self.assertEqual(unfiltered[0]['legs'][0]['mode'], 'bus')
        self.assertEqual(len(filtered), 1)
        self.assertTrue(all(leg['mode'] == 'train' for leg in filtered[0]['legs']))
