from django.urls import include, path

urlpatterns = [
    path("api/", include("trucking.api.urls")),
]
