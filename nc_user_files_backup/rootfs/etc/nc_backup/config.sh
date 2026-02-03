#!/bin/bash
set -euo pipefail

# Configuration loader and validator
#
# Responsibilities:
# - Create default configuration on first run
# - Validate user-provided settings.yaml
# - Export validated settings as environment variables

# Load logging helpers
source /etc/nc_backup/logging.sh

# Validate cron format
# Performs a basic structural validation of cron expression.
# Expects exactly 5 fields:
#   minute hour day month weekday
#
# This does NOT validate cron semantics, only field count
validate_cron() {
    local CRON="$1"
    local FIELDS
    FIELDS=$(echo "$CRON" | awk '{print NF}')

    if [ "$FIELDS" -ne 5 ]; then
        log_red "Invalid cron format: '$CRON'"
        log_yellow "Expected: minute hour day month weekday"
        log_yellow "Example: 0 3 * * *"
        return 1
    fi

    return 0
}

# Validate configuration structure and values
# Checks:
# - Required sections existence
# - Required fields presence and non-empty values
# - Boolean fields validity (true / false)
#
# Does NOT validate filesystem paths or external resources.
validate_config() {
    log "Validating configuration file structure and values"
    local USER_CONFIG="$1"

    local required_fields=(
        "general.timezone"
        "general.schedule"
        "general.rsync_options"
        "general.test_mode"
        "storage.mount_path"
        "storage.label_backup"
        "storage.label_data"
        "storage.data_dir"
        "power.enable_power"
        "power.disc_switch"
        "notifications.enable_notifications"
        "notifications.notification_service"
        "notifications.success_message"
        "notifications.error_message"
    )

    # Expected top-level sections
    local expected_sections=("general" "storage" "power" "notifications")
    local actual_sections
    actual_sections=$(yq e 'keys | .[]' "$USER_CONFIG" 2>/dev/null | tr '\n' ' ')

    local has_errors=false
    local current_section=""

    # --- Validate sections
    for section in "${expected_sections[@]}"; do
        if [[ ! " $actual_sections " =~ " $section " ]]; then
            log_red "[MISSING SECTION] $section"
            log_yellow "Actual sections: $actual_sections"
            has_errors=true
        fi
    done

    # --- Validate fields
    for field in "${required_fields[@]}"; do
        local value
        value=$(yq e ".$field" "$USER_CONFIG" 2>/dev/null)

        local section="${field%.*}"
        local key="${field#*.}"

        if [[ " $actual_sections " =~ " $section " ]]; then
            if [ "$value" = "null" ] || [ -z "$value" ]; then
                if [ "$current_section" != "$section" ]; then
                    log_red "[FIELD ERRORS in $section]"
                    current_section="$section"
                fi
                log_red "Missing or empty: $key"
                has_errors=true
            fi

            # Explicit boolean validation
            if [[ "$key" =~ ^(test_mode|enable_power|enable_notifications)$ ]] &&
               [[ "$value" != "true" && "$value" != "false" ]]; then
                log_red "Invalid boolean: $section.$key = $value"
                log_yellow "Expected: true | false"
                has_errors=true
            fi
        fi
    done

    if [ "$has_errors" = true ]; then
        log_red "Configuration validation failed"
        return 1
    fi
    
    return 0
}

# Load configuration
# Return codes:
#   0 - configuration loaded successfully
#   1 - configuration error
#   2 - first run, default config created
load_config() {
    log "Loading configuration"

    local DEFAULT_CONFIG="/etc/nc_backup/defaults.yaml"
    local USER_CONFIG="/config/settings.yaml"

    # --- First run
    if [ ! -f "$USER_CONFIG" ]; then
        log_blue "====================================================="
        log_yellow "FIRST RUN DETECTED"
        log_blue "====================================================="

        if [ ! -f "$DEFAULT_CONFIG" ]; then
            log_red "Default config not found: $DEFAULT_CONFIG"
            return 1
        fi

        cp "$DEFAULT_CONFIG" "$USER_CONFIG"
        log_green "Default configuration created: $USER_CONFIG"
        log_yellow "Please edit settings.yaml and restart the addon"
        return 2
    fi

    log "Using configuration: $USER_CONFIG"

    # --- Validate config
    validate_config "$USER_CONFIG" || return 1

    # Load validated settings into environment
    export TIMEZONE=$(yq e '.general.timezone' "$USER_CONFIG")
    export BACKUP_SCHEDULE=$(yq e '.general.schedule // ""' "$USER_CONFIG")
    export RSYNC_OPTIONS=$(yq e '.general.rsync_options' "$USER_CONFIG")
    export TEST_MODE=$(yq e '.general.test_mode' "$USER_CONFIG")

    export MOUNT_PATH=$(yq e '.storage.mount_path' "$USER_CONFIG")
    export LABEL_BACKUP=$(yq e '.storage.label_backup' "$USER_CONFIG")
    export LABEL_DATA=$(yq e '.storage.label_data' "$USER_CONFIG")
    export DATA_DIR=$(yq e '.storage.data_dir' "$USER_CONFIG")

    export ENABLE_POWER=$(yq e '.power.enable_power' "$USER_CONFIG")
    export DISC_SWITCH=$(yq e '.power.disc_switch' "$USER_CONFIG")

    export ENABLE_NOTIFICATIONS=$(yq e '.notifications.enable_notifications' "$USER_CONFIG")
    export NOTIFICATION_SERVICE=$(yq e '.notifications.notification_service' "$USER_CONFIG")
    export SUCCESS_MESSAGE=$(yq e '.notifications.success_message' "$USER_CONFIG")
    export ERROR_MESSAGE=$(yq e '.notifications.error_message' "$USER_CONFIG")

    # --- Derived
    export MOUNT_POINT_BACKUP="/${MOUNT_PATH}/${LABEL_BACKUP}"
    export NEXTCLOUD_DATA_PATH="/${MOUNT_PATH}/${LABEL_DATA}/${DATA_DIR}"
    export DISC_SWITCH_SELECT="switch.${DISC_SWITCH}"
    # --- Notify
    export NOTIFICATION_SERVICE_SELECT="notify.${NOTIFICATION_SERVICE}"


    # --- Final cron validation
    validate_cron "$BACKUP_SCHEDULE" || return 1

    return 0
}
