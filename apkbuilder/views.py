from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from .models import APKBuild
from users.models import APIKey
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
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        api_key_value = request.data.get('api-key')

        if not api_key_value:
            return Response(
                {'error': 'API ключ обязателен. Добавьте "api-key" в JSON тело запроса'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            api_key = APIKey.objects.get(key=api_key_value, user=request.user, is_active=True)
        except APIKey.DoesNotExist:
            return Response(
                {'error': 'Неверный или неактивный API ключ'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Отправляем в очередь RabbitMQ (аналогично вашему подходу)
        celery_client.send_task(
            'apkbuild.log_api_key',
            args=[api_key_value],
            kwargs={
                'metadata': {
                    'user_id': request.user.id,
                    'username': request.user.username,
                    'endpoint': 'APKBuildCreateView',
                    'action': 'apk_build_creation',
                    'api_key_id': api_key.id
                }
            },
            queue='apkbuild'
        )

        request.api_key = api_key
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        apk_build = serializer.save(user=self.request.user, api_key=self.request.api_key)
        # TODO: Запуск сборки APK