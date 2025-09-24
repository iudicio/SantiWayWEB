from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from .models import APKBuild
from users.models import APIKey
from .serializers import APKBuildCreateSerializer, APKBuildStatusSerializer


class APKBuildCreateView(generics.CreateAPIView):
    """Создание задачи на сборку APK"""
    queryset = APKBuild.objects.all()
    serializer_class = APKBuildCreateSerializer
    parser_classes = [MultiPartParser, JSONParser]
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Получаем API ключ из JSON тела запроса
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

        # Сохраняем API ключ в request для использования в perform_create
        request.api_key = api_key

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Используем API ключ из request
        apk_build = serializer.save(user=self.request.user, api_key=self.request.api_key)

        # TODO: Запуск сборки в фоне
        # tasks.start_apk_build.delay(apk_build.id)


class APKBuildStatusView(generics.RetrieveAPIView):
    """Проверка статуса сборки APK"""
    serializer_class = APKBuildStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return APKBuild.objects.filter(user=self.request.user)

    def get_object(self):
        apk_build_id = self.kwargs.get('build_id')
        return get_object_or_404(self.get_queryset(), id=apk_build_id)


class APKBuildDownloadView(generics.GenericAPIView):
    """Скачивание готового APK файла"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return APKBuild.objects.filter(user=self.request.user)

    def get(self, request, *args, **kwargs):
        apk_build_id = self.kwargs.get('build_id')
        apk_build = get_object_or_404(self.get_queryset(), id=apk_build_id)

        # Проверяем, что сборка завершена и файл существует
        if apk_build.status != APKBuild.BuildStatus.COMPLETED:
            return Response(
                {'error': 'APK файл еще не готов для скачивания'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not apk_build.output_file:
            return Response(
                {'error': 'APK файл не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Возвращаем файл для скачивания
        response = FileResponse(
            apk_build.output_file.open('rb'),
            filename=apk_build.output_file.name.split('/')[-1],
            as_attachment=True
        )
        return response