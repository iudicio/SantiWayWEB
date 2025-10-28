from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, resolve
from django.utils.deprecation import MiddlewareMixin
from urllib.parse import urlencode
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.utils.decorators import sync_and_async_middleware

@sync_and_async_middleware
def redirect_to_login_middleware(get_response):
    """
    Перенаправляет неавторизованных пользователей на страницу логина,
    кроме перечисленных в EXEMPT_URL_NAMES и EXEMPT_PATH_PREFIXES.
    ASGI-compatible middleware.
    """
    # Разрешенные url
    exempt_url_names = getattr(settings, 'AUTH_EXEMPT_URL_NAMES', [
        'users:login',
        'users:registration'
    ])
    exempt_path_prefixes = getattr(settings, 'AUTH_EXEMPT_PATH_PREFIXES', [
        '/static/',
        '/media/',
        '/admin/',
        '/api/',
        '/ws/'  # WebSocket пути
    ])
    
    if iscoroutinefunction(get_response):
        # ASGI
        async def middleware(request):
            # Пропускаем WebSocket запросы и другие exempt пути
            path = request.path
            if any(path.startswith(prefix) for prefix in exempt_path_prefixes):
                return await get_response(request)
            
            # Пропускаем AJAX/JSON запросы
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return await get_response(request)
            
            # Проверяем exempt url names
            try:
                resolved_url = resolve(path)
                if resolved_url and (resolved_url.url_name in exempt_url_names or
                                    f"{resolved_url.app_name}:{resolved_url.url_name}" in exempt_url_names):
                    return await get_response(request)
            except Exception:
                pass
            
            # Проверяем аутентификацию (user уже загружен AuthenticationMiddleware)
            if hasattr(request, 'user') and request.user.is_authenticated:
                return await get_response(request)
            
            # Если ничего не совпало - редирект на логин
            login_path = reverse('users:login')
            qs = urlencode({'next': request.get_full_path()})
            return redirect(f"{login_path}?{qs}")
    else:
        # WSGI (обратная совместимость)
        def middleware(request):
            path = request.path
            if any(path.startswith(prefix) for prefix in exempt_path_prefixes):
                return get_response(request)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return get_response(request)
            
            try:
                resolved_url = resolve(path)
                if resolved_url and (resolved_url.url_name in exempt_url_names or
                                    f"{resolved_url.app_name}:{resolved_url.url_name}" in exempt_url_names):
                    return get_response(request)
            except Exception:
                pass
            
            if hasattr(request, 'user') and request.user.is_authenticated:
                return get_response(request)
            
            login_path = reverse('users:login')
            qs = urlencode({'next': request.get_full_path()})
            return redirect(f"{login_path}?{qs}")
    
    return middleware


# Для обратной совместимости с MiddlewareMixin
class RedirectToLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.middleware = redirect_to_login_middleware(get_response)
    
    def __call__(self, request):
        return self.middleware(request)
    
    async def __acall__(self, request):
        return await self.middleware(request)