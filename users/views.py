from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import APIKey, Device, User
from .serializers import DeviceAPIKeySerializer
from .forms import RegistrationForm
from django.contrib.auth import login
from django.contrib import messages
    
class APIKeyViewSet(viewsets.ViewSet):
    def create(self, request):
        device_name = request.data.get("name")
        if not device_name:
            return Response({"error": "Device name required"}, status=status.HTTP_400_BAD_REQUEST)

        device = create_device_with_token(request.user, device_name)

        return Response({
            "device_name": device.name,
            "api_key": device.api_key.key  # отдаём токен пользователю
        }, status=status.HTTP_201_CREATED)

def create_device_with_token(user, device_name):
    # Создаём или получаем устройство
    device, created = Device.objects.get_or_create(
        name=device_name,
        defaults={"user": user}  # привязываем к пользователю
    )

    # Если у устройства нет токена — создаём
    if not device.api_key:
        device.api_key = APIKey.objects.create()
        device.save()

    return device

def register_view(request):
    """
    Обработчик страницы регистрации
    """
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Проверяем что пользователь действительно сохранился в БД
            user_in_db = User.objects.filter(username=user.username).first()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно! Добро пожаловать!')
            # Переход на другую следующую страницу при успешной регистрации
            # return redirect('home')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = RegistrationForm()

    return render(request, 'users/registration.html', {'form': form})


# Профиль пользователя — обзор
def profile_overview(request):
    user = request.user
    api_keys = user.api_keys.all()
    return render(request, "users/profile_overview.html", {"user": user, "api_keys": api_keys})

# Детали конкретного API ключа
def api_key_detail(request, key_id):
    api_key = get_object_or_404(APIKey, id=key_id)
    devices = api_key.devices.all()
    return render(request, "users/api_key_detail.html", {"api_key": api_key, "devices": devices})

# Список всех устройств (можно фильтровать по API ключу)
def devices_list(request):
    api_key_id = request.GET.get("api_key")
    if api_key_id:
        devices = Device.objects.filter(api_key__id=api_key_id)
    else:
        devices = Device.objects.all()
    api_keys = request.user.api_keys.all()
    return render(request, "users/devices_list.html", {"devices": devices, "api_keys": api_keys})