from django.urls import path
from .consumers import NotificationConsumer


websocket_urlpatterns = [
    path("ws/notify/", NotificationConsumer.as_asgi()),
]