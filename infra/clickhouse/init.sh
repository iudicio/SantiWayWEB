#!/bin/bash
# init.sh - Скрипт инициализации ClickHouse

set -e

echo "Waiting for ClickHouse to be ready..."

# Ждём пока ClickHouse станет доступен
for i in {1..30}; do
    if clickhouse-client --host clickhouse --query "SELECT 1" &>/dev/null; then
        echo "ClickHouse is ready!"
        break
    fi
    echo "Waiting for ClickHouse... ($i/30)"
    sleep 2
done

# Выполняем SQL скрипт
echo "Creating database and tables..."
clickhouse-client --host clickhouse --multiquery < /docker-entrypoint-initdb.d/schema.sql

echo "ClickHouse initialization completed successfully!"
