"""
WebSocket consumers для системы уведомлений
"""

import json
import logging

from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket Consumer для получения уведомлений о аномалиях в реальном времени

    Подключение: ws://host/ws/notifications/?api_key=YOUR_API_KEY
    или для authenticated пользователей: ws://host/ws/notifications/
    """

    async def connect(self):
        """Обработка подключения клиента"""
        self.user = None
        self.user_group_name = None

        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            api_key = self.get_api_key_from_query()
            if api_key:
                user = await self.get_user_by_api_key(api_key)

        if not user or not user.is_authenticated:
            logger.warning("WebSocket connection rejected: no authentication")
            await self.close(code=4001)
            return

        self.user = user
        self.user_group_name = f"user_notifications_{user.id}"

        await self.channel_layer.group_add(self.user_group_name, self.channel_name)

        await self.accept()

        logger.info(
            f"WebSocket connected: user={user.username}, group={self.user_group_name}"
        )

        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_established",
                    "message": "Connected to notification service",
                    "user_id": str(user.id),
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

        await self.send_pending_notifications()

    async def disconnect(self, close_code):
        """Обработка отключения клиента"""
        if self.user_group_name:
            await self.channel_layer.group_discard(
                self.user_group_name, self.channel_name
            )
            logger.info(
                f"WebSocket disconnected: group={self.user_group_name}, code={close_code}"
            )

    async def receive(self, text_data):
        """Обработка входящих сообщений от клиента"""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "ping":
                await self.send(
                    text_data=json.dumps(
                        {"type": "pong", "timestamp": timezone.now().isoformat()}
                    )
                )

            elif message_type == "mark_as_read":
                notification_id = data.get("notification_id")
                if notification_id:
                    success = await self.mark_notification_as_read(notification_id)
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "notification_marked",
                                "notification_id": notification_id,
                                "success": success,
                                "timestamp": timezone.now().isoformat(),
                            }
                        )
                    )

            elif message_type == "request_pending":
                await self.send_pending_notifications()

        except json.JSONDecodeError:
            logger.error("Invalid JSON received from WebSocket")
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Invalid JSON format"}
                )
            )
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
            await self.send(text_data=json.dumps({"type": "error", "message": str(e)}))

    async def notification_alert(self, event):
        """
        Обработчик события notification.alert из channel layer
        Отправляет уведомление клиенту
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "notification",
                    "notification": event["notification"],
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

    def get_api_key_from_query(self):
        """Извлечь API ключ из query параметров"""
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        params = dict(qc.split("=") for qc in query_string.split("&") if "=" in qc)
        return params.get("api_key")

    @database_sync_to_async
    def get_user_by_api_key(self, api_key_value):
        """Получить пользователя по API ключу"""
        from users.models import APIKey, User

        try:
            api_key = APIKey.objects.get(key=api_key_value)
            user = User.objects.filter(api_keys=api_key).first()
            return user
        except APIKey.DoesNotExist:
            return None

    @database_sync_to_async
    def get_pending_notifications_data(self):
        """Получить данные непрочитанных уведомлений"""
        from .models import Notification

        if not self.user:
            return []

        pending_notifications = (
            Notification.objects.filter(
                anomaly__polygon_action__polygon__user=self.user,
                status__in=["pending", "sent", "delivered"],
            )
            .select_related("anomaly__polygon_action__polygon", "target")
            .order_by("-created_at")[:50]
        )

        notifications_data = []
        for notification in pending_notifications:
            notifications_data.append(
                {
                    "id": str(notification.id),
                    "title": notification.title,
                    "message": notification.message,
                    "severity": notification.anomaly.severity,
                    "anomaly_type": notification.anomaly.anomaly_type,
                    "polygon_name": notification.anomaly.polygon_action.polygon.name,
                    "created_at": notification.created_at.isoformat(),
                    "status": notification.status,
                }
            )

            if notification.status in ["pending", "sent"]:
                notification.mark_as_delivered()

        return notifications_data

    async def send_pending_notifications(self):
        """Отправить все непрочитанные уведомления пользователю"""
        notifications_data = await self.get_pending_notifications_data()

        if notifications_data:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "pending_notifications",
                        "notifications": notifications_data,
                        "count": len(notifications_data),
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

    @database_sync_to_async
    def mark_notification_as_read(self, notification_id):
        """Отметить уведомление как прочитанное"""
        from .models import Notification

        try:
            notification = Notification.objects.get(
                id=notification_id, anomaly__polygon_action__polygon__user=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            logger.warning(
                f"Notification {notification_id} not found for user {self.user.id}"
            )
            return False
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False
