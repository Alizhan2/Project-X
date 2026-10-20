from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase

from .exports import calendar_bytes
from .models import Booking
from .tests import BookingTestBase, body, checkout, pay, make_user, client_for, dep_at
from .travel import travel_plan, upcoming_plan


class TravelTests(BookingTestBase, TestCase):
    def confirmed(self, dep=None):
        ref = checkout(self.c, body(dep or self.dep)).json()["reference"]
        self.assertEqual(pay(self.c, ref).status_code, 200)
        return Booking.objects.get(reference=ref)

    def test_upcoming_is_owner_scoped_and_ignores_unpaid_cancelled_and_finished(self):
        booking = self.confirmed()
        checkout(self.c, body(dep_at("VC1", "08:00")))
        other = client_for(make_user("other@example.com"))
        self.assertIsNone(other.get("/api/bookings/upcoming/").json()["journey"])
        self.assertEqual(self.c.get("/api/bookings/upcoming/").json()["journey"]["reference"], booking.reference)
        end = booking.legs.get().arrives_at
        with patch("apps.bookings.travel.timezone.now", return_value=end + timedelta(seconds=1)):
            self.assertIsNone(upcoming_plan(self.user))
        booking.status = "cancelled"
        booking.save()
        self.assertIsNone(upcoming_plan(self.user))

    def test_upcoming_orders_by_departure_not_purchase_date(self):
        early = self.confirmed(dep_at("VC1", "08:00"))
        self.confirmed()
        self.assertEqual(upcoming_plan(self.user)["reference"], early.reference)

    def test_current_times_preserve_purchase_and_include_delayed_in_progress(self):
        booking = self.confirmed()
        original = booking.legs.get().departs_at
        self.dep.delay_minutes = 120
        self.dep.status = "delayed"
        self.dep.save()
        current = travel_plan(booking)
        self.assertEqual(current["legs"][0]["departs_at"], original + timedelta(hours=2))
        self.assertEqual(booking.legs.get().departs_at, original)
        payload = self.c.get(f"/api/bookings/{booking.reference}/").json()["travel_plan"]
        from django.utils import timezone
        self.assertEqual(payload["legs"][0]["departs_at"], timezone.localtime(original + timedelta(hours=2)).isoformat())
        with patch("apps.bookings.travel.timezone.now", return_value=original + timedelta(hours=2, minutes=10)):
            self.assertEqual(upcoming_plan(self.user)["progress"], "in_progress")
        ics = self.c.get(f"/api/bookings/{booking.reference}/calendar/").content
        from .exports import stamp
        self.assertIn(f"DTSTART:{stamp(original + timedelta(hours=2))}".encode(), ics)

    def test_exports_require_owner_and_confirmed_booking(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        other = client_for(make_user("other@example.com"))
        for extension in ("pdf", "calendar"):
            url = f"/api/bookings/{ref}/{extension}/"
            self.assertIn(Client().get(url).status_code, (401, 403))
            self.assertEqual(other.get(url).status_code, 404)
            self.assertEqual(self.c.get(url).status_code, 409)
        self.assertIn(Client().get("/api/bookings/upcoming/").status_code, (401, 403))
        pay(self.c, ref)
        for status in ("expired", "cancelled"):
            Booking.objects.filter(reference=ref).update(status=status)
            for extension in ("pdf", "calendar"):
                self.assertEqual(self.c.get(f"/api/bookings/{ref}/{extension}/").status_code, 409)

    def test_download_headers_valid_pdf_and_calendar_no_personal_data(self):
        booking = self.confirmed()
        for extension, mime in (("pdf", "application/pdf"), ("calendar", "text/calendar")):
            result = self.c.get(f"/api/bookings/{booking.reference}/{extension}/")
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result["Content-Type"].startswith(mime))
            self.assertEqual(result["Cache-Control"], "private, no-store")
            self.assertIn("attachment;", result["Content-Disposition"])
            self.assertNotIn(booking.contact_email.encode(), result.content)
            if extension == "pdf":
                self.assertTrue(result.content.startswith(b"%PDF-"))
            else:
                self.assertIn(b"BEGIN:VEVENT\r\n", result.content)
                self.assertIn(b"CLASS:PRIVATE", result.content)
                self.assertTrue(all(len(line) <= 75 for line in result.content.split(b"\r\n")))

    def test_disrupted_journey_remains_visible_pdf_warns_calendar_blocked(self):
        booking = self.confirmed()
        self.dep.status = "cancelled"
        self.dep.save()
        plan = upcoming_plan(self.user)
        self.assertEqual(plan["progress"], "needs_attention")
        self.assertEqual(plan["legs"][0]["state"], "unavailable")
        self.assertEqual(self.c.get(f"/api/bookings/{booking.reference}/calendar/").status_code, 409)
        self.assertEqual(self.c.get(f"/api/bookings/{booking.reference}/pdf/").status_code, 200)

    def test_replaced_legs_are_excluded_from_exports(self):
        booking = self.confirmed()
        leg = booking.legs.get()
        leg.pk = None
        leg.sequence = 1
        leg.status = "replaced"
        leg.save()
        plan = travel_plan(booking)
        self.assertEqual(len(plan["legs"]), 1)
        self.assertEqual(calendar_bytes(plan).count(b"BEGIN:VEVENT"), 1)

    def test_calendar_folds_utf8_and_escapes_injection_with_stable_uid(self):
        plan = travel_plan(self.confirmed())
        plan["legs"][0]["from"] = "Станция " * 30 + ",;\\\r\nBEGIN:VEVENT"
        content = calendar_bytes(plan)
        self.assertTrue(all(len(line) <= 75 for line in content.split(b"\r\n")))
        self.assertEqual(content.count(b"\r\nBEGIN:VEVENT\r\n"), 1)
        unfolded = content.decode().replace("\r\n ", "")
        self.assertIn("\\,\\;\\\\\\nBEGIN:VEVENT", unfolded)
        uid = next(line for line in content.split(b"\r\n") if line.startswith(b"UID:"))
        plan["generated_at"] += timedelta(minutes=5)
        self.assertIn(uid, calendar_bytes(plan))

    def test_download_languages_preserve_event_identity_times_and_snapshot(self):
        booking = self.confirmed()
        snapshot = list(booking.legs.values())
        originals = None
        for lang, word in [('en', 'Simulated journey'), ('ru', 'Симулированная поездка'), ('kk', 'Үлгі сапар')]:
            response = self.c.get(f'/api/bookings/{booking.reference}/calendar/', HTTP_ACCEPT_LANGUAGE=lang)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Language'], lang)
            self.assertTrue(all(len(line) <= 75 for line in response.content.split(b'\r\n')))
            unfolded = response.content.decode().replace('\r\n ', '')
            self.assertIn(word, unfolded)
            identity = [line for line in unfolded.splitlines() if line.startswith(('UID:', 'DTSTART:', 'DTEND:'))]
            if originals is None:
                originals = identity
            self.assertEqual(identity, originals)
            pdf = self.c.get(f'/api/bookings/{booking.reference}/pdf/', HTTP_ACCEPT_LANGUAGE=lang)
            self.assertEqual(pdf['Content-Language'], lang)
            self.assertTrue(pdf.content.startswith(b'%PDF-'))
        self.assertEqual(list(booking.legs.values()), snapshot)
