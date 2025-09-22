import os
import json
import logging
from typing import Dict, List
from celery_app import app

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VENDOR_JSON = os.getenv("MAC_VENDOR_JSON", "mac-vendors.json")

def _norm_hex(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch in "0123456789ABCDEF")

def _load_vendor_index(path: str) -> Dict[str, str]:
    """Загружаем только MA-L (/24)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    m24: Dict[str, str] = {}
    for item in data:
        try:
            raw = item["macPrefix"]       # "00:00:0C"
            vendor = item["vendorName"]
        except KeyError:
            continue
        clean = _norm_hex(raw)
        if len(clean) == 6:  # только первые 3 байта
            key = ":".join([clean[0:2], clean[2:4], clean[4:6]])
            m24[key] = vendor
    return m24

try:
    M24 = _load_vendor_index(VENDOR_JSON)
    log.info("Vendors loaded: %d entries", len(M24))
except Exception as e:
    log.exception("Failed to load vendor DB '%s': %s", VENDOR_JSON, e)
    M24 = {}

def _vendor_by_device_id(device_id: str) -> str | None:
    if not isinstance(device_id, str):
        return None
    clean = _norm_hex(device_id)
    if len(clean) < 6:
        return None
    prefix = ":".join([clean[0:2], clean[2:4], clean[4:6]])
    return M24.get(prefix)

@app.task(name="vendor", queue="process_queue")
def vendor(devices: List[dict]) -> int:
    """
    Принимает список устройств, достаёт MAC из поля `device_id`,
    берёт только первые 3 байта, ищет в словаре MA-L,
    добавляет поле vendor и отправляет весь список одним батчем.
    """
    if not isinstance(devices, list):
        log.warning("Expected list[dict], got %s", type(devices))
        return 0

    processed = 0
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        vend = _vendor_by_device_id(dev.get("device_id", ""))
        dev["vendor"] = vend
        processed += 1

    app.send_task("to_es", args=[devices], queue="es_queue")
    return processed
