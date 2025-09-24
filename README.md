"# SantiWayWEB" 

docker compose up -d --build

Django admin: При сборке и запуске суперпользователь создаётся автоматически.
Username: admin@example.com
Password: admin

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
## Если Вы все сделали по порядку, и видите, как все контейнеры запущены, то Вы молодец!
Итак, мы имеем поднятый WEB сервер + микросервисы

# Создание Api ключа
1. При поднятом сервере пишем в поисковую строку ```http://localhost/users/registration```
2. Регистрируемся и нас сразу логинит в аккаунт
3. Жмем кнопку New Key, вводим какое хотим имя и создаем ключ
## Поздравляем! Вы создали свой первый Api-Key!
Теперь научимся делать запросы к Api с помощью Api-key

# 2. Запросы к Api для самых маленьких
Запросы к Api не получится сделать, не имея Api-Key, потому что эндпоинты защищены  
Чтобы отправить список просканированных устройств в очередь обработки и записи в Elasticsearch нужно отправить POST запрос на эндпоинт ```http://localhost/api/devices/```:  
В Headers прописываем:  
```Content-Type: application/json```  
```Authorization: Api-Key 0028e040-db1f-4144-b711-7011d71fbbcf``` <- Ваш Api-Key, который Вы создали  
В Body прописываем список обнаруженных устройств, например:
```[
  {
    "device_id": "00:1A:2B:3C:4D:5E",
    "latitude": 55.755826,
    "longitude": 37.617299,
    "signal_strength": -62,
    "network_type": "WiFi",
    "is_ignored": false,
    "is_alert": false,
    "user_api": "8e9b2e50-0a3a-4f6e-9c17-0c6d5e1b8b2c",
    "user_phone_mac": "00:1A:2B:3C:4D:5E",
    "detected_at": "2025-09-22T10:21:34Z",
    "folder_name": "HQ/Main Lobby",
    "system_folder_name": "hq_main_lobby"
  },
  {
    "device_id": "F4:5C:89:AA:BB:CC",
    "latitude": 59.931058,
    "longitude": 30.360909,
    "signal_strength": -78,
    "network_type": "LTE",
    "is_ignored": false,
    "is_alert": true,
    "user_api": "2a4c1e1b-7b3a-4a84-9e2f-1e9b9f0b3d77",
    "user_phone_mac": "F4:5C:89:AA:BB:CC",
    "detected_at": "2025-09-22T10:25:03Z",
    "folder_name": "Warehouse/Back Yard",
    "system_folder_name": "warehouse_back_yard"
  }
]
```
### Этот пункт можно пропустить, если Вам не интересно какой путь проделывает ваше сообщение
- После отправки запроса мы можем проследить, как наше сообщение идет по очереди. Достаточно зайти в логи контейнера vendor. Там Вы увидите что-то типа  
```Task vendor[631a4a3a-f909-4015-8b5c-c6f157fc2af7] succeeded in 0.020938121999961368s: 2```  
Нам нужно последнее число (у меня двоечка). Если у Вас оно соответствует числу отправленных устройств, то этот этап пройден и мы знаем производителя устройств.
- После определения производителя можем записывать устройство в Elasticsearch. Заходим в логи контейнера es-writer и видим
```Task esWriter[2b169cb8-57d6-4e93-aadd-2d3e013bf0b8] succeeded in 0.2044868770001358s: {'indexed': 2, 'errors_count': 0, 'errors_sample': []}```
Если indexed = числу устройств, то все хорошо и данные поступили в Elasticsearch.

### Получение данных из ElasticSearch
Отправляем GET запрос на эндпоинт ```http://localhost/api/devices/```:
В Headers прописываем:
```Authorization: Api-Key 0028e040-db1f-4144-b711-7011d71fbbcf``` <- Ваш Api-Key, который Вы создали
Получаем в ответ список устройств, которые есть в Elasticsearch

Если хотим получить список устройств с фильтрами прописываем их прямо в эндпоинт, например  
GET ```http://localhost/api/devices/?is_alert=true```  
Получим список устройств, у которых включена тревога



