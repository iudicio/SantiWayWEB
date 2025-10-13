from celery.utils.log import get_task_logger
from django.http import FileResponse
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
BROKER_URL = getenv("CELERY_BROKER_URL", "amqp://celery:celerypassword@rabbitmq:5672/")
celery_client = Celery("apkbuild_producer", broker=BROKER_URL)


IN_PROGRESS_STATUSES = {"pending"}
SUCCESS_STATUS = "success"
FILE_NAME = "Wave Hunter"


class APKBuildCreateView(generics.CreateAPIView):
    """
    POST /apkbuild/                  -> создать задачу (если нет активной)
    GET  /apkbuild/?action=status    -> статус последней сборки по ключу
    GET  /apkbuild/?action=download  -> скачать, если готово; иначе 409 с сообщением
    """

    queryset = APKBuild.objects.all()
    serializer_class = APKBuildCreateSerializer
    parser_classes = [MultiPartParser, JSONParser]
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]

    def _get_key(self, request):
        # Берём API-ключ строго из заголовка Authorization: Api-Key <key>
        api_key_value = get_authorization_header(request)
        if api_key_value:
            parts = api_key_value.split()
            if len(parts) == 2 and parts[0].lower() == b"api-key":
                return parts[1].decode()
        return None

    def _get_last_build(self, api_key_obj):
        return (
            APKBuild.objects.filter(api_key=api_key_obj).order_by("-created_at").first()
        )

    def create(self, request, *args, **kwargs):
        key = self._get_key(request)

        if not key:
            return Response(
                {"error": "API key required"}, status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            api_key_obj = APIKey.objects.get(key=key)
            user = User.objects.filter(api_keys=api_key_obj).first()
        except APIKey.DoesNotExist:
            return Response(
                {"error": "Invalid API key"}, status=status.HTTP_401_UNAUTHORIZED
            )

        # Если по ключу уже есть последняя сборка «в работе», новую не создаём
        last_build = self._get_last_build(api_key_obj)
        if last_build and last_build.status in IN_PROGRESS_STATUSES:
            return Response(
                {
                    "error": "Build already in progress",
                    "apk_build_id": str(last_build.id),
                    "status": last_build.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Создаем запись в базе данных
        apk_build = APKBuild.objects.create(
            user=user,
            api_key=api_key_obj,
        )

        apk_build_id = str(apk_build.id)

        print(
            f"Создана запись APKBuild с ID: {apk_build_id} для пользователя {user.username} с ключом {key}"
        )

        # Отправляем в очередь RabbitMQ
        celery_client.send_task(
            "apkbuild",
            args=[{"key": key, "apk_build_id": apk_build_id}],
            queue="apkbuilder",
        )

        # Возвращаем ответ с информацией о созданной записи
        return Response(
            {
                "status": "Задача на сборку APK принята",
                "apk_build_id": apk_build_id,
                "created_at": apk_build.created_at,
                "build_status": apk_build.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ——— GET: статус / скачивание ———
    def get(self, request, *args, **kwargs):
        key = self._get_key(request)
        if not key:
            return Response(
                {"error": "API key required"}, status=status.HTTP_401_UNAUTHORIZED
            )

        action = request.query_params.get("action", "status")

        try:
            api_key_obj = APIKey.objects.get(key=key)
        except APIKey.DoesNotExist:
            return Response(
                {"error": "Invalid API key"}, status=status.HTTP_401_UNAUTHORIZED
            )

        build = self._get_last_build(api_key_obj)
        if not build:
            return Response(
                {"error": "No builds found"}, status=status.HTTP_404_NOT_FOUND
            )

        if action == "status":
            return Response(
                {
                    "apk_build_id": str(build.id),
                    "status": build.status,
                    "created_at": build.created_at,
                    "completed_at": build.completed_at,
                }
            )

        if action == "download":
            # Если не готово — явно сообщаем
            if build.status != SUCCESS_STATUS:
                return Response(
                    {
                        "error": "APK is not ready yet",
                        "message": "Файл ещё не собран",
                        "apk_build_id": str(build.id),
                        "status": build.status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if not build.apk_file:
                # Теоретически success без файла — тоже считаем неготовым
                return Response(
                    {
                        "error": "APK file not available",
                        "message": "Файл ещё не собран",
                        "apk_build_id": str(build.id),
                        "status": build.status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # новое имя файла
            new_filename = f"{FILE_NAME}.apk"

            # Отдаём файл
            response = FileResponse(
                build.apk_file.open("rb"),
                as_attachment=True,
                filename=new_filename,
            )
            response["Content-Type"] = "application/vnd.android.package-archive"
            return response

        return Response({"error": "Unknown action"}, status=status.HTTP_400_BAD_REQUEST)
