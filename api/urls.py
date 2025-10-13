
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apkbuilder.views import APKBuildCreateView
from .views import DeviceViewSet, WayAPIView
from users.views import APIKeyViewSet

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from polygons.views import PolygonViewSet


router = DefaultRouter()
router.register(r"devices", DeviceViewSet, basename="devices")
router.register(r"api-key", APIKeyViewSet, basename="api-key")
router.register(r"polygons", PolygonViewSet, basename="polygons")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
    path("userinfo/", WayAPIView.as_view(), name="userinfo"),
    # JSON-схема OpenAPI (генерится на лету)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # ReDoc (альтернативная документация)

    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Создание сборки APK
    path('apk/build/', APKBuildCreateView.as_view(), name='apk-build-create'),
]

