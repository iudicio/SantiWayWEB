from asynch import connect
import re
from asynch.pool import Pool
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


class ClickHouseClient:
    """Async клиент для работы с ClickHouse с connection pooling"""

    def __init__(self):
        self.pool: Optional[Pool] = None
        self._connection_params = {
            'host': settings.CLICKHOUSE_HOST,
            'port': settings.CLICKHOUSE_PORT,
            'user': settings.CLICKHOUSE_USER,
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
        Установка connection pool с retry logic

        Retry strategy:
        - Max attempts: 5
        - Exponential backoff: 2s -> 4s -> 8s -> 16s -> 30s
        - Retry on: ConnectionError, TimeoutError, OSError
        """
        try:
            self.pool = await Pool(
                minsize=2,
                maxsize=10,
                **self._connection_params
            )
            logger.info(
                f"Connected to ClickHouse pool: {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}"
            )
        except Exception as e:
            logger.error(f"ClickHouse connection pool failed: {e}")
            raise

    async def disconnect(self):
        """Закрытие connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("ClickHouse connection pool closed")

    async def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Выполнение запроса без результата с защитой от SQL injection

        Args:
            query: SQL запрос с placeholders %(name)s
            parameters: Словарь параметров для подстановки
        """
        if not self.pool:
            raise RuntimeError("ClickHouse pool is not connected")

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, parameters or {})
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
            query: SQL запрос с placeholders %s (для списка) или %(name)s (для словаря)
            parameters: Список или словарь параметров для подстановки

        Returns:
            List of dictionaries с результатами
        """
        if not self.pool:
            raise RuntimeError("ClickHouse pool is not connected")

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    params = None
                    if parameters:
                        params = tuple(parameters) if isinstance(parameters, list) else parameters

                    await cursor.execute(query, params)
                    columns = [col[0] for col in cursor.description]
                    rows: List[Dict[str, Any]] = []
                    async for row in cursor:
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
        if not self.pool:
            raise RuntimeError("ClickHouse pool is not connected")

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

            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]

                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        placeholders = ', '.join([
                            '(' + ', '.join(['%s'] * len(columns)) + ')'
                            for _ in batch
                        ])

                        values = []
                        for row in batch:
                            values.extend([row.get(col) for col in columns])

                        insert_query = (
                            f"INSERT INTO {table} ({', '.join(columns)}) "
                            f"VALUES {placeholders}"
                        )

                        await cursor.execute(insert_query, values)
                        total_inserted += len(batch)

            logger.info(f"Inserted {total_inserted} rows into {table}")
            return total_inserted

        except Exception as e:
            logger.error(f"Insert failed: {e}")
            raise

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """
        Валидация имен таблиц/колонок для защиты от SQL injection
        Разрешены: буквы, цифры, подчеркивания, точки (для db.table)
        """
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$'
        return bool(re.match(pattern, name))


ch_client = ClickHouseClient()
