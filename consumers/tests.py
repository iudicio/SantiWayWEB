from celery_app import app

if __name__ == "__main__":
    # Пример данных
    data = {"device_id": "44:38:39:ff:ef:57"}

    # Отправляем задачу в очередь vendor
    result = app.send_task("vendor", args=[data], queue="process_queue")
    print("Task sent! ID:", result.id)
