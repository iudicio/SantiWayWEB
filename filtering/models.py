from django.conf import settings
from django.db import models
from django.core.validators import FileExtensionValidator
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import JSONField


class SearchQuery(models.Model):
    class FileStatus(models.TextChoices):
        PENDING = "PENDING", _("В обработке")
        READY   = "READY",   _("Готов")
        FAILED  = "FAILED",  _("Ошибка")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="queries")

    # Параметры запроса (как пришли от фронта)
    params = models.JSONField(default=dict, blank=True)

    # Результаты (первые 300 объектов)
    results = models.JSONField(default=list, blank=True)

    # Служебное
    created_at = models.DateTimeField(auto_now_add=True)
    paid = models.BooleanField(default=False, verbose_name="оплачено")

    # Файл-выгрузка (например, CSV/ZIP) и статус его готовности
    export_file = models.FileField(
        upload_to="exports/%Y/%m/%d/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["csv", "json", "zip"])]
    )
    export_status = models.CharField(
        max_length=16, choices=FileStatus.choices, default=FileStatus.PENDING
    )

    # Для быстрой навигации — последние MAC, попавшие в мониторинг
    monitored_macs = ArrayField(models.CharField(max_length=32), blank=True, default=list)

    def __str__(self):
        return f"SearchQuery#{self.pk} by {self.user_id} @ {self.created_at:%Y-%m-%d %H:%M}"
