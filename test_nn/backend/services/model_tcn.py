import torch
import torch.nn as nn
from pathlib import Path

class Chomp1d(nn.Module):
    """Trim padding on the right to enforce causality."""

    def __init__(self, chomp_size: int):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.chomp_size == 0:
            return x
        return x[:, :, :-self.chomp_size]

class TemporalBlock(nn.Module):
    """TCN блок с dilated causal convolution"""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int,
        dropout: float = 0.2,
    ):
        super().__init__()

        padding = (kernel_size - 1) * dilation

        self.conv1 = nn.Conv1d(
            in_channels, out_channels, kernel_size,
            padding=padding, dilation=dilation,
        )
        self.chomp1 = Chomp1d(padding)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout)

        self.conv2 = nn.Conv1d(
            out_channels, out_channels, kernel_size,
            padding=padding, dilation=dilation,
        )
        self.chomp2 = Chomp1d(padding)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(dropout)

        self.downsample = (
            nn.Conv1d(in_channels, out_channels, 1)
            if in_channels != out_channels
            else None
        )

        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv1(x)
        out = self.chomp1(out)
        out = self.relu1(out)
        out = self.dropout1(out)

        out = self.conv2(out)
        out = self.chomp2(out)
        out = self.relu2(out)
        out = self.dropout2(out)

        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)

class TCN_Autoencoder(nn.Module):
    """TCN Autoencoder для anomaly detection"""

    def __init__(
        self,
        input_channels: int = 17,
        hidden_channels: list[int] | None = None,
        kernel_size: int = 3,
        dropout: float = 0.2,
    ):
        super().__init__()

        if hidden_channels is None:
            hidden_channels = [64, 128, 256]

        self.input_channels = input_channels
        self.hidden_channels = hidden_channels

        encoder_layers = []
        num_levels = len(hidden_channels)

        for i in range(num_levels):
            in_ch = input_channels if i == 0 else hidden_channels[i - 1]
            out_ch = hidden_channels[i]
            dilation = 2 ** i

            encoder_layers.append(
                TemporalBlock(in_ch, out_ch, kernel_size, dilation, dropout)
            )

        self.encoder = nn.Sequential(*encoder_layers)

        self.bottleneck = nn.Linear(hidden_channels[-1], 64)

        decoder_layers: list[nn.Module] = []
        hidden_channels_reversed = hidden_channels[::-1]

        for i in range(num_levels):
            in_ch = 64 if i == 0 else hidden_channels_reversed[i - 1]
            out_ch = (
                hidden_channels_reversed[i]
                if i < num_levels - 1
                else input_channels
            )

            decoder_layers.append(
                nn.ConvTranspose1d(in_ch, out_ch, kernel_size, padding=1)
            )
            if i < num_levels - 1:
                decoder_layers.append(nn.ReLU())
                decoder_layers.append(nn.Dropout(dropout))

        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(x)

        pooled = encoded.mean(dim=2)

        bottleneck = self.bottleneck(pooled)

        bottleneck = bottleneck.unsqueeze(2).repeat(1, 1, x.size(2))

        reconstructed = self.decoder(bottleneck)

        return reconstructed

    def anomaly_score(self, x: torch.Tensor) -> torch.Tensor:
        """Вычисление anomaly score (reconstruction error)

        Возвращает:
            Tensor размерность (batch,) с MSE для каждого примера"""
        reconstructed = self.forward(x)
        mse = torch.mean((x - reconstructed) ** 2, dim=(1, 2))
        return mse

def load_model(model_path: str, device: str = "cpu", input_channels: int | None = None) -> TCN_Autoencoder:
    """Загрузка обученной модели"""

    if input_channels is None:
        metadata_path = Path(model_path).parent / 'model_metadata.json'
        if metadata_path.exists():
            try:
                import json
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                input_channels = metadata.get('input_channels', 17)
            except Exception:
                input_channels = 17
        else:
            input_channels = 17

    model = TCN_Autoencoder(input_channels=input_channels)

    if Path(model_path).exists():
        try:
            checkpoint = torch.load(model_path, map_location=device)
            state_dict = (
                checkpoint['model_state_dict']
                if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint
                else checkpoint
            )
            model.load_state_dict(state_dict)
            model.eval()
        except Exception as e:
            print(f"Warning: Failed to load model from {model_path}: {e}")
    else:
        print(f"Warning: Model not found at {model_path}")

    return model.to(device)
