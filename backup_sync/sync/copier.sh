#!/usr/bin/env bash

# =========================
# Backup copy logic
# =========================

set -euo pipefail

RETRY_COUNT=3
RETRY_DELAY=600

copy_backup() {

  local source_file="$1"
  local target_dir="/media/${MOUNT_POINT}"

  if [ -z "${source_file}" ]; then
    log_error "No source file provided to copier"
    return 1
  fi

  if [ ! -f "${source_file}" ]; then
    log_error "Source file does not exist: ${source_file}"
    return 1
  fi

  if [ ! -d "${target_dir}" ]; then
    log_error "Target directory does not exist: ${target_dir}"
    return 1
  fi

  local filename
  filename="$(basename "${source_file}")"
  local target_file="${target_dir}/${filename}"

  if [ -f "${target_file}" ]; then
    log_info "Backup already exists on USB, skipping: ${filename}"
    return 0  # Уже есть - считаем успехом
  fi

  log_info "Starting copy: ${filename}"

  local attempt=1
  while [ "${attempt}" -le "${RETRY_COUNT}" ]; do

    local start_ts
    start_ts=$(date +%s)

    if cp -f "${source_file}" "${target_file}"; then
      sync

      local end_ts
      end_ts=$(date +%s)

      local duration=$((end_ts - start_ts))
      local size_bytes
      size_bytes=$(stat -c %s "${target_file}")
      local size_mb=$((size_bytes / 1024 / 1024))

      log_info "Copy completed: ${filename}"
      log_info "Size: ${size_mb} MB, Time: ${duration}s"
      
      log_debug "Copy attempt ${attempt}/${RETRY_COUNT}"

      return 0
    fi

    log_warn "Copy failed for ${filename}"

    if [ "${attempt}" -lt "${RETRY_COUNT}" ]; then
      log_warn "Retrying in ${RETRY_DELAY} seconds"
      sleep "${RETRY_DELAY}"
    fi

    attempt=$((attempt + 1))
  done

  log_error "All copy attempts failed for ${filename}"
  return 1
}

# Ручной запуск
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  copy_backup "$@"
fi
