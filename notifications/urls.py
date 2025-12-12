from django.urls import path
from . import views

urlpatterns = [
    path('github/', views.github_webhook, name='github_webhook'),
    path('api/send/', views.send_ml_notification, name='ml_notification'),
]