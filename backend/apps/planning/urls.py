from django.urls import path

from . import views

urlpatterns = [
    path("stops/", views.stops, name="stops"),
    path("search/", views.search, name="search"),
    path("itinerary/", views.itinerary, name="itinerary"),
]
