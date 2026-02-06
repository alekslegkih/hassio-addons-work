#!/usr/bin/env bash

# =========================
# Logging utility for addon
# =========================

# Цвета (ANSI)
COLOR_RESET="\033[0m"

COLOR_FATAL="\033[1;31m"   # ярко-красный
COLOR_ERROR="\033[0;31m"   # красный
COLOR_WARN="\033[0;33m"    # жёлтый
COLOR_INFO="\033[0;32m"    # зелёный
COLOR_DEBUG="\033[0;36m"   # циан
COLOR_OFF=""

# Уровни логов (по возрастанию подробности)
LOG_LEVEL_FATAL=1
LOG_LEVEL_ERROR=2
LOG_LEVEL_WARN=3
LOG_LEVEL_INFO=4
LOG_LEVEL_DEBUG=5
LOG_LEVEL_OFF=0

# Значение по умолчанию (если config ещё не загружен)
CURRENT_LOG_LEVEL=${LOG_LEVEL_INFO}

# =========================
# Внутренние функции
# =========================

_log() {
  local level_name="$1"
  local level_value="$2"
  local color="$3"
  shift 3
  local message="$*"

  if [ "${CURRENT_LOG_LEVEL}" -ge "${level_value}" ]; then
    echo -e "${color}[${level_name}]${COLOR_RESET} ${message}"
  fi
}

# =========================
# Публичные функции
# =========================

log_fatal() {
  _log "FATAL" "${LOG_LEVEL_FATAL}" "${COLOR_FATAL}" "$@"
}

log_error() {
  _log "ERROR" "${LOG_LEVEL_ERROR}" "${COLOR_ERROR}" "$@"
}

log_warn() {
  _log "WARN" "${LOG_LEVEL_WARN}" "${COLOR_WARN}" "$@"
}

log_info() {
  _log "INFO" "${LOG_LEVEL_INFO}" "${COLOR_INFO}" "$@"
}

log_debug() {
  _log "DEBUG" "${LOG_LEVEL_DEBUG}" "${COLOR_DEBUG}" "$@"
}

# =========================
# Установка уровня логов
# =========================

set_log_level() {
  case "$1" in
    off)   CURRENT_LOG_LEVEL=${LOG_LEVEL_OFF} ;;
    fatal) CURRENT_LOG_LEVEL=${LOG_LEVEL_FATAL} ;;
    error) CURRENT_LOG_LEVEL=${LOG_LEVEL_ERROR} ;;
    warn)  CURRENT_LOG_LEVEL=${LOG_LEVEL_WARN} ;;
    info)  CURRENT_LOG_LEVEL=${LOG_LEVEL_INFO} ;;
    debug) CURRENT_LOG_LEVEL=${LOG_LEVEL_DEBUG} ;;
    *)
      echo "[WARN] Unknown log level '$1', fallback to 'info'"
      CURRENT_LOG_LEVEL=${LOG_LEVEL_INFO}
      ;;
  esac
}
