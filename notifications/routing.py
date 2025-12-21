from django.urls import path
from .consumers import NotificationConsumer, MLNotificationConsumer


websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
    path("ws/ml-notifications/", MLNotificationConsumer.as_asgi()),
]