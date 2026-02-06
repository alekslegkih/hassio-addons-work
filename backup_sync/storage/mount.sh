#!/usr/bin/env bash

# =========================
# USB mount logic
# =========================

set -euo pipefail

mount_usb() {

  local device="/dev/${USB_DEVICE}"
  local target="/media/${MOUNT_POINT}"

  log_info "Preparing to mount ${device} to ${target}"

  # Проверка устройства
  if [ ! -b "${device}" ]; then
    log_error "Device ${device} does not exist or is not a block device"
    return 1
  fi

  # Создаём точку монтирования
  if [ ! -d "${target}" ]; then
    log_debug "Creating mount point ${target}"
    mkdir -p "${target}"
  fi

  # Проверяем, не смонтировано ли уже
  if mountpoint -q "${target}"; then
    log_info "Mount point ${target} already mounted"
    return 0
  fi

  # Пытаемся смонтировать
  log_info "Mounting ${device}..."
  if mount "${device}" "${target}"; then
    log_info "Successfully mounted ${device} to ${target}"
  else
    log_error "Failed to mount ${device} to ${target}"
    return 1
  fi

  # Финальная проверка
  if mountpoint -q "${target}"; then
    log_debug "Mount verification successful"
    return 0
  else
    log_error "Mount verification failed for ${target}"
    return 1
  fi
}

# Для ручного запуска
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  mount_usb
fi
