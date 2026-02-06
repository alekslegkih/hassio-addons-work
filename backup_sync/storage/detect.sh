#!/usr/bin/env bash

# =========================
# Storage device detection
# =========================

set -euo pipefail

# Фильтры системных дисков
SYSTEM_DISKS_REGEX="^(sda|mmcblk0|zram)"

detect_devices() {

  log_info "Scanning available storage devices..."

  # Получаем список partition:
  # NAME TYPE FSTYPE SIZE LABEL
  lsblk -pn -o NAME,TYPE,FSTYPE,SIZE,LABEL \
    | while read -r name type fstype size label; do

        # Нас интересуют только partition
        [ "${type}" != "part" ] && continue

        base_name="$(basename "${name}")"

        # Фильтруем системные диски
        if [[ "${base_name}" =~ ${SYSTEM_DISKS_REGEX} ]]; then
          log_debug "Skipping system device ${base_name}"
          continue
        fi

        # Должна быть файловая система
        if [ -z "${fstype}" ]; then
          log_debug "Skipping ${base_name} (no filesystem)"
          continue
        fi

        # Формируем строку для вывода
        if [ -n "${label}" ]; then
          echo "${base_name} (${fstype}, ${size}, ${label})"
        else
          echo "${base_name} (${fstype}, ${size})"
        fi
    done
}

# Если скрипт запущен напрямую — просто выводим результат
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  detect_devices
fi
