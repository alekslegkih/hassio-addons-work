#!/usr/bin/env bash

# =========================
# Storage sanity checks
# =========================

set -euo pipefail

check_storage() {

  local source="/backup"
  local target="/media/${MOUNT_POINT}"

  log_info "Checking source and target directories"

  # --- Source checks ---
  if [ ! -d "${source}" ]; then
    log_error "Source directory ${source} does not exist"
    return 1
  fi

  if [ ! -r "${source}" ]; then
    log_error "Source directory ${source} is not readable"
    return 1
  fi

  log_debug "Source directory ${source} OK"

  # --- Target checks ---
  if [ ! -d "${target}" ]; then
    log_error "Target directory ${target} does not exist"
    return 1
  fi

  if ! mountpoint -q "${target}"; then
    log_error "Target directory ${target} is not a mount point"
    return 1
  fi

  if [ ! -w "${target}" ]; then
    log_error "Target directory ${target} is not writable"
    return 1
  fi

  log_debug "Target directory ${target} OK"

  # --- Free space check (soft) ---
  local free_space
  free_space=$(df -Pk "${target}" | awk 'NR==2 {print $4}')

  if [ -z "${free_space}" ] || [ "${free_space}" -le 0 ]; then
    log_error "Unable to determine free space on ${target}"
    return 1
  fi

  log_info "Free space on target: $((free_space / 1024)) MB"

  return 0
}

# Для ручного запуска
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  check_storage
fi
