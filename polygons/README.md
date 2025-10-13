# WebSocket уведомления о аномалиях

Система real-time уведомлений о обнаруженных аномалиях в полигонах через WebSocket.

## Быстрый старт

### 1. Запустить WebSocket клиент

```bash
# Из корня проекта
python polygons/websocket_client.py --api-key YOUR_API_KEY --host localhost:8000
```

### 2. Создать тестовую аномалию

```bash
docker exec santi_web python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SantiWayWEB.settings')
django.setup()

from polygons.models import PolygonAction, AnomalyDetection
import random

action = PolygonAction.objects.filter(
    polygon_id='YOUR_POLYGON_ID',
    action_type='mac_monitoring'
).first()

if action:
    mac = ':'.join([f'{random.randint(0, 255):02X}' for _ in range(6)])
    anomaly = AnomalyDetection.objects.create(
        polygon_action=action,
        anomaly_type='new_device',
        severity='critical',
        device_id=mac,
        device_data={'mac': mac, 'vendor': 'Test'},
        description=f'🚨 ТЕСТОВАЯ АНОМАЛИЯ {mac}',
        metadata={'test': True}
    )
    print(f'✅ Аномалия создана: {anomaly.id}')
    print(f'Уведомлений: {anomaly.notifications.count()}')
else:
    print('❌ PolygonAction не найден')
" 2>/dev/null
```

### 3. Результат

В терминале с WebSocket клиентом должно появиться уведомление:
```
╔══════════════════════════════════════════════════════════════════
║ 🚨 Новое уведомление!
╠══════════════════════════════════════════════════════════════════
║ ID: ...
║ Заголовок: Обнаружено новое устройство
║ Сообщение: 🚨 ТЕСТОВАЯ АНОМАЛИЯ AA:BB:CC:DD:EE:FF
║ Важность: critical
╚══════════════════════════════════════════════════════════════════
```

## Настройка мониторинга

```bash
# 1. Создать полигон
POST /api/polygons/
Authorization: Api-Key YOUR_API_KEY

{
    "name": "Охраняемая зона",
    "geometry": { "type": "Polygon", "coordinates": [...] }
}

# 2. Запустить мониторинг
POST /api/polygons/{polygon_id}/start_monitoring/
Authorization: Api-Key YOUR_API_KEY

{
    "action_type": "mac_monitoring",
    "notify_targets": [
        {
            "target_type": "api_key",
            "target_value": "YOUR_API_KEY"
        }
    ]
}
```

## Формат WebSocket сообщений

**Подключение:**
```
ws://localhost:8000/ws/notifications/?api_key=YOUR_API_KEY
```

**Входящие:**
```json
{
    "type": "notification",
    "id": "...",
    "title": "Обнаружено новое устройство",
    "message": "...",
    "severity": "critical",
    "anomaly_type": "new_device",
    "device_id": "AA:BB:CC:DD:EE:FF"
}
```

**Исходящие:**
```json
{"type": "ping"}
{"type": "request_pending"}
{"type": "mark_as_read", "notification_id": "..."}
```

## Статусы уведомлений

- `pending` - Ожидает отправки
- `sent` - Отправлено через WebSocket
- `delivered` - Доставлено клиенту
- `read` - Прочитано пользователем
- `failed` - Ошибка при отправке
