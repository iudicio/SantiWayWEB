from celery.utils.log import get_task_logger
from rest_framework import generics, status
from rest_framework.authentication import get_authorization_header
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, JSONParser

from users.models import User, APIKey
from users.urls import app_name
from .models import APKBuild
from api.auth import APIKeyAuthentication
from api.permissions import HasAPIKey
from .serializers import APKBuildCreateSerializer
from celery import Celery
from os import getenv


log = get_task_logger(__name__)


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

        # Получаем пользователя и APIKey объект по ключу
        try:
            api_key_obj = APIKey.objects.get(key=key)
            user = User.objects.filter(api_keys=api_key_obj).first()
        except APIKey.DoesNotExist:
            return Response({"error": "Invalid API key"}, status=status.HTTP_401_UNAUTHORIZED)

        # Создаем запись в базе данных
        apk_build = APKBuild.objects.create(
            user=user,
            api_key=api_key_obj,
        )

        apk_build_id = str(apk_build.id)

        print(f"Создана запись APKBuild с ID: {apk_build_id} для пользователя {user.username} с ключом {key}")

        # Отправляем в очередь RabbitMQ
        celery_client.send_task(
            'apkbuild',
            args=[{"key": key, "apk_build_id": apk_build_id}],
            queue='apkbuilder'
        )

        # Возвращаем ответ с информацией о созданной записи
        return Response({
            "status": "Задача на сборку APK принята",
            "apk_build_id": apk_build_id,
            "created_at": apk_build.created_at,
            "build_status": apk_build.status
        }, status=status.HTTP_202_ACCEPTED)