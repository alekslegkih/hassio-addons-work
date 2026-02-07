#!/usr/bin/env bash

mount_usb() {
  local device="/dev/${USB_DEVICE}"
  local target="/media/${MOUNT_POINT}"

  log_info "Preparing USB mount"
  log_info "  Device : ${device}"
  log_info "  Target : ${target}"

  # Ensure target directory exists
  if [ ! -d "${target}" ]; then
    log_info "Creating target directory ${target}"
    mkdir -p "${target}" || {
      log_error "Failed to create target directory ${target}"
      return 1
    }
  fi

  # 1. Target already mounted → OK
  if findmnt --target "${target}" >/dev/null 2>&1; then
    log_info "Target ${target} is already mounted"
    return 0
  fi

  # 2. Device already mounted somewhere → bind-mount
  local src_mount
  src_mount="$(findmnt -n -o TARGET --source "${device}" 2>/dev/null || true)"

  if [ -n "${src_mount}" ]; then
    log_info "Device ${device} already mounted at ${src_mount}"
    log_info "Bind-mounting ${src_mount} → ${target}"

    if mount --bind "${src_mount}" "${target}"; then
      log_info "Bind-mount successful"
      return 0
    else
      log_error "Bind-mount failed"
      return 1
    fi
  fi

  # 3. Device not mounted anywhere → mount directly
  log_info "Device ${device} not mounted, mounting directly to ${target}"

  if mount "${device}" "${target}"; then
    log_info "Direct mount successful"
    return 0
  fi

  log_error "Failed to mount ${device} to ${target}"
  return 1
}
