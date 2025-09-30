import uuid
from django.db import models


class APKBuild(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Время завершения')

    user = models.ForeignKey(
        'users.User',
        related_name='apk_builds',
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )

    api_key = models.ForeignKey(
        'users.APIKey',
        related_name='apk_builds',
        on_delete=models.CASCADE,
        verbose_name='API ключ'
    )

    status = models.CharField(
        max_length=20,
        default="pending",
        verbose_name='Статус сборки'
    )

    apk_file = models.FileField(
        upload_to="apks/",
        null=True,
        blank=True,
        verbose_name="APK файл"
    )

    def __str__(self):
        return f"{self.id} - {self.status})"