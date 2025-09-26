from rest_framework import generics, status
from rest_framework.authentication import get_authorization_header
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, JSONParser
from .models import APKBuild
from api.auth import APIKeyAuthentication
from api.permissions import HasAPIKey
from .serializers import APKBuildCreateSerializer
from celery import Celery
from os import getenv


# Инициализация Celery клиента (аналогично вашему подходу)
BROKER_URL = getenv('CELERY_BROKER_URL', 'amqp://celery:celerypassword@rabbitmq:5672/')
celery_client = Celery('apkbuild_producer', broker=BROKER_URL)


class APKBuildCreateView(generics.CreateAPIView):
    """Создание задачи на сборку APK"""
    queryset = APKBuild.objects.all()
    serializer_class = APKBuildCreateSerializer
    parser_classes = [MultiPartParser, JSONParser]
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]

    def create(self, request, *args, **kwargs):
        api_key_value = get_authorization_header(request)
        key = None
        if api_key_value:
            parts = api_key_value.split()
            if len(parts) == 2 and parts[0].lower() == b"api-key":
                key = parts[1].decode()

        # Отправляем в очередь RabbitMQ
        celery_client.send_task(
            'apkbuild',
            args=[{"key": key}],
            queue='apkbuilder'
        )

        return Response({"status": f"Задача на сборку APK '{key}' принята"}, status=status.HTTP_202_ACCEPTED)