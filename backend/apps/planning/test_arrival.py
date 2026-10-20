from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.bookings.tests import make_user, client_for, checkout, body
from apps.bookings.models import Booking
from apps.transport import demo_data
from apps.transport.models import Departure
from .tests import REF, DAY, NEXT, at, get


class ArrivalSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        demo_data.reset_transport_data(REF)

    def search(self, deadline=None, **kwargs):
        return get(self.client, depart_after=None, arrive_by=deadline or at("13:10"), **kwargs)

    def test_deadline_inclusive_latest_departure_first_and_24_hour_window(self):
        response = self.search(max_transfers="0")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(results)
        self.assertEqual(results[0]["departs_at"][:16], at("12:30"))
        deadline = demo_data._local(DAY, "13:10")
        self.assertTrue(all(datetime.fromisoformat(r["arrives_at"]) <= deadline for r in results))
        self.assertTrue(all(datetime.fromisoformat(r["departs_at"]) >= deadline - timedelta(hours=24) for r in results))
        self.assertEqual(results[0]["arrives_at"][:16], at("13:10"))
        earlier = self.search(at("13:09"), max_transfers="0").json()["results"]
        self.assertNotIn(at("12:30"), [r["departs_at"][:16] for r in earlier])

    def test_previous_day_departure_and_midnight_arrival(self):
        results = self.search(at("00:40", NEXT), max_transfers="0").json()["results"]
        self.assertEqual(results[0]["legs"][0]["route_code"], "GL3")
        self.assertEqual(results[0]["departs_at"][:16], at("23:30"))
        self.assertEqual(results[0]["arrives_at"][:16], at("00:40", NEXT))

    def test_delayed_cancelled_and_full_services(self):
        results = self.search(at("10:55"), max_transfers="0").json()["results"]
        self.assertFalse(any(r["legs"][0]["route_code"] == "VC1" and r["departs_at"][:16] == at("10:00") for r in results))
        delayed = next(r for r in results if r["legs"][0]["delay_minutes"] == 45)
        self.assertEqual(delayed["arrives_at"][:16], at("09:40"))
        results = self.search(at("08:10"), max_transfers="0", passengers=2).json()["results"]
        self.assertFalse(any(r["departs_at"][:16] == at("07:30") for r in results))

    def test_direct_taxi_is_scheduled_near_deadline_and_respects_closing(self):
        params = {"origin": "PM-RAIL", "destination": "PM-MARINA", "modes": "taxi"}
        result = self.search(at("13:00"), **params).json()["results"][0]
        self.assertEqual(result["departs_at"][:16], at("12:48"))
        self.assertEqual(result["arrives_at"][:16], at("13:00"))
        result = self.search(at("04:00", NEXT), **params).json()["results"][0]
        self.assertEqual(result["departs_at"][:16], at("23:59"))
        self.assertEqual(result["arrives_at"][:16], at("00:11", NEXT))
        self.assertEqual(self.search(at("13:00"), passengers=5, **params).json()["results"], [])

    def test_multimodal_results_replay_identically_at_checkout_including_taxi_first(self):
        for origin, destination in [("NG-BUS", "PM-MARINA"), ("LK-BUS", "PM-RAIL")]:
            results = self.search(at("19:00"), origin=origin, destination=destination).json()["results"]
            self.assertTrue(results)
            if origin == "LK-BUS":
                self.assertTrue(any(r["legs"][0]["mode"] == "taxi" for r in results))
            else:
                self.assertTrue(any([l["mode"] for l in r["legs"]] == ["bus", "train", "taxi"] for r in results))
            for result in results:
                fresh = self.client.get("/api/itinerary/", {"legs": result["legs_param"], "arrive_by": at("19:00")})
                self.assertEqual(fresh.status_code, 200, fresh.content)
                self.assertEqual(fresh.json()["departs_at"], result["departs_at"])
                self.assertEqual(fresh.json()["arrives_at"], result["arrives_at"])
                self.assertEqual(fresh.json()["total_price"], result["total_price"])

    def test_filters_and_alternate_sort_apply_before_limit(self):
        results = self.search(at("19:00"), origin="NG-RAIL", destination="PM-RAIL", modes="train", max_transfers="0", sort="price").json()["results"]
        self.assertTrue(results)
        self.assertTrue(all(r["transfers"] == 0 and all(l["mode"] == "train" for l in r["legs"]) for r in results))
        with patch("apps.planning.services.MAX_RESULTS", 1):
            latest = self.search(max_transfers="0").json()["results"]
        self.assertEqual(latest[0]["departs_at"][:16], at("12:30"))
        connected = self.search(at("19:00"), destination="PM-MARINA", max_connection_minutes="30").json()["results"]
        self.assertTrue(connected)
        for result in connected:
            for a, b in zip(result["legs"], result["legs"][1:]):
                self.assertLessEqual(datetime.fromisoformat(b["departs_at"]) - datetime.fromisoformat(a["arrives_at"]), timedelta(minutes=30))

    def test_validation_and_past_deadline(self):
        for deadline in ("", "not-a-date", (timezone.now() - timedelta(minutes=1)).isoformat()):
            self.assertEqual(get(self.client, depart_after=None, arrive_by=deadline).status_code, 400)
        response = get(self.client, arrive_by=at("13:10"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("arrive_by", response.json())
        self.assertEqual(self.search(max_transfers="3").status_code, 400)

    def test_nonexistent_local_clock_time_is_rejected(self):
        from datetime import timezone as utc
        with patch("django.utils.timezone.now", return_value=datetime(2027, 3, 27, tzinfo=utc.utc)):
            response = self.search("2027-03-28T02:30")
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not exist", str(response.json()))

    def test_repeated_local_time_requires_explicit_offset(self):
        from datetime import timezone as utc
        with patch("django.utils.timezone.now", return_value=datetime(2027, 10, 30, tzinfo=utc.utc)):
            self.assertEqual(self.search("2027-10-31T02:30").status_code, 400)
            self.assertEqual(self.search("2027-10-31T02:30+01:00").status_code, 200)

    def test_explicit_offset_is_same_instant_as_local_deadline(self):
        local = self.search(max_transfers="0").json()["results"]
        from datetime import timezone as utc
        explicit = demo_data._local(DAY, "13:10").astimezone(utc.utc).isoformat()
        self.assertEqual(local, self.search(explicit, max_transfers="0").json()["results"])

    def test_no_departures_in_the_past(self):
        now = demo_data._local(DAY, "12:40")
        with patch("django.utils.timezone.now", return_value=now):
            results = self.search(at("15:00")).json()["results"]
        self.assertTrue(all(datetime.fromisoformat(r["departs_at"]) > now for r in results))

    def test_details_and_checkout_reject_new_delay_without_holding_seats(self):
        departure = Departure.objects.get(route__code="VC1", departs_at=demo_data._local(DAY, "12:00"))
        self.client = client_for(make_user())
        params = {"legs": f"d{departure.pk}:NG-BUS:RV-BUS", "arrive_by": at("13:00")}
        self.assertEqual(self.client.get("/api/itinerary/", params).status_code, 200)
        departure.delay_minutes = 30
        departure.status = "delayed"
        departure.save()
        self.assertEqual(self.client.get("/api/itinerary/", params).status_code, 409)
        result = checkout(self.client, {**body(departure), "arrive_by": at("13:00")})
        self.assertEqual((result.status_code, result.json()["code"]), (409, "arrival_deadline_missed"))
        self.assertFalse(Booking.objects.exists())
        departure.refresh_from_db()
        self.assertEqual(departure.places_taken, 0)

    def test_deadline_checkout_succeeds_and_keeps_idempotency(self):
        departure = Departure.objects.get(route__code="VC1", departs_at=demo_data._local(DAY, "12:00"))
        self.client = client_for(make_user())
        payload = {**body(departure), "arrive_by": at("12:55")}
        first = checkout(self.client, payload, key="arrival-checkout-test")
        again = checkout(self.client, payload, key="arrival-checkout-test")
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["reference"], again.json()["reference"])
