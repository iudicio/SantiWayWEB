from django.conf import settings
from django.shortcuts import render

def dashboard(request):
    api_key_value = ''
    try:
        api_key_obj = request.user.api_keys.first()
        if api_key_obj:
            api_key_value = str(api_key_obj.key)
    except Exception:
        api_key_value = ''

    return render(request, 'interface/dashboard.html', {
        'API_BASE': getattr(settings, 'API_BASE_URL', '/api'),
        'API_KEY': api_key_value,
    })

def monitoring_results(request):
    api_key_value = ''
    try:
        api_key_obj = request.user.api_keys.first()
        if api_key_obj:
            api_key_value = str(api_key_obj.key)
    except Exception:
        api_key_value = ''

    return render(request, 'interface/monitoring_results.html', {
        'API_BASE': getattr(settings, 'API_BASE_URL', '/api'),
        'API_KEY': api_key_value,
    })