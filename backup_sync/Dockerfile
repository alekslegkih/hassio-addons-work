ARG BUILD_FROM=ghcr.io/home-assistant/home-assistant:stable
FROM ${BUILD_FROM}

# Рабочая директория аддона
WORKDIR /usr/local/bin/backup_sync

# Системные зависимости
RUN apk add --no-cache \
    jq \
    util-linux \
    mc

# Python зависимости
RUN python3 -m pip install --no-cache-dir \
    watchdog \
    click

# Копируем код аддона
COPY . .

# CLI команда
RUN ln -sf /usr/local/bin/backup_sync/api/cli.py /usr/local/bin/backup-sync \
    && chmod +x /usr/local/bin/backup-sync \
    && chmod +x api/cli.py \
    && chmod +x main.py

# Entry point для HA
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
