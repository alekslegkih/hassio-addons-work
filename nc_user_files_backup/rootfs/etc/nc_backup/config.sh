#!/bin/bash
set -euo pipefail

# ============================================================================
# Configuration loader: options.json → environment variables
#
# Responsibilities:
# - Load configuration from /data/options.json
# - Export variables required by runtime scripts (run.sh, backup.sh)
# - Perform cross-field validation NOT covered by config.yaml schema
# - Prepare derived paths and Home Assistant helper variables
#
# NOTE:
# - Structural validation (types, regex, required keys) is handled by
#   Home Assistant Supervisor via config.yaml schema
# - This file focuses on runtime safety and logical consistency
# ============================================================================

# Load logging helpers (colored output, etc.)
source /etc/nc_backup/logging.sh

OPTIONS_FILE="/data/options.json"

load_config() {
    log "Loading configuration from options.json"

    # ------------------------------------------------------------------------
    # Sanity check
    # ------------------------------------------------------------------------
    if [ ! -f "$OPTIONS_FILE" ]; then
        log_red "Configuration file not found: $OPTIONS_FILE"
        return 1
    fi

    # ------------------------------------------------------------------------
    # General settings
    # ------------------------------------------------------------------------
    export BACKUP_SCHEDULE="$(jq -r '.schedule' "$OPTIONS_FILE")"
    export RSYNC_OPTIONS="$(jq -r '.rsync_options' "$OPTIONS_FILE")"
    export TIMEZONE="$(jq -r '.timezone' "$OPTIONS_FILE")"
    export TEST_MODE="$(jq -r '.test_mode' "$OPTIONS_FILE")"

    # ------------------------------------------------------------------------
    # Storage settings
    # ------------------------------------------------------------------------
    MOUNT_ROOT="$(jq -r '.storage.mount_root' "$OPTIONS_FILE")"
    BACKUP_DISK_LABEL="$(jq -r '.storage.backup_disk_label' "$OPTIONS_FILE")"
    DATA_DISK_LABEL="$(jq -r '.storage.data_disk_label' "$OPTIONS_FILE")"
    NEXTCLOUD_DATA_DIR="$(jq -r '.storage.nextcloud_data_dir' "$OPTIONS_FILE")"

    # ------------------------------------------------------------------------
    # Power management
    #
    # POWER_DISK_SWITCH is intentionally NOT exported.
    # It is only used locally to construct derived variables.
    # ------------------------------------------------------------------------
    export POWER_ENABLED="$(jq -r '.power.enabled' "$OPTIONS_FILE")"
    POWER_DISK_SWITCH="$(jq -r '.power.disk_switch // ""' "$OPTIONS_FILE")"

    # ------------------------------------------------------------------------
    # Notifications
    #
    # NOTIFICATIONS_SERVICE IS exported because:
    # - Supervisor API paths use raw service names
    #   (services/notify/<service>)
    # ------------------------------------------------------------------------
    export NOTIFICATIONS_ENABLED="$(jq -r '.notifications.enabled' "$OPTIONS_FILE")"
    export NOTIFICATIONS_SERVICE="$(jq -r '.notifications.service // ""' "$OPTIONS_FILE")"
    export SUCCESS_MESSAGE="$(jq -r '.notifications.success_message // ""' "$OPTIONS_FILE")"
    export ERROR_MESSAGE="$(jq -r '.notifications.error_message // ""' "$OPTIONS_FILE")"

    # ------------------------------------------------------------------------
    # Cross-field validation (logical constraints)
    # These conditions cannot be expressed in config.yaml schema
    # ------------------------------------------------------------------------
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

    # ------------------------------------------------------------------------
    # Derived paths
    # These are the actual filesystem paths used by backup.sh
    # ------------------------------------------------------------------------
    export MOUNT_POINT_BACKUP="/${MOUNT_ROOT}/${BACKUP_DISK_LABEL}"
    export DATA_MOUNT_POINT="/${MOUNT_ROOT}/${DATA_DISK_LABEL}"
    export NEXTCLOUD_DATA_PATH="/${DATA_MOUNT_POINT}/${NEXTCLOUD_DATA_DIR}"

    # ------------------------------------------------------------------------
    # Home Assistant entity helpers
    #
    # Pattern:
    # - Raw option values (without domain):
    #     POWER_DISK_SWITCH
    #     NOTIFICATIONS_SERVICE
    #
    # - Derived *_SELECT variables:
    #     DISC_SWITCH_SELECT="switch.<entity_id>"
    #     NOTIFICATION_SERVICE_SELECT="notify.<service>"
    #
    # Why:
    # - Supervisor API uses raw service names in URLs
    # - Logs and HA state queries require full entity IDs
    # - Separation avoids accidental mixing of concepts
    # ------------------------------------------------------------------------
    if [ -n "$POWER_DISK_SWITCH" ]; then
        export DISC_SWITCH_SELECT="switch.${POWER_DISK_SWITCH}"
    fi

    if [ -n "$NOTIFICATIONS_SERVICE" ]; then
        export NOTIFICATION_SERVICE_SELECT="notify.${NOTIFICATIONS_SERVICE}"
    fi

    log_green "Configuration loaded successfully"
    return 0
}
