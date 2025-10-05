import json
from typing import Dict, Any, Iterable, List

# ---- Быстрый парсер MAC → OUI (24 бита) ----
_HEXMAP = [-1] * 256
for i, ch in enumerate("0123456789ABCDEF"):
    _HEXMAP[ord(ch)] = i
    _HEXMAP[ord(ch.lower())] = i

def mac_to_oui(mac: str) -> int:
    """
    Берёт MAC-адрес в любом формате (00:1A:2B:12:34:56, 00-1A-2B-..., 001A2B123456)
    и возвращает OUI как целое число.
    """
    v = 0
    count = 0
    for ch in mac:
        h = _HEXMAP[ord(ch)]
        if h >= 0:
            v = (v << 4) | h
            count += 1
            if count == 6:   # достаточно 6 hex-символов (3 байта)
                return v
    raise ValueError(f"Некорректный MAC: {mac!r}")

# ---- Загрузка базы ----
def load_vendors(filepath: str) -> Dict[int, str]:
    """
    Загружает mac-vendors.json и возвращает словарь { OUI_int: vendorName }.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    vendors: Dict[int, str] = {}
    for entry in data:
        prefix = entry.get("macPrefix")
        vendor = entry.get("vendorName")
        if not prefix or not vendor:
            continue
        try:
            oui = mac_to_oui(prefix)
        except ValueError:
            continue
        vendors[oui] = vendor  # последнее вхождение перезапишет
    return vendors

# ---- Обогащение входящего сообщения ----
def enrich_with_vendor(messages: Iterable[Dict[str, Any]],
                       vendors: Dict[int, str],
                       mac_field: str = "device_id",
                       out_field: str = "vendor") -> Iterable[Dict[str, Any]]:
    """
    Добавляет к сообщению производителя по MAC.
    """
    for msg in messages:
            mac_val = msg.get(mac_field)
            if isinstance(mac_val, str):
                try:
                    oui = mac_to_oui(mac_val)
                    msg[out_field] = vendors.get(oui, "Unknown")
                except Exception:
                    msg[out_field] = "Unknown"
            else:
                msg[out_field] = "Unknown"
    return messages