from django.urls import path
from . import DeviceViewSet
from users.views import APIKeyViewSet
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

app_name = "api"

urlpatterns = [
    path("devices", DeviceViewSet, name="devices"),
    path("api-key", APIKeyViewSet, name="api-keys"),
    # JSON-схема OpenAPI (генерится на лету)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc (альтернативная документация)
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc")
]