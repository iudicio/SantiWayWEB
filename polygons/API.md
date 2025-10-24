> Все endpoints требуют API ключ: `Authorization: Api-Key YOUR_KEY`

## 🗺️ Полигоны

### Список полигонов
```python
import requests

r = requests.get("http://localhost:8000/api/polygons/", 
    headers={"Authorization": "Api-Key YOUR_KEY"})
print(r.json())
```

**Ответ:**
```json
[{
    "id": "550e8400-...",
    "name": "Моя зона",
    "geometry": {"type": "Polygon", "coordinates": [[[37.6,55.7],[37.7,55.7],...]]},
    "area": 123.45,
    "monitoring_status": "running"
}]
```

**Ошибки:**
- 403 - неправильный ключ `{"detail": "Invalid API key"}`
- 401 - нет ключа `{"detail": "Authentication credentials..."}`

---

### Создать полигон
```python
import requests

data = {
    "name": "Новая зона",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[37.6,55.7],[37.7,55.7],[37.7,55.8],[37.6,55.8],[37.6,55.7]]]
    }
}

r = requests.post("http://localhost:8000/api/polygons/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json=data)
print(r.json())
```

**Ответ (201):**
```json
{
    "id": "650e8400-...",
    "name": "Новая зона",
    "area": 123.45,
    "monitoring_status": "not_started"
}
```

**Ошибки:**
- 400 - кривая геометрия `{"geometry": ["invalid polygon geometry"]}`
- 405 - не тот метод `{"detail": "Method \"GET\" not allowed"}`

---

### Получить полигон
```python
r = requests.get(f"http://localhost:8000/api/polygons/{polygon_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ошибки:**
- 404 - не найден или чужой `{"detail": "Not found."}`

---

### Обновить полигон
```python
# Частичное обновление (PATCH)
r = requests.patch(f"http://localhost:8000/api/polygons/{polygon_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json={"name": "Новое название"})

# Полное обновление (PUT) - нужны все поля
r = requests.put(f"http://localhost:8000/api/polygons/{polygon_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json={"name": "...", "geometry": {...}})
```

**Ошибки:**
- 403 - чужой полигон `{"detail": "Not your polygon"}`

---

### Удалить полигон
```python
r = requests.delete(f"http://localhost:8000/api/polygons/{polygon_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
# 204 No Content (успех)
```

> При удалении автоматически останавливаются все действия

---

### Поиск устройств в полигоне
```python
r = requests.post(f"http://localhost:8000/api/polygons/{polygon_id}/search/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
print(r.json())
```

**Ответ:**
```json
{
    "polygon_id": "550e8400-...",
    "polygon_name": "Моя зона",
    "devices_found": 15,
    "devices": [
        {
            "device_id": "AA:BB:CC:DD:EE:FF",
            "vendor": "Apple Inc.",
            "latitude": 55.75,
            "longitude": 37.65,
            "signal_strength": -45
        }
    ]
}
```

**Ошибки:**
- 500 - ES не работает `{"error": "Ошибка поиска: Connection refused"}`

---

### Запустить мониторинг
```python
data = {
    "monitoring_interval": 300,  # секунды
    "notify_targets": [
        {"target_type": "api_key", "target_value": "YOUR_KEY"},
        {"target_type": "device", "target_value": "AA:BB:CC:DD:EE:FF"}
    ]
}

r = requests.post(f"http://localhost:8000/api/polygons/{polygon_id}/start_monitoring/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json=data)
print(r.json())
```

**Ответ:**
```json
{
    "message": "Мониторинг MAC адресов запущен",
    "polygon_id": "550e8400-...",
    "task_id": "a1b2c3d4-...",
    "action_id": "750e8400-..."
}
```

**Ошибки:**
- 400 - уже запущен `{"error": "Мониторинг уже запущен", "action_id": "..."}`
- 400 - кривой тип `{"error": "Недопустимый тип цели: invalid"}`

> **Важно:** без `notify_targets` уведомления не будут создаваться!

---

### Остановить мониторинг
```python
r = requests.post(f"http://localhost:8000/api/polygons/{polygon_id}/stop_monitoring/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{
    "message": "Мониторинг MAC адресов остановлен",
    "polygon_id": "550e8400-..."
}
```

**Ошибки:**
- 400 - не запущен `{"message": "Мониторинг не запущен..."}`

---

### Статус мониторинга (1 полигон)
```python
r = requests.get(f"http://localhost:8000/api/polygons/{polygon_id}/monitoring_status/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{
    "polygon_id": "550e8400-...",
    "monitoring_status": "running",  // not_started, running, stopped, completed
    "actions": [{
        "id": "750e8400-...",
        "status": "running",
        "parameters": {
            "devices_found": 15,
            "last_check": "2025-10-14T14:30:00Z"
        }
    }]
}
```

---

### Статусы всех полигонов (оптимизированный)
```python
r = requests.get("http://localhost:8000/api/polygons/monitoring_statuses/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{
    "count": 3,
    "results": [
        {
            "polygon_id": "550e8400-...",
            "polygon_name": "Зона 1",
            "monitoring_status": "running",
            "last_action": {...}
        }
    ]
}
```

---

## 🚨 Аномалии

### Список аномалий
```python
# Все аномалии
r = requests.get("http://localhost:8000/api/anomalies/",
    headers={"Authorization": "Api-Key YOUR_KEY"})

# С фильтрами
params = {
    "severity": "critical",           # low, medium, high, critical
    "anomaly_type": "new_device",     # new_device, suspicious_activity, signal_anomaly...
    "is_resolved": "false",           # true/false
    "polygon_id": "550e8400-..."
}
r = requests.get("http://localhost:8000/api/anomalies/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    params=params)
```

**Ответ:**
```json
[{
    "id": "a50e8400-...",
    "polygon_name": "Моя зона",
    "anomaly_type": "new_device",
    "severity": "critical",
    "device_id": "AA:BB:CC:DD:EE:FF",
    "device_data": {"mac": "...", "vendor": "Unknown"},
    "description": "Обнаружено новое устройство",
    "is_resolved": false,
    "detected_at": "2025-10-14T14:15:00Z"
}]
```

---

### Получить аномалию
```python
r = requests.get(f"http://localhost:8000/api/anomalies/{anomaly_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

---

### Отметить как решенную
```python
r = requests.post(f"http://localhost:8000/api/anomalies/{anomaly_id}/resolve/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{
    "message": "Аномалия отмечена как решенная",
    "anomaly_id": "a50e8400-...",
    "resolved_at": "2025-10-14T15:00:00Z",
    "resolved_by": "admin"
}
```

**Ошибки:**
- 405 - не тот метод `{"detail": "Method \"GET\" not allowed"}`

---

## 🔔 Уведомления

### Список уведомлений
```python
# Все
r = requests.get("http://localhost:8000/api/notifications/",
    headers={"Authorization": "Api-Key YOUR_KEY"})

# Только непрочитанные
r = requests.get("http://localhost:8000/api/notifications/?unread_only=true",
    headers={"Authorization": "Api-Key YOUR_KEY"})

# С фильтрами
params = {
    "status": "delivered",      # pending, sent, delivered, failed, read
    "severity": "critical",
    "polygon_id": "550e8400-..."
}
r = requests.get("http://localhost:8000/api/notifications/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    params=params)
```

**Ответ:**
```json
[{
    "id": "b50e8400-...",
    "title": "🚨 Новое устройство",
    "message": "Обнаружена аномалия в полигоне...",
    "status": "delivered",
    "anomaly_details": {
        "anomaly_type": "new_device",
        "severity": "critical",
        "device_id": "AA:BB:CC:DD:EE:FF"
    },
    "created_at": "2025-10-14T14:15:00Z"
}]
```

---

### Количество непрочитанных
```python
r = requests.get("http://localhost:8000/api/notifications/unread_count/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{"unread_count": 5}
```

---

### Отметить как прочитанное
```python
r = requests.post(f"http://localhost:8000/api/notifications/{notif_id}/mark_as_read/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
{
    "message": "Уведомление отмечено как прочитанное",
    "notification_id": "b50e8400-...",
    "read_at": "2025-10-14T15:00:00Z"
}
```

---

## 🎯 Цели уведомлений

### Список целей
```python
r = requests.get("http://localhost:8000/api/notification-targets/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
```

**Ответ:**
```json
[{
    "id": "c50e8400-...",
    "polygon_action": "750e8400-...",
    "target_type": "api_key",  // api_key, device
    "target_value": "YOUR_KEY",
    "is_active": true
}]
```

---

### Создать цель
```python
data = {
    "polygon_action": "750e8400-...",
    "target_type": "api_key",
    "target_value": "YOUR_KEY"
}

r = requests.post("http://localhost:8000/api/notification-targets/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json=data)
```

**Ошибки:**
- 400 - дубликат `{"non_field_errors": ["Такая цель уже существует..."]}`
- 403 - чужое действие `{"detail": "Not your polygon action"}`

---

### Обновить цель
```python
# Деактивировать
r = requests.patch(f"http://localhost:8000/api/notification-targets/{target_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"},
    json={"is_active": False})
```

---

### Удалить цель
```python
r = requests.delete(f"http://localhost:8000/api/notification-targets/{target_id}/",
    headers={"Authorization": "Api-Key YOUR_KEY"})
# 204 No Content
```

---

## 🚀 Полный пример: от создания до уведомлений

```python
import requests
import time

KEY = "your-key"
BASE = "http://localhost:8000"
headers = {"Authorization": f"Api-Key {KEY}"}

# 1. Создать полигон
poly = requests.post(f"{BASE}/api/polygons/", headers=headers, json={
    "name": "Тестовая зона",
    "geometry": {"type": "Polygon", "coordinates": [[[37.6,55.7],[37.7,55.7],[37.7,55.8],[37.6,55.8],[37.6,55.7]]]}
}).json()
print(f"✓ Полигон: {poly['id']}")

# 2. Запустить мониторинг
mon = requests.post(f"{BASE}/api/polygons/{poly['id']}/start_monitoring/", 
    headers=headers,
    json={
        "monitoring_interval": 300,
        "notify_targets": [{"target_type": "api_key", "target_value": KEY}]
    }).json()
print(f"✓ Мониторинг: {mon['action_id']}")

# 3. Подождать и проверить аномалии
time.sleep(5)
anomalies = requests.get(f"{BASE}/api/anomalies/?polygon_id={poly['id']}&is_resolved=false",
    headers=headers).json()
print(f"✓ Аномалий: {len(anomalies)}")

# 4. Проверить уведомления
count = requests.get(f"{BASE}/api/notifications/unread_count/", headers=headers).json()
print(f"✓ Непрочитанных: {count['unread_count']}")

# 5. Остановить
requests.post(f"{BASE}/api/polygons/{poly['id']}/stop_monitoring/", headers=headers)
print("✓ Остановлено")
```

---

## ⚠️ Типичные ошибки

| Код | Что случилось | Как исправить |
|-----|---------------|---------------|
| 401 | Нет ключа | Добавь `Authorization: Api-Key ...` |
| 403 | Неправильный ключ | Проверь ключ |
| 404 | Не найдено | Проверь ID или это чужой ресурс |
| 405 | Не тот метод | Используй POST вместо GET (или наоборот) |
| 400 | Кривые данные | Читай текст ошибки |

---

## 🌐 WebSocket для real-time уведомлений

**Подключение:**
```python
import websockets
ws = await websockets.connect("ws://localhost:8000/ws/notifications/?api_key=YOUR_KEY")
```

**Готовый клиент:**
```bash
python polygons/websocket_client.py --api-key YOUR_KEY --host localhost:8000
```

**Детали:** см. `polygons/README.md` и `polygons/TESTING_WEBSOCKET.md`

---

**Типы аномалий:**
- `new_device` - новое устройство
- `suspicious_activity` - подозрительная активность
- `signal_anomaly` - аномалия сигнала
- `location_anomaly` - аномалия местоположения
- `frequency_anomaly` - аномалия частоты
- `unknown_vendor` - неизвестный производитель

**Уровни серьезности:**
- `low` - низкая
- `medium` - средняя
- `high` - высокая
- `critical` - критическая

**Статусы мониторинга:**
- `not_started` - не запускался
- `running` - работает
- `stopped` - остановлен
- `completed` - завершен

**Статусы уведомлений:**
- `pending` - ожидает
- `sent` - отправлено
- `delivered` - доставлено
- `failed` - ошибка
- `read` - прочитано

