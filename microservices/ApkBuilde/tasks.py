from typing import Dict, Any
from celery_app import app
from celery.utils.log import get_task_logger

log = get_task_logger(__name__)


@app.task(name='apkbuild', queue='apkbuilder')
def log_api_key_task(messages: Dict[str, Any]):
    api_key = messages.get("key")
    if api_key:
        try:
            log.info(f"Твой aoi-key принят: {api_key}")
        except Exception:
            log.error("Ошибка при логировании API ключа")
    return {"status": "okey", "api_key": api_key}