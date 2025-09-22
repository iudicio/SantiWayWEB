import os, logging
from celery_app import app
from mac_vendor_lookup import MacLookup, AsyncMacLookup

CACHE_PATH = os.getenv("MAC_VENDOR_CACHE", "/app/cache/mac-vendors.txt")
os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)

# один кэш для обеих реализаций
MacLookup.cache_path = CACHE_PATH
AsyncMacLookup.cache_path = CACHE_PATH

mac_lookup = MacLookup()

# безопасная попытка обновить базу на старте
if os.getenv("MAC_VENDOR_UPDATE_ON_START", "true").lower() in {"1","true","yes"}:
    try:
        mac_lookup.update_vendors()
    except Exception as e:
        logging.warning("OUI update failed: %s. Continue with cached/offline data.", e)

@app.task(name='vendor', queue='process_queue')
def vendor(data):
    did = (data or {}).get('device_id')
    try:
        # добавляем поля
        data['vendor'] = mac_lookup.lookup(did) if did else None
    except Exception:
        data['vendor'] = None
    # отправляем дальше (в очередь для ES)
    app.send_task('to_es', args=[data], queue='es_queue')
    return True
