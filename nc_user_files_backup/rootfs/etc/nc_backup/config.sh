#!/bin/bash
set -euo pipefail

# ===================================================
# Load logging
# ===================================================
source /etc/nc_backup/logging.sh

# ===================================================
# Validate cron format
# ===================================================
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

# ===================================================
# Validate configuration structure
# ===================================================
validate_config() {
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

    local expected_sections=("general" "storage" "power" "notifications")
    local actual_sections
    actual_sections=$(yq e 'keys | .[]' "$USER_CONFIG" 2>/dev/null | tr '\n' ' ')

    local has_errors=false
    local current_section=""

    # --- Check sections
    for section in "${expected_sections[@]}"; do
        if [[ ! " $actual_sections " =~ " $section " ]]; then
            log_red "[MISSING SECTION] $section"
            log_yellow "Actual sections: $actual_sections"
            has_errors=true
        fi
    done

    # --- Check fields
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

    log_green "Configuration validation passed"
    return 0
}

# ===================================================
# Load configuration
# ===================================================
load_config() {
    log "Setting up configuration…"

    local DEFAULT_CONFIG="/etc/nc_backup/defaults.yaml"
    local USER_CONFIG="/config/settings.yaml"

    # --- First run
    if [ ! -f "$USER_CONFIG" ]; then
        log_section "FIRST RUN DETECTED"

        if [ ! -f "$DEFAULT_CONFIG" ]; then
            log_red "Default config not found: $DEFAULT_CONFIG"
            return 1
        fi

        cp "$DEFAULT_CONFIG" "$USER_CONFIG"
        log_green "Default configuration created: $USER_CONFIG"
        log_yellow "Please edit settings.yaml and restart the addon"
        return 2
    fi

    log "Using existing settings: $USER_CONFIG"

    # --- Validate
    validate_config "$USER_CONFIG" || return 1
    validate_cron "$BACKUP_SCHEDULE" || return 1

    # ===================================================
    # Load settings
    # ===================================================
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

    return 0
}


# ===================================================
# Execute
# ===================================================
load_config
RC=$?

case "$RC" in
    0)
        log_green "Configuration loaded successfully"
        ;;
    2)
        log_yellow "Waiting for user configuration"
        exit 0
        ;;
    *)
        log_red "Configuration loaded failed"
        exit 1
        ;;
esac
