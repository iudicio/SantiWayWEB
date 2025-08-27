from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import APIKey, Device
from .serializers import DeviceAPIKeySerializer

class DeviceAPIKeyViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

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
