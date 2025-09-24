# Берём официальный RabbitMQ с Management
FROM rabbitmq:3.12-management

# Копируем конфигурацию
COPY rabbitmq.conf /etc/rabbitmq/rabbitmq.conf
COPY definitions.json /etc/rabbitmq/definitions.json

# Включаем необходимые плагины
RUN rabbitmq-plugins enable --offline rabbitmq_management

# Порты для брокера и Management UI
EXPOSE 5672 15672
