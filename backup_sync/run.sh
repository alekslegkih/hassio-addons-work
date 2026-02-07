#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/usr/local/backup_sync"
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
NOTIFY_BIN="${BASE_DIR}/notifications/ha_notify.py"

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
# STATE 5 — INITIAL SCAN 
# =========================

if [ "${SYNC_EXIST_START}" = "true" ]; then
  log_info "Initial sync enabled, running scanner"
  
  # Создаем именованный канал для обработки событий в основном процессе
  SCANNER_FIFO="/tmp/scanner_fifo.$$"
  rm -f "$SCANNER_FIFO"
  mkfifo "$SCANNER_FIFO"
  
  # Запускаем scanner, пишем в FIFO
  python3 "${BASE_DIR}/sync/scanner.py" "${MOUNT_POINT}" > "$SCANNER_FIFO" 2>&1 &
  SCANNER_PID=$!
  
  # Обрабатываем события в основном процессе
  NEW_COUNT=0
  SKIPPED_COUNT=0
  
  while read -r line; do
    case "${line}" in
      EVENT:SCANNER_STARTED)
        log_info "Scanner started"
        ;;
      EVENT:SCANNER_TARGET:*)
        target="${line#EVENT:SCANNER_TARGET:}"
        log_debug "Scanner target: $target"
        ;;
      EVENT:SCANNER_ENQUEUED:*)
        file="${line#EVENT:SCANNER_ENQUEUED:}"
        state_inc TOTAL_FOUND
        NEW_COUNT=$((NEW_COUNT + 1))
        log_debug "Scanner queued: $(basename "${file}")"
        ;;
      EVENT:SCANNER_SKIPPED:*)
        file="${line#EVENT:SCANNER_SKIPPED:}"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        [ "$LOG_LEVEL" = "debug" ] && log_debug "Scanner skipped: $file"
        ;;
      EVENT:SCANNER_SKIPPED_COUNT:*)
        count="${line#EVENT:SCANNER_SKIPPED_COUNT:}"
        log_info "Scanner skipped $count already existing backup(s)"
        ;;
      EVENT:SCANNER_FOUND:*)
        total="${line#EVENT:SCANNER_FOUND:}"
        log_debug "Total backups found: $total"
        ;;
      EVENT:SCANNER_EXISTING:*)
        existing="${line#EVENT:SCANNER_EXISTING:}"
        log_debug "Existing backups on USB: $existing"
        ;;
      EVENT:SCANNER_EMPTY)
        log_info "No backups found in /backup"
        ;;
      EVENT:SCANNER_ALL_EXIST)
        log_info "All backups already exist on USB"
        ;;
      EVENT:SCANNER_DONE:*)
        count="${line#EVENT:SCANNER_DONE:}"
        if [ "$count" -eq 0 ]; then
          log_info "Scanner completed, no new backups found"
        else
          log_info "Scanner queued $count new backup(s)"
        fi
        ;;
      EVENT:FATAL:*)
        reason="${line#EVENT:FATAL:}"
        log_error "Scanner fatal error: $reason"
        state_set LAST_ERROR "Scanner: $reason"
        
        if [ -n "${NOTIFY_SERVICE:-}" ]; then
          python3 "${NOTIFY_BIN}" fatal \
            "Backup Sync addon stopped" \
            "Reason: Scanner failed - $reason"
        fi
        
        # Убиваем процесс scanner если он еще жив
        kill $SCANNER_PID 2>/dev/null || true
        rm -f "$SCANNER_FIFO"
        log_fatal "Scanner fatal error: $reason"
        exit 1
        ;;
      *)
        # Неизвестное событие - логируем только в debug
        [ "$LOG_LEVEL" = "debug" ] && log_debug "Unknown scanner event: $line"
        ;;
    esac
  done < "$SCANNER_FIFO"
  
  # Ждем завершения scanner процесса
  wait $SCANNER_PID
  SCANNER_EXIT_CODE=$?
  
  # Очищаем FIFO
  rm -f "$SCANNER_FIFO"
  
  if [ $SCANNER_EXIT_CODE -ne 0 ] && [ $SCANNER_EXIT_CODE -ne 141 ]; then
    # 141 = SIGPIPE, нормально при закрытии FIFO
    log_error "Scanner exited with code: $SCANNER_EXIT_CODE"
    state_set LAST_ERROR "Scanner exited with code: $SCANNER_EXIT_CODE"
  fi
  
  log_debug "Scanner completed"
fi

# =========================
# STATE 6 — ЗАПУСК WATCHER В ФОНЕ
# =========================

log_info "Starting watcher in background"

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
    log_info "Processing backup: ${filename}"
    
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