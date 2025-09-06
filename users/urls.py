from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('registration/', views.register_view, name='register'),
    path("profile/", views.profile_overview, name="profile_overview"),
    path("api-key/<int:key_id>/", views.api_key_detail, name="api_key_detail"),
    path("devices/", views.devices_list, name="devices_list"),
]