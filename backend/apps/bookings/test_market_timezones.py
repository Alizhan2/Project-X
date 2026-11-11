"""Kazakhstan demo timestamps stay UTC+5 without changing historic Berlin journeys."""
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.transport.markets import city_id_for_stop, timezone_for_stops
from apps.transport.models import CancellationPolicy, Departure, Fare, Operator, OperatorMembership, Route, RouteStop, Stop
from .models import Booking
from .tests import checkout, client_for, make_user, pay
from .travel import travel_plan


class MarketTimezoneTests(TestCase):
    def setUp(self):
        self.user = make_user("market@example.test")
        self.client = client_for(self.user)
        self.at = (timezone.now() + timedelta(days=2)).astimezone(ZoneInfo("Asia/Almaty")).replace(
            hour=11, minute=20, second=0, microsecond=0)
        self.operator = Operator.objects.create(code="market", name="Synthetic market operator")
        self.policy = CancellationPolicy.objects.create(name="Market flexible", full_refund_hours_before=0,
            partial_refund_hours_before=0, partial_refund_percent=100)
        self.kz_origin = Stop.objects.create(code="KZ-750000000-B", name="Almaty", kind="bus", step_free=True)
        self.kz_destination = Stop.objects.create(code="KZ-710000000-B", name="Astana", kind="bus", step_free=True)
        self.old_origin = Stop.objects.create(code="MARKET-A", name="Legacy A", kind="bus", step_free=True)
        self.old_destination = Stop.objects.create(code="MARKET-B", name="Legacy B", kind="bus", step_free=True)
        self.kz_departure = self.service("KZ-MARKET", self.kz_origin, self.kz_destination)
        # Currency alone must not change the market of the existing KZT acceptance fixtures.
        self.old_departure = self.service("OLD-MARKET", self.old_origin, self.old_destination)

    def service(self, code, origin, destination):
        route = Route.objects.create(code=code, name=code, operator=self.operator, policy=self.policy, mode="bus")
        for sequence, stop in enumerate((origin, destination)):
            RouteStop.objects.create(route=route, sequence=sequence, stop=stop,
                arrival_offset_min=60 * sequence, departure_offset_min=60 * sequence)
        Fare.objects.create(route=route, from_stop=origin, to_stop=destination, price="1200.00", currency="KZT")
        return Departure.objects.create(route=route, departs_at=self.at, capacity=20, wheelchair_accessible=True)

    def reserve(self, departure, origin, destination):
        response = checkout(self.client, {"passengers": 1,
            "legs": [{"departure_id": departure.pk, "from_stop": origin.code, "to_stop": destination.code}],
            "contact_email": "market@example.test", "travellers": ["Market passenger"]})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_kz_search_booking_activity_and_exports_use_market_offset(self):
        query = {"origin": self.kz_origin.code, "destination": self.kz_destination.code,
                 "depart_after": (self.at - timedelta(minutes=1)).isoformat(), "passengers": 1}
        result = self.client.get("/api/search/", query).json()["results"][0]
        self.assertEqual(result["timezone"], "Asia/Almaty")
        self.assertEqual(result["departs_at"], self.at.isoformat())
        self.assertEqual(result["legs"][0]["departs_at"], self.at.isoformat())
        payload = self.reserve(self.kz_departure, self.kz_origin, self.kz_destination)
        self.assertEqual(payload["origin_city"], "kz-almaty")
        self.assertEqual(payload["destination_city"], "kz-astana")
        self.assertEqual(payload["timezone"], "Asia/Almaty")
        self.assertTrue(all(payload[field].endswith("+05:00") for field in ("created_at", "expires_at")))
        ref = payload["reference"]
        paid = pay(self.client, ref).json()["booking"]
        self.assertTrue(paid["payments"][0]["created_at"].endswith("+05:00"))
        self.assertTrue(all(event["at"].endswith("+05:00") for event in paid["activity"]))
        plan = paid["travel_plan"]
        self.assertEqual((plan["timezone"], plan["origin_city"], plan["destination_city"]),
                         ("Asia/Almaty", "kz-almaty", "kz-astana"))
        self.assertEqual(plan["legs"][0]["departs_at"], self.at.isoformat())
        internal = travel_plan(Booking.objects.get(reference=ref))
        self.assertEqual(internal["legs"][0]["departs_at"].utcoffset(), timedelta(hours=5))
        upcoming = self.client.get("/api/bookings/upcoming/").json()["journey"]
        self.assertTrue(upcoming["generated_at"].endswith("+05:00"))
        self.assertEqual(upcoming["legs"][0]["departs_at"], self.at.isoformat())
        calendar = self.client.get(f"/api/bookings/{ref}/calendar/").content.decode()
        from .exports import stamp
        self.assertIn(f"DTSTART:{stamp(self.at)}", calendar)
        from reportlab.platypus import Paragraph
        with patch("reportlab.platypus.Paragraph", wraps=Paragraph) as paragraphs:
            pdf = self.client.get(f"/api/bookings/{ref}/pdf/")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        rendered = "\n".join(str(call.args[0]) for call in paragraphs.call_args_list)
        self.assertIn("Asia/Almaty", rendered)
        self.assertIn("11:20 +05", rendered)
        self.assertNotIn("Europe/Berlin", rendered)
        cancelled = self.client.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json").json()
        self.assertTrue(cancelled["refunds"][0]["created_at"].endswith("+05:00"))

    def test_legacy_kzt_fare_stays_in_berlin(self):
        payload = self.reserve(self.old_departure, self.old_origin, self.old_destination)
        self.assertEqual(payload["timezone"], "Europe/Berlin")
        self.assertEqual(payload["legs"][0]["departs_at"], self.at.astimezone(ZoneInfo("Europe/Berlin")).isoformat())
        self.assertEqual(payload["currency"], "KZT")
        self.assertIsNone(payload["origin_city"])
        self.assertEqual(timezone_for_stops(self.old_origin), "Europe/Berlin")
        self.assertEqual(city_id_for_stop("KZ-750000000-R"), "kz-almaty")
        self.assertIsNone(city_id_for_stop("NG-BUS"))

    def test_recovery_constraints_and_offers_keep_kazakhstan_offset(self):
        payload = self.reserve(self.kz_departure, self.kz_origin, self.kz_destination)
        ref = payload["reference"]
        self.assertEqual(pay(self.client, ref).status_code, 200)
        Departure.objects.create(route=self.kz_departure.route, departs_at=self.at + timedelta(hours=1),
                                 capacity=20, wheelchair_accessible=True)
        self.kz_departure.status = "cancelled"
        self.kz_departure.save(update_fields=["status"])
        response = self.client.get(f"/api/bookings/{ref}/replacements/", {
            "earliest_departure": (self.at - timedelta(hours=1)).replace(tzinfo=None).isoformat(),
            "latest_arrival": (self.at + timedelta(hours=5)).replace(tzinfo=None).isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertTrue(result["offers"], result)
        self.assertEqual(result["timezone"], "Asia/Almaty")
        self.assertTrue(result["original_arrival"].endswith("+05:00"))
        for field in ("earliest_departure", "latest_arrival", "reachable_after"):
            self.assertTrue(result["constraints"][field].endswith("+05:00"))
        self.assertEqual(result["constraints"]["earliest_departure"], (self.at - timedelta(hours=1)).isoformat())
        for offer in result["offers"]:
            self.assertEqual(offer["timezone"], "Asia/Almaty")
            self.assertTrue(offer["arrives_at"].endswith("+05:00"))
            self.assertTrue(offer["expires_at"].endswith("+05:00"))
            self.assertTrue(offer["legs"][0]["departs_at"].endswith("+05:00"))

    def test_operator_change_notification_uses_kazakhstan_clock(self):
        from apps.disruptions.services import apply_change
        from apps.notifications.models import Notification

        ref = self.reserve(self.kz_departure, self.kz_origin, self.kz_destination)["reference"]
        self.assertEqual(pay(self.client, ref).status_code, 200)
        apply_change(actor=self.user, departure_id=self.kz_departure.pk, action="delay", minutes=15)
        notice = Notification.objects.get(user=self.user, kind="journey_delayed")
        self.assertIn(self.at.strftime("%d.%m %H:%M"), notice.body)
        row = next(item for item in self.client.get("/api/notifications/").json()["results"] if item["id"] == notice.pk)
        self.assertEqual(row["timezone"], "Asia/Almaty")
        self.assertTrue(row["created_at"].endswith("+05:00"))

    def test_operator_times_and_naive_service_input_follow_selected_route(self):
        operator = make_user("operator-market@example.test")
        operator.role = "operator"
        operator.save(update_fields=["role"])
        OperatorMembership.objects.create(user=operator, operator=self.operator)
        client = client_for(operator)
        routes = client.get("/api/operator/routes/").json()["results"]
        self.assertEqual({r["code"]: r["timezone"] for r in routes},
                         {"KZ-MARKET": "Asia/Almaty", "OLD-MARKET": "Europe/Berlin"})
        services = client.get("/api/operator/services/").json()["results"]
        kz = next(service for service in services if service["route_code"] == "KZ-MARKET")
        self.assertEqual(kz["departs_at"], self.at.isoformat())
        self.assertTrue(kz["ends_at"].endswith("+05:00"))
        when = (self.at + timedelta(hours=2)).replace(tzinfo=None).isoformat()
        created = client.post("/api/operator/services/", {"route_id": self.kz_departure.route_id,
                              "departs_at": when, "capacity": 10}, content_type="application/json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["departs_at"], (self.at + timedelta(hours=2)).isoformat())
        changed = client.patch(f"/api/operator/services/{created.json()['id']}/", {
            "departs_at": (self.at + timedelta(hours=3)).replace(tzinfo=None).isoformat()}, content_type="application/json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["departs_at"], (self.at + timedelta(hours=3)).isoformat())
        change = client.post(f"/api/operator/services/{self.kz_departure.pk}/change/", {
            "action": "delay", "minutes": 15}, content_type="application/json")
        self.assertEqual(change.status_code, 200, change.content)
        details = client.get(f"/api/operator/services/{self.kz_departure.pk}/").json()
        self.assertTrue(details["events"][0]["created_at"].endswith("+05:00"))

    def test_followed_kazakhstan_line_notice_uses_local_departure(self):
        from apps.notifications.follows import notify_followers
        from apps.notifications.models import LineFollow, Notification

        LineFollow.objects.create(user=self.user, route=self.kz_departure.route)
        self.assertEqual(notify_followers(self.kz_departure, "delay", 15, 12345,
                         now=self.at - timedelta(hours=1)), 1)
        notice = Notification.objects.get(user=self.user, kind="line_delay")
        self.assertIn(self.at.strftime("%a %d %b %H:%M"), notice.body)
