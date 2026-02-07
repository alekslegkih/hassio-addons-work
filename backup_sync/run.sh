#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/usr/local/bin/backup_sync"
QUEUE_FILE="/tmp/backup_sync.queue"

# =========================
# Core
# =========================
source "${BASE_DIR}/core/logger.sh"
source "${BASE_DIR}/core/config.sh"
source "${BASE_DIR}/core/state.sh"

# =========================
# Storage
# =========================
source "${BASE_DIR}/storage/detect.sh"
source "${BASE_DIR}/storage/mount.sh"
source "${BASE_DIR}/storage/checks.sh"
source "${BASE_DIR}/storage/cleanup.sh"

# =========================
# Sync
# =========================
source "${BASE_DIR}/sync/copier.sh"

# =========================
# Notify
# =========================
NOTIFY_BIN="${BASE_DIR}/notifi/ha_notify.py"

# =========================
# Exit handler
# =========================
trap 'state_dump' EXIT

# =========================
# START
# =========================

log_info "--------------------------------------------------"
log_info "Backup Sync addon starting..."

load_config
state_load

log_info "Configuration:"
log_info "  usb_device        = ${USB_DEVICE:-<not set>}"
log_info "  mount_point       = ${MOUNT_POINT}"
log_info "  max_copies        = ${MAX_COPIES}"
log_info "  sync_exist_start  = ${SYNC_EXIST_START}"
log_info "  log_level         = ${LOG_LEVEL}"

# =========================
# STATE 1 — VALIDATE CONFIG
# =========================

if [ -z "${USB_DEVICE:-}" ]; then
  log_warn "usb_device is not set"
  log_info "Available storage devices:"
  detect_devices || true

  state_set LAST_ERROR "usb_device not configured"

  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: usb_device not configured"
  fi

  log_fatal "Please configure usb_device and restart addon"
  exit 1
fi

# =========================
# STATE 2 — CHECK STORAGE
# =========================

log_info "Running storage checks"

if ! check_storage; then
  state_set LAST_ERROR "Storage checks failed"

  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: Storage checks failed"
  fi

  log_fatal "Storage checks failed"
  exit 1
fi

# =========================
# STATE 3 — MOUNT USB
# =========================

if ! mount_usb; then
  state_set LAST_ERROR "USB bind-mount failed"

  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: USB bind-mount failed"
  fi

  log_fatal "USB bind-mount failed"
  exit 1
fi

# =========================
# STATE 4 — CHECK TARGET
# =========================

if ! check_target; then
  state_set LAST_ERROR "Target directory check failed"

  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: Target directory check failed"
  fi

  log_fatal "Target directory check failed"
  exit 1
fi

# =========================
# STATE 5 — ЗАПУСК WATCHER ПЕРВЫМ (ВСЕГДА)
# =========================

log_info "Starting watcher (always first)"

# Запускаем watcher в фоне, перенаправляем вывод в лог
WATCHER_LOG="/tmp/watcher.$$.log"
log_debug "Watcher log: $WATCHER_LOG"

python3 "${BASE_DIR}/sync/watcher.py" > "$WATCHER_LOG" 2>&1 &
WATCHER_PID=$!

# Даем watcher время на запуск
log_debug "Waiting for watcher to start (PID: $WATCHER_PID)"
sleep 3

# Проверяем, что watcher запустился
if ! kill -0 "$WATCHER_PID" 2>/dev/null; then
  # Watcher не запустился - проверяем лог на ошибки
  if [ -f "$WATCHER_LOG" ]; then
    if grep -q "EVENT:FATAL:" "$WATCHER_LOG"; then
      reason=$(grep "EVENT:FATAL:" "$WATCHER_LOG" | tail -1 | cut -d: -f3-)
      log_error "Watcher fatal error: $reason"
      state_set LAST_ERROR "Watcher: $reason"
    else
      state_set LAST_ERROR "Watcher failed to start"
    fi
  else
    state_set LAST_ERROR "Watcher failed to start (no log)"
  fi
  
  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: Watcher failed to start"
  fi
  
  log_fatal "Watcher failed to start"
  exit 1
fi

log_info "Watcher started successfully with PID: $WATCHER_PID"

# =========================
# STATE 6 — INITIAL SCAN
# =========================

if [ "${SYNC_EXIST_START}" = "true" ]; then
  log_info "Initial sync enabled, running scanner"
  
  # Временный файл для событий (без FIFO - проще)
  SCANNER_EVENTS="/tmp/scanner_events.$$.txt"
  
  # Запускаем scanner
  python3 "${BASE_DIR}/sync/scanner.py" "${MOUNT_POINT}" > "$SCANNER_EVENTS" 2>&1
  SCANNER_EXIT=$?
  
  if [ $SCANNER_EXIT -ne 0 ]; then
    # Ошибка scanner
    if grep -q "EVENT:FATAL:" "$SCANNER_EVENTS"; then
      reason=$(grep "EVENT:FATAL:" "$SCANNER_EVENTS" | tail -1 | cut -d: -f3-)
      log_error "Scanner fatal error: $reason"
      state_set LAST_ERROR "Scanner: $reason"
      
      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" fatal \
          "Backup Sync addon stopped" \
          "Reason: Scanner failed - $reason"
      fi
      
      log_fatal "Scanner fatal error: $reason"
      exit 1
    fi
  fi
  
  # Логируем результаты
  new_count=$(grep -c "EVENT:SCANNER_ENQUEUED:" "$SCANNER_EVENTS" 2>/dev/null || echo 0)
  skipped_count=$(grep -c "EVENT:SCANNER_SKIPPED:" "$SCANNER_EVENTS" 2>/dev/null || echo 0)
  
  if [ "$new_count" -gt 0 ]; then
    log_info "Scanner queued $new_count new backup(s)"
    # Обновляем статистику
    for ((i=0; i<new_count; i++)); do
      state_inc TOTAL_FOUND
    done
  fi
  
  if [ "$skipped_count" -gt 0 ]; then
    log_info "Scanner skipped $skipped_count already existing backup(s)"
  fi
  
  if [ "$new_count" -eq 0 ] && [ "$skipped_count" -gt 0 ]; then
    log_info "All backups already exist on USB"
  fi
  
  rm -f "$SCANNER_EVENTS"
  log_info "Scanner completed"
fi

# =========================
# STATE 7 — ГЛАВНЫЙ ЦИКЛ ОБРАБОТКИ ОЧЕРЕДИ
# =========================

log_info "Initialization complete. Entering main loop."

while true; do
  # Периодически проверяем, жив ли watcher
  if ! kill -0 "$WATCHER_PID" 2>/dev/null; then
    # Watcher умер - проверяем лог на ошибки
    if [ -f "$WATCHER_LOG" ]; then
      if grep -q "EVENT:FATAL:" "$WATCHER_LOG"; then
        reason=$(grep "EVENT:FATAL:" "$WATCHER_LOG" | tail -1 | cut -d: -f3-)
        log_error "Watcher died with fatal error: $reason"
        state_set LAST_ERROR "Watcher died: $reason"
      else
        state_set LAST_ERROR "Watcher process died unexpectedly"
      fi
    else
      state_set LAST_ERROR "Watcher process died (no log)"
    fi
    
    if [ -n "${NOTIFY_SERVICE:-}" ]; then
      python3 "${NOTIFY_BIN}" fatal \
        "Backup Sync addon stopped" \
        "Reason: Watcher process died"
    fi
    
    log_fatal "Watcher process died"
    exit 1
  fi
  
  # Обрабатываем очередь
  if [ -s "${QUEUE_FILE}" ]; then
    # Читаем первый файл из очереди
    read -r backup_file < "${QUEUE_FILE}"
    
    # Удаляем обработанную строку из очереди
    sed -i '1d' "${QUEUE_FILE}"
    
    filename="$(basename "${backup_file}")"
    log_debug "Processing backup: ${filename}"
    
    # Проверяем, существует ли файл
    if [ ! -f "${backup_file}" ]; then
      log_warn "Backup file disappeared: ${filename}"
      state_set LAST_ERROR "File disappeared: ${filename}"
      continue
    fi
    
    # Копируем файл
    if copy_backup "${backup_file}"; then
      # Успешное копирование
      log_info "Backup copied successfully: ${filename}"
      
      # Очищаем старые бэкапы (если нужно)
      if cleanup_backups; then
        log_debug "Cleanup completed"
      else
        log_warn "Cleanup had issues"
      fi
      
      # ОБНОВЛЯЕМ СТАТИСТИКУ
      state_inc TOTAL_COPIED
      state_set LAST_BACKUP "${filename}"
      state_set LAST_SYNC_TIME "$(date +%s)"
      state_set LAST_ERROR ""
      
      # УВЕДОМЛЕНИЕ ОБ УСПЕХЕ
      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" success \
          "Backup saved successfully" \
          "File: ${filename}"
      fi
      
    else
      # Ошибка копирования
      log_error "Backup copy failed: ${filename}"
      
      # ОБНОВЛЯЕМ СТАТИСТИКУ ОШИБОК
      state_inc TOTAL_FAILED
      state_set LAST_ERROR "Copy failed: ${filename}"
      
      # УВЕДОМЛЕНИЕ ОБ ОШИБКЕ
      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" error \
          "Backup copy failed" \
          "File: ${filename}"
      fi
    fi
  else
    # Очередь пуста - небольшая пауза
    sleep 10
  fi
done