import re
import uuid
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.db import transaction
from django.utils import timezone

from users.models import APIKey
from .models import WSConnection, Notification


GROUP_PREFIX_API = "api_"


def _sanitize_group(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", name)[:99]

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        qs = parse_qs(self.scope["query_string"].decode())
        api_key_str = qs.get("api_key", [None])[0]
        device_id = qs.get("device_id", [None])[0]  # <--- НОВОЕ
        if not api_key_str:
            headers = {k.decode().lower(): v.decode() for k, v in self.scope["headers"]}
            api_key_str = headers.get("x-api-key")
            device_id = device_id or headers.get("x-device-id")  # <--- НОВОЕ
        if not api_key_str:
            await self.close(code=4001); return

        api_key_obj = await self._get_apikey(api_key_str)
        if not api_key_obj:
            await self.close(code=4003); return

        group = _sanitize_group(f"{GROUP_PREFIX_API}{api_key_str}")
        self.api_key_str = api_key_str
        self.group_name = group

        client_ip = self.scope["client"][0] if self.scope.get("client") else None
        hdrs = dict((k.decode().lower(), v.decode()) for k, v in self.scope["headers"])
        ua = hdrs.get("user-agent", "")
        devname = hdrs.get("x-device-name", "")
        appv = hdrs.get("x-app-version", "")

        # upsert
        self.conn_id = await self._upsert_ws_connection(
            api_key_id=api_key_obj.id,
            device_id=device_id,
            channel_name=self.channel_name,
            group_name=group,
            ip=client_ip,
            ua=ua,
            devname=devname,
            appv=appv,
        )

        await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "system.connected",
            "ts": timezone.now().isoformat(),
            "api_key_tail": api_key_str[-6:],
            "device_id": device_id,
        })

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if getattr(self, "conn_id", None):
            await self._mark_disconnected(self.conn_id)

    async def receive_json(self, content, **kwargs):
        t = content.get("type")
        if t == "ping":
            if getattr(self, "conn_id", None):
                await self._touch(self.conn_id)
            await self.send_json({"type": "pong"})
        elif t == "ack":
            notif_id = content.get("notif_id")
            if notif_id:
                await self._mark_delivered(str(notif_id))

    async def notify_message(self, event):
        await self.send_json(event.get("payload", {}))

    # ---- DB helpers ----
    @database_sync_to_async
    def _get_apikey(self, api_key_str: str):
        try:
            key_uuid = uuid.UUID(api_key_str)
        except Exception:
            return None
        return APIKey.objects.filter(key=key_uuid).first()

    @database_sync_to_async
    def _upsert_ws_connection(self, api_key_id, device_id, channel_name, group_name, ip, ua, devname, appv):
        """
        Правила:
        - если пришёл device_id: поддерживаем РОВНО одну живую запись на (api_key, device_id).
          при новом connect: либо обновляем существующую запись, либо помечаем старую offline и создаём новую.
        - если device_id нет: гасим все "похожие" живые соединения (api_key + тот же ip+ua), потом создаём новую.
        """
        now = timezone.now()
        with transaction.atomic():
            if device_id:
                qs = WSConnection.objects.select_for_update().filter(
                    api_key_id=api_key_id, device_id=device_id, is_connected=True
                )
                existing = qs.first()
                if existing:
                    # обновляем "на месте"
                    existing.channel_name = channel_name
                    existing.group_name = group_name
                    existing.connected_at = now
                    existing.disconnected_at = None
                    existing.last_seen = now
                    existing.client_ip = ip
                    existing.user_agent = ua or ""
                    existing.device_name = devname or ""
                    existing.app_version = appv or ""
                    existing.is_connected = True
                    existing.save()
                    return existing.id
                # нет живой — можно почистить любые "подвисшие"
                WSConnection.objects.filter(
                    api_key_id=api_key_id, device_id=device_id, is_connected=False
                ).delete()

                obj = WSConnection.objects.create(
                    api_key_id=api_key_id,
                    device_id=device_id,
                    channel_name=channel_name,
                    group_name=group_name,
                    is_connected=True,
                    connected_at=now,
                    last_seen=now,
                    client_ip=ip,
                    user_agent=ua or "",
                    device_name=devname or "",
                    app_version=appv or "",
                )
                return obj.id

            # device_id нет — fallback: отключим активные "похожие" сессии
            WSConnection.objects.filter(
                api_key_id=api_key_id,
                is_connected=True,
                client_ip=ip,
                user_agent=ua,
            ).update(is_connected=False, disconnected_at=now)

            obj = WSConnection.objects.create(
                api_key_id=api_key_id,
                device_id=None,
                channel_name=channel_name,
                group_name=group_name,
                is_connected=True,
                connected_at=now,
                last_seen=now,
                client_ip=ip,
                user_agent=ua or "",
                device_name=devname or "",
                app_version=appv or "",
            )
            return obj.id

    @database_sync_to_async
    def _mark_disconnected(self, conn_id):
        try:
            obj = WSConnection.objects.get(id=conn_id)
            obj.mark_disconnected()
        except WSConnection.DoesNotExist:
            pass

    @database_sync_to_async
    def _touch(self, conn_id):
        WSConnection.objects.filter(id=conn_id).update(last_seen=timezone.now())

    @database_sync_to_async
    def _mark_delivered(self, notif_id: str):
        Notification.objects.filter(id=notif_id).update(
            status=Notification.Status.DELIVERED,
            delivered_at=timezone.now(),
        )