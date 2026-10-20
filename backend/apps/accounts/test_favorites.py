from itertools import permutations

from django.core.cache import cache
from django.test import TestCase

from apps.transport.models import Stop
from .models import FavoriteRoute, User
from .tests import csrf_client, fresh


class FavoriteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('saved@example.com', 'saved@example.com', 'test-passphrase-456')
        self.other = User.objects.create_user('other@example.com', 'other@example.com', 'test-passphrase-456')
        self.origin = Stop.objects.create(code='ORIGIN', name='Origin', kind='bus')
        self.destination = Stop.objects.create(code='DEST', name='Destination', kind='rail')
        self.client.force_login(self.user)

    def save(self, **extra):
        return self.client.post('/api/favorites/', {'origin': 'ORIGIN', 'destination': 'DEST', **extra}, content_type='application/json')

    def test_saved_direction_persists_and_duplicates_are_idempotent(self):
        first = self.save()
        self.assertEqual(first.status_code, 201)
        second = self.save()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/favorites/').json(), [first.json()])
        self.assertEqual(self.client.delete(f'/api/favorites/{first.json()["id"]}/').status_code, 204)
        self.assertEqual(self.client.get('/api/favorites/').json(), [])

    def test_owner_cannot_be_overridden_and_other_users_cannot_read_or_delete(self):
        saved = self.save(user=self.other.pk).json()
        self.assertEqual(FavoriteRoute.objects.get(pk=saved['id']).user, self.user)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/favorites/').json(), [])
        self.assertEqual(self.client.delete(f'/api/favorites/{saved["id"]}/').status_code, 404)
        self.assertTrue(FavoriteRoute.objects.filter(pk=saved['id']).exists())

    def test_invalid_stops_same_direction_and_anonymous_access(self):
        self.assertEqual(self.save(destination='MISSING').status_code, 400)
        self.assertEqual(self.save(destination='ORIGIN').status_code, 400)
        self.client.logout()
        self.assertEqual(self.save().status_code, 403)
        self.assertEqual(self.client.get('/api/favorites/').status_code, 403)

    def test_favorites_require_csrf_for_writes(self):
        c, _ = csrf_client()
        c.force_login(self.user)
        data = {'origin': 'ORIGIN', 'destination': 'DEST'}
        self.assertEqual(c.post('/api/favorites/', data).status_code, 403)
        saved = c.post('/api/favorites/', data, **fresh(c))
        self.assertEqual(saved.status_code, 201)
        url = f'/api/favorites/{saved.json()["id"]}/'
        self.assertEqual(c.delete(url).status_code, 403)
        self.assertEqual(c.delete(url, **fresh(c)).status_code, 204)

    def test_fifty_direction_limit_and_existing_save_at_limit(self):
        stops = [self.origin, self.destination] + [Stop.objects.create(code=f'S{i}', name=f'Stop {i}', kind='bus') for i in range(7)]
        pairs = list(permutations(stops, 2))
        FavoriteRoute.objects.bulk_create([FavoriteRoute(user=self.user, origin=a, destination=b) for a, b in pairs[:50]])
        a, b = pairs[50]
        self.assertEqual(self.save(origin=a.code, destination=b.code).status_code, 400)
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(FavoriteRoute.objects.count(), 50)
