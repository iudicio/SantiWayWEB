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
        device_name = request.data.get("name")
        if not device_name:
            return Response(
                {"error": "Device name required"}, status=status.HTTP_400_BAD_REQUEST
            )

        api_key = APIKey.objects.create()

        device = Device.objects.create(name=device_name, api_key=api_key)

        request.user.api_keys.add(api_key)

        return Response(
            {
                "key_id": device.api_key.id,
                "device_name": device.name,
                "api_key": device.api_key.key,  # отдаём токен пользователю
            },
            status=status.HTTP_201_CREATED,
        )

    # Удаление устройства
    def destroy(self, request, pk=None):
        device = get_object_or_404(Device, pk=pk)
        # проверить, что девайс принадлежит юзеру
        if not request.user.api_keys.filter(id=device.api_key.id).exists():
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        device.api_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Вывод всех API ключей
    def list(self, request):
        api_keys = request.user.api_keys.all()
        data = dict()
        for key in api_keys:
            device = Device.objects.get(api_key__key=key.key)
            data[str(key.key)] = device.name
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
    api_keys = user.api_keys.all()
    devices = Device.objects.filter(api_key__in=api_keys)
    return render(
        request,
        "users/profile_overview.html",
        {
            "user": user,
            "api_keys": api_keys,
            "devices": devices,
        },
    )


# Детали конкретного API ключа
def api_key_detail(request, key_id):
    api_key = get_object_or_404(APIKey, id=key_id)
    devices = api_key.devices.all()
    return render(
        request, "users/api_key_detail.html", {"api_key": api_key, "devices": devices}
    )


# Список всех устройств (можно фильтровать по API ключу)
def devices_list(request):
    api_key_id = request.GET.get("api_key")
    if api_key_id:
        devices = Device.objects.filter(api_key__id=api_key_id)
    else:
        devices = Device.objects.all()
    api_keys = request.user.api_keys.all()
    return render(
        request, "users/devices_list.html", {"devices": devices, "api_keys": api_keys}
    )
