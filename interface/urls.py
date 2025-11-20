from django.urls import path
from .views import dashboard, monitoring_results

app_name = 'interface'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('monitoring-results/', monitoring_results, name='monitoring_results'),
]