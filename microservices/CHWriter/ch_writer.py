from typing import List, Dict, Any, Optional
from os import getenv
from datetime import datetime
import clickhouse_connect
from clickhouse_connect.driver import Client

CH_HOST = getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT = int(getenv("CLICKHOUSE_PORT", "8123"))
CH_USER = getenv("CLICKHOUSE_USER", "default")
CH_PASSWORD = getenv("CLICKHOUSE_PASSWORD", "")
CH_DATABASE = getenv("CLICKHOUSE_DATABASE", "santi")
CH_TABLE = getenv("CLICKHOUSE_TABLE", "way_data")

try:
    CH_CLIENT: Client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE,
    )
    print(f"ClickHouse client connected to {CH_HOST}:{CH_PORT}/{CH_DATABASE}")
except Exception as e:
    print(f"ClickHouse connection failed: {e}")
    CH_CLIENT = None


def parse_datetime(dt_value: Any) -> str:
    """
    Парсит дату в формат ClickHouse DateTime (YYYY-MM-DD HH:MM:SS).

    Поддерживает:
    - ISO 8601 строки: "2025-12-04T10:30:00Z" или "2025-12-04T10:30:00+00:00"
    - datetime объекты
    - Обычные строки: "2025-12-04 10:30:00"

    Args:
        dt_value: Значение даты (строка или datetime)

    Returns:
        Строка в формате "YYYY-MM-DD HH:MM:SS"
    """
    if isinstance(dt_value, datetime):
        return dt_value.strftime('%Y-%m-%d %H:%M:%S')

    if isinstance(dt_value, str):
        dt_str = dt_value.replace('Z', '+00:00')

        try:
            if 'T' in dt_str:
                dt = datetime.fromisoformat(dt_str)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                return dt_str
        except (ValueError, AttributeError):
            return "1970-01-01 00:00:00"

    return "1970-01-01 00:00:00"


def validate_document(doc: Dict[str, Any]) -> Optional[str]:
    """
    Валидирует документ перед вставкой в ClickHouse.

    Args:
        doc: Документ для валидации

    Returns:
        None если документ валиден, иначе строка с описанием ошибки
    """
    required_fields = {
        'device_id': str,
        'latitude': (int, float),
        'longitude': (int, float),
        'detected_at': (str, datetime),
    }

    for field, expected_types in required_fields.items():
        if field not in doc:
            return f"Missing required field: {field}"

        value = doc[field]
        if value is None:
            return f"Field {field} cannot be None"

        if not isinstance(value, expected_types):
            return f"Field {field} has invalid type: expected {expected_types}, got {type(value)}"

        if field == 'device_id' and isinstance(value, str):
            if len(value.strip()) == 0:
                return "device_id cannot be empty"

        if field in ['latitude', 'longitude']:
            if field == 'latitude' and not (-90 <= value <= 90):
                return f"latitude out of range: {value}"
            if field == 'longitude' and not (-180 <= value <= 180):
                return f"longitude out of range: {value}"

    return None


def insert_docs_to_way(docs: List[Dict[str, Any]], *, chunk_size: int = 2000) -> Dict[str, Any]:
    """
    Вставляет документы в таблицу ClickHouse батчами.

    Args:
        docs: Список документов для вставки
        chunk_size: Размер батча для вставки

    Returns:
        Словарь с результатами: {inserted: int, errors_count: int, errors_sample: list}
    """
    if not CH_CLIENT:
        return {
            "inserted": 0,
            "errors_count": len(docs),
            "errors_sample": [{"error": "ClickHouse client not initialized"}]
        }

    if not docs:
        return {"inserted": 0, "errors_count": 0, "errors_sample": []}

    inserted = 0
    errors = []
    skipped = 0

    try:
        columns = [
            "device_id",
            "user_phone_mac",
            "latitude",
            "longitude",
            "signal_strength",
            "network_type",
            "is_ignored",
            "is_alert",
            "user_api",
            "detected_at",
            "folder_name",
            "system_folder_name",
            "vendor"
        ]

        for i in range(0, len(docs), chunk_size):
            batch = docs[i:i + chunk_size]

            rows = []
            for doc_idx, doc in enumerate(batch):
                validation_error = validate_document(doc)
                if validation_error:
                    error_detail = {
                        "doc_index": i + doc_idx,
                        "error": f"Validation failed: {validation_error}",
                        "device_id": doc.get("device_id", "unknown")
                    }
                    errors.append(error_detail)
                    skipped += 1
                    continue

                detected_at_parsed = parse_datetime(doc.get("detected_at"))

                row = [
                    doc.get("device_id", ""),
                    doc.get("user_phone_mac", ""),
                    doc.get("latitude", 0.0),
                    doc.get("longitude", 0.0),
                    doc.get("signal_strength", 0),
                    doc.get("network_type", ""),
                    1 if doc.get("is_ignored") else 0,
                    1 if doc.get("is_alert") else 0,
                    doc.get("user_api", ""),
                    detected_at_parsed,
                    doc.get("folder_name", ""),
                    doc.get("system_folder_name", ""),
                    doc.get("vendor", "Unknown")
                ]
                rows.append(row)

            if rows:
                try:
                    CH_CLIENT.insert(
                        table=CH_TABLE,
                        data=rows,
                        column_names=columns
                    )
                    inserted += len(rows)
                except Exception as e:
                    error_detail = {
                        "batch_start": i,
                        "batch_size": len(batch),
                        "error": str(e)
                    }
                    errors.append(error_detail)
                    print(f"ClickHouse insert error: {error_detail}")

        if skipped > 0:
            print(f"Skipped {skipped} invalid documents")
        if inserted > 0:
            print(f"Inserted {inserted} documents to ClickHouse")

    except Exception as e:
        errors.append({"error": f"General error: {str(e)}"})
        print(f"✗ ClickHouse operation failed: {e}")

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors_count": len(errors),
        "errors_sample": errors[:5]  
    }
