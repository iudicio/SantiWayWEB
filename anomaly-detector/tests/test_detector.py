"""
Базовые pytest тесты для BackendAnomalyDetector
"""

import numpy as np
import pandas as pd
import pytest
from anomaly_detector import BackendAnomalyDetector
from sklearn.datasets import make_classification


class TestBackendAnomalyDetector:

    @pytest.fixture
    def sample_data(self):
        """Генерация тестовых данных"""
        X, _ = make_classification(
            n_samples=500, n_features=5, n_informative=3, n_redundant=2, random_state=42
        )
        return X

    @pytest.fixture
    def detector(self):
        """Создание экземпляра детектора"""
        return BackendAnomalyDetector(
            contamination=0.1,
            n_estimators=50,  # Меньше для быстрых тестов
            random_state=42,
        )

    def test_detector_initialization(self, detector):
        """Тест инициализации детектора"""
        assert detector.is_fitted == False
        assert detector.feature_names is None
        assert detector.model.contamination == 0.1
        assert detector.batch_size == 1000

    def test_fit_with_numpy_array(self, detector, sample_data):
        """Тест обучения на numpy массиве"""
        detector.fit(sample_data)

        assert detector.is_fitted == True
        assert detector.n_features_ == sample_data.shape[1]
        assert detector.train_scores is not None
        assert detector.severity_thresholds is not None

    def test_fit_with_dataframe(self, detector, sample_data):
        """Тест обучения на DataFrame"""
        df = pd.DataFrame(
            sample_data, columns=[f"feature_{i}" for i in range(sample_data.shape[1])]
        )
        detector.fit(df)

        assert detector.is_fitted == True
        assert detector.feature_names is not None
        assert len(detector.feature_names) == sample_data.shape[1]

    def test_predict_before_fit_raises_error(self, detector, sample_data):
        """Тест что предсказание до обучения вызывает ошибку"""
        with pytest.raises(ValueError):
            detector.predict_anomalies(sample_data)

    def test_predict_anomalies(self, detector, sample_data):
        """Тест предсказания аномалий"""
        detector.fit(sample_data)
        preds = detector.predict_anomalies(sample_data)
        assert len(preds) == len(sample_data)
        assert set(np.unique(preds)).issubset({-1, 1})
        # доля аномалий вблизи contamination с допуском
        rate = np.mean(preds == -1)
        assert 0.02 < rate < 0.5

    def test_anomaly_scores(self, detector, sample_data):
        """Тест получения скоров аномальности"""
        detector.fit(sample_data)
        scores = detector.anomaly_scores(sample_data)

        assert len(scores) == len(sample_data)
        assert all(isinstance(s, (float, np.floating)) for s in scores)

    def test_get_anomaly_details(self, detector, sample_data):
        """Тест получения детальной информации об аномалиях"""
        detector.fit(sample_data)
        details = detector.get_anomaly_details(sample_data)

        assert len(details) == len(sample_data)

        for detail in details:
            assert "is_anomaly" in detail
            assert "anomaly_score" in detail
            assert "anomaly_probability" in detail
            assert "severity" in detail
            assert "confidence" in detail
            assert detail["severity"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            assert 0 <= detail["confidence"] <= 1

    def test_custom_threshold(self, detector, sample_data):
        """Тест использования кастомного порога"""
        detector.fit(sample_data)

        threshold = -0.1
        predictions = detector.predict_anomalies(sample_data, threshold=threshold)
        scores = detector.anomaly_scores(sample_data)

        # Проверяем что порог применился правильно
        expected_predictions = np.where(scores < threshold, -1, 1)
        np.testing.assert_array_equal(predictions, expected_predictions)

    def test_statistics_tracking(self, detector, sample_data):
        """Тест отслеживания статистики"""
        detector.fit(sample_data)

        # Первое предсказание
        detector.predict_anomalies(sample_data[:100])
        stats1 = detector.get_detection_stats()

        # Второе предсказание
        detector.predict_anomalies(sample_data[100:200])
        stats2 = detector.get_detection_stats()

        assert stats2["total_predictions"] > stats1["total_predictions"]
        assert stats2["last_prediction"] != stats1["last_prediction"]

        # Сброс статистики
        detector.reset_stats()
        stats3 = detector.get_detection_stats()
        assert stats3["total_predictions"] == 0

    def test_empty_data_validation(self, detector):
        """Тест валидации пустых данных"""
        with pytest.raises(ValueError):
            detector.fit(np.array([]))

        with pytest.raises(ValueError):
            detector.fit(pd.DataFrame())

    def test_model_save_load(self, detector, sample_data, tmp_path):
        """Тест сохранения и загрузки модели"""
        detector.fit(sample_data)
        original_predictions = detector.predict_anomalies(sample_data)

        # Сохранение
        model_path = tmp_path / "test_model.joblib"
        detector.save_model(str(model_path))

        # Загрузка в новый детектор
        new_detector = BackendAnomalyDetector()
        new_detector.load_model(str(model_path))

        # Проверка что предсказания одинаковые
        loaded_predictions = new_detector.predict_anomalies(sample_data)
        np.testing.assert_array_equal(original_predictions, loaded_predictions)

    def test_batch_processing(self, detector, sample_data):
        """Тест батчевой обработки"""
        detector.batch_size = 100  # Маленький батч для теста
        detector.fit(sample_data)

        results = detector.predict_batch(sample_data)
        assert len(results) == len(sample_data)
