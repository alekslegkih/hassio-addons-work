ARG BUILD_FROM
FROM $BUILD_FROM

# Устанавливаем Python и необходимые пакеты
RUN apk add --no-cache python3 py3-pip && \
    python3 -m pip install --no-cache-dir watchdog

# Копируем скрипт
COPY backup_sync.py /usr/local/bin/backup_sync.py
RUN chmod a+x /usr/local/bin/backup_sync.py

# Запускаем скрипт
CMD ["python3", "/usr/local/bin/backup_sync.py"]