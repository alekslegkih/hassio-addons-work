#!/usr/bin/env bash

check_storage() {
  log_info "Running storage checks"

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
