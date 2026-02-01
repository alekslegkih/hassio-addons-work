#!/bin/bash
set -euo pipefail

# Load logging functions and colors
source /etc/nc_backup/logging.sh

# Function to validate configuration structure
validate_config() {
    local USER_CONFIG="$1"
    
    # Required fields with full paths
    local required_fields=(
        "general.timezone"
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
    
    local has_errors=false
    local current_section=""
    
    # First, check if sections exist and have correct names
    local expected_sections=("general" "storage" "power" "notifications")
    local actual_sections=$(yq e "keys | .[]" "$USER_CONFIG" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
    
    for expected_section in "${expected_sections[@]}"; do
        if [[ ! " $actual_sections " =~ " $expected_section " ]]; then
            log_red "[MISSING SECTION]"
            log_red "  Expected: $expected_section"
            log_red "  → Actual sections: $actual_sections"
            log_green "  → Should be: '$expected_section'"
            has_errors=true
            echo ""
        fi
    done
    
    # Then check fields within existing sections
    for field in "${required_fields[@]}"; do
        local value=$(yq e ".$field" "$USER_CONFIG" 2>/dev/null)
        local section="${field%.*}"
        local key="${field#*.}"
        
        # Only check fields if section exists
        if [[ " $actual_sections " =~ " $section " ]]; then
            if [ "$value" = "null" ] || [ -z "$value" ]; then
                if [ "$section" != "$current_section" ]; then
                    if [ "$has_errors" = true ]; then
                        echo ""  # Add spacing between sections
                    fi
                    log_red "[FIELD ERRORS in $section]"
                    current_section="$section"
                fi
                
                # Get actual fields in this section for comparison
                local actual_fields=$(yq e ".$section | keys | .[]" "$USER_CONFIG" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
                if [ -n "$actual_fields" ]; then
                    log_red "  Expected: $key"
                    log_red "  → Actual:  $actual_fields"
                    log_green "  → Should be: '$key'"
                else
                    log_red "    Missing: $key (section exists but empty)"
                fi
                
                has_errors=true
            elif [[ "$key" == "test_mode" || "$key" == "enable_power" || "$key" == "enable_notifications" ]] && \
                [ "$value" != "true" ] && [ "$value" != "false" ]; then
                # Boolean field validation
                if [ "$section" != "$current_section" ]; then 
                    if [ "$has_errors" = true ]; then
                        echo ""  # Add spacing between sections
                    fi
                    log_red "[FIELD ERRORS in $section]"
                    current_section="$section"
                fi
                
                log_red "  → Invalid boolean: $key = '$value'"
                log_green "  → Should be: 'true' or 'false'"
                
                has_errors=true
            fi
        fi
    done
    
    if [ "$has_errors" = true ]; then
        echo ""  # Add spacing before final message
        log_red "Configuration validation failed!"
        log_yellow "Please check for typos in your settings.yaml"
        return 1
    fi
    
    log_green "Configuration validation passed"
    return 0
}

# load funktion
load_config() {
    log "Setting up configuration..."
    
    local DEFAULT_CONFIG="/etc/nc_backup/defaults.yaml"  
    local CONFIG_DIR="/config"
    local USER_CONFIG="${CONFIG_DIR}/settings.yaml"
    
    # Create default settings if not exists
    if [ ! -f "$USER_CONFIG" ]; then
        echo -e "${BLUE}-----------------------------------------------------------${NC}"
        echo -e "${BLUE} Add-on:  Nextcloud User Files Backup${NC}"
        echo -e "${BLUE}       for Home Assistant${NC}"
        echo -e "${YELLOW}  === FIRST RUN DETECTED${NC} ==="
        echo -e "${BLUE}-----------------------------------------------------------${NC}"

        log "Creating default settings file..."
        if [ -f "$DEFAULT_CONFIG" ]; then
            cp "$DEFAULT_CONFIG" "$USER_CONFIG"
            log "Settings file created: $USER_CONFIG"
            echo -e "${YELLOW}-----------------------------------------------------------${NC}"
            echo -e "${YELLOW} Configuration file has been created at: $USER_CONFIG${NC}"
            echo -e "${YELLOW} Please edit this file to configure your backup settings:${NC}"
            echo -e "${YELLOW}   - Set correct disk labels${NC}"
            echo -e "${YELLOW}   - Configure timezone${NC}" 
            echo -e "${YELLOW}   - Adjust other settings as needed${NC}"
            echo -e "${GREEN} After configuration, restart the addon.${NC}"
            echo -e "${YELLOW}-------------------------------------------------${NC}"
            return 2
        else
            log_red "Default config not found: $DEFAULT_CONFIG"
            return 1
        fi
    else
        log "Using existing settings: $USER_CONFIG"
    fi
    
    # Validate configuration structure
    if ! validate_config "$USER_CONFIG"; then
        return 1
    fi

    # Load HA token from addon options
    # if [ -r /data/options.json ]; then
    #     HA_TOKEN=$(jq -r '.ha_token // ""' /data/options.json)
    #     log "Loaded HA token ${#HA_TOKEN}"
    #     # Validate HA Token
    #     if [ -z "$HA_TOKEN" ]; then
    #         log_red "HA Token is empty"
    #         return 1
    #     fi
    # else
    #     log_red "Cannot read /data/options.json"
    #     return 1
    # fi

    # Load settings from USER config
    export TIMEZONE=$(yq e '.general.timezone // "Europe/Moscow"' "$USER_CONFIG")
    export RSYNC_OPTIONS=$(yq e '.general.rsync_options // "-aHAX --delete"' "$USER_CONFIG")
    export TEST_MODE=$(yq e '.general.test_mode // false' "$USER_CONFIG")

    # Storage settings
    export MOUNT_PATH=$(yq e '.storage.mount_path // "media"' "$USER_CONFIG")
    export LABEL_BACKUP=$(yq e '.storage.label_backup // "NC_backup"' "$USER_CONFIG")
    export LABEL_DATA=$(yq e '.storage.label_data // "Data"' "$USER_CONFIG")
    export DATA_DIR=$(yq e '.storage.data_dir // "data"' "$USER_CONFIG")

    # Power settings
    export ENABLE_POWER=$(yq e '.power.enable_power // false' "$USER_CONFIG")
    export DISC_SWITCH=$(yq e '.power.disc_switch // "switch.usb_disk_power"' "$USER_CONFIG")

    # Notification settings
    export ENABLE_NOTIFICATIONS=$(yq e '.notifications.enable_notifications // true' "$USER_CONFIG")
    export NOTIFICATION_SERVICE=$(yq e '.notifications.notification_service // "telegram_cannel_system"' "$USER_CONFIG")
    export SUCCESS_MESSAGE=$(yq e '.notifications.success_message // "Nextcloud user files backup completed successfully!"' "$USER_CONFIG")
    export ERROR_MESSAGE=$(yq e '.notifications.error_message // "Nextcloud backup completed with errors!"' "$USER_CONFIG")

    # Set derived values
    export MOUNT_POINT_BACKUP="/${MOUNT_PATH}/${LABEL_BACKUP}"
    export NEXTCLOUD_DATA_PATH="/${MOUNT_PATH}/${LABEL_DATA}/${DATA_DIR}"
    export DISC_SWITCH_SELECT="switch.${DISC_SWITCH}"
    
    log "Configuration loaded successfully"

    return 0
}