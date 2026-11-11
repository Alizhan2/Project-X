from datetime import timedelta
from decimal import Decimal
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import User, JourneyPlan


class JourneyPlanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='planner', password='test-only-plan-password') # pragma: allowlist secret
        self.other = User.objects.create_user(username='other-planner')
        self.client.force_login(self.user)
        self.data = {'origin': 'kz-almaty', 'destination': 'kz-astana', 'date': (timezone.now() + timedelta(days=2)).date().isoformat(),
                     'time': '06:00', 'passengers': 2, 'modes': 'train', 'note': 'Private trip note'}
        self.url = '/api/kazakhstan/plans/'

    def save(self, **changes):
        return self.client.post(self.url, {**self.data, **changes}, content_type='application/json')

    def test_create_read_update_delete_and_owner_is_server_assigned(self):
        response = self.save(user=self.other.pk)
        self.assertEqual(response.status_code, 201)
        pk = response.json()['id']
        self.assertEqual(JourneyPlan.objects.get(pk=pk).user, self.user)
        self.assertEqual(self.client.get(self.url).json()[0]['note'], self.data['note'])
        response = self.client.put(f'{self.url}{pk}/', {**self.data, 'note': 'Updated', 'passengers': 3}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['passengers'], 3)
        self.assertEqual(self.client.delete(f'{self.url}{pk}/').status_code, 204)
        self.assertFalse(JourneyPlan.objects.exists())

    def test_other_account_cannot_read_update_or_delete(self):
        pk = self.save().json()['id']
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).json(), [])
        self.assertEqual(self.client.put(f'{self.url}{pk}/', self.data, content_type='application/json').status_code, 404)
        self.assertEqual(self.client.delete(f'{self.url}{pk}/').status_code, 404)
        self.assertEqual(JourneyPlan.objects.get(pk=pk).note, self.data['note'])

    def test_anonymous_and_csrf_protection(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get(self.url).status_code, 403)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.data, format='json').status_code, 403)

    def test_invalid_values_never_create_plans(self):
        for changes in ({'destination': 'kz-almaty'}, {'origin': 'NG-BUS'}, {'date': '2000-01-01'},
                        {'passengers': 0}, {'passengers': 10}, {'modes': 'taxi'}, {'time': '25:00'}, {'note': 'x' * 1001}):
            with self.subTest(changes=changes):
                self.assertEqual(self.save(**changes).status_code, 400)
        self.assertFalse(JourneyPlan.objects.exists())

    def test_limit_and_old_plans_remain_readable_and_deletable(self):
        JourneyPlan.objects.bulk_create([JourneyPlan(user=self.user, **{**self.data, 'date': '2000-01-01'}) for _ in range(50)])
        self.assertEqual(self.save().status_code, 400)
        self.assertEqual(len(self.client.get(self.url).json()), 50)
        pk = JourneyPlan.objects.first().pk
        self.assertEqual(self.client.delete(f'{self.url}{pk}/').status_code, 204)
        self.assertEqual(self.save().status_code, 201)

    def test_search_preferences_roundtrip_and_can_be_cleared(self):
        response = self.save(time_mode='arrival', wheelchair_required=True, max_price='12345.60')
        self.assertEqual(response.status_code, 201, response.content)
        pk = response.json()['id']
        for payload in (response.json(), self.client.get(self.url).json()[0]):
            self.assertEqual(payload['time_mode'], 'arrival')
            self.assertIs(payload['wheelchair_required'], True)
            self.assertEqual(payload['max_price'], '12345.60')
        saved = JourneyPlan.objects.get(pk=pk)
        self.assertEqual(saved.max_price, Decimal('12345.60'))
        # An old client that sends only the original fields keeps departure-search defaults.
        response = self.client.put(f'{self.url}{pk}/', self.data, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['time_mode'], 'departure')
        self.assertIs(response.json()['wheelchair_required'], False)
        self.assertIsNone(response.json()['max_price'])

    def test_old_format_requests_and_rows_have_safe_preference_defaults(self):
        for payload in (self.save().json(), self.client.get(self.url).json()[0]):
            self.assertEqual(payload['time_mode'], 'departure')
            self.assertIs(payload['wheelchair_required'], False)
            self.assertIsNone(payload['max_price'])

    def test_previous_application_can_create_a_plan_during_a_rolling_update(self):
        old_apps = MigrationLoader(connection).project_state([('accounts', '0005_savedtraveller')]).apps
        old_plan = old_apps.get_model('accounts', 'JourneyPlan').objects.create(user_id=self.user.pk, **self.data)
        saved = JourneyPlan.objects.get(pk=old_plan.pk)
        self.assertEqual(saved.time_mode, 'departure')
        self.assertIs(saved.wheelchair_required, False)
        self.assertIsNone(saved.max_price)
        self.assertEqual(saved.note, self.data['note'])

    def test_invalid_preferences_do_not_create_or_replace_a_plan(self):
        pk = self.save(note='Keep this note').json()['id']
        for changes in ({'time_mode': 'yesterday'}, {'wheelchair_required': 'maybe'},
                        {'max_price': '-0.01'}, {'max_price': 'NaN'}, {'max_price': 'Infinity'},
                        {'max_price': '123.456'}, {'max_price': '10000000000.00'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.save(**changes).status_code, 400)
                response = self.client.put(f'{self.url}{pk}/', {**self.data, **changes}, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(JourneyPlan.objects.get(pk=pk).note, 'Keep this note')
        self.assertEqual(JourneyPlan.objects.count(), 1)

    def test_zero_budget_is_distinct_from_no_budget(self):
        response = self.save(max_price='0.00')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['max_price'], '0.00')

    def test_preference_constraints_protect_non_api_writes(self):
        for invalid in ({'time_mode': 'bad'}, {'max_price': Decimal('-0.01')}):
            with self.subTest(invalid=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                JourneyPlan.objects.create(user=self.user, **self.data, **invalid)
