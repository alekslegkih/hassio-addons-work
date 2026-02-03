#!/bin/bash
set -euo pipefail

# Configuration loader (options.json → environment)
#
# Responsibilities:
# - Load validated configuration from /data/options.json
# - Export environment variables used by runtime scripts
# - Prepare derived and helper values
#
# Validation is handled by Home Assistant Supervisor via config.yaml schema

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

    # --- Storage
    export MOUNT_PATH="$(jq -r '.storage.mount_path' "$OPTIONS_FILE")"
    export LABEL_BACKUP="$(jq -r '.storage.label_backup' "$OPTIONS_FILE")"
    export LABEL_DATA="$(jq -r '.storage.label_data' "$OPTIONS_FILE")"
    export DATA_DIR="$(jq -r '.storage.data_dir' "$OPTIONS_FILE")"

    # --- Power
    export ENABLE_POWER="$(jq -r '.power.enable_power' "$OPTIONS_FILE")"
    export DISC_SWITCH="$(jq -r '.power.disc_switch // ""' "$OPTIONS_FILE")"

    # --- Notifications
    export ENABLE_NOTIFICATIONS="$(jq -r '.notifications.enable_notifications' "$OPTIONS_FILE")"
    export NOTIFICATION_SERVICE="$(jq -r '.notifications.notification_service // ""' "$OPTIONS_FILE")"
    export SUCCESS_MESSAGE="$(jq -r '.notifications.success_message // ""' "$OPTIONS_FILE")"
    export ERROR_MESSAGE="$(jq -r '.notifications.error_message // ""' "$OPTIONS_FILE")"

    # Cross-field validation 
    if [ "$ENABLE_POWER" = "true" ] && [ -z "$DISC_SWITCH" ]; then
        log_red "Invalid configuration:"
        log_red "power.enable_power is true, but power.disc_switch is empty"
        return 1
    fi

    if [ "$ENABLE_NOTIFICATIONS" = "true" ] && [ -z "$NOTIFICATION_SERVICE" ]; then
        log_red "Invalid configuration:"
        log_red "notifications.enable_notifications is true, but notifications.notification_service is empty"
        return 1
    fi

    # --- Derived paths
    export MOUNT_POINT_BACKUP="/${MOUNT_PATH}/${LABEL_BACKUP}"
    export NEXTCLOUD_DATA_PATH="/${MOUNT_PATH}/${LABEL_DATA}/${DATA_DIR}"

    # --- Home Assistant entity helpers
    if [ -n "$DISC_SWITCH" ]; then
        export DISC_SWITCH_SELECT="switch.${DISC_SWITCH}"
    fi

    if [ -n "$NOTIFICATION_SERVICE" ]; then
        export NOTIFICATION_SERVICE_SELECT="notify.${NOTIFICATION_SERVICE}"
    fi

    log_green "Configuration loaded successfully"
    return 0
}
