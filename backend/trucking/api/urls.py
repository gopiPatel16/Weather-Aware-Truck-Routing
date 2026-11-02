from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import GeocodeView, HealthView, HeatmapView, PlanView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("plan/", PlanView.as_view(), name="plan"),
    path("heatmap/", HeatmapView.as_view(), name="heatmap"),
    path("geocode/", GeocodeView.as_view(), name="geocode"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
