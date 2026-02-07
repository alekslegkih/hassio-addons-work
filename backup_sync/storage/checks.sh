#!/usr/bin/env bash

check_storage() {
  # 1. Source directory (/backup)
  if [ ! -d "/backup" ]; then
    log_error "Source directory /backup does not exist"
    return 1
  fi
  log_info "Source directory /backup OK"

  # 2. Device exists
  local device="/dev/${USB_DEVICE}"

  if [ ! -e "${device}" ]; then
    log_error "Device ${device} does not exist"
    return 1
  fi
  log_info "Device ${device} exists"

  # 3. Must be block device
  if [ ! -b "${device}" ]; then
    log_error "Device ${device} is not a block device"
    return 1
  fi

  # 4. Protect system disks
  case "${USB_DEVICE}" in
    sda*|mmcblk0*|nvme0n1*)
      log_error "Refusing to use system device: ${USB_DEVICE}"
      return 1
      ;;
  esac

  # 5. Filesystem detection
  local fstype
  fstype="$(lsblk -no FSTYPE "${device}" 2>/dev/null || true)"

  if [ -z "${fstype}" ]; then
    log_error "Filesystem not detected on ${device}"
    return 1
  fi

  log_info "Device ${device} filesystem: ${fstype}"

  return 0
}

check_target() {
  local target="/media/${MOUNT_POINT}"

  log_info "Checking target directory ${target}"

  # 1. Exists
  if [ ! -d "${target}" ]; then
    log_error "Target directory ${target} does not exist"
    return 1
  fi

  # 2. Is mountpoint
  if ! findmnt --target "${target}" >/dev/null 2>&1; then
    log_error "Target ${target} is not a mountpoint"
    return 1
  fi

  # 3. Writable test
  local testfile="${target}/.write_test"

  if ! touch "${testfile}" 2>/dev/null; then
    log_error "Target ${target} is not writable"
    return 1
  fi

  rm -f "${testfile}"

  log_info "Target directory ${target} OK"
  return 0
}
