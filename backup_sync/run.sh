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
log_info "  sync_exis_start   = ${SYNC_EXIST_START}"
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
# STATE 1.5 — WAIT FOR SUPERVISOR MOUNTS
# =========================

log_info "Waiting for Supervisor mounts (/backup)"

SUPERVISOR_WAIT_MAX=3660   # seconds
SUPERVISOR_WAIT_STEP=5
elapsed=0

while [ ! -d "/backup" ]; do
  if [ "${elapsed}" -ge "${SUPERVISOR_WAIT_MAX}" ]; then
    state_set LAST_ERROR "Supervisor mount /backup not available"

    if [ -n "${NOTIFY_SERVICE:-}" ]; then
      python3 "${NOTIFY_BIN}" fatal \
        "Backup Sync addon stopped" \
        "Reason: /backup not available"
    fi

    log_fatal "/backup directory not available after ${SUPERVISOR_WAIT_MAX}s"
    exit 1
  fi

  sleep "${SUPERVISOR_WAIT_STEP}"
  elapsed=$((elapsed + SUPERVISOR_WAIT_STEP))
done

log_info "/backup is available"

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

        if [ -n "${NOTIFY_SERVICE:-}" ]; then
          python3 "${NOTIFY_BIN}" fatal \
            "Backup Sync addon stopped" \
            "Reason: ${reason}"
        fi

        log_fatal "Scanner fatal error: ${reason}"
        exit 1
        ;;
    esac
  done
fi

# =========================
# STATE 6 — WATCHER
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

      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" fatal \
          "Backup Sync addon stopped" \
          "Reason: ${reason}"
      fi

      log_fatal "Watcher fatal error: ${reason}"
      exit 1
      ;;
  esac
done &

# =========================
# STATE 7 — MAIN LOOP
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

      if [ -n "${NOTIFY_SERVICE:-}" ]; then
        python3 "${NOTIFY_BIN}" success \
          "Backup saved successfully" \
          "File: ${filename}"
      fi
    else
      state_inc TOTAL_FAILED
      state_set LAST_ERROR "Copy failed: ${filename}"

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
