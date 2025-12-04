# Test Suite

Comprehensive test suite для системы детекции аномалий.

## Структура тестов

```
tests/
├── test_models.py           # Тесты ML моделей
├── test_feature_engineer.py # Тесты feature engineering
├── test_api.py              # Тесты API endpoints
└── requirements-test.txt    # Зависимости для тестов
```

## Установка зависимостей

```bash
pip install -r tests/requirements-test.txt
```

## Запуск тестов

### Все тесты
```bash
pytest
```

### Конкретный файл
```bash
pytest tests/test_models.py
```

### Конкретный класс
```bash
pytest tests/test_models.py::TestTCNAutoencoder
```

### Конкретный тест
```bash
pytest tests/test_models.py::TestTCNAutoencoder::test_forward_pass
```

### С coverage
```bash
pytest --cov=backend --cov-report=html
```

### Только быстрые тесты (без integration)
```bash
pytest -m "not integration"
```

### Verbose output
```bash
pytest -v
```

### С детальным выводом при ошибках
```bash
pytest -vv --tb=long
```

## Типы тестов

### Unit Tests
Быстрые тесты отдельных компонентов без зависимостей:
```bash
pytest -m unit
```

### Integration Tests
Тесты требующие запущенных сервисов (ClickHouse, etc):
```bash
pytest -m integration
```

## Coverage Report

Создание HTML отчета о покрытии:
```bash
pytest --cov=backend --cov=ml --cov-report=html
open htmlcov/index.html
```

## Continuous Integration

Для CI/CD pipeline используйте:
```bash
pytest --cov=backend --cov=ml --cov-report=xml --junitxml=junit.xml
```

## Что тестируется

### test_models.py
- ✅ Создание моделей (basic и advanced)
- ✅ Forward pass с корректными размерностями
- ✅ Вычисление anomaly scores
- ✅ Multi-head attention механизм
- ✅ Извлечение embeddings
- ✅ Gradient flow
- ✅ Оптимизация параметров

### test_feature_engineer.py
- ✅ Haversine distance calculation
- ✅ Bearing calculation
- ✅ Velocity features
- ✅ Location entropy
- ✅ Temporal features
- ✅ Stationarity score
- ✅ Statistical features (skewness, kurtosis, etc)
- ✅ Rolling features (EMA, trend, etc)
- ✅ Autocorrelation features
- ✅ Spatial advanced features
- ✅ Behavioral patterns
- ✅ Timeseries preparation (17 и 67 features)

### test_api.py
- ✅ Health endpoints
- ✅ Metrics endpoint
- ✅ Ingest endpoints
- ✅ Anomaly endpoints
- ✅ Analysis endpoints
- ✅ Comparison endpoints
- ✅ Explanation endpoints
- ✅ CORS middleware
- ✅ Request validation

## Примеры запуска

```bash
# Быстрая проверка всех тестов
pytest --tb=short

# Детальный вывод с покрытием
pytest -vv --cov=backend --cov-report=term-missing

# Только тесты моделей
pytest tests/test_models.py -v

# Тесты с keyword фильтром
pytest -k "test_model" -v

# Остановка на первой ошибке
pytest -x

# Запуск последних упавших тестов
pytest --lf

# Parallel execution (требует pytest-xdist)
pytest -n auto
```

## Best Practices

1. **Изоляция**: Каждый тест должен быть независимым
2. **Fixtures**: Используйте fixtures для переиспользуемых данных
3. **Mocking**: Мокайте внешние зависимости (БД, API)
4. **Assertions**: Четкие и информативные assertions
5. **Naming**: Понятные имена тестов (test_what_when_then)
6. **Coverage**: Стремитесь к 80%+ покрытию критического кода

## Добавление новых тестов

1. Создайте файл `test_<module>.py`
2. Импортируйте pytest и тестируемый модуль
3. Создайте классы `Test<Feature>`
4. Добавьте методы `test_<scenario>`
5. Используйте fixtures для setup/teardown
6. Запустите: `pytest tests/test_<module>.py`

Пример:
```python
import pytest

class TestNewFeature:
    @pytest.fixture
    def sample_data(self):
        return {"key": "value"}

    def test_feature_works(self, sample_data):
        assert sample_data["key"] == "value"
```
