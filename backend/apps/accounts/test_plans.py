from datetime import timedelta
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
