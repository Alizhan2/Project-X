from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, HttpResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.transport.kazakhstan import views as kazakhstan

handler500 = "apps.core.errors.server_error"
handler404 = "apps.core.errors.not_found"


def spa_index(request, *args, **kwargs):
    """Deep links (/booking/DD-...) must load the SPA: serve index.html for every non-API, non-asset path."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse("Frontend is not built (run `npm run build` in frontend/).", status=404, content_type="text/plain")
    response = FileResponse(open(index, "rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"   # index.html references hashed assets: must always be revalidated
    return response


urlpatterns = [
    path("api/kazakhstan/catalog/", kazakhstan.catalog),
    path("api/kazakhstan/search/", kazakhstan.search),
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.planning.urls")),
    path("api/", include("apps.bookings.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.transport.operator_urls")),
]
if settings.ENABLE_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
if settings.IS_DEPLOYED:
    urlpatterns += [re_path(r"^(?!api/|admin/|static/).*$", spa_index)]
