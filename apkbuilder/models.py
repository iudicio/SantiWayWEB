import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class APKBuild(models.Model):
    class BuildStatus(models.TextChoices):
        PENDING = 'pending', 'В ожидании'
        PROCESSING = 'processing', 'В обработке'
        COMPLETED = 'completed', 'Завершено'
        FAILED = 'failed', 'Ошибка'
        CANCELLED = 'cancelled', 'Отменено'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Время завершения')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        choices=BuildStatus.choices,
        default=BuildStatus.PENDING,
        verbose_name='Статус сборки'
    )

    # Дополнительные поля для хранения информации о сборке
    app_name = models.CharField(max_length=255, verbose_name='Название приложения')
    package_name = models.CharField(max_length=255, verbose_name='Имя пакета')
    version_code = models.IntegerField(default=1, verbose_name='Код версии')
    version_name = models.CharField(max_length=50, default='1.0', verbose_name='Версия')

    source_file = models.FileField(
        upload_to='apk_sources/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name='Исходный файл'
    )
    output_file = models.FileField(
        upload_to='apk_builds/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name='Собранный APK'
    )

    class Meta:
        verbose_name = 'Сборка APK'
        verbose_name_plural = 'Сборки APK'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.app_name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Автоматически устанавливаем completed_at при завершении сборки
        if self.status in [self.BuildStatus.COMPLETED, self.BuildStatus.FAILED, self.BuildStatus.CANCELLED]:
            if not self.completed_at:
                self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def build_duration(self):
        """Возвращает продолжительность сборки в секундах"""
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    def mark_as_processing(self):
        """Пометить как в процессе сборки"""
        self.status = self.BuildStatus.PROCESSING
        self.save()

    def mark_as_completed(self, output_file=None):
        """Пометить как завершенную"""
        self.status = self.BuildStatus.COMPLETED
        if output_file:
            self.output_file = output_file
        self.save()

    def mark_as_failed(self, error_message=''):
        """Пометить как неудачную"""
        self.status = self.BuildStatus.FAILED
        self.error_message = error_message
        self.save()