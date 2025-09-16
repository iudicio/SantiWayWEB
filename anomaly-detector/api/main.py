from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional, Union
import pandas as pd
import numpy as np
import uvicorn
import logging
import time
from datetime import datetime
from threading import Lock
import io
import os
import csv
from anomaly_detector import BackendAnomalyDetector

os.makedirs("./models", exist_ok=True)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("anomaly-api")

# Глобальный детектор + лок
detector = BackendAnomalyDetector(
    contamination=0.1,
    n_estimators=100,
    batch_size=1000,
    thread_safe=True,
    enable_warnings=True
)
detector_lock = Lock()

app = FastAPI(
    title="Anomaly Detection API",
    version="1.0.0-beta",
    description="REST API для детекции аномалий в больших данных"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic модели JSON

class DetectionRequest(BaseModel):
    data: Union[List[List[float]], Dict[str, List[float]]] = Field(..., description="Данные: либо список строк, либо столбцы-словарь")
    threshold: Optional[float] = Field(None, description="Кастомный порог детекции")
    return_details: bool = Field(True, description="Возвращать детальную информацию")

    @validator('data')
    def validate_data(cls, v):
        if isinstance(v, list):
            if not v or not v[0]:
                raise ValueError("Данные не могут быть пустыми")
            n = len(v[0])
            if not all(len(row) == n for row in v):
                raise ValueError("Все строки должны иметь одинаковую длину")
        elif isinstance(v, dict):
            if not v:
                raise ValueError("Данные не могут быть пустыми")
            lengths = [len(values) for values in v.values()]
            if not all(L == lengths[0] for L in lengths):
                raise ValueError("Все столбцы должны иметь одинаковую длину")
        return v

class TrainingRequest(BaseModel):
    data: Union[List[List[float]], Dict[str, List[float]]] = Field(..., description="Обучающие данные")
    feature_names: Optional[List[str]] = None
    validation_split: float = Field(0.2, ge=0.0, lt=1.0)
    contamination: float = Field(0.1, gt=0.0, lt=0.5)
    n_estimators: int = Field(100, gt=0, le=1000)

    @validator('data')
    def validate_data(cls, v):
        return DetectionRequest.validate_data(v)

class DetectionResponse(BaseModel):
    success: bool
    message: str
    total_samples: int
    anomalies_detected: int
    anomaly_rate: float
    processing_time: float
    details: Optional[List[Dict[str, Any]]] = None

class TrainingResponse(BaseModel):
    success: bool
    message: str
    training_samples: int
    training_time: float
    model_info: Dict[str, Any]

# Вспомогательные CSV

def _sniff_delimiter(sample: bytes) -> str:
    """Пробуем определить разделитель автоматически по первому куску файла."""
    try:
        dialect = csv.Sniffer().sniff(sample.decode('utf-8', errors='ignore'), delimiters=[',',';','\t','|'])
        return dialect.delimiter
    except Exception:
        return ','

def _read_csv_dataframe(
    file_bytes: bytes,
    has_header: bool = True,
    delimiter: Optional[str] = None,
    decimal: str = '.',
    encoding: str = 'utf-8',
    na_values: Optional[str] = None,
    use_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Читаем CSV целиком в DataFrame."""
    buffer = io.BytesIO(file_bytes)

    if delimiter is None:
        # авто-определение по первым ~32KB
        peek = file_bytes[:32768]
        delimiter = _sniff_delimiter(peek)

    # настройка NA-токенов
    na_vals = None
    if na_values:
        na_vals = [s.strip() for s in na_values.split(',') if s.strip()]

    header = 0 if has_header else None
    df = pd.read_csv(
        buffer,
        sep=delimiter,
        decimal=decimal,
        header=header,
        encoding=encoding,
        na_values=na_vals
    )

    # если нет заголовка — генерируем имена
    if not has_header:
        df.columns = [f"feature_{i}" for i in range(df.shape[1])]

    # приводим к числам всё, что можем (грязные колонки -> NaN)
    df = df.apply(pd.to_numeric, errors='coerce')

    # при необходимости — выбрать подмножество колонок
    if use_columns:
        missing = set(use_columns) - set(df.columns)
        if missing:
            raise HTTPException(status_code=400, detail=f"В CSV отсутствуют колонки: {sorted(missing)}")
        df = df[use_columns]

    # выкидываем полностью пустые/нечисловые колонки
    all_nan = [c for c in df.columns if df[c].isna().all()]
    if all_nan:
        logger.warning(f"Полностью NaN-колонки удалены: {all_nan}")
        df = df.drop(columns=all_nan)

    if df.shape[1] == 0:
        raise HTTPException(status_code=400, detail="После очистки не осталось числовых признаков")

    return df

def _iter_csv_chunks(
    file_like,
    has_header: bool = True,
    delimiter: Optional[str] = None,
    decimal: str = '.',
    encoding: str = 'utf-8',
    na_values: Optional[str] = None,
    chunksize: int = 50000,
):
    """Итератор по чанкам CSV без загрузки всего файла в память."""
    # Для авто-детекта разделителя заглянем в начало потока
    # Сохраним содержимое в BytesIO, чтобы Pandas мог читать повторно
    raw = file_like.read()
    buffer = io.BytesIO(raw)

    if delimiter is None:
        delimiter = _sniff_delimiter(raw[:32768])

    na_vals = None
    if na_values:
        na_vals = [s.strip() for s in na_values.split(',') if s.strip()]

    header = 0 if has_header else None
    chunk_iter = pd.read_csv(
        buffer,
        sep=delimiter,
        decimal=decimal,
        header=header,
        encoding=encoding,
        na_values=na_vals,
        chunksize=chunksize
    )

    for chunk in chunk_iter:
        # привести к числам
        chunk = chunk.apply(pd.to_numeric, errors='coerce')
        # выкинуть полностью NaN-колонки в чанке 
        all_nan = [c for c in chunk.columns if chunk[c].isna().all()]
        if all_nan:
            chunk = chunk.drop(columns=all_nan)
        yield chunk

# Эндпоинты

@app.get("/")
async def root():
    return {
        "name": "Anomaly Detection API",
        "version": "1.0.0-beta",
        "status": "running",
        "model_fitted": detector.is_fitted,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model_status": "fitted" if detector.is_fitted else "not_fitted",
        "timestamp": datetime.now().isoformat()
    }

# JSON обучение 
@app.post("/train", response_model=TrainingResponse)
async def train_model(request: TrainingRequest):
    start = time.time()
    try:
        # Подготовка данных
        if isinstance(request.data, dict):
            df = pd.DataFrame(request.data)
            data = df
            feature_names = list(df.columns)
            if request.feature_names and request.feature_names != feature_names:
                raise HTTPException(
                    status_code=400,
                    detail="feature_names не совпадают с ключами data"
                )
        else:
            data = np.array(request.data, dtype=float)
            feature_names = request.feature_names

        # Переинициализируем детектор 
        with detector_lock:
            global detector
            detector = BackendAnomalyDetector(
                contamination=request.contamination,
                n_estimators=request.n_estimators,
                batch_size=1000,
                thread_safe=True,
                enable_warnings=True
            )
            detector.fit(data, feature_names, request.validation_split)
            model_info = detector.get_model_info()

        t = time.time() - start
        return TrainingResponse(
            success=True,
            message="Модель успешно обучена",
            training_samples=len(data),
            training_time=t,
            model_info=model_info
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обучении")
        raise HTTPException(status_code=500, detail=f"Ошибка обучения: {e}")

# JSON детекция
@app.post("/detect", response_model=DetectionResponse)
async def detect_anomalies(request: DetectionRequest):
    start = time.time()
    try:
        if not detector.is_fitted:
            raise HTTPException(status_code=400, detail="Модель не обучена. Сначала вызовите /train")

        if isinstance(request.data, dict):
            data = pd.DataFrame(request.data)
            total = len(data)
        else:
            data = np.array(request.data, dtype=float)
            total = data.shape[0]

        if request.return_details:
            results = detector.get_anomaly_details(data, request.threshold)
            anomalies = sum(1 for d in results if d["is_anomaly"])
            details = results
        else:
            preds = detector.predict_anomalies(data, request.threshold)
            anomalies = int(np.sum(preds == -1))
            details = None

        t = time.time() - start
        return DetectionResponse(
            success=True,
            message=f"Обработано {total} образцов",
            total_samples=total,
            anomalies_detected=anomalies,
            anomaly_rate=(anomalies / total) if total else 0.0,
            processing_time=t,
            details=details
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при детекции")
        raise HTTPException(status_code=500, detail=f"Ошибка детекции: {e}")

#  CSV обучение 
@app.post("/train/csv", response_model=TrainingResponse)
async def train_model_csv(
    file: UploadFile = File(..., description="CSV-файл с обучающими данными"),
    has_header: bool = Query(True, description="Есть ли строка заголовков"),
    delimiter: Optional[str] = Query(None, description="Разделитель (по умолчанию авто)"),
    decimal: str = Query('.', description="Десятичный разделитель ('.' или ',')"),
    encoding: str = Query('utf-8', description="Кодировка файла"),
    na_values: Optional[str] = Query(None, description="Список NA-токенов через запятую, например 'NA,NULL,?'"),
    validation_split: float = Query(0.2, ge=0.0, lt=1.0),
    contamination: float = Query(0.1, gt=0.0, lt=0.5),
    n_estimators: int = Query(100, gt=0, le=1000),
    sample_rows: Optional[int] = Query(None, description="Если указано — случайно подвыбрать N строк для обучения"),
    feature_names_policy: str = Query('strict', description="'strict' или 'flexible' политика признаков")
):
    start = time.time()
    try:
        file_bytes = await file.read()
        df = _read_csv_dataframe(
            file_bytes=file_bytes,
            has_header=has_header,
            delimiter=delimiter,
            decimal=decimal,
            encoding=encoding,
            na_values=na_values
        )

        if sample_rows and sample_rows < len(df):
            df = df.sample(n=sample_rows, random_state=42).reset_index(drop=True)

        with detector_lock:
            global detector
            detector = BackendAnomalyDetector(
                contamination=contamination,
                n_estimators=n_estimators,
                batch_size=1000,
                thread_safe=True,
                enable_warnings=True,
                feature_names_policy=feature_names_policy
            )
            detector.fit(df, validation_split=validation_split)
            model_info = detector.get_model_info()

        t = time.time() - start
        return TrainingResponse(
            success=True,
            message="Модель успешно обучена по CSV",
            training_samples=len(df),
            training_time=t,
            model_info=model_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обучении по CSV")
        raise HTTPException(status_code=500, detail=f"Ошибка обучения по CSV: {e}")

# CSV детекция (с поддержкой чанков)
@app.post("/detect/csv", response_model=DetectionResponse)
async def detect_anomalies_csv(
    file: UploadFile = File(..., description="CSV-файл с данными для детекции"),
    has_header: bool = Query(True, description="Есть ли строка заголовков"),
    delimiter: Optional[str] = Query(None, description="Разделитель (по умолчанию авто)"),
    decimal: str = Query('.', description="Десятичный разделитель ('.' или ',')"),
    encoding: str = Query('utf-8', description="Кодировка файла"),
    na_values: Optional[str] = Query(None, description="Список NA-токенов через запятую"),
    threshold: Optional[float] = Query(None, description="Кастомный порог детекции"),
    return_details: bool = Query(True, description="Вернуть детальные результаты по каждой строке"),
    chunksize: int = Query(50000, gt=0, description="Размер чанка для потоковой обработки больших CSV")
):
    start = time.time()
    try:
        if not detector.is_fitted:
            raise HTTPException(status_code=400, detail="Модель не обучена. Сначала вызовите /train или /train/csv")

        # потоковая обработка
        total = 0
        anomalies = 0
        details: Optional[List[Dict[str, Any]]] = [] if return_details else None

        row_offset = 0
        async_file = await file.read()
        for chunk in _iter_csv_chunks(
            io.BytesIO(async_file),
            has_header=has_header,
            delimiter=delimiter,
            decimal=decimal,
            encoding=encoding,
            na_values=na_values,
            chunksize=chunksize
        ):
            if chunk.empty:
                continue

            # если модель обучалась на DF с фиксацией фич — индексы и выравнивание колонок сделает сам детектор
            # чтобы индексы в ответе были сквозными по всему файлу:
            chunk.index = range(row_offset, row_offset + len(chunk))

            if return_details:
                chunk_details = detector.get_anomaly_details(chunk, threshold)
                if details is not None:
                    details.extend(chunk_details)
                anomalies += sum(1 for d in chunk_details if d['is_anomaly'])
            else:
                preds = detector.predict_anomalies(chunk, threshold)
                anomalies += int(np.sum(preds == -1))

            total += len(chunk)
            row_offset += len(chunk)

        t = time.time() - start
        return DetectionResponse(
            success=True,
            message=f"Обработано {total} строк из CSV",
            total_samples=total,
            anomalies_detected=anomalies,
            anomaly_rate=(anomalies / total) if total else 0.0,
            processing_time=t,
            details=details
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при детекции по CSV")
        raise HTTPException(status_code=500, detail=f"Ошибка детекции по CSV: {e}")

@app.get("/model/info")
async def model_info():
    try:
        return detector.get_model_info()
    except Exception as e:
        logger.exception("Ошибка получения информации о модели")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def stats():
    try:
        return detector.get_detection_stats()
    except Exception as e:
        logger.exception("Ошибка получения статистики")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stats/reset")
async def reset_stats():
    try:
        detector.reset_stats()
        return {"success": True, "message": "Статистика сброшена"}
    except Exception as e:
        logger.exception("Ошибка сброса статистики")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Необработанная ошибка: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "timestamp": datetime.now().isoformat()}
    )

@app.post("/export/onnx")
async def export_onnx_model(
    onnx_filename: str = Query("anomaly.onnx"),
    meta_filename: str = Query("metadata.json.gz")
):
    if not detector.is_fitted:
        raise HTTPException(status_code=400, detail="Модель не обучена")
    
    try:
        onnx_path = f"./models/{onnx_filename}"
        meta_path = f"./models/{meta_filename}"
        
        with detector_lock:
            detector.export_to_onnx(onnx_path, meta_path)
        
        return {
            "success": True,
            "message": f"Модель экспортирована: {onnx_filename} + {meta_filename}",
            "onnx_path": onnx_path,
            "meta_path": meta_path,
            "download_urls": {
                "onnx": f"/download/onnx/{onnx_filename}",
                "metadata": f"/download/meta/{meta_filename}"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/onnx/{filename}")
async def download_onnx(filename: str):
    file_path = f"./models/{filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(file_path, filename=filename)

@app.get("/download/meta/{filename}")
async def download_metadata(filename: str):
    file_path = f"./models/{filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(file_path, filename=filename)

# Тест для подбора допуска
@app.post("/test/onnx_accuracy")
async def test_onnx_accuracy(n_samples: int = Query(100)):
    """Тест точности ONNX vs sklearn для подбора допуска"""
    if not detector.is_fitted:
        raise HTTPException(status_code=400, detail="Модель не обучена")
    
    try:
        import onnxruntime as ort
        
        # Генерируем случайные данные
        np.random.seed(42)
        test_data = np.random.randn(n_samples, detector.n_features_)
        
        # Предсказания sklearn
        sklearn_scores = detector.anomaly_scores(test_data)
        
        # Экспортируем временную ONNX модель
        temp_onnx = "./models/temp_test.onnx"
        temp_meta = "./models/temp_test.json.gz"
        detector.export_to_onnx(temp_onnx, temp_meta)
        
        # Предсказания ONNX
        session = ort.InferenceSession(temp_onnx)
        input_name = session.get_inputs()[0].name
        onnx_result = session.run(None, {input_name: test_data.astype(np.float32)})
        
        # Извлекаем scores (может быть разный индекс/тип)
        onnx_scores = None
        for i, output in enumerate(onnx_result):
            if hasattr(output, 'shape') and output.shape == (n_samples,):
                if output.dtype in [np.float32, np.float64]:
                    onnx_scores = output.astype(np.float32)
                    break
        
        if onnx_scores is None:
            return {"error": "Не удалось извлечь scores из ONNX"}
        
        # Сравнение
        diff = np.abs(sklearn_scores.astype(np.float32) - onnx_scores)
        max_diff = float(np.max(diff))
        mean_diff = float(np.mean(diff))
        
        # Удаляем временные файлы
        os.remove(temp_onnx)
        os.remove(temp_meta)
        
        return {
            "max_difference": max_diff,
            "mean_difference": mean_diff,
            "recommended_tolerance": max_diff * 1.5,  # с запасом
            "samples_tested": n_samples
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)