#!/bin/bash
set -euo pipefail

# Configuration loader (options.json → environment)
#
# Responsibilities:
# - Load validated configuration from /data/options.json
# - Export environment variables used by runtime scripts
# - Prepare derived and helper values
#
# Structural validation is handled by Home Assistant Supervisor via config.yaml schema

# Load logging helpers
source /etc/nc_backup/logging.sh

OPTIONS_FILE="/data/options.json"

load_config() {
    log "Loading configuration from options.json"

    if [ ! -f "$OPTIONS_FILE" ]; then
        log_red "Configuration file not found: $OPTIONS_FILE"
        return 1
    fi

    # --- General
    export BACKUP_SCHEDULE="$(jq -r '.schedule' "$OPTIONS_FILE")"
    export RSYNC_OPTIONS="$(jq -r '.rsync_options' "$OPTIONS_FILE")"
    export TIMEZONE="$(jq -r '.timezone' "$OPTIONS_FILE")"
    export TEST_MODE="$(jq -r '.test_mode' "$OPTIONS_FILE")"

    # --- Storage (NEW KEYS)
    export MOUNT_ROOT="$(jq -r '.storage.mount_root' "$OPTIONS_FILE")"
    export BACKUP_DISK_LABEL="$(jq -r '.storage.backup_disk_label' "$OPTIONS_FILE")"
    export DATA_DISK_LABEL="$(jq -r '.storage.data_disk_label' "$OPTIONS_FILE")"
    export NEXTCLOUD_DATA_DIR="$(jq -r '.storage.nextcloud_data_dir' "$OPTIONS_FILE")"

    # --- Power (NEW KEYS)
    export POWER_ENABLED="$(jq -r '.power.enabled' "$OPTIONS_FILE")"
    export POWER_DISK_SWITCH="$(jq -r '.power.disk_switch // ""' "$OPTIONS_FILE")"

    # --- Notifications (NEW KEYS)
    export NOTIFICATIONS_ENABLED="$(jq -r '.notifications.enabled' "$OPTIONS_FILE")"
    export NOTIFICATIONS_SERVICE="$(jq -r '.notifications.service // ""' "$OPTIONS_FILE")"
    export SUCCESS_MESSAGE="$(jq -r '.notifications.success_message // ""' "$OPTIONS_FILE")"
    export ERROR_MESSAGE="$(jq -r '.notifications.error_message // ""' "$OPTIONS_FILE")"

    # --- Cross-field validation (NOT covered by schema)
    if [ "$POWER_ENABLED" = "true" ] && [ -z "$POWER_DISK_SWITCH" ]; then
        log_red "Invalid configuration:"
        log_red "power.enabled is true, but power.disk_switch is empty"
        return 1
    fi 

    if [ "$NOTIFICATIONS_ENABLED" = "true" ] && [ -z "$NOTIFICATIONS_SERVICE" ]; then
        log_red "Invalid configuration:"
        log_red "notifications.enabled is true, but notifications.service is empty"
        return 1
    fi

    # --- Derived paths
    export MOUNT_POINT_BACKUP="/${MOUNT_ROOT}/${BACKUP_DISK_LABEL}"
    export NEXTCLOUD_DATA_PATH="/${MOUNT_ROOT}/${DATA_DISK_LABEL}/${NEXTCLOUD_DATA_DIR}"

    # ---------------------------------------------------------------------
    # Home Assistant entity helpers
    #
    # Pattern:
    # - *_SERVICE / *_SWITCH variables store raw option values
    #   (without Home Assistant domain prefix).
    #   These values are used for Supervisor API calls.
    #
    # - *_SELECT variables add the required Home Assistant domain prefix
    #   (e.g. notify., switch.) and are intended for:
    #   - logging
    #   - passing full entity IDs where required
    #
    # This separation avoids mixing API paths and entity IDs
    # and keeps logging human-readable and HA-consistent.
    # ---------------------------------------------------------------------

    if [ -n "$POWER_DISK_SWITCH" ]; then
        export DISC_SWITCH_SELECT="switch.${POWER_DISK_SWITCH}"
    fi

    if [ -n "$NOTIFICATIONS_SERVICE" ]; then
        export NOTIFICATION_SERVICE_SELECT="notify.${NOTIFICATIONS_SERVICE}"
    fi

    log_green "Configuration loaded successfully"
    return 0
}
