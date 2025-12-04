import clickhouse_connect
from clickhouse_connect.driver import Client
from typing import List, Dict, Any, Optional
from loguru import logger
from backend.utils.config import settings

class ClickHouseClient:
    """Async клиент для работы с ClickHouse"""

    def __init__(self):
        self.client: Optional[Client] = None

    async def connect(self):
        """Установка соединения"""
        try:
            self.client = clickhouse_connect.get_client(
                host=settings.CLICKHOUSE_HOST,
                port=settings.CLICKHOUSE_PORT,
                username=settings.CLICKHOUSE_USER,
                password=settings.CLICKHOUSE_PASSWORD,
                database=settings.CLICKHOUSE_DATABASE,
            )
            logger.info(f"Connected to ClickHouse: {settings.CLICKHOUSE_HOST}")
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {e}")
            raise

    async def disconnect(self):
        """Закрытие соединения"""
        if self.client:
            self.client.close()
            logger.info("ClickHouse connection closed")

    async def execute(self, query: str) -> None:
        """Выполнение запроса без результата"""
        try:
            assert self.client is not None, "ClickHouse client is not connected"
            self.client.command(query)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    async def query(self, query: str) -> List[Dict[str, Any]]:
        """Выполнение SELECT запроса"""
        try:
            assert self.client is not None, "ClickHouse client is not connected"
            result = self.client.query(query)
            columns = result.column_names
            rows: List[Dict[str, Any]] = []
            for row in result.result_rows:
                rows.append(dict(zip(columns, row)))
            return rows
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise

    async def insert(self, table: str, data: List[Dict[str, Any]]) -> int:
        """Вставка данных"""
        try:
            assert self.client is not None, "ClickHouse client is not connected"
            if not data:
                return 0

            columns = list(data[0].keys())

            values = [[row.get(col) for col in columns] for row in data]

            self.client.insert(table, values, column_names=columns)

            logger.info(f"Inserted {len(data)} rows into {table}")
            return len(data)
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            raise

ch_client = ClickHouseClient()
