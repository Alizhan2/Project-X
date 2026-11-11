from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone


class KazakhstanDemoAPITests(TestCase):
    def test_search_is_bookable_simulation_without_contacting_supplier(self):
        day = (timezone.now().astimezone(ZoneInfo("Asia/Almaty")) + timedelta(days=2)).date()
        catalog = self.client.get("/api/kazakhstan/catalog/").json()
        self.assertTrue(catalog["simulated"])
        self.assertTrue(catalog["booking_enabled"])
        self.assertEqual(catalog["provider"]["code"], "kazakhstan_demo")
        self.assertEqual(catalog["geography"]["city_count"], 90)
        with patch("apps.transport.kazakhstan.views.get_provider") as real_supplier:
            response = self.client.get("/api/kazakhstan/search/", {
                "origin": "kz-temirtau", "destination": "kz-zharkent",
                "date": day.isoformat(), "time": "06:00", "passengers": 2, "modes": "train", "sort": "price",
            })
        real_supplier.assert_not_called()
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["results"])
        self.assertTrue(payload["simulated"])
        for result in payload["results"]:
            self.assertEqual((result["currency"], result["timezone"], result["passengers"]), ("KZT", "Asia/Almaty", 2))
            self.assertTrue(result["departs_at"].endswith("+05:00"))
            self.assertEqual(result["legs"][0]["mode"], "train")
            self.assertTrue(result["legs_param"].startswith("d"))
            self.assertIn("departure_id", result["selection"][0])
