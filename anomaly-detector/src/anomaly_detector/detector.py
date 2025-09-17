import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import joblib
import logging
import numpy as np
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import sklearn
import sys
import time
from functools import wraps
import warnings
import threading
from sklearn.pipeline import Pipeline
from skl2onnx import to_onnx
from skl2onnx.common.data_types import FloatTensorType
from onnx import helper
import json
import gzip

def log_execution_time(func):
    """Декоратор для замера времени выполнения методов"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        result = func(self, *args, **kwargs)
        execution_time = time.time() - start_time
        self.logger.debug(f"{func.__name__} выполнен за {execution_time:.3f}с")
        return result
    return wrapper

class BackendAnomalyDetector:
    def __init__(self, contamination=0.1, n_estimators=100, random_state=42, 
                 batch_size=1000, enable_warnings=True, thread_safe=False,
                 feature_names_policy='strict'):
        """
        Инициализация детектора аномалий для backend систем
        
        Args:
            contamination: Ожидаемая доля аномалий в данных (0.1 = 10%)
            n_estimators: Количество деревьев в IsolationForest
            random_state: Сид для воспроизводимости результатов
            batch_size: Размер батча для обработки больших данных
            enable_warnings: Включить/отключить предупреждения
            thread_safe: Использовать потокобезопасные счетчики
            feature_names_policy: 'strict' или 'flexible' для обработки признаков
        """
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,  # используем все доступные ядра
            max_samples='auto',
            max_features=1.0
        )
        self.scaler = StandardScaler()
        self.imputer = SimpleImputer(strategy='median')
        self.is_fitted = False
        self.feature_names = None
        self.n_features_ = None
        self.batch_size = batch_size
        self.enable_warnings = enable_warnings
        self.thread_safe = thread_safe
        self.feature_names_policy = feature_names_policy

        # Данные для калибровки модели
        self.train_scores = None
        self.severity_thresholds = None
        self.severity_quantiles = None
        self.score_bounds = None
        self.empirical_cdf = None
        self.class_version = "1.0.0"
        
        # Настройка потокобезопасности
        if thread_safe:
            self._lock = threading.Lock()
            self._prediction_count = 0
            self._anomaly_count = 0
            self._last_prediction_time = None
        else:
            self._lock = None
            self.prediction_count = 0
            self.anomaly_count = 0
            self.last_prediction_time = None
        
        self.logger = logging.getLogger(__name__)
        
        if not enable_warnings:
            warnings.filterwarnings('ignore', category=UserWarning)

    def _update_stats(self, predictions: np.ndarray):
        """Обновление статистики использования модели"""
        anomalies = np.sum(predictions == -1)
        
        if self.thread_safe and self._lock:
            with self._lock:
                self._prediction_count += len(predictions)
                self._anomaly_count += anomalies
                self._last_prediction_time = datetime.now()
        else:
            self.prediction_count += len(predictions)
            self.anomaly_count += anomalies
            self.last_prediction_time = datetime.now()

    def _get_stats(self) -> Dict[str, Any]:
        """Получение текущей статистики """
        if self.thread_safe and self._lock:
            with self._lock:
                return {
                    'prediction_count': self._prediction_count,
                    'anomaly_count': self._anomaly_count,
                    'last_prediction_time': self._last_prediction_time
                }
        else:
            return {
                'prediction_count': self.prediction_count,
                'anomaly_count': self.anomaly_count,
                'last_prediction_time': self.last_prediction_time
            }

    def _validate_and_clean_data(self, X: Union[pd.DataFrame, np.ndarray], 
                                is_training: bool = False) -> tuple:
        """Валидация входных данных и их очистка"""
        
        if X is None:
            raise ValueError("Входные данные не могут быть None")
            
        if isinstance(X, pd.DataFrame):
            if X.empty:
                raise ValueError("DataFrame не может быть пустым")
            
            # Приводим к числам
            X = X.apply(pd.to_numeric, errors='coerce')

            if self.feature_names is not None:
                if self.feature_names_policy == 'strict':
                    missing = set(self.feature_names) - set(X.columns)
                    if missing:
                        raise ValueError(f"Отсутствуют признаки: {missing}")
                    X = X[self.feature_names]
                elif self.feature_names_policy == 'flexible':
                    # Надёжно выравниваем набор признаков
                    X = X.reindex(columns=self.feature_names, fill_value=0.0)
            elif not is_training and self.feature_names_policy == 'strict':
                raise ValueError("Модель обучена на ndarray без feature_names. "
                               "Нельзя использовать DataFrame на инференсе.")

            original_index = X.index
            X_values = X.values
        elif isinstance(X, np.ndarray):
            if X.size == 0:
                raise ValueError("Массив не может быть пустым")
            X_values = X
            original_index = None
            
            if not is_training and self.feature_names is not None and self.feature_names_policy == 'strict':
                raise ValueError("Модель обучена на DataFrame. "
                               "Нельзя использовать ndarray на инференсе.")
        else:
            raise TypeError("Поддерживаются только pandas DataFrame и numpy ndarray")
        
        if X_values.ndim != 2:
            raise ValueError(f"Ожидается 2D массив, получен {X_values.ndim}D")
        
        if X_values.shape[0] == 0:
            raise ValueError("Данные не содержат ни одного образца")

        # Проверка соответствия количества признаков
        if not is_training and self.is_fitted and self.n_features_ is not None:
            if X_values.shape[1] != self.n_features_:
                if self.feature_names_policy == 'strict':
                    raise ValueError(f"Ожидается {self.n_features_} признаков, "
                                   f"получено {X_values.shape[1]}")
                else:
                    self.logger.warning(f"Изменилось количество признаков: "
                                      f"{self.n_features_} -> {X_values.shape[1]}")

        # Обработка бесконечных значений
        if np.isinf(X_values).any():
            if self.enable_warnings:
                self.logger.warning("Обнаружены бесконечные значения. Замена на NaN.")
            X_values = np.where(np.isinf(X_values), np.nan, X_values)

        # Импьютация пропущенных значений
        X_values = self.imputer.transform(X_values)
        if np.isnan(X_values).any():
            self.logger.debug("Остались NaN после импьютации - проверьте данные")

        return X_values, original_index

    def _create_empirical_cdf(self, scores: np.ndarray):
        """Создание эмпирической функции распределения для калибровки"""
        sorted_scores = np.sort(scores)
        n = len(sorted_scores)
        
        def empirical_cdf(x):
            positions = np.searchsorted(sorted_scores, x, side='right')
            return positions / n
        
        self.empirical_cdf = {
            'function': empirical_cdf,
            'sorted_scores': sorted_scores,
            'n_samples': n
        }

    @log_execution_time
    def fit(self, X: Union[pd.DataFrame, np.ndarray], 
            feature_names: Optional[List[str]] = None, 
            validation_split: float = 0.0):
        """
        Обучение модели детекции аномалий
        
        Args:
            X: Обучающие данные
            feature_names: Названия признаков (для numpy массивов)
            validation_split: Доля данных для валидации (0-1)
        """
        try: 
            start_time = time.time()
            if isinstance(X, np.ndarray):
                if X.ndim != 2 or X.shape[0] == 0 or X.shape[1] == 0:
                   raise ValueError("Ожидается непустой 2D ndarray (n_samples x n_features)")
            elif isinstance(X, pd.DataFrame):
                if X.empty or X.shape[1] == 0:
                    raise ValueError("DataFrame не может быть пустым и должен содержать признаки")
            else:
                raise TypeError("Поддерживаются только pandas DataFrame и numpy ndarray")
            
            if validation_split < 0 or validation_split >= 1:
                raise ValueError("validation_split должен быть в диапазоне [0, 1)")
            
            # Определяем названия признаков
            if isinstance(X, pd.DataFrame):
                self.feature_names = X.columns.tolist()
                X_values = X.values
            elif feature_names: 
                self.feature_names = feature_names
                X_values = X
            else:
                if self.enable_warnings and self.feature_names_policy == 'strict':
                    self.logger.warning("Обучение на ndarray без feature_names. "
                                      "DataFrame будет запрещен на инференсе.")
                X_values = X
            
            self.n_features_ = X_values.shape[1]
            
            # Детерминированное разделение данных для валидации
            if validation_split > 0:
                n_val = int(len(X_values) * validation_split)
                rng = np.random.RandomState(self.random_state)
                indices = rng.permutation(len(X_values))
                train_idx, val_idx = indices[n_val:], indices[:n_val]
                X_train, X_val = X_values[train_idx], X_values[val_idx]
                self.logger.info(f"Детерминированное разделение данных (seed={self.random_state}): "
                               f"{len(X_train)} обучение, {len(X_val)} валидация")
            else:
                X_train = X_values
                X_val = None
            
            # Обучение импьютера на всех данных (включая NaN)
            X_clean = self.imputer.fit_transform(X_train)
            if np.isnan(X_train).any():
                self.logger.info("Импьютер обучен на данных с NaN")
            else:
                self.logger.debug("Импьютер обучен на данных без NaN")

            # Нормализация данных
            X_scaled = self.scaler.fit_transform(X_clean)
            self.logger.debug(f"Данные нормализованы: {X_scaled.shape}")
            
            # Обучение модели
            self.model.fit(X_scaled)

            # Калибровка порогов на обучающих данных
            self.train_scores = self.model.decision_function(X_scaled)
            self._calibrate_thresholds()
            self._create_empirical_cdf(self.train_scores)

            # Валидация модели если есть валидационная выборка
            if X_val is not None:
                self._validate_model(X_val)

            self.is_fitted = True
            training_time = time.time() - start_time
            
            self.logger.info(f"Модель обучена на {X_clean.shape[0]} образцах "
                           f"с {X_clean.shape[1]} признаками за {training_time:.2f}с")
            return self
            
        except Exception as e:
            self.logger.error(f"Ошибка при обучении модели: {str(e)}", exc_info=True)
            raise
    
    def _validate_model(self, X_val: np.ndarray):
        """Валидация модели на отложенной выборке"""
        try:
            X_val_clean = self.imputer.transform(X_val)
            X_val_scaled = self.scaler.transform(X_val_clean)
            
            val_scores = self.model.decision_function(X_val_scaled)
            val_predictions = self.model.predict(X_val_scaled)
            
            anomaly_rate = np.sum(val_predictions == -1) / len(val_predictions)
            score_stats = {
                'mean': np.mean(val_scores),
                'std': np.std(val_scores),
                'min': np.min(val_scores),
                'max': np.max(val_scores)
            }
            
            self.logger.info(f"Валидация: доля аномалий {anomaly_rate:.3f}, "
                           f"скор статистика: {score_stats}")
            
        except Exception as e:
            self.logger.warning(f"Ошибка при валидации модели: {str(e)}")
    
    def _calibrate_thresholds(self):
        """Калибровка порогов серьезности на основе обучающих данных"""
        if self.train_scores is None:
            return
            
        # Вычисляем квантили для анализа распределения
        percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
        self.severity_quantiles = {}
        
        for p in percentiles:
            self.severity_quantiles[f'q{p:02d}'] = float(np.percentile(self.train_scores, p))
        
        # Определяем пороги на основе аномальных скоров
        anomaly_scores = self.train_scores[self.train_scores < 0]
        
        if len(anomaly_scores) > 0:
            self.severity_thresholds = {
                'CRITICAL': float(np.percentile(anomaly_scores, 5)),
                'HIGH': float(np.percentile(anomaly_scores, 15)),
                'MEDIUM': float(np.percentile(anomaly_scores, 40))
            }
            self.logger.info(f"Калиброванные пороги: {self.severity_thresholds}")
        else:
            # Фаллбек на статистические пороги если нет аномалий
            mean_score = np.mean(self.train_scores)
            std_score = np.std(self.train_scores)
            
            self.severity_thresholds = {
                'CRITICAL': float(mean_score - 2.5 * std_score),
                'HIGH': float(mean_score - 2.0 * std_score),
                'MEDIUM': float(mean_score - 1.5 * std_score)
            }
            self.logger.warning("Нет аномалий в обучающих данных. "
                              "Используем статистические пороги.")
        
        # Сохраняем границы для нормализации скоров
        score_min, score_max = float(np.min(self.train_scores)), float(np.max(self.train_scores))
        self.score_bounds = {
            'min': score_min,
            'max': score_max,
            'range': max(score_max - score_min, 1e-8),
            'mean': float(np.mean(self.train_scores)),
            'std': float(np.std(self.train_scores))
        }

    def _validate_threshold(self, threshold: float) -> bool:
        """Проверка разумности порогового значения"""
        if not isinstance(threshold, (int, float)):
            raise ValueError("threshold должен быть числом")
        
        if self.train_scores is not None:
            # Проверяем относительно обучающих данных
            train_min, train_max = np.min(self.train_scores), np.max(self.train_scores)
            train_mean, train_std = np.mean(self.train_scores), np.std(self.train_scores)
            
            reasonable_min = min(train_min - abs(train_min) * 0.5, train_mean - 3 * train_std)
            reasonable_max = max(train_max + abs(train_max) * 0.5, train_mean + 3 * train_std)
            
            if threshold < reasonable_min or threshold > reasonable_max:
                if self.enable_warnings:
                    self.logger.warning(f"Threshold {threshold:.3f} вне разумного диапазона "
                                      f"[{reasonable_min:.3f}, {reasonable_max:.3f}] "
                                      f"на основе обучающих данных")
                return False
        else:
            # Общие границы если нет данных обучения
            if threshold < -5 or threshold > 5:
                if self.enable_warnings:
                    self.logger.warning(f"Threshold {threshold} вне общего диапазона [-5, 5]")
                return False
        
        return True
    
    def predict_anomalies(self, X: Union[pd.DataFrame, np.ndarray], 
                         threshold: Optional[float] = None) -> np.ndarray:
        """
        Предсказание аномалий
        
        Args:
            X: Данные для анализа
            threshold: Пользовательский порог (если None, используется встроенный)
            
        Returns:
            Массив предсказаний: -1 для аномалий, 1 для нормальных точек
        """
        if not self.is_fitted:
            raise ValueError("Модель должна быть обучена перед предсказанием")
            
        try:
            X_clean, _ = self._validate_and_clean_data(X)
            X_scaled = self.scaler.transform(X_clean)
            
            if threshold is not None:
                self._validate_threshold(threshold)
            
            self.logger.debug(f"Предсказание для {X_scaled.shape[0]} образцов")
            
            if threshold is not None:
                # Используем пользовательский порог
                scores = self.model.decision_function(X_scaled)
                predictions = np.where(scores < threshold, -1, 1)
            else:
                # Используем встроенный алгоритм модели
                predictions = self.model.predict(X_scaled)
            
            self._update_stats(predictions)
            
            return predictions
            
        except Exception as e:
            self.logger.error(f"Ошибка при предсказании: {str(e)}", exc_info=True)
            raise
    
    def anomaly_scores(self, X: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
        """Получение скоров аномальности (чем меньше, тем более аномально)"""
        if not self.is_fitted:
            raise ValueError("Модель должна быть обучена перед предсказанием")
         
        X_clean, _ = self._validate_and_clean_data(X)
        X_scaled = self.scaler.transform(X_clean)
        return self.model.decision_function(X_scaled)
    
    def _scores_to_proba(self, scores: np.ndarray) -> np.ndarray:
        """Преобразование скоров в вероятности с использованием эмпирической CDF"""
        if self.empirical_cdf is not None:
            # Используем эмпирическую CDF для более точной калибровки
            cdf_values = self.empirical_cdf['function'](scores)
            return 1 - cdf_values  # инвертируем: меньший скор = больше вероятность
        
        # Фаллбек методы если CDF недоступна
        if self.score_bounds is None:
            offset = getattr(self.model, 'offset_', 0.0)
            scale = np.std(scores) if len(scores) > 1 else 1.0
            scaled_scores = (scores - offset) / max(scale, 1e-8)
            return 1 / (1 + np.exp(scaled_scores))
        
        # нормализация через z-score
        score_mean = self.score_bounds['mean']
        score_std = self.score_bounds['std']
        
        z_scores = (scores - score_mean) / max(score_std, 1e-8)
        z_scores = np.clip(z_scores, -5, 5)  # ограничиваем экстремумы
        
        return 1 / (1 + np.exp(z_scores))
    
    def predict_proba_anomaly(self, X: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
        """Получение вероятностей аномальности (0-1, где 1 = точно аномалия)"""
        scores = self.anomaly_scores(X)
        return self._scores_to_proba(scores)
    
    def predict_batch(self, X: Union[pd.DataFrame, np.ndarray]) -> List[Dict[str, Any]]:
        """Батчевая обработка больших объемов данных"""
        if len(X) <= self.batch_size:
            return self.get_anomaly_details(X)
        
        self.logger.info(f"Батчевая обработка {len(X)} образцов "
                        f"с размером батча {self.batch_size}")
        
        results = []
        for i in range(0, len(X), self.batch_size):
            batch_end = min(i + self.batch_size, len(X))
            
            if isinstance(X, pd.DataFrame):
                batch = X.iloc[i:batch_end]
            else:
                batch = X[i:batch_end]
                
            batch_results = self.get_anomaly_details(batch)
            results.extend(batch_results)
            
            # Логируем прогресс каждые 10 батчей
            if i % (self.batch_size * 10) == 0:
                self.logger.debug(f"Обработано {min(i + self.batch_size, len(X))} "
                                f"из {len(X)} образцов")
        
        return results
    
    @log_execution_time
    def get_anomaly_details(self, X: Union[pd.DataFrame, np.ndarray], 
                           threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        
        """
        Получение детальной информации об аномалиях
        
        Returns:
            Список словарей с подробной информацией о каждой точке
        """
        X_clean, original_index = self._validate_and_clean_data(X)
        X_scaled = self.scaler.transform(X_clean)
        
        scores = self.model.decision_function(X_scaled)
        
        if threshold is not None:
            self._validate_threshold(threshold)
            predictions = np.where(scores < threshold, -1, 1)
        else:
            predictions = self.model.predict(X_scaled)
        
        anomaly_proba = self._scores_to_proba(scores)

        results = []
        for i, (pred, score, proba) in enumerate(zip(predictions, scores, anomaly_proba)):
            is_anomaly = pred == -1
            
            # Вычисляем уверенность на основе эмпирического распределения
            if self.empirical_cdf is not None:
                cdf_value = self.empirical_cdf['function']([score])[0]
                confidence = abs(cdf_value - 0.5) * 2  # расстояние от медианы
            else:
                # Фаллбек логика для уверенности
                if is_anomaly:
                    confidence = min(abs(score), 2.0) / 2.0
                else:
                    confidence = min(max(score, 0), 2.0) / 2.0
            
            result = {
                'index': original_index[i] if original_index is not None else i,
                'is_anomaly': is_anomaly,
                'anomaly_score': float(score),
                'anomaly_probability': float(proba),
                'severity': self._get_severity(score),
                'confidence': float(confidence),
                'timestamp': datetime.now().isoformat()
            }
            results.append(result)

        return results
    
    def _get_severity(self, score: float) -> str:
        """Определение уровня серьезности аномалии"""
        if not hasattr(self, 'severity_thresholds') or self.severity_thresholds is None: 
            # Дефолтные пороги если калибровка не проводилась
            if score < -0.5:
                return 'CRITICAL'
            elif score < -0.3:
                return 'HIGH'
            elif score < -0.1:
                return 'MEDIUM'
            else:
                return 'LOW'
        
        # Используем калиброванные пороги
        if score < self.severity_thresholds['CRITICAL']:
            return 'CRITICAL'
        elif score < self.severity_thresholds['HIGH']:
            return 'HIGH'
        elif score < self.severity_thresholds['MEDIUM']:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def get_detection_stats(self) -> Dict[str, Any]:
        """Получение статистики работы детектора"""
        current_stats = self._get_stats()
        
        stats = {
            'total_predictions': current_stats['prediction_count'],
            'total_anomalies': current_stats['anomaly_count'],
            'anomaly_rate': (current_stats['anomaly_count'] / current_stats['prediction_count'] 
                           if current_stats['prediction_count'] > 0 else 0.0),
            'last_prediction': (current_stats['last_prediction_time'].isoformat() 
                              if current_stats['last_prediction_time'] else None),
            'model_fitted': self.is_fitted,
            'thread_safe': self.thread_safe
        }
        
        # Добавляем статистику обучения если модель обучена
        if self.is_fitted and self.train_scores is not None:
            stats.update({
                'training_samples': len(self.train_scores),
                'training_anomaly_rate': float(np.sum(self.train_scores < 0) / len(self.train_scores)),
                'score_distribution': {
                    'mean': float(np.mean(self.train_scores)),
                    'std': float(np.std(self.train_scores)),
                    'min': float(np.min(self.train_scores)),
                    'max': float(np.max(self.train_scores))
                }
            })
        
        return stats
    
    def reset_stats(self):
        """Сброс накопленной статистики использования"""
        if self.thread_safe and self._lock:
            with self._lock:
                self._prediction_count = 0
                self._anomaly_count = 0
                self._last_prediction_time = None
        else:
            self.prediction_count = 0
            self.anomaly_count = 0
            self.last_prediction_time = None
        
        self.logger.info("Статистика детектора сброшена")
    
    def save_model(self, filepath: str):
        """Сохранение обученной модели с метаданными"""
        if not self.is_fitted:
            raise ValueError("Нет обученной модели для сохранения")
        
        model_params = self.model.get_params()
        current_stats = self._get_stats()
        
        # Собираем все необходимые данные для сохранения
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'imputer': self.imputer,
            'feature_names': self.feature_names,
            'n_features_': self.n_features_,
            'is_fitted': self.is_fitted,
            'train_scores': self.train_scores,
            'severity_thresholds': self.severity_thresholds,
            'severity_quantiles': self.severity_quantiles,
            'score_bounds': self.score_bounds,
            'batch_size': self.batch_size,
            'feature_names_policy': self.feature_names_policy,
            'sklearn_version': sklearn.__version__,
            'class_version': self.class_version,
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'created_at': datetime.now().isoformat(),
            'contamination': model_params.get('contamination'),
            'n_estimators': model_params.get('n_estimators'),
            'random_state': model_params.get('random_state'),
            'prediction_count': current_stats['prediction_count'],
            'anomaly_count': current_stats['anomaly_count']
        }
        
        try:
            joblib.dump(model_data, filepath)
            self.logger.info(f"Модель сохранена в {filepath}")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении модели: {str(e)}")
            raise
    
    def load_model(self, filepath: str, strict_version_check: bool = True):
        """Загрузка сохраненной модели с проверкой совместимости"""
        try:
            model_data = joblib.load(filepath)
            
            # Проверка версий для совместимости
            saved_class_version = model_data.get('class_version', '1.0')
            saved_sklearn_version = model_data.get('sklearn_version')
            current_sklearn_version = sklearn.__version__
            
            version_issues = []
            
            if saved_class_version != self.class_version:
                msg = f"Версия класса: {saved_class_version} != {self.class_version}"
                version_issues.append(msg)
            
            if saved_sklearn_version and saved_sklearn_version != current_sklearn_version:
                saved_major_minor = '.'.join(saved_sklearn_version.split('.')[:2])
                current_major_minor = '.'.join(current_sklearn_version.split('.')[:2])
                
                if saved_major_minor != current_major_minor:
                    msg = f"Критическое несовпадение sklearn: {saved_sklearn_version} != {current_sklearn_version}"
                    version_issues.append(msg)
                    if strict_version_check:
                        raise ValueError(f"Несовместимые версии sklearn. {msg}")
            
            if version_issues:
                for issue in version_issues:
                    self.logger.warning(issue)
            
            # Восстановление состояния модели
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.imputer = model_data.get('imputer', SimpleImputer(strategy='median'))
            self.feature_names = model_data.get('feature_names')
            self.n_features_ = model_data.get('n_features_')
            self.is_fitted = model_data.get('is_fitted', False)
            self.train_scores = model_data.get('train_scores')
            self.severity_thresholds = model_data.get('severity_thresholds')
            self.severity_quantiles = model_data.get('severity_quantiles')
            self.score_bounds = model_data.get('score_bounds')
            self.empirical_cdf = None
            if self.train_scores is not None and len(self.train_scores) > 0:
                self._create_empirical_cdf(self.train_scores)
            self.batch_size = model_data.get('batch_size', 1000)
            self.feature_names_policy = model_data.get('feature_names_policy', 'strict')
            
            # Восстановление статистики использования
            if self.thread_safe and self._lock:
                with self._lock:
                    self._prediction_count = model_data.get('prediction_count', 0)
                    self._anomaly_count = model_data.get('anomaly_count', 0)
            else:
                self.prediction_count = model_data.get('prediction_count', 0)
                self.anomaly_count = model_data.get('anomaly_count', 0)
            
            created_at = model_data.get('created_at', 'неизвестно')
            contamination = model_data.get('contamination', 'неизвестно')
            self.logger.info(f"Модель загружена из {filepath}, создана: {created_at}, "
                           f"contamination: {contamination}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке модели: {str(e)}", exc_info=True)
            raise
    
    def export_to_onnx(self, onnx_path: str, meta_path: str):
        """Экспорт полного пайплайна в ONNX + метаданные"""
        if not self.is_fitted:
            raise ValueError("Модель должна быть обучена перед экспортом")
        
        
        # Собираем полный пайплайн
        pipeline = Pipeline([
            ('imputer', self.imputer),
            ('scaler', self.scaler), 
            ('iforest', self.model)
        ])
        
        # Экспорт в ONNX
        initial_types = [("input", FloatTensorType([None, self.n_features_]))]
        onnx_model = to_onnx(pipeline, initial_types=initial_types)
        
        # Логируем имена выходов для отладки
        out_names = [o.name for o in onnx_model.graph.output]
        self.logger.info(f"ONNX outputs: {out_names}")
        
        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
        
        # Сохраняем метаданные для совместимости
        metadata = {
            "n_features": int(self.n_features_),
            "feature_names": self.feature_names,
            "severity_thresholds": self.severity_thresholds or {
                "CRITICAL": -0.65, "HIGH": -0.45, "MEDIUM": -0.2
            },
            "severity_quantiles": self.severity_quantiles,
            "score_bounds": self.score_bounds or {
                "mean": 0.0, "std": 1.0, "min": -1.0, "max": 1.0, "range": 2.0
            },
            "class_version": self.class_version,
            "export_timestamp": datetime.now().isoformat(),
            "contamination": float(self.model.contamination),
            "n_estimators": int(self.model.n_estimators),
            "onnx_outputs": out_names
        }
        
        with gzip.open(meta_path, "wt", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)
        
        self.logger.info(f"Модель экспортирована в {onnx_path} + {meta_path}")

    

    def get_model_info(self) -> Dict[str, Any]:
        """Получение полной информации о состоянии модели"""
        info = {
            'is_fitted': self.is_fitted,
            'feature_names': self.feature_names,
            'n_features': self.n_features_,
            'severity_thresholds': self.severity_thresholds,
            'severity_quantiles': self.severity_quantiles,
            'score_bounds': self.score_bounds,
            'class_version': self.class_version,
            'batch_size': self.batch_size,
            'feature_names_policy': self.feature_names_policy,
            'thread_safe': self.thread_safe,
            'has_empirical_cdf': self.empirical_cdf is not None
        }
        
        # Добавляем статистику использования
        info.update(self.get_detection_stats())
        
        return info
    
    def __repr__(self) -> str:
        """Строковое представление объекта для отладки"""
        status = "fitted" if self.is_fitted else "not fitted"
        n_features = f", {self.n_features_} features" if self.n_features_ else ""
        policy = f", policy={self.feature_names_policy}"
        thread_info = ", thread_safe" if self.thread_safe else ""
        
        return (f"BackendAnomalyDetector(contamination="
                f"{self.model.contamination}, n_estimators="
                f"{self.model.n_estimators}, {status}{n_features}{policy}{thread_info})")
