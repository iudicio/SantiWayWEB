import clickhouse_connect
from clickhouse_connect.driver.client import Client
import re
from typing import List, Dict, Any, Optional, Union
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from backend.utils.config import settings
import asyncio
from functools import wraps


def async_retry(func):
    """Decorator to run sync function in async context with retry logic"""
    @wraps(func)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, logger.level("WARNING").no)
    )
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper


class ClickHouseClient:
    """Async-compatible клиент для работы с ClickHouse используя clickhouse-connect"""

    def __init__(self):
        self.client: Optional[Client] = None
        self._connection_params = {
            'host': settings.CLICKHOUSE_HOST,
            'port': settings.CLICKHOUSE_PORT,
            'username': settings.CLICKHOUSE_USER,
            'password': settings.CLICKHOUSE_PASSWORD,
            'database': settings.CLICKHOUSE_DATABASE,
        }

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, logger.level("WARNING").no)
    )
    async def connect(self):
        """
        Установка соединения с retry logic

        Retry strategy:
        - Max attempts: 5
        - Exponential backoff: 2s -> 4s -> 8s -> 16s -> 30s
        - Retry on: ConnectionError, TimeoutError, OSError
        """
        try:
            loop = asyncio.get_event_loop()
            self.client = await loop.run_in_executor(
                None,
                lambda: clickhouse_connect.get_client(**self._connection_params)
            )
            logger.info(
                f"Connected to ClickHouse: {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}"
            )
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {e}")
            raise

    async def disconnect(self):
        """Закрытие соединения"""
        if self.client:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.client.close)
            logger.info("ClickHouse connection closed")

    async def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Выполнение запроса без результата с защитой от SQL injection

        Args:
            query: SQL запрос с placeholders {name:Type}
            parameters: Словарь параметров для подстановки
        """
        if not self.client:
            raise RuntimeError("ClickHouse client is not connected")

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.command(query, parameters=parameters or {})
            )
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, logger.level("WARNING").no)
    )
    async def query(
        self,
        query: str,
        parameters: Optional[Union[List[Any], Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Выполнение SELECT запроса с защитой от SQL injection и retry logic

        Retry strategy:
        - Max attempts: 3
        - Exponential backoff: 1s -> 2s -> 4s -> 10s
        - Retry on: ConnectionError, TimeoutError, OSError

        Args:
            query: SQL запрос с placeholders {name:Type}
            parameters: Словарь параметров для подстановки

        Returns:
            List of dictionaries с результатами
        """
        if not self.client:
            raise RuntimeError("ClickHouse client is not connected")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.query(query, parameters=parameters or {})
            )

            rows: List[Dict[str, Any]] = []
            if result.result_rows:
                columns = result.column_names
                for row in result.result_rows:
                    rows.append(dict(zip(columns, row)))

            return rows
        except Exception as e:
            logger.error(f"Query failed: {e}\nQuery: {query}\nParams: {parameters}")
            raise

    async def insert(
        self,
        table: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        Вставка данных с batching и защитой от SQL injection

        Args:
            table: Имя таблицы (ВАЛИДИРУЕТСЯ, не параметризуется)
            data: Список словарей с данными
            batch_size: Размер batch для вставки

        Returns:
            Количество вставленных строк
        """
        if not self.client:
            raise RuntimeError("ClickHouse client is not connected")

        if not data:
            return 0

        if not self._is_valid_identifier(table):
            raise ValueError(f"Invalid table name: {table}")

        try:
            columns = list(data[0].keys())

            for col in columns:
                if not self._is_valid_identifier(col):
                    raise ValueError(f"Invalid column name: {col}")

            total_inserted = 0
            loop = asyncio.get_event_loop()

            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]

                values = [[row.get(col) for col in columns] for row in batch]
                def _do_insert(t, v, c):
                    return self.client.insert(t, v, column_names=c)

                await loop.run_in_executor(None, _do_insert, table, values, columns)
                total_inserted += len(batch)

            logger.info(f"Inserted {total_inserted} rows into {table}")
            return total_inserted

        except Exception as e:
            logger.error(f"Insert failed: {e}")
            raise

    async def initialize_schema(self):
        """
        Инициализация схемы БД из SQL файлов (idempotent)
        Запускает schema.sql и views.sql если они существуют
        """
        from pathlib import Path

        schema_files = [
            Path('clickhouse/schema.sql'),
            Path('clickhouse/views.sql'),
        ]

        for sql_file in schema_files:
            if not sql_file.exists():
                logger.warning(f"Schema file not found: {sql_file}, skipping...")
                continue

            try:
                logger.info(f"Executing schema file: {sql_file}")
                sql_content = sql_file.read_text()
                statements = [s.strip() for s in sql_content.split(';') if s.strip()]

                loop = asyncio.get_event_loop()
                for statement in statements:
                    if statement:
                        await loop.run_in_executor(
                            None,
                            lambda s=statement: self.client.command(s)
                        )

                logger.info(f"Successfully executed {sql_file}")

            except Exception as e:
                logger.error(f"Failed to execute {sql_file}: {e}")
                logger.warning(f"Continuing despite error (schema might already exist)")

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """
        Валидация имен таблиц/колонок для защиты от SQL injection
        Разрешены: буквы, цифры, подчеркивания, точки (для db.table)
        """
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$'
        return bool(re.match(pattern, name))


ch_client = ClickHouseClient()
