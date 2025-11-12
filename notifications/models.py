import uuid
from django.db import models
from django.utils import timezone
from django.db.models import Q


class WSConnection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey("users.APIKey", on_delete=models.CASCADE, related_name="ws_connections")
    # уникально в рамках живой сессии у Channels, но меняется при reconnect
    channel_name = models.CharField(max_length=255, unique=True, db_index=True)
    group_name = models.CharField(max_length=100, db_index=True)

    # НОВОЕ: стабильный идентификатор устройства (UUID/строка от клиента)
    device_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    is_connected = models.BooleanField(default=True)
    connected_at = models.DateTimeField(default=timezone.now)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(default=timezone.now)

    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    device_name = models.CharField(max_length=128, blank=True, default="")
    app_version = models.CharField(max_length=64, blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["api_key", "is_connected"]),
            models.Index(fields=["group_name", "is_connected"]),
            models.Index(fields=["api_key", "device_id"]),
        ]
        # Postgres: одна «живая» запись на (api_key, device_id)
        constraints = [
            models.UniqueConstraint(
                fields=["api_key", "device_id"],
                condition=Q(is_connected=True) & ~Q(device_id=None) & ~Q(device_id=""),
                name="uniq_live_ws_per_device",
            )
        ]

    def mark_disconnected(self):
        self.is_connected = False
        self.disconnected_at = timezone.now()
        self.save(update_fields=["is_connected", "disconnected_at"])

    def touch(self):
        self.last_seen = timezone.now()
        self.save(update_fields=["last_seen"])


class Notification(models.Model):
    """
    Журнал уведомлений: отправки по ключу с полезной нагрузкой и статусом.
    """
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered (ACK)"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey("users.APIKey", on_delete=models.CASCADE, related_name="notifications")

    # ТВОИ ПОЛЯ (все опциональны)
    recorded_at = models.DateTimeField(null=True, blank=True)  # дата/время записи
    title = models.CharField(max_length=255, blank=True, default="")  # заголовок
    text = models.TextField(blank=True, default="")  # текст уведомления
    notif_type = models.CharField(max_length=16, default="INFO")  # ALARM|SYSTEM|INFO
    coords = models.JSONField(default=dict, blank=True)  # {"lat":..., "lon":...}

    # типы бинарных файлов (массив строк), сами байты мы не храним в БД
    binary_types = models.JSONField(default=list, blank=True)

    # полный JSON, который ушёл по сокету
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["api_key", "status"]),
            models.Index(fields=["created_at"]),
        ]
