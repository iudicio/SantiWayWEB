# WAY Elasticsearch

Готовая инфраструктура для индексов `way-*` в Elasticsearch:
- **ILM** с ротацией по **100 млн** документов на индекс;
- **Composable Index Template** с **строгим маппингом**;
- **Ingest-pipeline** для нормализации MAC и сборки `geo_point`;
- **Alias** `way` с write-index для записи и управляемого ролловера.


---

## Структура репозитория

```
infra/elasticsearch/
├─ docker-compose.yml
├─ bootstrap.sh
├─ README.md            ← этот файл
├─ ilm/
│  └─ way-100m.policy.json
├─ templates/
│  └─ way.index-template.json
└─ pipelines/
   └─ way.normalize.json
```

---

## Требования

- Docker & Docker Compose (Compose V2).  
- `curl` (и опционально `jq` для удобного вывода).  
- Порт `9200` свободен на хосте.

---

## Быстрый старт (локально)

```bash
docker compose -f infra/elasticsearch/docker-compose.yml up -d
bash infra/elasticsearch/bootstrap.sh
```

Скрипт **`bootstrap.sh`** выполняет:
1. Публикует ILM‑политику `way-rollover-100m` (ролловер при 100 млн документов).
2. Создаёт ingest‑pipeline `way-normalize` (нормализация MAC, сборка `geo_point`).
3. Создаёт index‑template `way-template` (маппинг, normalizer, sort by `detected_at`).
4. Создаёт стартовый индекс `way-000001` и назначает alias `way` с `is_write_index=true`.

> Можно переопределить адрес кластера:  
> `ES_URL=http://127.0.0.1:9200 bash infra/elasticsearch/bootstrap.sh`

---

## Как это работает (коротко)

- **Alias `way`** — точка записи. ILM выполняет **rollover**: `way-000001 → way-000002 → …` при достижении лимита документов.
- **Index Template** задаёт **маппинг** и настройки: `dynamic: "strict"`, сортировку по времени, `default_pipeline: way-normalize`.
- **Ingest Pipeline `way-normalize`** — очищает MAC от `:.-` и формирует `location` из `longitude/latitude`.
- **ILM Policy** отвечает только за ротацию (по `max_docs: 100_000_000`).

---

## Модель данных (маппинг)

| Поле                  | Тип           | Описание                                                                 |
|-----------------------|---------------|--------------------------------------------------------------------------|
| `device_id`           | `keyword`     | Идентификатор устройства / MAC (lowercase, без `:.-`).                   |
| `user_phone_mac`      | `keyword`     | MAC телефона пользователя (тот же режим нормализации).                   |
| `latitude`            | `float`       | Широта.                                                                  |
| `longitude`           | `float`       | Долгота.                                                                 |
| `location`            | `geo_point`   | Геоточка, формируется пайплайном `way-normalize`.                         |
| `signal_strength`     | `short`       | RSSI в dBm (диапазон ~ −120…0). Если нужны дроби — используйте `scaled_float` с `scaling_factor: 10`. |
| `network_type`        | `keyword`     | Тип сети: `wifi` / `bluetooth` / `gsm` (lowercase).                      |
| `is_ignored`          | `boolean`     | Флаг игнорирования устройства.                                           |
| `is_alert`            | `boolean`     | Флаг «alert».                                                            |
| `user_api`            | `keyword`     | Идентификатор/ключ пользователя, отправившего событие.                   |
| `detected_at`         | `date`        | Время обнаружения (`strict_date_optional_time` или `epoch_millis`).      |
| `folder_name`         | `keyword`     | Бизнес‑метка «Название папки».                                           |
| `system_folder_name`  | `keyword`     | Системное название папки.                                                |

---

## Проверки и отладка

**Проверить, что шаблон применяется к индексу**
```bash
curl -s -X POST localhost:9200/_index_template/_simulate_index/way-000777 | jq .
```

**Симуляция пайплайна**
```bash
curl -s -X POST localhost:9200/_ingest/pipeline/way-normalize/_simulate   -H 'Content-Type: application/json' -d '{
  "docs":[{"_source":{"device_id":"AA:BB-CC.DD:EE-FF","latitude":55.75,"longitude":37.62}}]
}' | jq .
```

**Тестовая запись**
```bash
curl -X POST localhost:9200/way/_doc   -H 'Content-Type: application/json' -d '{
  "device_id":"AA:BB:CC:DD:EE:FF",
  "latitude":55.75, "longitude":37.62,
  "signal_strength":-67,
  "network_type":"wifi",
  "is_ignored": false,
  "is_alert":   false,
  "user_api": "api_123",
  "detected_at": 1737571200000,
  "folder_name":"Moscow",
  "system_folder_name":"msk"
}'
```

---

## Ролловер и ILM

**Dry‑run ролловера**
```bash
curl -s -X POST "localhost:9200/way/_rollover?dry_run=true" | jq .
```

**Фактический ролловер**
```bash
curl -s -X POST localhost:9200/way/_rollover   -H 'Content-Type: application/json' -d '{
  "conditions": { "max_docs": 100000000 }
}' | jq .
```

---
