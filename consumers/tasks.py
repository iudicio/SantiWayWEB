from .celery_app import app
from mac_vendor_lookup import MacLookup

mac_lookup = MacLookup()
mac_lookup.update_vendors()  # скачает базу OUI (разово)

@app.task(name='device_preprocessing.vendor', queue='process_queue')
def vendor(data):
    # добавляем поля
    data['vendor'] = mac_lookup.lookup(data['device_id'])

    # отправляем дальше (в очередь для ES)
    app.send_task('device_processor.to_es', args=[data], queue='es_queue')

    return True

@app.task(name='device_preprocessing.to_es', queue='es_queue')
def to_es(data):
    # заглушка — тут отправка в Elasticsearch
    print('TO ES:', data)
    return True
