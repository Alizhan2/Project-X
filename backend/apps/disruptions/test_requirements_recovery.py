"""SC01/SC02 synthetic acceptance examples: replacement charge and old refund are independent."""
import uuid
from datetime import datetime, timedelta, time
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from apps.bookings.tests import make_user, client_for, checkout, pay
from apps.bookings.models import Booking, BookingLeg
from apps.transport.models import Operator, Stop, CancellationPolicy, Route, RouteStop, Fare, Departure, TaxiOffer, TransferLink
from apps.payments.models import PaymentAttempt, Refund


class RequirementsRecoveryTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate() + timedelta(days=1)
        self.user = make_user()
        self.c = client_for(self.user)
        self.op = Operator.objects.create(code="sc", name="Synthetic SC operator")
        self.policy = CancellationPolicy.objects.create(name="Flexible unused", full_refund_hours_before=0, partial_refund_hours_before=0, partial_refund_percent=100)
        def stop(code, kind="bus"):
            return Stop.objects.create(code=code, name=code, kind=kind, step_free=True)
        self.a, self.hub, self.rail, self.end, self.dest = stop("SC-A"), stop("SC-HUB"), stop("SC-RAIL", "rail"), stop("SC-END", "rail"), stop("SC-DEST", "taxi")
        self.link = TransferLink.objects.create(from_stop=self.hub, to_stop=self.rail, minutes=8, boarding_buffer_minutes=10, step_free=True)
        def service(code, origin, dest, departure, duration, price):
            route = Route.objects.create(operator=self.op, code=code, name=code, mode="train" if origin.kind == "rail" else "bus", policy=self.policy)
            RouteStop.objects.create(route=route, sequence=0, stop=origin, arrival_offset_min=0, departure_offset_min=0)
            RouteStop.objects.create(route=route, sequence=1, stop=dest, arrival_offset_min=duration, departure_offset_min=duration)
            Fare.objects.create(route=route, from_stop=origin, to_stop=dest, price=price, currency="KZT")
            return Departure.objects.create(route=route, departs_at=self.at(departure), capacity=20, wheelchair_accessible=True)
        self.bus = service("B12", self.a, self.hub, "08:00", 30, 400)
        self.train = service("T101", self.rail, self.end, "09:00", 100, 2500)
        def taxi(origin, dest, start, ride):
            return TaxiOffer.objects.create(operator=self.op, from_stop=origin, to_stop=dest, price=1800, currency="KZT", pickup_wait_min=0,
                ride_min=ride, max_passengers=4, service_start=time.fromisoformat(start), service_end=time(23,59), policy=self.policy, wheelchair_accessible=True)
        self.final_taxi = taxi(self.end, self.dest, "10:55", 20)
        self.replacement_taxi = taxi(self.a, self.hub, "08:05", 30)
        # Production demo uses Europe/Berlin; the acceptance examples use full aware timestamps.
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:40")):
            self.ref = checkout(self.c, {"passengers":1, "legs":[
                {"departure_id":self.bus.pk, "from_stop":self.a.code, "to_stop":self.hub.code},
                {"departure_id":self.train.pk, "from_stop":self.rail.code, "to_stop":self.end.code},
                {"taxi_offer_id":self.final_taxi.pk, "from_stop":self.end.code, "to_stop":self.dest.code}],
                "contact_email":"sc@example.com", "travellers":["Demo passenger"]}).json()["reference"]
            result = pay(self.c, self.ref)
            self.assertEqual(result.json()["booking"]["status"], "confirmed", result.content)
        Departure.objects.filter(pk=self.bus.pk).update(delay_minutes=20, status="delayed")

    def at(self, hhmm):
        return timezone.make_aware(datetime.combine(self.day, time.fromisoformat(hhmm)))

    def options(self, **params):
        query = {"origin": self.a.code, "earliest_departure": self.at("07:50").isoformat(),
                 "latest_arrival": self.at("11:30").isoformat(), "max_payment_now":2000, **params}
        return self.c.get(f"/api/bookings/{self.ref}/replacements/", query)

    def accept(self, offer, outcome="success", key=None, reconcile=False):
        return self.c.post(f"/api/bookings/{self.ref}/replacements/{offer['id']}/accept/", {"outcome":outcome,"reconcile":reconcile},
                           content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)

    def test_sc01_full_new_charge_old_leg_refund_and_retained_train_taxi(self):
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            response = self.options()
            self.assertEqual(response.status_code, 200, response.content)
            offer = next(o for o in response.json()["offers"] if len(o["legs"]) == 1 and o["legs"][0]["mode"] == "taxi")
            self.assertEqual((offer["payment_now"],offer["eligible_refund"],offer["net_extra_cost"]),("1800.00","400.00","1400.00"))
            before = list(BookingLeg.objects.filter(booking__reference=self.ref).exclude(departure=self.bus).values("pk","unit_price","departs_at"))
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:54")):
            result = self.accept(offer)
            self.assertEqual(result.status_code, 200, result.content)
            self.assertEqual(result.json()["offer"]["status"], "accepted", result.content)
        replacement_charge = PaymentAttempt.objects.get(purpose="replacement")
        self.assertEqual(replacement_charge.amount, Decimal("1800"))
        self.assertEqual(Refund.objects.get().amount, Decimal("400"))
        self.assertEqual(Refund.objects.get().status, "requested")
        self.assertEqual(list(BookingLeg.objects.filter(pk__in=[x["pk"] for x in before]).values("pk","unit_price","departs_at")),before)
        active = list(Booking.objects.get(reference=self.ref).legs.filter(status="booked"))
        self.assertEqual([leg.departure_id for leg in active],[None,self.train.pk,None])
        self.assertEqual(Booking.objects.get(reference=self.ref).total_amount,Decimal("6100"))

    def test_budget_uses_full_payment_not_eventual_net_extra(self):
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            response = self.options(max_payment_now=1500)
        self.assertEqual(response.json()["state"], "none", response.content)
        self.assertEqual(PaymentAttempt.objects.count(),1)
        self.assertEqual(Refund.objects.count(),0)

    def test_sc02_unknown_path_excluded_when_accessibility_required(self):
        self.link.step_free = None
        self.link.save()
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            response = self.options(wheelchair_required="true")
        self.assertEqual(response.json()["state"],"none",response.content)
        self.assertEqual(BookingLeg.objects.filter(status="booked").count(),3)

    def test_pending_acceptance_keeps_original_then_reconciles_same_charge(self):
        key=uuid.uuid4().hex
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            offer=self.options().json()["offers"][0]
            pending=self.accept(offer,"pending",key)
            self.assertEqual(pending.status_code,200,pending.content)
            self.assertEqual(BookingLeg.objects.filter(status="replaced").count(),0)
            self.assertEqual(self.accept(offer,"success").json()["code"],"payment_pending")
            result=self.accept(offer,"success",key,reconcile=True)
            self.assertEqual(result.json()["offer"]["status"],"accepted",result.content)
        self.assertEqual(PaymentAttempt.objects.filter(purpose="replacement").count(),1)

    def test_late_replacement_success_compensates_full_charge_preserving_original(self):
        key=uuid.uuid4().hex
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            offer=self.options().json()["offers"][0]
            self.accept(offer,"pending",key)
        from apps.disruptions.models import ReplacementOffer
        ReplacementOffer.objects.filter(pk=offer["id"]).update(expires_at=self.at("07:51"))
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:54")):
            result=self.accept(offer,"success",key,reconcile=True)
        self.assertEqual(result.status_code,200,result.content)
        self.assertNotEqual(result.json()["offer"]["status"],"accepted")
        self.assertEqual(BookingLeg.objects.filter(status="booked").count(),3)
        charge=PaymentAttempt.objects.get(purpose="replacement")
        self.assertEqual(Refund.objects.get(reason="commit_failed").amount,charge.amount)
        self.assertEqual(Refund.objects.count(),1)

    def test_unreachable_location_and_invalid_constraints_rejected(self):
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            self.assertEqual(self.options(origin=self.dest.code).json()["code"],"location_unreachable")
            self.assertEqual(self.options(max_payment_now=-1).status_code,400)
            self.assertEqual(self.options(latest_arrival=self.at("07:00").isoformat()).status_code,400)

    def test_refresh_does_not_replace_identical_offers_when_clock_advances(self):
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            first = self.c.get(f"/api/bookings/{self.ref}/replacements/").json()
        self.assertTrue(first["offers"])
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50") + timedelta(seconds=9)):
            second = self.c.get(f"/api/bookings/{self.ref}/replacements/").json()
        self.assertEqual([o["id"] for o in first["offers"]], [o["id"] for o in second["offers"]])
        self.assertEqual(first["constraints"]["earliest_departure"], second["constraints"]["earliest_departure"])
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:54")):
            accepted = self.accept(first["offers"][0])
        self.assertEqual(accepted.json()["offer"]["status"], "accepted", accepted.content)

    def test_background_refresh_preserves_explicit_zero_budget_without_any_offer(self):
        from apps.disruptions.recovery import ensure_offers
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50")):
            initial = self.options(max_payment_now=0, wheelchair_required="true").json()
        self.assertEqual(initial["state"], "none")
        with mock.patch("django.utils.timezone.now", return_value=self.at("07:50") + timedelta(seconds=20)):
            state, generated = ensure_offers(Booking.objects.get(reference=self.ref).pk)
            refreshed = self.c.get(f"/api/bookings/{self.ref}/replacements/").json()
        self.assertEqual((state, generated), ("none", []))
        self.assertEqual(refreshed["constraints"]["max_payment_now"], 0)
        self.assertTrue(refreshed["constraints"]["wheelchair_required"])
        self.assertEqual(refreshed["constraints"]["latest_arrival"], initial["constraints"]["latest_arrival"])
        self.assertEqual(refreshed["constraints"]["earliest_departure"], initial["constraints"]["earliest_departure"])
