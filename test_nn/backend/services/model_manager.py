from pathlib import Path
from typing import Any, Dict, Optional, Union
import json
from loguru import logger
import torch
from backend.services.model_tcn import TCN_Autoencoder, load_model
from backend.services.model_tcn_advanced import TCN_Autoencoder_Advanced, load_advanced_model
from backend.utils.config import settings

class ModelManager:
    """Управление загрузкой/сохранением модели и метаданных"""

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None):
        self.model_path = Path(model_path or settings.MODEL_PATH)
        self.device = device or settings.DEVICE

        if 'advanced' in str(self.model_path):
            self.metadata_path = self.model_path.parent / 'model_metadata_advanced.json'
        else:
            self.metadata_path = self.model_path.parent / 'model_metadata.json'

        self._model: Optional[Union[TCN_Autoencoder, TCN_Autoencoder_Advanced]] = None

    def load(self) -> Union[TCN_Autoencoder, TCN_Autoencoder_Advanced]:
        logger.info(f"Loading model from {self.model_path}")

        metadata = self.load_metadata()
        input_channels = metadata.get('input_channels', settings.INPUT_CHANNELS)
        model_type = metadata.get('model_type', 'tcn_basic')

        # Проверка соответствия количества признаков
        if settings.INPUT_CHANNELS != input_channels:
            logger.warning(
                f"INPUT_CHANNELS mismatch! "
                f"Config: {settings.INPUT_CHANNELS}, Model metadata: {input_channels}. "
                f"Using metadata value: {input_channels}"
            )


        if model_type == 'tcn_advanced' or 'advanced' in str(self.model_path):
            logger.info(f"Loading ADVANCED model (type: {model_type})")
            logger.info(f"Model configuration: input_channels={input_channels}, "
                       f"hidden_channels={metadata.get('hidden_channels', settings.HIDDEN_CHANNELS)}, "
                       f"kernel_size={metadata.get('kernel_size', settings.KERNEL_SIZE)}, "
                       f"use_attention={metadata.get('use_attention', settings.USE_ATTENTION)}")

            model = TCN_Autoencoder_Advanced(
                input_channels=input_channels,
                hidden_channels=metadata.get('hidden_channels', settings.HIDDEN_CHANNELS),
                kernel_size=metadata.get('kernel_size', settings.KERNEL_SIZE),
                dropout=metadata.get('dropout', settings.DROPOUT),
                use_attention=metadata.get('use_attention', settings.USE_ATTENTION),
                num_attention_heads=metadata.get('num_attention_heads', settings.NUM_ATTENTION_HEADS),
            )
        else:
            logger.info(f"Loading BASIC model (type: {model_type})")
            logger.info(f"Model configuration: input_channels={input_channels}")

            model = TCN_Autoencoder(
                input_channels=input_channels,
                hidden_channels=[64, 128, 256],
                kernel_size=3,
                dropout=0.2,
            )

        if self.model_path.exists():
            try:
                checkpoint = torch.load(str(self.model_path), map_location=self.device, weights_only=False)
                state_dict = (
                    checkpoint['model_state_dict']
                    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint
                    else checkpoint
                )

                try:
                    model.load_state_dict(state_dict)
                    logger.info(f" Model loaded successfully with {input_channels} input channels")
                except RuntimeError as e:
                    logger.error(f"Model architecture mismatch: {e}")
                    logger.error(f"Expected input_channels: {input_channels}, but weights don't match")
                    raise ValueError(
                        f"Model weights don't match expected architecture. "
                        f"Check that MODEL_PATH and INPUT_CHANNELS in .env are correct."
                    )
            except Exception as e:
                logger.error(f"Failed to load model weights: {e}")
                raise
        else:
            logger.warning(f"Model file not found at {self.model_path}")

        model.eval()
        self._model = model.to(self.device)
        return self._model

    def model(self) -> Union[TCN_Autoencoder, TCN_Autoencoder_Advanced]:
        if self._model is None:
            return self.load()
        return self._model

    def save_metadata(self, meta: Dict[str, Any]) -> None:
        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved metadata to {self.metadata_path}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def load_metadata(self) -> Dict[str, Any]:
        if not self.metadata_path.exists():
            logger.warning(f"Metadata not found at {self.metadata_path}")
            return {}
        try:
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return {}
