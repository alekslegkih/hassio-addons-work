#!/usr/bin/env bash

mount_usb() {
  local device="/dev/${USB_DEVICE}"
  local target="/media/${MOUNT_POINT}"

  log_info "Checking mount state for ${device}"

  # 1. Проверяем, смонтирован ли девайс вообще
  if ! findmnt --source "${device}" >/dev/null 2>&1; then
    log_error "Device ${device} is not mounted by HAOS"
    return 1
  fi

  # 2. Получаем реальную точку монтирования
  local real_mount
  real_mount="$(findmnt -n -o TARGET --source "${device}")"

  if [ -z "${real_mount}" ]; then
    log_error "Unable to determine mount point for ${device}"
    return 1
  fi

  log_info "Device ${device} already mounted at ${real_mount}"

  # 3. Если пользовательский mount_point совпадает — всё ок
  if [ "${real_mount}" = "${target}" ]; then
    log_info "Mount point matches configured path (${target})"
    return 0
  fi

  # 4. Проверяем, не сделан ли уже bind-mount
  if findmnt --target "${target}" >/dev/null 2>&1; then
    log_info "Target ${target} already mounted"
    return 0
  fi

  # 5. Делаем bind-mount
  log_info "Bind-mounting ${real_mount} to ${target}"
  mkdir -p "${target}"

  if mount --bind "${real_mount}" "${target}"; then
    log_info "Bind-mount successful"
    return 0
  fi

  log_error "Bind-mount failed"
  return 1
}
