from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

app_name = 'users'

urlpatterns = [
    path('registration/', views.register_view, name='registration'),
    path('login/', views.login_view, name='login'),
    path('logout/', LogoutView.as_view(next_page='users:login'), name='logout'),
    path("profile/", views.profile_overview, name="profile_overview"),
    path("api-key/<int:key_id>/", views.api_key_detail, name="api_key_detail"),
    path("devices/", views.api_keys_list, name="devices_list"),
]