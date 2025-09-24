from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apkbuilder.views import APKBuildCreateView, APKBuildStatusView, APKBuildDownloadView
from .views import DeviceViewSet
from users.views import APIKeyViewSet
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

router = DefaultRouter()
router.register(r"devices", DeviceViewSet, basename="devices")
router.register(r"api-key", APIKeyViewSet, basename="api-key")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
    # JSON-схема OpenAPI (генерится на лету)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc (альтернативная документация)
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Создание сборки APK
    path('apk/build/', APKBuildCreateView.as_view(), name='apk-build-create'),
    # Проверка статуса сборки
    path('apk/build/<uuid:build_id>/status/', APKBuildStatusView.as_view(), name='apk-build-status'),
    # Скачивание готового APK
    path('apk/build/<uuid:build_id>/download/', APKBuildDownloadView.as_view(), name='apk-build-download'),
]