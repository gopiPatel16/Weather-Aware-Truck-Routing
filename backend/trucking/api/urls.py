from django.urls import path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import GeocodeView, HealthView, HeatmapView, PlanView

# The contract (docs/PLAN.md section 7) is written without a trailing slash; both forms are accepted
# because Django cannot redirect a POST to the slash form.
urlpatterns = [
    re_path(r"^health/?$", HealthView.as_view(), name="health"),
    re_path(r"^plan/?$", PlanView.as_view(), name="plan"),
    re_path(r"^heatmap/?$", HeatmapView.as_view(), name="heatmap"),
    re_path(r"^geocode/?$", GeocodeView.as_view(), name="geocode"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
