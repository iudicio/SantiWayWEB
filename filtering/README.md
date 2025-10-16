# Фильтрация

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

1. Служебные

    |Парамет|Тип|Описание|
    |---|---|---|
    |size|integer|Количество записей, максимум 10000 (по умолчанию 300)|
    |detected_at__gte, detected_at__lte|string|Альтернативное поле времени, если у устройства используется detected_at.|


2. Идентификаторы и связи

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |device_id-string|list (через запятую)|device_id=001A2B3C4D5E,AA:BB:CC:DD:EE:FF|Уникальный идентификатор устройства.
    |user_api|string|user_api=8e9b2e50-0a3a-4f6e-9c17-0c6d5e1b8b2c|API-ключ пользователя, к которому привязано устройство.
    |folder_name|string|folder_name=Warehouse/Back%20Yard|Имя папки/зоны, заданное пользователем.


3. Сетевые параметры

   |Параметр| Тип     | Пример                   |Описание|
   |---|---------|--------------------------|---|
   |network_type|string / list|network_type=WiFi,LTE|Тип сети, где зафиксировано устройство.
   |signal_strength| integer |signal_strength=-62|Уровень сигнала (в dBm).
   |signal_strength__gte / __lte| integer | signal_strength__lte=-70 |Диапазон уровня сигнала.


4. Атрибуты устройства

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |user_phone_mac|string|user_phone_mac=F45C89AABBCC|MAC телефона пользователя, если логируется.


5. Логические флаги

    |Параметр|Тип|Пример|Описание|
    |---|---|---|---|
    |is_alert|boolean|is_alert=true|Устройство срабатывало на тревогу.
    |is_ignored|boolean|is_ignored=false|Игнорируется пользователем или нет.


6. Пример

    Получение всех записей в этот промежуток времени:
    
    ```/api/filtering/?detected_at__gte=2025-09-22T16:10:44Z&detected_at__lte=2025-09-22T22:10:44Z```