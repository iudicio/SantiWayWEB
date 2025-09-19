from django.urls import path
from .views import dashboard

app_name = 'interface'

urlpatterns = [
    path('', dashboard, name='dashboard'),
]