"""
Продвинутая архитектура TCN Autoencoder с Multi-Head Attention
"""
import torch
import torch.nn as nn
from pathlib import Path


class MultiHeadAttention(nn.Module):
    """Multi-head self-attention для temporal features"""

    def __init__(self, embed_dim: int, num_heads: int = 8, dropout: float = 0.1):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        assert embed_dim % num_heads == 0, "embed_dim must be divisible by num_heads"

        self.qkv = nn.Linear(embed_dim, embed_dim * 3)
        self.out_proj = nn.Linear(embed_dim, embed_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Аргументы:
            x: [batch, channels, time]

        Возвращает:
            [batch, channels, time]"""
        batch, channels, time = x.shape

        x = x.permute(0, 2, 1)

        qkv = self.qkv(x)

        q, k, v = qkv.chunk(3, dim=-1)

        q = q.view(batch, time, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch, time, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch, time, self.num_heads, self.head_dim).transpose(1, 2)

        scores = torch.matmul(q, k.transpose(-2, -1)) / (self.head_dim ** 0.5)
        attn_weights = torch.softmax(scores, dim=-1)
        attn_weights = self.dropout(attn_weights)

        attn_output = torch.matmul(attn_weights, v)

        attn_output = attn_output.transpose(1, 2).contiguous().view(batch, time, self.embed_dim)

        output = self.out_proj(attn_output)

        output = output.permute(0, 2, 1)

        return output


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


class TCN_Autoencoder_Advanced(nn.Module):
    """
    Продвинутый TCN Autoencoder с Multi-Head Attention

    Улучшения:
    - Увеличенная capacity: [128, 256, 512, 1024]
    - Multi-head attention после encoder
    - Больший kernel size (5 вместо 3)
    - Residual connections
    """

    def __init__(
        self,
        input_channels: int = 67,
        hidden_channels: list[int] | None = None,
        kernel_size: int = 5,
        dropout: float = 0.3,
        use_attention: bool = True,
        num_attention_heads: int = 8,
    ):
        super().__init__()

        if hidden_channels is None:
            hidden_channels = [128, 256, 512, 1024]

        self.input_channels = input_channels
        self.hidden_channels = hidden_channels
        self.use_attention = use_attention

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

        if use_attention:
            self.attention = MultiHeadAttention(
                embed_dim=hidden_channels[-1],
                num_heads=num_attention_heads,
                dropout=dropout,
            )
        else:
            self.attention = None

        self.bottleneck = nn.Linear(hidden_channels[-1], 128)

        decoder_layers: list[nn.Module] = []
        hidden_channels_reversed = hidden_channels[::-1]

        for i in range(num_levels):
            in_ch = 128 if i == 0 else hidden_channels_reversed[i - 1]
            out_ch = (
                hidden_channels_reversed[i]
                if i < num_levels - 1
                else input_channels
            )

            decoder_layers.append(
                nn.ConvTranspose1d(in_ch, out_ch, kernel_size, padding=2)
            )
            if i < num_levels - 1:
                decoder_layers.append(nn.ReLU())
                decoder_layers.append(nn.Dropout(dropout))

        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Аргументы:
            x: [batch, channels, time]

        Возвращает:
            Reconstructed x: [batch, channels, time]"""
        encoded = self.encoder(x)

        if self.attention is not None:
            encoded = encoded + self.attention(encoded)

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

    def get_embeddings(self, x: torch.Tensor) -> torch.Tensor:
        """Получение embeddings из bottleneck для similarity analysis

        Возвращает:
            Tensor размерность (batch, 128)"""
        encoded = self.encoder(x)
        if self.attention is not None:
            encoded = encoded + self.attention(encoded)
        pooled = encoded.mean(dim=2)
        embeddings = self.bottleneck(pooled)
        return embeddings


def load_advanced_model(
    model_path: str,
    device: str = "cpu",
    input_channels: int | None = None,
    use_attention: bool = True,
) -> TCN_Autoencoder_Advanced:
    """Загрузка продвинутой модели"""

    if input_channels is None:
        metadata_path = Path(model_path).parent / 'model_metadata.json'
        if metadata_path.exists():
            try:
                import json
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                input_channels = metadata.get('input_channels', 67)
            except Exception:
                input_channels = 67
        else:
            input_channels = 67

    model = TCN_Autoencoder_Advanced(
        input_channels=input_channels,
        hidden_channels=[128, 256, 512, 1024],
        kernel_size=5,
        dropout=0.3,
        use_attention=use_attention,
        num_attention_heads=8,
    )

    if Path(model_path).exists():
        try:
            checkpoint = torch.load(model_path, map_location=device, weights_only=False)
            state_dict = (
                checkpoint['model_state_dict']
                if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint
                else checkpoint
            )
            model.load_state_dict(state_dict)
            model.eval()
            print(f"Advanced model loaded from {model_path}")
        except Exception as e:
            print(f"Warning: Failed to load model from {model_path}: {e}")
    else:
        print(f"Warning: Model not found at {model_path}")

    return model.to(device)


if __name__ == "__main__":
    batch_size = 8
    input_channels = 67
    time_steps = 24

    x = torch.randn(batch_size, input_channels, time_steps)

    model = TCN_Autoencoder_Advanced(
        input_channels=input_channels,
        hidden_channels=[128, 256, 512, 1024],
        use_attention=True,
    )

    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    reconstructed = model(x)
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {reconstructed.shape}")

    scores = model.anomaly_score(x)
    print(f"Anomaly scores shape: {scores.shape}")
    print(f"Anomaly scores: {scores}")

    embeddings = model.get_embeddings(x)
    print(f"Embeddings shape: {embeddings.shape}")
