#!/usr/bin/env bash

set -euo pipefail

BASE_DIR="/usr/local/bin/backup_sync"

# Подключаем core-модули
source "${BASE_DIR}/core/logger.sh"
source "${BASE_DIR}/core/config.sh"

log_info "Backup Sync addon starting..."

# Загружаем конфигурацию
load_config

log_debug "Configuration loaded"
log_debug "usb_device=${USB_DEVICE:-<empty>}"
log_debug "mount_point=${MOUNT_POINT}"
log_debug "max_copies=${MAX_COPIES}"
log_debug "sync_exist_start=${SYNC_EXIST_START}"
log_debug "notify_service=${NOTIFY_SERVICE:-<disabled>}"
log_debug "log_level=${LOG_LEVEL}"

log_info "Initialization complete. Waiting for next steps..."

# Пока просто idle
while true; do
  sleep 3600
done
