from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
from django.db.models import Index, Q


class Polygon(models.Model):
    """Модель для хранения полигонов пользователей"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='polygons')
    name = models.CharField(max_length=255, verbose_name='Название полигона')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    
    # TODO: Заменить на PostGIS
    geometry = models.JSONField(verbose_name='Геометрия полигона')
    area = models.FloatField(verbose_name='Площадь (кв.км)', null=True, blank=True)
    
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')
    
    class Meta:
        verbose_name = 'Полигон'
        verbose_name_plural = 'Полигоны'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"


class PolygonAction(models.Model):
    """Модель для действий с полигонами"""
    
    ACTION_TYPES = [
        ('device_search', 'Поиск устройств'),
        ('mac_monitoring', 'Мониторинг MAC-адресов'),
        ('anomaly_detection', 'Поиск аномалий'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('running', 'Выполняется'),
        ('paused', 'Приостановлен'),
        ('stopped', 'Остановлен'),
        ('completed', 'Завершен'),
        ('failed', 'Ошибка'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    polygon = models.ForeignKey(Polygon, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES, verbose_name='Тип действия')
    
    parameters = models.JSONField(default=dict, verbose_name='Параметры действия')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    task_id = models.CharField(max_length=255, blank=True, null=True, verbose_name='ID задачи Celery')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Запущен')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершен')
    
    class Meta:
        verbose_name = 'Действие полигона'
        verbose_name_plural = 'Действия полигонов'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['polygon', 'action_type'],
                condition=Q(status__in=['running', 'pending']),
                name='uniq_active_action_per_polygon_type'
            )
        ]
    
    def __str__(self):
        return f"{self.get_action_type_display()} для {self.polygon.name}"
    
    def start(self):
        """Запуск действия"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()
    
    def stop(self):
        """Остановка действия"""
        self.status = 'stopped'
        self.completed_at = timezone.now()
        self.save()
    
    def pause(self):
        """Приостановка действия"""
        self.status = 'paused'
        self.save()
    
    def complete(self):
        """Завершение действия"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()


class NotificationTarget(models.Model):
    """Модель для целей уведомлений (API ключи или устройства)"""
    
    TARGET_TYPES = [
        ('api_key', 'API ключ'),
        ('device', 'Устройство'),
        ('email', 'Email'),
        ('webhook', 'Webhook URL'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    polygon_action = models.ForeignKey(PolygonAction, on_delete=models.CASCADE, related_name='notification_targets')
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES, verbose_name='Тип цели')
    target_value = models.CharField(max_length=500, verbose_name='Значение цели')  # API key, device ID, email, URL
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    
    class Meta:
        verbose_name = 'Цель уведомления'
        verbose_name_plural = 'Цели уведомлений'
        unique_together = ['polygon_action', 'target_type', 'target_value']
    
    def __str__(self):
        return f"{self.get_target_type_display()}: {self.target_value}"


class AnomalyDetection(models.Model):
    """Модель для обнаруженных аномалий в полигонах"""
    
    ANOMALY_TYPES = [
        ('new_device', 'Новое устройство'),
        ('suspicious_activity', 'Подозрительная активность'),
        ('signal_anomaly', 'Аномалия сигнала'),
        ('location_anomaly', 'Аномалия местоположения'),
        ('frequency_anomaly', 'Аномалия частоты'),
        ('unknown_vendor', 'Неизвестный производитель'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Низкая'),
        ('medium', 'Средняя'),
        ('high', 'Высокая'),
        ('critical', 'Критическая'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    polygon_action = models.ForeignKey(PolygonAction, on_delete=models.CASCADE, related_name='anomalies')
    
    anomaly_type = models.CharField(max_length=50, choices=ANOMALY_TYPES, verbose_name='Тип аномалии')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='medium', verbose_name='Уровень серьезности')
    
    device_id = models.CharField(max_length=17, verbose_name='ID устройства')
    device_data = models.JSONField(verbose_name='Данные устройства')
    
    description = models.TextField(verbose_name='Описание аномалии')
    metadata = models.JSONField(default=dict, verbose_name='Дополнительные данные')
    
    is_resolved = models.BooleanField(default=False, verbose_name='Решена')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Время решения')
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Решена пользователем')
    
    detected_at = models.DateTimeField(auto_now_add=True, verbose_name='Обнаружена')
    
    class Meta:
        verbose_name = 'Обнаруженная аномалия'
        verbose_name_plural = 'Обнаруженные аномалии'
        ordering = ['-detected_at']
        indexes = [
            Index(fields=['polygon_action', 'anomaly_type']),
            Index(fields=['severity', 'is_resolved']),
            Index(fields=['detected_at']),
        ]
    
    def __str__(self):
        return f"{self.get_anomaly_type_display()} в {self.polygon_action.polygon.name}"
    
    def resolve(self, user=None):
        """Отметить аномалию как решенную"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        if user:
            self.resolved_by = user
        self.save()


class Notification(models.Model):
    """Модель для уведомлений об аномалиях"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает отправки'),
        ('sent', 'Отправлено'),
        ('delivered', 'Доставлено'),
        ('failed', 'Ошибка отправки'),
        ('read', 'Прочитано'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anomaly = models.ForeignKey(AnomalyDetection, on_delete=models.CASCADE, related_name='notifications')
    target = models.ForeignKey(NotificationTarget, on_delete=models.CASCADE, related_name='notifications')
    
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    message = models.TextField(verbose_name='Сообщение')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    
    delivery_metadata = models.JSONField(default=dict, verbose_name='Метаданные доставки')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлено')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Доставлено')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Прочитано')
    
    retry_count = models.IntegerField(default=0, verbose_name='Количество попыток')
    max_retries = models.IntegerField(default=3, verbose_name='Максимум попыток')
    
    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        indexes = [
            Index(fields=['status', 'created_at']),
            Index(fields=['anomaly', 'target']),
        ]
    
    def __str__(self):
        return f"Уведомление: {self.title} -> {self.target}"
    
    def mark_as_sent(self):
        """Отметить как отправленное"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()
    
    def mark_as_delivered(self):
        """Отметить как доставленное"""
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        self.save()
    
    def mark_as_read(self):
        """Отметить как прочитанное"""
        self.status = 'read'
        self.read_at = timezone.now()
        self.save()
    
    def mark_as_failed(self):
        """Отметить как неудачное"""
        self.status = 'failed'
        self.retry_count += 1
        self.save()
    
    def can_retry(self):
        """Проверить, можно ли повторить отправку"""
        return self.retry_count < self.max_retries and self.status == 'failed'
