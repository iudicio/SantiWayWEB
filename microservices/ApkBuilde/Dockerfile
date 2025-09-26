FROM python:3.11-slim-bookworm

# ---- базовые утилиты ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget unzip zip git build-essential \
    openjdk-17-jdk-headless \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---- Android SDK (cmdline-tools) ----
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
RUN mkdir -p $ANDROID_SDK_ROOT/cmdline-tools

# Ставим commandline-tools и принимаем лицензии
RUN wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmd.zip \
    && unzip -q /tmp/cmd.zip -d $ANDROID_SDK_ROOT/cmdline-tools \
    && mv $ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools $ANDROID_SDK_ROOT/cmdline-tools/tools \
    && rm -f /tmp/cmd.zip

# sdkmanager в PATH
ENV PATH=$PATH:$ANDROID_SDK_ROOT/cmdline-tools/tools/bin

# Устанавливаем нужное под проект (SDK 35) и принимаем лицензии
RUN yes | sdkmanager --licenses && \
    sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"

# apksigner/adb в PATH
ENV PATH=$PATH:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/build-tools/35.0.0

# ---- Python deps & приложение ----
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celery_app.py build_apk.py tasks.py ./

# Кэш gradle локально
ENV GRADLE_USER_HOME=/app/.gradle

# Стандартные питон-флаги
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- пользователь celery ----
RUN addgroup --system celery  \
    && adduser --system --ingroup celery --home /home/celery celery \
    && mkdir -p /app/logs /app/artifacts /home/celery/.android \
    && chown -R celery:celery /app /home/celery /opt/android-sdk

# Явно задаём HOME и prefs Android
ENV HOME=/home/celery \
    ANDROID_USER_HOME=/home/celery/.android \
    GRADLE_USER_HOME=/app/.gradle

USER celery

# Запуск воркера
CMD ["sh", "-c", "celery -A celery_app worker -Q apkbuilder -n apkbuilder@%h -l info"]