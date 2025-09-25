import vendorsFunc
from typing import Dict, Any, Iterable
from celery_app import app

base = vendorsFunc.load_vendors("mac-vendors.json")

@app.task(name="vendor", queue="vendor_queue")
def vendor(messages: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """
    Принимает список устройств, достаёт MAC из поля `device_id`,
    берёт только первые 3 байта, ищет в словаре
    добавляет поле vendor и отправляет весь список одним батчем.
    """
    processed = 0
    global base
    for msg in messages:
            mac_val = msg.get("device_id")
            if isinstance(mac_val, str):
                try:
                    oui = vendorsFunc.mac_to_oui(mac_val)
                    msg["vendor"] = base.get(oui, "Unknown")
                except Exception:
                    msg["vendor"] = "Unknown"
            else:
                msg["vendor"] = "Unknown"
            processed += 1

    app.send_task("esWriter", args=[messages], queue="es_writer")
    return processed
