from celery_app import app

if __name__ == "__main__":
    # Пример данных
    data = [
    {"device_id": "00:00:0C:12:34:56"},
    {"device_id": "F0-9F-C2-11-22-33"},
    {"device_id": "001A.2B12.3456"},
    {"device_id": "badmac"},
    ]

    # Отправляем задачу в очередь vendor
    result = app.send_task("vendor", args=[data], queue="preprocessor_queue")
    print("Task sent! ID:", result.id)
