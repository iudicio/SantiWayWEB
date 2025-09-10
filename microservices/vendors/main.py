import os
from confluent_kafka import Consumer, Producer
from mac_vendor_lookup import MacLookup
import json

KAFKA_BROKER = os.getenv("KAFKA_BROKER")
TOPIC_IN = os.getenv("TOPIC_IN")
TOPIC_OUT = os.getenv("TOPIC_OUT")

mac_lookup = MacLookup()
mac_lookup.update_vendors()

def get_vendor(mac):
    try:
        return mac_lookup.lookup(mac)
    except Exception:
        return "Unknown"

producer = Producer({'bootstrap.servers': KAFKA_BROKER})

def delivery_report(err, msg):
    if err is not None:
        print('Message delivery failed:', err)
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

consumer = Consumer({
    'bootstrap.servers': KAFKA_BROKER,
    'group.id': 'vendor-service',
    'auto.offset.reset': 'earliest'
})

consumer.subscribe([TOPIC_IN])

print(" [*] Waiting for messages...")
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Consumer error:", msg.error())
        continue

    data = json.loads(msg.value().decode('utf-8'))
    mac = data.get("mac")
    vendor = get_vendor(mac)

    result = {"mac": mac, "vendor": vendor}
    producer.produce(TOPIC_OUT, json.dumps(result).encode("utf-8"), callback=delivery_report)
    producer.flush()

consumer.close()
