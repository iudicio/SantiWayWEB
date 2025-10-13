from os import getenv
from typing import Any, Dict, Iterable

import vendorsFunc
from celery_app import app

base = vendorsFunc.load_vendors("mac-vendors.json")

cName = getenv("CELERY_C_TASK_NAME")
cQueue = getenv("CELERY_C_QUEUE_NAME")

pName = getenv("CELERY_P_TASK_NAME")
pQueue = getenv("CELERY_P_QUEUE_NAME")


@app.task(name=cName, queue=cQueue)
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

    app.send_task(name=pName, args=[messages], queue=pQueue)
    return print(f"Выполнено {processed}, отправлено в {pQueue}")
