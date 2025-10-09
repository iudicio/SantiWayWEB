from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin


class RedirectToLoginMiddleware(MiddlewareMixin):
    """
    Перенаправляет неавторизованных пользователей на страницу логина,
    кроме перечисленных в EXEMPT_URL_NAMES и EXEMPT_PATH_PREFIXES.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        # Разрешенные url
        self.exempt_url_names = getattr(
            settings, "AUTH_EXEMPT_URL_NAMES", ["users:login", "users:registration"]
        )
        self.exempt_path_prefixes = getattr(
            settings,
            "AUTH_EXEMPT_PATH_PREFIXES",
            ["/static/", "/media/", "/admin/", "/api/"],
        )

    def __call__(self, request):
        # Если пользователь зарегистрирован
        if request.user.is_authenticated:
            return self.get_response(request)

        # Если разрешенный префикс
        path = request.path
        if any(path.startswith(prefix) for prefix in self.exempt_path_prefixes):
            return self.get_response(request)

        if (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or request.content_type == "application/json"
        ):
            return self.get_response(request)

        try:
            resolved_url = resolve(path)
        except Exception:
            resolved_url = None
        # Проверка на разрешенные для всех ссылки
        if resolved_url and (
            resolved_url.url_name in self.exempt_url_names
            or f"{resolved_url.app_name}:{resolved_url.url_name}"
            in self.exempt_url_names
        ):
            return self.get_response(request)

        # Если ничего не совпало (доступ к странице требует авторизации)
        login_path = reverse("users:login")
        qs = urlencode({"next": request.get_full_path()})
        return redirect(f"{login_path}?{qs}")
