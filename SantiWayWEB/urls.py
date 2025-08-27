from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import DeviceViewSet
from users.views import APIKeyViewSet

router = DefaultRouter()

router.register(r"devices", DeviceViewSet, basename="devices")
router.register(r"api-keys", APIKeyViewSet, basename="api-keys")

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include(router.urls)),
]
