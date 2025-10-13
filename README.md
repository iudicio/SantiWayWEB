"# SantiWayWEB" 

docker compose up -d --build

Django admin: При сборке и запуске суперпользователь создаётся автоматически.
Username: admin@example.com
Password: admin

Чтобы сборка APK работала необходимо в microservices/ApkBuilde создать папку keystore (если нет) и 
добавить в нее файл, что Влад кидал в группу ("release.jsx").

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
Теперь научимся делать запросы к Api с помощью Api-key

# 2. Запросы к Api для получений APK файлов
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

# 3. Отправка списка устройств в Elasticsearch

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

# 4. Получение устройств из Elasticsearch
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

# 5. Получение информации о пользователе (Список Api-Key's, Устройств, Папок)
## 5.1 Список ключей
С postgres подгружается список ключей, которые есть у пользователя
Авторизированный (CORS) ```GET``` запрос на ```http://localhost/api/api-key/```
Возвращает json в формате:

```
{
    "Api-Key-name": "Api-key",
    "Api-Key-name2": "api-key"
}
```

## 5.2 Список устройств и папок пользователя
Микросервис из Elasticsearch подгружает список устройств и папок в зависимости от содержания отправленных данных
Авторизованный (CORS) ```POST``` запрос на ```http://localhost/api/userinfo/```
Тело запроса:

```
{
    "api_keys": "api-key1", "api-key2",
    "devices": "mac1", "mac2", "mac3"
}
```

### Поле ```devices``` может отсутствовать, тогда вернется json:

```
{
    ["mac1", "mac2"...]
}
```

### Если поле ```devices``` присутствует, тогда вернется json:

```
{
    ["folder1", "folder2"...]
}
```

### Поле ```api_keys``` является обязательным