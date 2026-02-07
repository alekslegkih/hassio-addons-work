#!/usr/bin/env bash

# =========================
# State management
# =========================

STATE_FILE="/data/state.env"

# Значения по умолчанию
state_defaults() {
  START_TIME="$(date +%s)"
  TOTAL_FOUND=0
  TOTAL_COPIED=0
  TOTAL_FAILED=0
  LAST_BACKUP=""
  LAST_ERROR=""
  LAST_SYNC_TIME=0
}

state_load() {
  if [ -f "${STATE_FILE}" ]; then
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  else
    state_defaults
    state_save
  fi
}

state_save() {
  cat > "${STATE_FILE}" <<EOF
START_TIME=${START_TIME}
TOTAL_FOUND=${TOTAL_FOUND}
TOTAL_COPIED=${TOTAL_COPIED}
TOTAL_FAILED=${TOTAL_FAILED}
LAST_BACKUP="${LAST_BACKUP}"
LAST_ERROR="${LAST_ERROR}"
LAST_SYNC_TIME=${LAST_SYNC_TIME}
EOF
}

state_init() {
  state_defaults
  state_save
}

state_inc() {
  local key="$1"

  case "${key}" in
    TOTAL_FOUND)
      TOTAL_FOUND=$((TOTAL_FOUND + 1))
      ;;
    TOTAL_COPIED)
      TOTAL_COPIED=$((TOTAL_COPIED + 1))
      ;;
    TOTAL_FAILED)
      TOTAL_FAILED=$((TOTAL_FAILED + 1))
      ;;
    *)
      return 1
      ;;
  esac

  state_save
}

state_set() {
  local key="$1"
  local value="$2"

  case "${key}" in
    LAST_BACKUP)
      LAST_BACKUP="${value}"
      ;;
    LAST_ERROR)
      LAST_ERROR="${value}"
      ;;
    LAST_SYNC_TIME)
      LAST_SYNC_TIME="${value}"
      ;;
    *)
      return 1
      ;;
  esac

  state_save
}

state_dump() {
  log_info "State summary:"
  log_info "  Started at        : $(date -d "@${START_TIME}" 2>/dev/null || echo ${START_TIME})"
  log_info "  Backups found     : ${TOTAL_FOUND}"
  log_info "  Backups copied    : ${TOTAL_COPIED}"
  log_info "  Copy failures     : ${TOTAL_FAILED}"
  log_info "  Last backup       : ${LAST_BACKUP:-<none>}"
  log_info "  Last sync time    : ${LAST_SYNC_TIME:-<never>}"
  log_info "  Last error        : ${LAST_ERROR:-<none>}"
}
