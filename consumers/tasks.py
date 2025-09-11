from celery_app import app
from mac_vendor_lookup import MacLookup, AsyncMacLookup

AsyncMacLookup.cache_path = "/app/mac-vendors.txt"

mac_lookup = MacLookup()
mac_lookup.update_vendors()  # скачает базу OUI (разово)

@app.task(name='vendor', queue='process_queue')
def vendor(data):
    # добавляем поля
    data['vendor'] = mac_lookup.lookup(data['device_id'])

    # отправляем дальше (в очередь для ES)
    app.send_task('to_es', args=[data], queue='es_queue')

    return True
