ARG BUILD_FROM=ghcr.io/home-assistant/home-assistant:stable
FROM ${BUILD_FROM}

# Рабочая директория аддона
WORKDIR /usr/local/bin/backup_sync

# Системные зависимости
RUN apk add --no-cache \
    bash \
    coreutils \
    util-linux \
    lsblk \
    blkid \
    jq \
    python3 \
    py3-pip

# Python зависимости (watchdog + уведомления)
RUN python3 -m pip install --no-cache-dir \
    watchdog \
    requests

# Копируем код аддона
COPY . .

# Права на скрипты
RUN chmod +x \
    /usr/local/bin/backup_sync/run.sh \
    /usr/local/bin/backup_sync/core/*.sh \
    /usr/local/bin/backup_sync/storage/*.sh \
    /usr/local/bin/backup_sync/sync/*.sh

# Entry point для Home Assistant
CMD ["/usr/local/bin/backup_sync/run.sh"]
