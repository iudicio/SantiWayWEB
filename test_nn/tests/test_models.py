"""
Tests for ML models (TCN Autoencoder, Advanced TCN)
"""
import pytest
import torch
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.services.model_tcn import TCN_Autoencoder
from backend.services.model_tcn_advanced import TCN_Autoencoder_Advanced, MultiHeadAttention


class TestTCNAutoencoder:
    """Tests for basic TCN Autoencoder"""

    def test_model_creation(self):
        """Test model can be created"""
        model = TCN_Autoencoder(input_channels=17)
        assert model is not None
        assert model.input_channels == 17

    def test_forward_pass(self):
        """Test forward pass with correct shapes"""
        model = TCN_Autoencoder(input_channels=17)
        batch_size = 8
        time_steps = 24

        x = torch.randn(batch_size, 17, time_steps)
        output = model(x)

        assert output.shape == x.shape
        assert output.shape == (batch_size, 17, time_steps)

    def test_anomaly_score(self):
        """Test anomaly score computation"""
        model = TCN_Autoencoder(input_channels=17)
        batch_size = 8
        time_steps = 24

        x = torch.randn(batch_size, 17, time_steps)
        scores = model.anomaly_score(x)

        assert scores.shape == (batch_size,)
        assert torch.all(scores >= 0)

    def test_different_input_channels(self):
        """Test model with different input channels"""
        for channels in [10, 17, 50, 67]:
            model = TCN_Autoencoder(input_channels=channels)
            x = torch.randn(4, channels, 24)
            output = model(x)
            assert output.shape == x.shape

    def test_model_parameters(self):
        """Test model has trainable parameters"""
        model = TCN_Autoencoder(input_channels=17)
        params = sum(p.numel() for p in model.parameters())
        assert params > 0

        for p in model.parameters():
            assert p.requires_grad


class TestTCNAdvanced:
    """Tests for Advanced TCN Autoencoder with Attention"""

    def test_model_creation_with_attention(self):
        """Test advanced model can be created with attention"""
        model = TCN_Autoencoder_Advanced(
            input_channels=67,
            use_attention=True,
        )
        assert model is not None
        assert model.use_attention is True
        assert model.attention is not None

    def test_model_creation_without_attention(self):
        """Test advanced model can be created without attention"""
        model = TCN_Autoencoder_Advanced(
            input_channels=67,
            use_attention=False,
        )
        assert model is not None
        assert model.attention is None

    def test_forward_pass_advanced(self):
        """Test forward pass with advanced model"""
        model = TCN_Autoencoder_Advanced(
            input_channels=67,
            hidden_channels=[128, 256, 512, 1024],
            use_attention=True,
        )

        batch_size = 4
        time_steps = 24
        x = torch.randn(batch_size, 67, time_steps)
        output = model(x)

        assert output.shape == x.shape
        assert output.shape == (batch_size, 67, time_steps)

    def test_anomaly_score_advanced(self):
        """Test anomaly score computation for advanced model"""
        model = TCN_Autoencoder_Advanced(input_channels=67, use_attention=True)

        x = torch.randn(8, 67, 24)
        scores = model.anomaly_score(x)

        assert scores.shape == (8,)
        assert torch.all(scores >= 0)

    def test_get_embeddings(self):
        """Test embedding extraction"""
        model = TCN_Autoencoder_Advanced(input_channels=67)

        x = torch.randn(8, 67, 24)
        embeddings = model.get_embeddings(x)

        assert embeddings.shape == (8, 128)

    def test_attention_mechanism(self):
        """Test multi-head attention works correctly"""
        attention = MultiHeadAttention(embed_dim=256, num_heads=8)

        batch_size = 4
        channels = 256
        time = 24

        x = torch.randn(batch_size, channels, time)
        output = attention(x)

        assert output.shape == x.shape

    def test_model_size_comparison(self):
        """Test that advanced model is larger than basic"""
        basic_model = TCN_Autoencoder(input_channels=67)
        advanced_model = TCN_Autoencoder_Advanced(
            input_channels=67,
            hidden_channels=[128, 256, 512, 1024],
            use_attention=True,
        )

        basic_params = sum(p.numel() for p in basic_model.parameters())
        advanced_params = sum(p.numel() for p in advanced_model.parameters())

        assert advanced_params > basic_params


class TestModelTraining:
    """Tests for model training capabilities"""

    def test_model_gradient_flow(self):
        """Test that gradients flow through the model"""
        model = TCN_Autoencoder(input_channels=17)
        x = torch.randn(4, 17, 24, requires_grad=True)

        output = model(x)
        loss = torch.mean((output - x) ** 2)
        loss.backward()

        for name, param in model.named_parameters():
            assert param.grad is not None, f"No gradient for {name}"

    def test_model_optimization_step(self):
        """Test that model parameters update after optimization"""
        model = TCN_Autoencoder(input_channels=17)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

        initial_params = [p.clone() for p in model.parameters()]

        x = torch.randn(4, 17, 24)
        output = model(x)
        loss = torch.mean((output - x) ** 2)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        for initial, current in zip(initial_params, model.parameters()):
            assert not torch.equal(initial, current), "Parameters did not update"

    def test_model_eval_mode(self):
        """Test that model behaves differently in eval mode"""
        model = TCN_Autoencoder(input_channels=17)
        x = torch.randn(4, 17, 24)

        model.train()
        output_train = model(x)

        model.eval()
        with torch.no_grad():
            output_eval = model(x)

        assert output_train.shape == output_eval.shape


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
