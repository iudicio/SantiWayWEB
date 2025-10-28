"# SantiWayWEB" 

docker compose up -d --build

Django admin: При сборке и запуске суперпользователь создаётся автоматически.
Username: admin@example.com
Password: admin

Чтобы сборка APK работала необходимо в microservices/ApkBuilde создать папку keystore (если нет) и 
добавить в нее файл, что Влад кидал в группу ("release.jsx").

### При желании добавить новую фоновую таску, пишите в settings.py:

```python
CRONJOBS = [
    ('*/30 * * * *', 'apkbuilder.cron.delete_background_task', '> /proc/1/fd/1 2>&1'),
]
```

Добавляете туда через запятую нужную вам функцию откуда угодно, данная таска выполняется каждые 30 минут, проверяет есть ли устаревшие apk файлы, если да - удаляет их.
# 1. Поднятие всего WEB проекта для самых маленьких
## Выполнять строго в этой последовательности, чтобы микросервисы подружились
1. Клонируем репозиторий к себе
2. Запускаем Docker Desktop
3. Открываем консоль. Создаем сеть:  
```docker network create app-network```
4. Переходим в консоли в SantiWayWEB (папка с кучей файлов и папок). Собираем проект WEB:  
```docker-compose up -d --build```
5. Открываем в консоли папку microservices/RabbitMQ и собираем:  
```docker-compose up -d --build```
6. Переходим в папку microservices/Vendor
7. Создаем .env файл и копируем в него содержимое .env.example
8. Открываем в консоли папку microservices/Vendor и собираем:  
```docker-compose up -d --build```
9. Переходим в папку microservices/ESWriter
10. Создаем .env файл и копируем в него содержимое .env.example
11. Открываем в консоли папку microservices/ESWriter и собираем:  
```docker-compose up -d --build```
12. Открываем в консоли папку microservices/APKBuilde и собираем:  
```docker-compose up -d --build```
## Если Вы все сделали по порядку, и видите, как все контейнеры запущены, то Вы молодец!
Итак, мы имеем поднятый WEB сервер + микросервисы

# Создание Api ключа
1. При поднятом сервере пишем в поисковую строку ```http://localhost/users/registration```
2. Регистрируемся и нас сразу логинит в аккаунт
3. Жмем кнопку New Key, вводим какое хотим имя и создаем ключ
## Поздравляем! Вы создали свой первый Api-Key!

# 2. Памятка для создания микросервисов.
## Конфигурация микросервиса Celery (.env)

Этот файл определяет переменные окружения для микросервиса, который работает через Celery и брокер сообщений (RabbitMQ или Redis).
Используется для обработки задач и передачи данных между сервисами.

### Основные переменные окружения

```
# Брокер сообщений (обязательно)
CELERY_BROKER_URL=amqp://celery:celerypassword@rabbitmq:5672//

# Если используется Redis как backend (опционально)
BACKEND_URL=redis://:strongpassword@redis:6379/0

# Имя текущего сервиса (обязательно)
CELERY_CONSUMER_NAME=userInfo

# Имя задачи, которую обрабатывает этот сервис (обязательно)
CELERY_C_TASK_NAME=devices

# Очередь, которую слушает этот сервис (обязательно)
CELERY_C_QUEUE_NAME=info_queue

# Уровень логирования Celery (DEBUG / INFO / WARNING / ERROR)
CELERY_LOG_LEVEL=INFO
```
### Прием задач
| Переменная                                   | Назначение                      | Пример               |
| -------------------------------------------- | ------------------------------- | -------------------- |
| `CELERY_C_QUEUE_NAME`                        | Очередь, которую слушает сервис | `info_queue`         |
| `CELERY_C_TASK_NAME`                         | Имя задачи                      | `devices`            |
| `CELERY_C_TASK_NAME1`, `CELERY_C_TASK_NAME2` | Сервисы с несколькими задачами  | `devices`, `folders` |

### Отправка данных
| Переменная            | Назначение                 | Пример           |
| --------------------- | -------------------------- | ---------------- |
| `CELERY_P_TASK_NAME`  | Имя следующей задачи       | `esWriter`       |
| `CELERY_P_QUEUE_NAME` | Очередь следующего сервиса | `esWriter_queue` |

Примечание: указывать только, если сервис шлет данные куда-то дальше

## Создание цепочек микросервисов
### В .env каждого звена указать, куда слать дальше:
```
CELERY_P_TASK_NAME=next_task
CELERY_P_QUEUE_NAME=next_queue
```
### В задаче после обработки отправить результат в следующую очередь
```Python
from os import getenv
from celery import Celery

app = Celery("svc")
pName  = getenv("CELERY_P_TASK_NAME")
pQueue = getenv("CELERY_P_QUEUE_NAME")

@app.task(name=getenv("CELERY_C_TASK_NAME"), queue=getenv("CELERY_C_QUEUE_NAME"))
def handle(messages):
    processed = do_work(messages)
    app.send_task(pName, args=[processed], queue=pQueue)
```
### Проверка согласованности
у продюсера ```app.send_task(name=..., queue=...)``` совпадает с ```@app.task(name=..., queue=...)``` у консюмера

# 3. Запросы к Api для получений APK файлов
Отправляем POST запрос на эндпоинт ```http://localhost/api/apk/build/```:

Headers:

```Authorization: Api-Key <your_api_key>``` <- Ваш Api-Key, который Вы создали

```Content-Type: application/json```

## Response:

### 202 Accepted - задача успешно создана

```
{
    "status": "Задача на сборку APK принята",
    "apk_build_id": "uuid-строка",
    "created_at": "2024-01-01T12:00:00Z",
    "build_status": "pending"
}
```

### 409 Conflict - сборка уже выполняется

```
{
    "error": "Build already in progress",
    "apk_build_id": "uuid-строка",
    "status": "pending"
}
```

### 401 Unauthorized - неверный или отсутствующий API ключ

Приложение начинает собираться

## Для получения статуса сборки отправляем GET запрос на эндпоинт ```http://localhost/api/apk/build/```

Headers:

```Authorization: Api-Key <your_api_key>``` <- Ваш Api-Key, который Вы создали

## Response:
### 200 OK

```
{
    "apk_build_id": "uuid-строка",
    "status": "pending|success|failed",
    "created_at": "2024-01-01T12:00:00Z",
    "completed_at": "2024-01-01T12:30:00Z"
}
```

### 404 Not Found - сборки не найдены

### 401 Unauthorized - неверный API ключ

## Для того, чтобы скачать собранный файл, отправляем GET запрос на эндпоинт ```http://localhost/api/apk/build/?action=download```

### Чтобы проверить скачается ли он, можно отправить такой запрос в cmd:

```curl -H "Authorization: Api-Key <Твой Api-Key>" -L "http://localhost/api/apk/build/?action=download" -o app.apk```

### Ключ всегда подтягивается из Api-Key, который вы используете в Headers

# 4. Запросы к Api для получений APK файлов
Отправляем POST запрос на эндпоинт ```http://localhost/api/apk/build/```:

Headers:

```Authorization: Api-Key <your_api_key>``` <- Ваш Api-Key, который Вы создали

```Content-Type: application/json```

## Response:

### 202 Accepted - задача успешно создана

```
{
    "status": "Задача на сборку APK принята",
    "apk_build_id": "uuid-строка",
    "created_at": "2024-01-01T12:00:00Z",
    "build_status": "pending"
}
```

### 409 Conflict - сборка уже выполняется

```
{
    "error": "Build already in progress",
    "apk_build_id": "uuid-строка",
    "status": "pending"
}
```

### 401 Unauthorized - неверный или отсутствующий API ключ

Приложение начинает собираться

## Для получения статуса сборки отправляем GET запрос на эндпоинт ```http://localhost/api/apk/build/```

Headers:

```Authorization: Api-Key <your_api_key>``` <- Ваш Api-Key, который Вы создали

## Response:
### 200 OK

```
{
    "apk_build_id": "uuid-строка",
    "status": "pending|success|failed",
    "created_at": "2024-01-01T12:00:00Z",
    "completed_at": "2024-01-01T12:30:00Z"
}
```

### 404 Not Found - сборки не найдены

### 401 Unauthorized - неверный API ключ

## Для того, чтобы скачать собранный файл, отправляем GET запрос на эндпоинт ```http://localhost/api/apk/build/?action=download```

### Чтобы проверить скачается ли он, можно отправить такой запрос в cmd:

```curl -H "Authorization: Api-Key <Твой Api-Key>" -L "http://localhost/api/apk/build/?action=download" -o app.apk```

### Ключ всегда подтягивается из Api-Key, который вы используете в Headers

# 5. Фильтрация

### POST ```localhost/api/filtering/```

Фильтры — в query-параметрах URL.

Полигоны — в теле запроса (JSON).

### Что передавать

В Headers прописываем:  
```Content-Type: application/json```  
```Authorization: Api-Key 0028e040-db1f-4144-b711-7011d71fbbcf``` <- Ваш Api-Key, который Вы создали

## База

``` POST http://<host>/api/filtering/?<query-params>```

## Тело (Body, raw JSON):

```json
{
  "polygons": [
    {
      "points": [
        [37.6003646850586, 55.76421316483773],
        [37.61993408203126, 55.75745221206816],
        [37.604999542236335, 55.75088330688495],
        [37.58817672729493, 55.75320187033113],
        [37.589550018310554, 55.762281583657895],
        [37.6003646850586, 55.76421316483773]
      ]
    }
  ]
}
```

## Что кладём в query (в ссылку)

### 1) Точное совпадение (term)

### Шаблон: field=value

Типы:

```строка: folder_name=test_folder```

```число: signal_strength=-62```

```булево: is_ignored=true / false```

### 2) Набор значений (terms)

### Шаблон: field=value1,value2,value3

Типы: те же, что и выше; значения разделяются запятой (без пробелов).

Примеры:

```?device_id=001A2B3C4D5E,AA:BB:CC:DD:EE:FF```

```?network_type=WiFi,LTE```

### 3) Диапазоны (range)

### Шаблон: field__op=value, где op ∈ {gte,lte,gt,lt}

Типы значений:

```числа: signal_strength__lte=-70```

```даты/время в ISO 8601: 2025-09-01T00:00:00Z```

Примеры:

```?detected_at__lt=2025-10-01T00:00:00Z```

```?signal_strength__gte=-80```

### 4) Размер выборки

### Шаблон: size=1..10000 (по умолчанию 100)

Пример:

```?size=10000```

### 5) Комбинирование фильтров

Все параметры комбинируются как AND (все условия одновременно). Пример комплексной ссылки:


```
POST /api/filtering/
  ?timestamp__gte=2025-09-01T00:00:00Z
  &device_type=apple
  &network_type=WiFi,LTE
  &is_ignored=false
  &size=10000
```

## Общие параметры фильтрации (query)

5.1. Служебные

    |Парамет|Тип|Описание|
    |---|---|---|
    |size|integer|Количество записей, максимум 10000 (по умолчанию 300)|
    |detected_at__gte, detected_at__lte|string|Альтернативное поле времени, если у устройства используется detected_at.|


5.2. Идентификаторы и связи

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |device_id-string|list (через запятую)|device_id=001A2B3C4D5E,AA:BB:CC:DD:EE:FF|Уникальный идентификатор устройства.
    |user_api|string|user_api=8e9b2e50-0a3a-4f6e-9c17-0c6d5e1b8b2c|API-ключ пользователя, к которому привязано устройство.
    |folder_name|string|folder_name=Warehouse/Back%20Yard|Имя папки/зоны, заданное пользователем.


5.3. Сетевые параметры

   |Параметр| Тип     | Пример                   |Описание|
   |---|---------|--------------------------|---|
   |network_type|string / list|network_type=WiFi,LTE|Тип сети, где зафиксировано устройство.
   |signal_strength| integer |signal_strength=-62|Уровень сигнала (в dBm).
   |signal_strength__gte / __lte| integer | signal_strength__lte=-70 |Диапазон уровня сигнала.


5.4. Атрибуты устройства

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |user_phone_mac|string|user_phone_mac=F45C89AABBCC|MAC телефона пользователя, если логируется.


5.5. Логические флаги

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |is_alert|boolean|is_alert=true|Устройство срабатывало на тревогу.
    |is_ignored|boolean|is_ignored=false|Игнорируется пользователем или нет.


5.6. Пример

    Получение всех записей в этот промежуток времени:
    
    ```/api/filtering/?detected_at__gte=2025-09-22T16:10:44Z&detected_at__lte=2025-09-22T22:10:44Z```

# 6. Отправка списка устройств в Elasticsearch

Авторизированный (по Api-Key) ```POST``` запрос на ```http://localhost/api/devices/``` со списком обнаруженных устройств

Пример:
```
import requests
import json

URL = "http://localhost/api/devices/"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Api-Key c8c65d46-2ccb-46a2-9c7d-6329614459ed",
}

DATA = [
    {
        "device_id": "00:1a:2b:3c:4d:5e",
        "latitude": 55.755826,
        "longitude": 37.617299,
        "signal_strength": -62,
        "network_type": "WiFi",
        "is_ignored": False,
        "is_alert": False,
        "user_api": "8e9b2e50-0a3a-4f6e-9c17-0c6d5e1b8b2c",
        "user_phone_mac": "00:1a:2b:3c:4d:5e",
        "detected_at": "2025-09-22T10:21:34Z",
        "folder_name": "HQ/Main Lobby",
        "system_folder_name": "hq_main_lobby"
    },
    {
        "device_id": "f4:5c:89:aa:bb:cc",
        "latitude": 59.931058,
        "longitude": 30.360909,
        "signal_strength": -78,
        "network_type": "LTE",
        "is_ignored": False,
        "is_alert": True,
        "user_api": "2a4c1e1b-7b3a-4a84-9e2f-1e9b9f0b3d77",
        "user_phone_mac": "f4:5c:89:aa:bb:cc",
        "detected_at": "2025-09-22T10:25:03Z",
        "folder_name": "Warehouse/Back Yard",
        "system_folder_name": "warehouse_back_yard"
    }
]

response = requests.post(URL, headers=HEADERS, data=json.dumps(DATA))

print("Status code:", response.status_code)
try:
    print("Response:", response.json())
except Exception:
    print("Response text:", response.text)
```
При успешной отправке возвращается 200 код и json:
```
{
  "status": "queued"
}
```
При неверном API ключе возвращается 403 ошибка и json:
```
{
    "detail": "invalid API key"
}
```

# 6. Получение устройств из Elasticsearch
Авторизированный (по Api-Key) ```GET``` запрос на ```http://localhost/api/devices/``` (допускаются фильтры)
Пример:

```
import requests
import json

URL = "http://localhost/api/devices/"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Api-Key c8c65d46-2ccb-46a2-9c7d-6329614459ed",
}

response = requests.get(URL, headers=HEADERS)

print("Status code:", response.status_code)
try:
    print("Response:", response.json())
except Exception:
    print("Response text:", response.text)
```

Пример с фильтрами:

```
import requests
import json

URL = "http://localhost/api/devices/?is_alert=true"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Api-Key c8c65d46-2ccb-46a2-9c7d-6329614459ed",
}

response = requests.get(URL, headers=HEADERS)

print("Status code:", response.status_code)
try:
    print("Response:", response.json())
except Exception:
    print("Response text:", response.text)
```
В результате вернется 200 код и json со списком устройств, соответствующих фильтрам в формате:

```
{
    "Response": [{...}, {...}, ..., {...}]
}
```

При неверном API ключе возвращается 403 ошибка и json:

```
{
    "detail": "invalid API key"
}
```

# 7. Микросервис PolygonDataGen

Потребитель Celery, который генерирует синтетические записи устройств и ПУБЛИКУЕТ их в микросервис ESWriter для индексации в Elasticsearch; примерно ~20% точек находятся внутри заданного полигона. Разработан для последующего использования в признаках на основе полигона и детектировании аномалий.

##  7.1. Переменные окружения
- `CELERY_BROKER_URL` (AMQP URL)
- `CELERY_C_TASK_NAME` (по умолчанию: `polygons.generate_data`)
- `CELERY_C_QUEUE_NAME` (по умолчанию: `polygon_gen`)
- `CELERY_CONSUMER_NAME` (например, `polygon-data-gen@%h`)
- `CELERY_LOG_LEVEL` (например, `info`)
- Маршрутизация в ESWriter:
  - `ESWRITER_TASK_NAME` (по умолчанию: `esWriter`)
  - `ESWRITER_QUEUE_NAME` (по умолчанию: `esWriter_queue`)
  - `ESWRITER_BULK_CHUNK` (по умолчанию: `2000`)

## 7.2. Сборка и запуск
```
cd microservices/PolygonDataGen
docker build -t polygon-data-gen .
# или
docker compose up -d --build
```

Compose ожидает внешнюю Docker-сеть `app-network` и файл `.env` с указанными выше переменными окружения.

## 7.3. Сигнатура задачи
Имя задачи: `polygons.generate_data` (настраивается через переменные окружения). Сервис генерирует документы и отправляет их пакетами в ESWriter. ESWriter всегда индексирует в алиас `way`.

Пример полезной нагрузки:
```json
{
  "index_name": "way",
  "mac_count": 100,
  "records_per_mac": [3000, 4000],
  "in_polygon_ratio": 0.2,
  "days_back": 30,
  "polygon_geojson": {
    "type": "Polygon",
    "coordinates": [[[37.6,55.72],[37.6,55.80],[37.75,55.80],[37.75,55.72],[37.6,55.72]]]
  },
  "tag": "polygons_gen_v1",
  "user_api": "<YOUR_API_KEY>",
  "seed": 42,
  "chunk_size": 5000
}
```

Вариант без полигона: передайте `polygon_bbox: [minx, miny, maxx, maxy]`.

## 7.4. Постановка задачи (пример, из Django API)
```python
from celery import Celery
import os

BROKER_URL = os.getenv('CELERY_BROKER_URL')
celery_client = Celery('producer', broker=BROKER_URL)

cfg = {
  "index_name": "way",
  "mac_count": 100,
  "records_per_mac": [3000, 4000],
  "in_polygon_ratio": 0.2,
  "days_back": 30,
  "polygon_geojson": {"type": "Polygon", "coordinates": [[[37.6,55.72],[37.6,55.80],[37.75,55.80],[37.75,55.72],[37.6,55.72]]]},
  "user_api": "<YOUR_API_KEY>"
}
celery_client.send_task('polygons.generate_data', args=[cfg], queue='polygon_gen')
```

## Примечание по маппингу
Маппинг индекса задаётся ESWriter (см. его логику). Сгенерированные документы содержат поля, совместимые с UI/API проекта (`device_id`, `mac`, `user_phone_mac`, `location`, `latitude/longitude`, `network_type`, `detected_at` и т. д.).

# 8. Получение API ключей пользователя, списка его устройств и папок.
## 8.1 Получение API ключей.
### Эндпоинт
```GET /api/api-key/```

### Описание
Возвращает список всех API ключей, принадлежащих текущему аутентифицированному пользователю.

### Что делает метод
- Извлекает все API ключи пользователя из базы данных
- Выбирает только поля: id, key, name
- Преобразует данные в словарь формата { "api_key": "название_ключа" }
- Возвращает данные со статусом 200 OK
### Требования к запросу
- Аутентификация: обязательна
- Параметры: не требуются
- Тело запроса: не требуется
### Статусы ответа
200 OK - успешное получение списка ключей
401 Unauthorized - пользователь не аутентифицирован
### Примечания
- Возвращаются только ключи текущего пользователя
- Для пустого списка вернется пустой объект {}

## 8.2 Получение устройств и папок.
### Эндпоинт
```POST /api/userinfo/```
### Описание
Микросервис для получения данных из Elasticsearch через Celery. В зависимости от входных данных возвращает либо список MAC-адресов устройств, либо список папок.
### Что делает метод
- Принимает данные от пользователя
- Валидирует данные через сериализатор
- Отправляет задачу в Celery:
  - Если не указаны устройства → задача getDevices (получить MAC-адреса)
  - Если указаны устройства → задача getFolders (получить папки)
- Ожидает результат (таймаут 5 секунд)
- Возвращает ответ
### Входные данные
```JSON
{
    "api_keys": ["ключ1", "ключ2"]
}
```
или
```JSON
{
    "api_keys": ["ключ1", "ключ2"],
    "devices": ["mac1", "mac2"]
}
```
### Выходные данные
```["mac1", "mac2", "mac3"]```
или
```["папка1", "папка2", "папка3"]```

## 8.3. Пример
```Python
import requests

session = requests.Session()

BASE = "http://localhost:8000"                  # один и тот же хост:порт
login_url = f"{BASE}/users/login/"              # URL страницы логина
api_url   = f"{BASE}/api/userinfo/"             # API для запроса данных

# 1️ Получаем CSRF-токен со страницы логина
r = session.get(login_url)
r.raise_for_status()
csrftoken = session.cookies.get("csrftoken")
if not csrftoken:
    raise RuntimeError("Не нашли csrftoken на странице логина")

# 2️ Логинимся (Referer обязателен)
payload = {
    "username": "example@gmail.com",             # твой логин
    "password": "admin12345",                    # твой пароль
    "csrfmiddlewaretoken": csrftoken,
}
headers = {"Referer": login_url}

r = session.post(login_url, data=payload, headers=headers, allow_redirects=False)
if r.status_code not in (200, 302):
    raise RuntimeError(f"Логин не удался, статус: {r.status_code}")

# Проверяем, что логин прошёл успешно
sessionid = session.cookies.get("sessionid")
if not sessionid:
    raise RuntimeError("Нет sessionid после логина — проверь логин/пароль и URL login_view")

print("Успешный логин. sessionid:", sessionid)

# 3 Формируем POST-запрос к API для получения устройств
payload = {
    "api_keys": ["8df33396-19cb-4ff2-9286-106e54fbb7b1"]
}

headers = {
    "Content-Type": "application/json",
    "Referer": api_url,                           # Django любит этот заголовок
    "X-CSRFToken": session.cookies.get("csrftoken"),  # возьмём CSRF из cookies
}

# 4️ Отправляем запрос
r = session.post(api_url, json=payload, headers=headers)
if r.status_code != 200:
    print("Ошибка:", r.status_code, r.text)
else:
    print("Data:", r.json())

# 5 Формируем POST-запрос к API для получения папок
payload = {
    "api_keys": ["8df33396-19cb-4ff2-9286-106e54fbb7b1"],
    "devices": ["d46e0e987654", "000C291A2B3C"]
}

headers = {
    "Content-Type": "application/json",
    "Referer": api_url,                           # Django любит этот заголовок
    "X-CSRFToken": session.cookies.get("csrftoken"),  # возьмём CSRF из cookies
}

# 6 Отправляем запрос
r = session.post(api_url, json=payload, headers=headers)
if r.status_code != 200:
    print("Ошибка:", r.status_code, r.text)
else:
    print("Data:", r.json())
```