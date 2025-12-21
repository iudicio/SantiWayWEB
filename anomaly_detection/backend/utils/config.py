from pydantic_settings import BaseSettings
import torch
from pathlib import Path

def get_device() -> str:
    """Автоматическое определение доступного устройства"""
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"

class Settings(BaseSettings):
    """Конфигурация приложения"""

    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "anomaly_ml"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True

    DJANGO_NOTIFICATION_URL: str = "http://web:8000"
    ML_BACKEND_KEY: str = "ml-secret-key-change-me"

    ALLOWED_ORIGINS: str = "http://localhost,http://localhost:8000,http://localhost:3000"

    VALID_API_KEYS: str = ""

    MODEL_PATH: str = "models/tcn_model.pt"
    MODEL_TYPE: str = "tcn_basic"
    BATCH_SIZE: int = 64
    DEVICE: str = "cpu"

    USE_EXTENDED_FEATURES: bool = True
    INPUT_CHANNELS: int = 98  

    HIDDEN_CHANNELS: list[int] = [128, 256, 512, 1024]
    KERNEL_SIZE: int = 5
    DROPOUT: float = 0.3
    USE_ATTENTION: bool = True
    NUM_ATTENTION_HEADS: int = 8

    ANOMALY_THRESHOLD_95: float = 0.87
    ANOMALY_THRESHOLD_99: float = 0.92
    WINDOW_SIZE: int = 24

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.DEVICE == "cpu" or self.DEVICE == "auto":
            detected_device = get_device()
            env_path = Path(".env")
            if env_path.exists():
                with open(env_path, 'r') as f:
                    env_content = f.read()
                    if 'DEVICE=' not in env_content or 'DEVICE=auto' in env_content:
                        self.DEVICE = detected_device
            else:
                self.DEVICE = detected_device

settings = Settings()
