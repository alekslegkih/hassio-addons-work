ARG BUILD_FROM=ghcr.io/home-assistant/home-assistant:stable
FROM $BUILD_FROM

# Установка зависимостей
RUN apk add --no-cache python3 py3-pip jq util-linux mc && \
    python3 -m pip install --no-cache-dir watchdog click

# Копируем все файлы
COPY . /usr/local/bin/backup_sync/

# Создаем символическую ссылку для команды backup-sync
RUN ln -sf /usr/local/bin/backup_sync/api/cli.py /usr/local/bin/backup-sync && \
    chmod +x /usr/local/bin/backup-sync && \
    chmod +x /usr/local/bin/backup_sync/api/cli.py

# Делаем основной скрипт исполняемым
RUN chmod a+x /usr/local/bin/backup_sync/main.py

# Запускающий скрипт
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Два варианта запуска:
# 1. Для работы аддона (основной режим)
# 2. Для CLI команд (через backup-sync)
CMD [ "/run.sh" ]