import logging
import time
from typing import Dict, Any, Optional
import json

# Настройка логирования
logger = logging.getLogger("apkbuild")


def setup_logging():
    """Настройка логирования для сервиса"""
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


setup_logging()


def log_api_key(api_key: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Логируем API ключ с метаданными."""
    if not isinstance(api_key, str):
        raise ValueError("api_key must be a string")

    # Маскируем ключ для безопасности
    masked_key = f"{api_key[:8]}..." if len(api_key) > 8 else "***"

    log_data = {
        "timestamp": time.time(),
        "api_key_masked": masked_key,
        "api_key_length": len(api_key),
        "metadata": metadata or {},
        "service": "apkbuild"
    }

    logger.info(f"API Key processed: {masked_key} (length: {len(api_key)})")

    if metadata:
        logger.info(f"Metadata: {json.dumps(metadata, indent=2)}")

    return {"logged": True, "data": log_data}