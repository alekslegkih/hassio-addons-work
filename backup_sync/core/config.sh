#!/usr/bin/env bash

# =========================
# Addon configuration loader
# =========================

CONFIG_FILE="/data/options.json"

# Переменные с дефолтами
USB_DEVICE=""
MOUNT_POINT=""
MAX_COPIES=0
SYNC_EXIST_START=false
NOTIFY_SERVICE=""
LOG_LEVEL="info"

load_config() {

  if [ ! -f "${CONFIG_FILE}" ]; then
    log_fatal "Config file ${CONFIG_FILE} not found"
    exit 1
  fi

  # Читаем значения из options.json
  USB_DEVICE=$(jq -r '.usb_device // ""' "${CONFIG_FILE}")
  MOUNT_POINT=$(jq -r '.mount_point // ""' "${CONFIG_FILE}")
  MAX_COPIES=$(jq -r '.max_copies // 0' "${CONFIG_FILE}")
  SYNC_EXIST_START=$(jq -r '.sync_exis_start // false' "${CONFIG_FILE}")
  NOTIFY_SERVICE=$(jq -r '.notify_service // ""' "${CONFIG_FILE}")
  LOG_LEVEL=$(jq -r '.log_level // "info"' "${CONFIG_FILE}")

  # Устанавливаем уровень логирования
  set_log_level "${LOG_LEVEL}"

  log_debug "Config loaded from ${CONFIG_FILE}"

  # Минимальная валидация формата (НЕ логики!)
  _validate_config
}

_validate_config() {

  # mount_point не должен быть пустым
  if [ -z "${MOUNT_POINT}" ]; then
    log_fatal "mount_point is empty"
    exit 1
  fi

  # mount_point не должен начинаться с /
  if [[ "${MOUNT_POINT}" == /* ]]; then
    log_fatal "mount_point must not start with '/' (use name only, e.g. baskups)"
    exit 1
  fi

  # max_copies должен быть > 0
  if ! [[ "${MAX_COPIES}" =~ ^[0-9]+$ ]] || [ "${MAX_COPIES}" -le 0 ]; then
    log_fatal "max_copies must be a positive integer"
    exit 1
  fi

  # log_level валидируется set_log_level, тут только лог
  log_debug "Config validation passed"
}
