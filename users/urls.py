from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('registration/', views.register_view, name='register'),
]