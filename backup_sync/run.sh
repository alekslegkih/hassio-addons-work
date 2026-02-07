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
NOTIFY_BIN="${BASE_DIR}/notifications/ha_notify.py"

# =========================
# Exit handler
# =========================
trap 'state_dump' EXIT

# =========================
# Startup
# =========================

log_info "--------------------------------------------------"
log_info "Backup Sync addon starting..."

load_config
state_load

log_info "Configuration:"
log_info "  usb_device        = ${USB_DEVICE:-<not set>}"
log_info "  mount_point       = ${MOUNT_POINT}"
log_info "  max_copies        = ${MAX_COPIES}"
log_info "  sync_exis_start   = ${SYNC_EXIST_START}"
log_info "  log_level         = ${LOG_LEVEL}"

# =========================
# USB device detection
# =========================

if [ -z "${USB_DEVICE}" ]; then
  log_warn "usb_device is not set"
  log_info "Available storage devices:"
  detect_devices || true

  state_set LAST_ERROR "usb_device not configured"
  python3 "${NOTIFY_BIN}" fatal \
    "Backup Sync addon stopped" \
    "Reason: usb_device not configured"

  log_fatal "Please configure usb_device and restart addon"
  exit 1
fi

# =========================
# Mount & checks
# =========================

if ! mount_usb; then
  state_set LAST_ERROR "USB mount failed"
  python3 "${NOTIFY_BIN}" fatal \
    "Backup Sync addon stopped" \
    "Reason: USB mount failed"

  log_fatal "USB mount failed"
  exit 1
fi

if ! check_storage; then
  state_set LAST_ERROR "Storage checks failed"
  python3 "${NOTIFY_BIN}" fatal \
    "Backup Sync addon stopped" \
    "Reason: Storage checks failed"

  log_fatal "Storage checks failed"
  exit 1
fi

# =========================
# Initial scan (scanner.py)
# =========================

if [ "${SYNC_EXIST_START}" = "true" ]; then
  log_info "Initial sync enabled, running scanner"

  python3 "${BASE_DIR}/sync/scanner.py" | while read -r line; do
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
        python3 "${NOTIFY_BIN}" fatal \
          "Backup Sync addon stopped" \
          "Reason: ${reason}"
        log_fatal "Scanner fatal error: ${reason}"
        exit 1
        ;;
    esac
  done
fi

# =========================
# Start watchdog
# =========================

log_info "Starting watchdog"

python3 "${BASE_DIR}/sync/watcher.py" | while read -r line; do
  case "${line}" in
    EVENT:WATCHER_STARTED)
      log_info "Watchdog started"
      ;;
    EVENT:NEW_BACKUP:*)
      file="${line#EVENT:NEW_BACKUP:}"
      state_inc TOTAL_FOUND
      log_info "New backup detected: $(basename "${file}")"
      ;;
    EVENT:ENQUEUED:*)
      file="${line#EVENT:ENQUEUED:}"
      log_debug "Backup enqueued: $(basename "${file}")"
      ;;
    EVENT:BACKUP_GONE:*)
      file="${line#EVENT:BACKUP_GONE:}"
      log_warn "Backup disappeared: $(basename "${file}")"
      ;;
    EVENT:FATAL:*)
      reason="${line#EVENT:FATAL:}"
      state_set LAST_ERROR "${reason}"
      python3 "${NOTIFY_BIN}" fatal \
        "Backup Sync addon stopped" \
        "Reason: ${reason}"
      log_fatal "Watcher fatal error: ${reason}"
      exit 1
      ;;
  esac
done &

# =========================
# Queue processing loop
# =========================

log_info "Initialization complete. Waiting for backups."

while true; do
  if [ -s "${QUEUE_FILE}" ]; then
    read -r backup_file < "${QUEUE_FILE}"
    sed -i '1d' "${QUEUE_FILE}"

    filename="$(basename "${backup_file}")"
    log_info "Processing backup: ${filename}"

    if copy_backup "${backup_file}"; then
      cleanup_backups

      state_inc TOTAL_COPIED
      state_set LAST_BACKUP "${filename}"
      state_set LAST_SYNC_TIME "$(date +%s)"
      state_set LAST_ERROR ""

      python3 "${NOTIFY_BIN}" success \
        "Backup saved successfully" \
        "File: ${filename}"

    else
      state_inc TOTAL_FAILED
      state_set LAST_ERROR "Copy failed: ${filename}"

      python3 "${NOTIFY_BIN}" error \
        "Backup copy failed" \
        "File: ${filename}"

      log_error "Backup copy failed: ${filename}"
    fi
  fi

  sleep 5
done
