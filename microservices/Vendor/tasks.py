import vendorsFunc
from typing import Dict, Any, Iterable, List
from celery_app import app
from os import getenv

base = vendorsFunc.load_vendors("mac-vendors.json")

cName = getenv("CELERY_C_TASK_NAME")
cQueue = getenv("CELERY_C_QUEUE_NAME")

pName = getenv("CELERY_P_TASK_NAME")
pQueue = getenv("CELERY_P_QUEUE_NAME")

chName = getenv("CELERY_CH_TASK_NAME", "chWriter")
chQueue = getenv("CELERY_CH_QUEUE_NAME", "chWriter_queue")

@app.task(name=cName, queue=cQueue)
def vendor(messages: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """
    Принимает список устройств, достаёт MAC из поля `device_id`,
    берёт только первые 3 байта, ищет в словаре
    добавляет поле vendor и отправляет весь список одним батчем.

    Данные отправляются ПАРАЛЛЕЛЬНО в:
    - ESWriter (Elasticsearch)
    - CHWriter (ClickHouse)
    """
    processed = 0
    global base

    messages_list: List[Dict[str, Any]] = list(messages) if not isinstance(messages, list) else messages

    for msg in messages_list:
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

    app.send_task(name=pName, args=[messages_list], queue=pQueue)

    app.send_task(name=chName, args=[messages_list], queue=chQueue)

    return print(f"Выполнено {processed}, отправлено в {pQueue} и {chQueue}")
