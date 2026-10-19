from django.urls import path

from . import operator_views as v

urlpatterns = [
    path("operator/routes/", v.routes),
    path("operator/services/", v.services),
    path("operator/services/<int:pk>/", v.service_detail),
    path("operator/services/<int:pk>/impact/", v.service_impact),
    path("operator/services/<int:pk>/change/", v.service_change),
    path("operator/fares/<int:pk>/", v.fare_detail),
]
