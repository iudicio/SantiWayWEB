from typing import Dict, Any, Optional, List
from celery_app import app
from celery.utils.log import get_task_logger
from build_apk import log_api_key

log = get_task_logger(__name__)


@app.task(name='apkbuild.log_api_key')
def log_api_key_task(api_key: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Таска для логирования одиночного API ключа."""
    try:
        res = log_api_key(api_key, metadata=metadata)
        log.info(f"API key logged successfully: {res['data']['api_key_masked']}")
        return res
    except Exception as e:
        log.error(f"Failed to log API key: {str(e)}")
        return {"logged": False, "error": str(e)}


@app.task(name='apkbuild.log_batch_api_keys')
def log_batch_api_keys_task(api_keys: List[str], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Таска для пакетного логирования API ключей."""
    results = []
    error_count = 0

    for i, key in enumerate(api_keys):
        try:
            key_metadata = {
                "batch_index": i,
                "total_keys": len(api_keys),
                **(metadata or {})
            }
            result = log_api_key(key, metadata=key_metadata)
            results.append(result)
        except Exception as e:
            error_count += 1
            log.error(f"Failed to log API key at index {i}: {str(e)}")
            results.append({"logged": False, "error": str(e)})

    log.info(f"Batch processing completed: {len(api_keys)} keys, {error_count} errors")

    return {
        "processed": len(api_keys),
        "successful": len(api_keys) - error_count,
        "errors": error_count,
        "results": results
    }