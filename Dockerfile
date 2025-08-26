FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

RUN pip install --upgrade pip

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект в контейнер
COPY . .

# Экспортируем порт для Django (по умолчанию 8000)
EXPOSE 8000

# Запуск сервера
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]