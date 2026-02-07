#!/usr/bin/env bash

# =========================
# Cleanup old backups
# =========================

set -euo pipefail

cleanup_backups() {

  local target_dir="/media/${MOUNT_POINT}"

  if [ ! -d "${target_dir}" ]; then
    log_error "Cleanup skipped: target directory does not exist (${target_dir})"
    return 1
  fi

  log_info "Running cleanup in ${target_dir}"
  log_info "Keeping last ${MAX_COPIES} backups"

  # Получаем список backup-файлов (новые сверху)
  mapfile -t backups < <(
    ls -1t "${target_dir}"/*.tar "${target_dir}"/*.tar.gz 2>/dev/null || true
)

  local total="${#backups[@]}"

  if [ "${total}" -le "${MAX_COPIES}" ]; then
    log_info "No cleanup needed (${total}/${MAX_COPIES})"
    return 0
  fi

  log_warn "Found ${total} backups, cleaning up $((total - MAX_COPIES)) old ones"

  local index="${MAX_COPIES}"
  while [ "${index}" -lt "${total}" ]; do
    local file="${backups[${index}]}"

    if [ -f "${file}" ]; then
      log_info "Removing old backup: $(basename "${file}")"
      rm -f "${file}"
    else
      log_warn "File disappeared before removal: ${file}"
    fi

    index=$((index + 1))
  done

  log_info "Cleanup completed"
  return 0
}

# Ручной запуск
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  cleanup_backups
fi
