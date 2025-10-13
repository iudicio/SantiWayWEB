import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Index, Q
from django.utils import timezone

User = get_user_model()


class Polygon(models.Model):
    """Модель для хранения полигонов пользователей"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="polygons")
    name = models.CharField(max_length=255, verbose_name="Название полигона")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")

    # TODO: Заменить на PostGIS
    geometry = models.JSONField(verbose_name="Геометрия полигона")
    area = models.FloatField(verbose_name="Площадь (кв.км)", null=True, blank=True)

    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Полигон"
        verbose_name_plural = "Полигоны"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class PolygonAction(models.Model):
    """Модель для действий с полигонами"""

    ACTION_TYPES = [
        ("device_search", "Поиск устройств"),
        ("mac_monitoring", "Мониторинг MAC-адресов"),
        ("anomaly_detection", "Поиск аномалий"),
    ]

    STATUS_CHOICES = [
        ("pending", "Ожидает"),
        ("running", "Выполняется"),
        ("paused", "Приостановлен"),
        ("stopped", "Остановлен"),
        ("completed", "Завершен"),
        ("failed", "Ошибка"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    polygon = models.ForeignKey(
        Polygon, on_delete=models.CASCADE, related_name="actions"
    )
    action_type = models.CharField(
        max_length=50, choices=ACTION_TYPES, verbose_name="Тип действия"
    )

    parameters = models.JSONField(default=dict, verbose_name="Параметры действия")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус"
    )
    task_id = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="ID задачи Celery"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Запущен")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершен")

    class Meta:
        verbose_name = "Действие полигона"
        verbose_name_plural = "Действия полигонов"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["polygon", "action_type"],
                condition=Q(status__in=["running", "pending"]),
                name="uniq_active_action_per_polygon_type",
            )
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} для {self.polygon.name}"

    def start(self):
        """Запуск действия"""
        self.status = "running"
        self.started_at = timezone.now()
        self.save()

    def stop(self):
        """Остановка действия"""
        self.status = "stopped"
        self.completed_at = timezone.now()
        self.save()

    def pause(self):
        """Приостановка действия"""
        self.status = "paused"
        self.save()

    def complete(self):
        """Завершение действия"""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save()
