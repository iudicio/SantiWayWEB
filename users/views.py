from django.shortcuts import render, redirect
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
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

        # ищем устройство пользователя
        device, created = Device.objects.get_or_create(
            name=device_name,
            defaults={"api_key": APIKey.objects.create()}
        )

        # если устройство существует, но без ключа — создаём ключ
        if not device.api_key:
            device.api_key = APIKey.objects.create()
            device.save()

        serializer = DeviceAPIKeySerializer(device)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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