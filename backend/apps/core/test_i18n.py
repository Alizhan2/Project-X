import threading
from concurrent.futures import ThreadPoolExecutor
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase
from .i18n import LanguageMiddleware, language, negotiate, tr


class LocalizationTests(SimpleTestCase):
    def test_negotiation_uses_quality_regional_variants_and_safe_fallback(self):
        for header, expected in [('ru-RU,kk;q=0.8', 'ru'), ('fr,kk-KZ;q=0.9,en;q=0.5', 'kk'),
                                 ('ru;q=0,en;q=0.5', 'en'), ('de-DE', 'en'), ('', 'en'), ('../../etc/passwd', 'en')]:
            self.assertEqual(negotiate(header), expected)

    def test_concurrent_requests_do_not_leak_language_or_change_contract(self):
        barrier = threading.Barrier(2)
        def view(request):
            barrier.wait(timeout=5)
            return JsonResponse({'code': 'cancelled', 'status': 'cancelled', 'mode': 'train',
                                 'name': 'Search', 'detail': tr('Search')})
        middleware = LanguageMiddleware(view)
        def invoke(lang):
            response = middleware(RequestFactory().get('/api/test/', HTTP_ACCEPT_LANGUAGE=lang))
            import json
            return json.loads(response.content), response['Content-Language'], response['Vary'], language()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, ['ru', 'kk']))
        for (data, selected, vary, after), expected in zip(results, ['Поиск', 'Іздеу']):
            self.assertEqual(data['detail'], expected)
            self.assertEqual(data['code'], 'cancelled')
            self.assertEqual(data['status'], 'cancelled')
            self.assertEqual(data['mode'], 'train')
            self.assertEqual(data['name'], 'Search')
            self.assertIn(selected, ('ru', 'kk'))
            self.assertIn('Accept-Language', vary)
            self.assertEqual(after, 'en')

    def test_composed_notifications_and_pdf_text(self):
        for lang, fragment in [('ru', 'Оператор отменил'), ('kk', 'Оператор')]:
            value = tr('Your service VC1 was cancelled by the operator. Open the booking to review replacement options or cancel for a full refund.', lang=lang)
            self.assertIn(fragment, value)
            self.assertNotIn('Open the booking', value)
            self.assertIn('VC1', value)
            self.assertNotIn('Updated', tr('Updated 21.10.2026, 12:00 CEST. All times use Europe/Berlin.', lang=lang))
