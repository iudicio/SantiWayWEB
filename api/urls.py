from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from users.views import APIKeyViewSet

from .views import DeviceViewSet

router = DefaultRouter()
router.register(r"devices", DeviceViewSet, basename="devices")
router.register(r"api-key", APIKeyViewSet, basename="api-key")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
    # JSON-схема OpenAPI (генерится на лету)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # ReDoc (альтернативная документация)
    path(
        "schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
]
