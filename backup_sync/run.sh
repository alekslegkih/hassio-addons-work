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
  
  # Создаем FIFO для обработки событий в основном процессе
  EVENT_FIFO="/tmp/scanner_events.fifo"
  rm -f "$EVENT_FIFO"
  mkfifo "$EVENT_FIFO"
  
  # Запускаем scanner и обрабатываем события в основном процессе
  python3 "${BASE_DIR}/sync/scanner.py" > "$EVENT_FIFO" &
  SCANNER_PID=$!
  
  # Обрабатываем события
  while read -r line; do
    case "${line}" in
      EVENT:SCANNER_STARTED)
        log_info "Scanner started"
        ;;
      EVENT:SCANNER_ENQUEUED:*)
        file="${line#EVENT:SCANNER_ENQUEUED:}"
        state_inc TOTAL_FOUND
        log_debug "Scanner queued: $(basename "${file}")"
        ;;
      EVENT:SCANNER_EMPTY)
        log_info "No existing backups found"
        ;;
      EVENT:SCANNER_DONE:*)
        count="${line#EVENT:SCANNER_DONE:}"
        log_info "Scanner finished, queued ${count} backups"
        ;;
      EVENT:FATAL:*)
        reason="${line#EVENT:FATAL:}"
        state_set LAST_ERROR "${reason}"
        
        if [ -n "${NOTIFY_SERVICE:-}" ]; then
          python3 "${NOTIFY_BIN}" fatal \
            "Backup Sync addon stopped" \
            "Reason: ${reason}"
        fi
        
        log_fatal "Scanner fatal error: ${reason}"
        exit 1
        ;;
    esac
  done < "$EVENT_FIFO"
  
  wait "$SCANNER_PID"
  rm -f "$EVENT_FIFO"
fi

# =========================
# STATE 6 — WATCHER (запуск в фоне, НО обработка через очередь)
# =========================

log_info "Starting watcher in background"

# Запускаем watcher в фоне
python3 "${BASE_DIR}/sync/watcher.py" > /tmp/watcher.log 2>&1 &
WATCHER_PID=$!

# Ждем, чтобы убедиться, что watcher запустился
sleep 2
if ! kill -0 "$WATCHER_PID" 2>/dev/null; then
  state_set LAST_ERROR "Watcher failed to start"
  
  if [ -n "${NOTIFY_SERVICE:-}" ]; then
    python3 "${NOTIFY_BIN}" fatal \
      "Backup Sync addon stopped" \
      "Reason: Watcher failed to start"
  fi
  
  log_fatal "Watcher failed to start"
  exit 1
fi

log_info "Watcher started with PID: ${WATCHER_PID}"

# =========================
# STATE 7 — ГЛАВНЫЙ ЦИКЛ ОБРАБОТКИ ОЧЕРЕДИ
# =========================

log_info "Initialization complete. Entering main loop."

while true; do
  # Проверяем, жив ли watcher
  if ! kill -0 "$WATCHER_PID" 2>/dev/null; then
    state_set LAST_ERROR "Watcher process died"
    
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
    read -r backup_file < "${QUEUE_FILE}"
    sed -i '1d' "${QUEUE_FILE}"
    
    filename="$(basename "${backup_file}")"
    log_info "Processing backup: ${filename}"
    
    # Проверяем, существует ли файл
    if [ ! -f "${backup_file}" ]; then
      log_warn "Backup file disappeared: ${filename}"
      continue
    fi
    
    # Обновляем статистику - НАЙДЕН файл
    # Эта статистика будет обновляться и из scanner, и при обработке новых файлов
    state_inc TOTAL_FOUND
    
    # Пытаемся скопировать
    if copy_backup "${backup_file}"; then
      # Очищаем старые бэкапы
      cleanup_backups
      
      # Обновляем статистику
      state_inc TOTAL_COPIED
      state_set LAST_BACKUP "${filename}"
      state_set LAST_SYNC_TIME "$(date +%s)"
      state_set LAST_ERROR ""
      
      # Уведомление об успехе
      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" success \
          "Backup saved successfully" \
          "File: ${filename}"
      fi
      
      log_info "Backup ${filename} copied successfully"
    else
      # Обновляем статистику ошибок
      state_inc TOTAL_FAILED
      state_set LAST_ERROR "Copy failed: ${filename}"
      
      # Уведомление об ошибке
      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" error \
          "Backup copy failed" \
          "File: ${filename}"
      fi
      
      log_error "Backup copy failed: ${filename}"
    fi
  fi
  
  sleep 5
done