import numpy as np
import torch
import shap
from typing import Dict, List, Any
from loguru import logger

class AnomalyExplainer:
    """SHAP-based explainability for anomaly detection"""

    FEATURE_NAMES = [
        'event_count', 'avg_activity', 'std_activity',
        'avg_lat', 'avg_lon', 'hour'
    ]

    FEATURE_NAMES_EXTENDED = [
        'event_count', 'avg_activity', 'std_activity',
        'min_activity', 'max_activity', 'activity_range', 'p95_activity',
        'avg_lat', 'avg_lon', 'std_lat', 'std_lon',
        'velocity', 'acceleration', 'bearing_change',
        'location_entropy', 'stationarity_score',
        'hour_sin', 'hour_cos', 'is_night'
    ]

    def __init__(self, model, device: str = 'cpu', input_channels: int = 6):
        self.model = model
        self.device = device
        self.input_channels = input_channels

        if input_channels == 6:
            self.feature_names = self.FEATURE_NAMES
        else:
            self.feature_names = self.FEATURE_NAMES_EXTENDED[:input_channels]

        self.explainer = None
        self.background_data = None

    def set_background(self, background_samples: np.ndarray):
        """Set background data for SHAP explainer"""
        self.background_data = background_samples
        logger.info(f"Background data set: {background_samples.shape}")

    def _model_predict(self, x: np.ndarray) -> np.ndarray:
        """Wrapper for model prediction (returns reconstruction error)"""
        if len(x.shape) == 2:
            x = x.reshape(-1, self.input_channels, x.shape[-1] // self.input_channels)

        tensor = torch.FloatTensor(x).to(self.device)

        with torch.no_grad():
            scores = self.model.anomaly_score(tensor).cpu().numpy()

        return scores

    def explain_anomaly(
        self,
        sample: np.ndarray,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Explain why a sample is anomalous using SHAP.

        Аргументы:
            sample: Input sample (window_size, num_features) or (num_features, window_size)
            top_k: Number of top features to return

        Возвращает:
            Dictionary with feature contributions and explanations"""
        if sample.ndim == 2:
            if sample.shape[0] == self.input_channels:
                sample_flat = sample.flatten()
            else:
                sample_flat = sample.T.flatten()
        else:
            sample_flat = sample.flatten()

        if self.background_data is None:
            background = np.zeros((10, len(sample_flat)))
        else:
            if self.background_data.ndim == 3:
                background = self.background_data.reshape(
                    self.background_data.shape[0], -1
                )
            else:
                background = self.background_data

        try:
            explainer = shap.KernelExplainer(
                self._model_predict_flat,
                background[:min(50, len(background))]
            )

            shap_values = explainer.shap_values(
                sample_flat.reshape(1, -1),
                nsamples=100
            )

            if isinstance(shap_values, list):
                shap_values = shap_values[0]

            shap_values = shap_values.flatten()

        except Exception as e:
            logger.warning(f"SHAP computation failed: {e}, using gradient-based")
            return self._gradient_based_explanation(sample, top_k)

        feature_importance = self._aggregate_shap_values(shap_values)

        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )

        top_features = sorted_features[:top_k]

        explanations = []
        for feature_name, importance in top_features:
            direction = "increases" if importance > 0 else "decreases"
            explanations.append({
                'feature': feature_name,
                'importance': float(abs(importance)),
                'direction': direction,
                'contribution': float(importance),
                'description': self._get_feature_description(feature_name, importance)
            })

        return {
            'top_features': explanations,
            'all_contributions': {k: float(v) for k, v in feature_importance.items()},
            'method': 'shap'
        }

    def _model_predict_flat(self, x: np.ndarray) -> np.ndarray:
        """Prediction wrapper for flattened input"""
        batch_size = x.shape[0]
        window_size = x.shape[1] // self.input_channels

        x_reshaped = x.reshape(batch_size, self.input_channels, window_size)

        tensor = torch.FloatTensor(x_reshaped).to(self.device)

        with torch.no_grad():
            scores = self.model.anomaly_score(tensor).cpu().numpy()

        return scores

    def _aggregate_shap_values(self, shap_values: np.ndarray) -> Dict[str, float]:
        """Aggregate SHAP values across time steps for each feature"""
        window_size = len(shap_values) // self.input_channels
        shap_reshaped = shap_values.reshape(self.input_channels, window_size)

        feature_importance = {}
        for i, name in enumerate(self.feature_names):
            importance = np.mean(np.abs(shap_reshaped[i]))
            sign = np.sign(np.sum(shap_reshaped[i]))
            feature_importance[name] = float(importance * sign)

        return feature_importance

    def _gradient_based_explanation(
        self,
        sample: np.ndarray,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Fallback gradient-based explanation"""
        if sample.ndim == 2:
            if sample.shape[0] != self.input_channels:
                sample = sample.T

        tensor = torch.FloatTensor(sample).unsqueeze(0).to(self.device)
        tensor.requires_grad = True

        reconstructed = self.model(tensor)
        loss = torch.mean((tensor - reconstructed) ** 2)
        loss.backward()

        gradients = tensor.grad.cpu().numpy().squeeze()
        feature_importance = {}

        for i, name in enumerate(self.feature_names):
            importance = np.mean(np.abs(gradients[i]))
            feature_importance[name] = float(importance)

        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )

        explanations = []
        for feature_name, importance in sorted_features[:top_k]:
            explanations.append({
                'feature': feature_name,
                'importance': float(importance),
                'direction': 'contributes',
                'contribution': float(importance),
                'description': self._get_feature_description(feature_name, importance)
            })

        return {
            'top_features': explanations,
            'all_contributions': feature_importance,
            'method': 'gradient'
        }

    def _get_feature_description(self, feature_name: str, importance: float) -> str:
        """Generate human-readable description for feature contribution"""
        descriptions = {
            'event_count': 'Number of events in the time window',
            'avg_activity': 'Average activity level',
            'std_activity': 'Variability in activity',
            'min_activity': 'Minimum activity level',
            'max_activity': 'Maximum activity level',
            'activity_range': 'Range between max and min activity',
            'p95_activity': '95th percentile of activity',
            'avg_lat': 'Average latitude position',
            'avg_lon': 'Average longitude position',
            'std_lat': 'Movement variation in latitude',
            'std_lon': 'Movement variation in longitude',
            'velocity': 'Speed of movement',
            'acceleration': 'Change in speed',
            'bearing_change': 'Direction changes',
            'location_entropy': 'Diversity of visited locations',
            'stationarity_score': 'How stationary the device is',
            'hour_sin': 'Time of day (sine component)',
            'hour_cos': 'Time of day (cosine component)',
            'is_night': 'Night time indicator',
            'hour': 'Hour of day'
        }

        base_desc = descriptions.get(feature_name, f'Feature: {feature_name}')

        if importance > 0:
            return f"{base_desc} - unusually high value contributes to anomaly"
        else:
            return f"{base_desc} - unusually low value contributes to anomaly"

    def batch_explain(
        self,
        samples: np.ndarray,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Explain multiple samples"""
        explanations = []

        for i in range(len(samples)):
            try:
                exp = self.explain_anomaly(samples[i], top_k)
                explanations.append(exp)
            except Exception as e:
                logger.warning(f"Failed to explain sample {i}: {e}")
                explanations.append({
                    'top_features': [],
                    'all_contributions': {},
                    'method': 'failed',
                    'error': str(e)
                })

        return explanations
