from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from rest_framework import status, viewsets
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .forms import LoginForm, RegistrationForm
from .models import APIKey, Device, User
from .serializers import DeviceAPIKeySerializer


class APIKeyViewSet(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def create(self, request):
        key_name = request.data.get("name")
        if not key_name:
            return Response(
                {"error": "API key name required"}, status=status.HTTP_400_BAD_REQUEST
            )

        api_key = APIKey.objects.create(name=key_name)
        request.user.api_keys.add(api_key)

        return Response(
            {
                "key_id": api_key.id,
                "api_key": str(api_key.key),
                "name": api_key.name,
                "created_at": api_key.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

    # Удаление ключа
    def destroy(self, request, pk=None):
        api_key = get_object_or_404(APIKey, pk=pk)
        if not request.user.api_keys.filter(id=api_key.id).exists():
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

        api_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Вывод всех API ключей
    def list(self, request):
        api_keys = request.user.api_keys.all().only("id", "key", "name")
        data = {str(k.key): k.name for k in api_keys}
        return Response(data, status=status.HTTP_200_OK)


def register_view(request):
    """
    Обработчик страницы регистрации
    """
    if request.user.is_authenticated:
        return redirect("users:profile_overview")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Проверяем что пользователь действительно сохранился в БД
            user_in_db = User.objects.filter(username=user.username).first()
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                return redirect(next_url)
            # Переход на другую следующую страницу при успешной регистрации
            return redirect("users:profile_overview")
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = RegistrationForm()

    return render(request, "users/registration.html", {"form": form})


def login_view(request):
    # Обработчик страницы входа
    if request.user.is_authenticated:
        return redirect("users:profile_overview")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                return redirect(next_url)
            return redirect("users:profile_overview")
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = LoginForm()
    return render(request, "users/login.html", {"form": form})


# Профиль пользователя — обзор
def profile_overview(request):
    user = request.user
    api_keys = user.api_keys.all().only("id", "key", "name", "created_at")
    return render(
        request,
        "users/profile_overview.html",
        {
            "user": user,
            "api_keys": api_keys,
        },
    )


# Детали конкретного API ключа
def api_key_detail(request, key_id):
    api_key = get_object_or_404(APIKey, id=key_id)
    # Если устройства больше не используются, можно не передавать:
    return render(request, "users/api_key_detail.html", {"api_key": api_key})


# Список всех устройств (можно фильтровать по API ключу)
def api_keys_list(request):
    api_keys = request.user.api_keys.all().only("id", "key", "name", "created_at")
    return render(request, "users/devices_list.html", {"api_keys": api_keys})
