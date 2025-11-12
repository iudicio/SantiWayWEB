import re
import uuid
import base64
from typing import Iterable, Optional, List, Dict, Any

from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from users.models import APIKey
from .models import Notification


GROUP_PREFIX_API = "api_"


def _sanitize_group(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", name)[:99]

def _group_api(api_key: str) -> str:
    return _sanitize_group(f"{GROUP_PREFIX_API}{api_key}")

def _to_b64_list(binary_contents: Optional[Iterable[bytes]]) -> Optional[List[str]]:
    if not binary_contents:
        return None
    return [base64.b64encode(b).decode("ascii") for b in binary_contents]

def _build_payload(
    *,
    notif_id: str,
    recorded_at: Optional[str] = None,
    title: Optional[str] = None,
    binary_contents: Optional[Iterable[bytes]] = None,
    binary_types: Optional[List[str]] = None,
    text: Optional[str] = None,
    notif_type: str = "INFO",
    coords: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"type": "notification", "notif_type": notif_type, "notif_id": notif_id}
    if recorded_at: payload["recorded_at"] = recorded_at
    if title:       payload["title"] = title
    if text:        payload["text"] = text
    if coords:      payload["coords"] = coords
    b64 = _to_b64_list(binary_contents)
    if b64:         payload["binary_contents_b64"] = b64
    if binary_types:payload["binary_types"] = binary_types
    return payload

def send_notification_to_api_key(
    api_key_str: str,
    *,
    recorded_at: Optional[str] = None,
    title: Optional[str] = None,
    binary_contents: Optional[Iterable[bytes]] = None,
    binary_types: Optional[List[str]] = None,
    text: Optional[str] = None,
    notif_type: str = "INFO",
    coords: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    1) создаёт запись Notification (QUEUED),
    2) шлёт JSON по группе api_<uuid>,
    3) обновляет статус на SENT/FAILED.
    Возвращает объект Notification (id будет в notif_id в payload).
    """
    key_uuid = uuid.UUID(api_key_str)
    apikey = APIKey.objects.get(key=key_uuid)

    notif = Notification.objects.create(
        api_key=apikey,
        recorded_at=recorded_at,
        title=title or "",
        text=text or "",
        notif_type=notif_type,
        coords=coords or {},
        binary_types=binary_types or [],
        status=Notification.Status.QUEUED,
        created_at=timezone.now(),
    )

    payload = _build_payload(
        notif_id=str(notif.id),
        recorded_at=recorded_at,
        title=title,
        binary_contents=binary_contents,
        binary_types=binary_types,
        text=text,
        notif_type=notif_type,
        coords=coords,
    )
    notif.payload = payload
    notif.save(update_fields=["payload"])

    layer = get_channel_layer()
    try:
        async_to_sync(layer.group_send)(
            _group_api(api_key_str),
            {"type": "notify.message", "payload": payload}
        )
        notif.status = Notification.Status.SENT
        notif.sent_at = timezone.now()
        notif.save(update_fields=["status", "sent_at"])
    except Exception as e:
        notif.status = Notification.Status.FAILED
        notif.error = str(e)
        notif.save(update_fields=["status", "error"])

    return notif