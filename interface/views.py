from django.conf import settings
from django.shortcuts import render

def dashboard(request):
    return render(request, 'interface/dashboard.html', {
        'API_BASE': getattr(settings, 'API_BASE_URL', '/api')
    })