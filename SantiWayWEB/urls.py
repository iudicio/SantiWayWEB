from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import DeviceViewSet
from users.views import APIKeyViewSet

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

router = DefaultRouter()

router.register(r"devices", DeviceViewSet, basename="devices")
router.register(r"devices/api-key", APIKeyViewSet, basename="api-keys")

urlpatterns = [
    path('admin/', admin.site.urls),
    # JSON-схема OpenAPI (генерится на лету)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc (альтернативная документация)
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/", include(router.urls)),
    path('users/', include('users.urls')),
]
