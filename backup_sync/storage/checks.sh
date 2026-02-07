#!/usr/bin/env bash

check_storage() {
  local src="/backup"
  local device="/dev/${USB_DEVICE}"
  local target="/media/${MOUNT_POINT}"

  log_info "Running storage checks"

  # 1. Проверка исходной директории
  if [ ! -d "${src}" ]; then
    log_error "Source directory ${src} does not exist"
    return 1
  fi

  if [ ! -r "${src}" ]; then
    log_error "Source directory ${src} is not readable"
    return 1
  fi

  log_info "Source directory ${src} OK"

  # 2. Проверка устройства
  if [ ! -b "${device}" ]; then
    log_error "Device ${device} not found or not a block device"
    return 1
  fi

  log_info "Device ${device} exists"

  # 3. Проверка, что устройство смонтировано HAOS
  if ! findmnt --source "${device}" >/dev/null 2>&1; then
    log_error "Device ${device} is not mounted by HAOS"
    return 1
  fi

  log_info "Device ${device} is mounted"

  # 4. Проверка каталога назначения
  if [ ! -d "${target}" ]; then
    log_error "Target directory ${target} does not exist"
    return 1
  fi

  if [ ! -w "${target}" ]; then
    log_error "Target directory ${target} is not writable"
    return 1
  fi

  # 5. Проверка записи (touch)
  local testfile="${target}/.backup_sync_test"

  if ! touch "${testfile}" 2>/dev/null; then
    log_error "Unable to write to ${target}"
    return 1
  fi

  rm -f "${testfile}"

  log_info "Target directory ${target} OK"

  return 0
}
