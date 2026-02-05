ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM ${BUILD_FROM}

WORKDIR /usr/local/bin/backup_sync

RUN apk add --no-cache \
        python3 \
        py3-pip \
        jq \
        util-linux \
        mc \
    && pip3 install --no-cache-dir \
        watchdog \
        click

COPY . .

RUN chmod +x main.py api/cli.py \
    && ln -sf /usr/local/bin/backup_sync/api/cli.py /usr/local/bin/backup-sync

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
