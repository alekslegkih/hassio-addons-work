#!/bin/bash
set -euo pipefail

echo "==== CRON TRIGGER $(date) ====" >> /config/backup.log

# -----------------------------------------------------------
# Lock to prevent parallel runs
# -----------------------------------------------------------
LOCKFILE="/data/backup.lock"

if [ -e "$LOCKFILE" ]; then
    if [ "$(find "$LOCKFILE" -mmin +720)" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Stale lock detected, removing"
        rm -f "$LOCKFILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') Backup already running. Exiting."
        exit 0
    fi
fi

touch "$LOCKFILE"

cleanup() {
    rm -f "$LOCKFILE"
}
trap cleanup EXIT

# -----------------------------------------------------------
# Load HA token (runtime only)
# -----------------------------------------------------------
HA_TOKEN=$(jq -r '.ha_token // empty' /data/options.json)

if [ -z "$HA_TOKEN" ]; then
    log_red "HA_TOKEN is empty or not set in addon options"
    exit 1
fi


# Load logging functions and colors
source /etc/nc_backup/logging.sh

# Load configuration
source /etc/nc_backup/config.sh

# =============================================================================
# Nextcloud User Files Backup Script for Home Assistant Addon
# =============================================================================

# ===================================================
# --- Debug
# ===================================================

# handle_final_result false "❌ Stop debug"
# ===================================================

# =============test===========================
log "DEBUG: backup.sh started"
log "DEBUG: HA_TOKEN length = ${#HA_TOKEN}"

if [ -z "$HA_TOKEN" ]; then
  log_red "DEBUG: HA_TOKEN is EMPTY at runtime"
else
  log "DEBUG: HA_TOKEN is PRESENT"
fi


RESP_FILE="/config/ha_api_debug.json"

HTTP_CODE=$(curl -s \
  -o "$RESP_FILE" \
  -w "%{http_code}" \
  -H "Authorization: Bearer $HA_TOKEN" \
  http://homeassistant:8123/api/config)

log "DEBUG: HA API HTTP code = $HTTP_CODE"
log "DEBUG: HA API response:"
cat "$RESP_FILE" >> "$LOG_FILE"


# ============================================

# Set timezone
export TZ="${TIMEZONE:-Europe/Moscow}"

# Function for Home Assistant API calls with token
ha_api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local url="http://homeassistant:8123/api/$endpoint"
    
    if [ -n "$data" ]; then
        curl -s -X "$method" \
            -H "Authorization: Bearer $HA_TOKEN" \
            -H "Content-Type: application/json" \
            --data "$data" \
            "$url"
    else
        curl -s -X "$method" \
            -H "Authorization: Bearer $HA_TOKEN" \
            -H "Content-Type: application/json" \
            "$url"
    fi
}

# --- Unified error/success handler
handle_final_result() {
    local success="$1"
    local error_msg="${2:-}"
    
    if [ "$success" = true ] && [ -z "$error_msg" ]; then
        FINAL_MSG="$SUCCESS_MESSAGE"
        FINAL_LOG="Backup script completed successfully!"
        EXIT_CODE=0
    else
        if [ -n "$error_msg" ]; then
            log_red "$error_msg"
            FINAL_MSG="$error_msg"
        else
            FINAL_MSG="$ERROR_MESSAGE"
        fi
        FINAL_LOG="Backup script failed!"
        EXIT_CODE=1
    fi
    
    log "$FINAL_LOG"
    
    # Send to if enabled
    if [ "$ENABLE_NOTIFICATIONS" = "true" ]; then
        PAYLOAD=$(jq -n --arg msg "$FINAL_MSG" '{"message": $msg}')
        if ha_api_call "POST" "services/notify/$NOTIFICATION_SERVICE" "$PAYLOAD" > /dev/null; then
            log "Notification sent to: $FINAL_MSG"
        else
            log "Failed to send notification"
        fi
    else
        log "Notifications disabled"
    fi
    
    exit $EXIT_CODE
}

# --- Info
print_header() {
    echo -e "${BLUE}-----------------------------------------------------${NC}"
    echo -e "${BLUE}Add-on:  Nextcloud User Files Backup${NC}"
    echo -e "${BLUE}      for Home Assistant${NC}"
    echo -e "${BLUE}-----------------------------------------------------${NC}"
    echo -e "${BLUE}System: $(uname -s) $(uname -r)${NC}"
    echo -e "${BLUE}Architecture: $(uname -m)${NC}"
    echo -e "${BLUE}Timezone set to: $TZ ${NC}"
    echo -e "${BLUE}Backup disk: $MOUNT_POINT_BACKUP${NC}"
    echo -e "${BLUE}Data source: $NEXTCLOUD_DATA_PATH${NC}"
    echo -e "$([ "$ENABLE_POWER" = "true" ] && echo "${BLUE}Power control:${NC}${RED} ENABLED" || echo "${BLUE}Power control:${NC}${GREEN} DISABLED${NC}")"
    echo -e "${BLUE}Switch entity: $DISC_SWITCH_SELECT${NC}"   
    echo -e "$([ "$ENABLE_NOTIFICATIONS" = "true" ] && echo "${BLUE}Notifications:${NC}${RED} ENABLED${NC}" || echo "${BLUE}Notifications:${NC}${GREEN} DISABLED${NC}")"
    echo -e "${BLUE}Service: $NOTIFICATION_SERVICE${NC}"
    echo -e "$([ "$TEST_MODE" = "true" ] && echo "${BLUE}Test mode:${NC}${RED} ACTIVE${NC}" || echo "${BLUE}Test mode:${NC}${GREEN} INACTIVE${NC}")"
    echo -e "${BLUE}-----------------------------------------------------------${NC}"
}

print_header

log_green "Starting user files backup"
log_green "Started: $(date)"

# --- Check Home Assistant API availability
log "Checking Home Assistant API connection..."
API_RESPONSE=$(ha_api_call "GET" "" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('API OK' if 'message' in data else 'API Error')
except:
    print('API Error')
" 2>/dev/null || echo "API Error")

if [ "$API_RESPONSE" = "API OK" ]; then
    log "Home Assistant API connection successful"
else
    handle_final_result false "Home Assistant API connection failed"
fi

# --- Power Control Logic
if [ "$ENABLE_POWER" = "true" ]; then
    # --- Turn on power outlet for backup disk
    log "Power control enabled - turning on disk switch: $DISC_SWITCH_SELECT"
    ha_api_call "POST" "services/switch/turn_on" "$(jq -n --arg entity "$DISC_SWITCH_SELECT" '{entity_id: $entity}')" > /dev/null

    # --- Wait for outlet to become 'on'
    STATE="unknown"
    for i in {1..30}; do
        RESPONSE=$(ha_api_call "GET" "states/$DISC_SWITCH_SELECT" | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin)))" 2>/dev/null || echo '{"state":"unknown"}')
        STATE=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('state', 'unknown'))" 2>/dev/null || echo "unknown")
        
        if [ "$STATE" = "on" ]; then
            log "Backup disk power outlet successfully turned on"
            break
        fi
        log "Outlet state - $STATE. Attempt $i/30"
        sleep 2
    done

    if [ "$STATE" != "on" ]; then
        handle_final_result false "Disk power switch failed to turn on within 60 seconds"
    fi

    # --- Wait for disk initialization and mounting
    log "Waiting for backup disk initialization (40 sec)..."
    sleep 40
else
    # --- No power control - check if disk is already mounted
    log "Power control disabled - checking if disk is mounted..."
    if [ ! -d "$MOUNT_POINT_BACKUP" ]; then
        log "Disk not mounted, waiting for auto-mount (20 sec)..."
        sleep 20
        
        # Check again after waiting
        if [ ! -d "$MOUNT_POINT_BACKUP" ]; then
            handle_final_result false "Backup disk not mounted. Please check disk connection."
        fi
    fi
    log "Backup disk already mounted"
fi

# --- Check 1: Verify backup disk is mounted
if [ ! -d "$MOUNT_POINT_BACKUP" ]; then
    handle_final_result false "Backup disk not mounted. Please check disk connection."
fi
log "Backup disk mounted and ready"

# --- Check 2: Verify write permissions
if touch "$MOUNT_POINT_BACKUP/.write_test" 2>/dev/null; then
    rm -f "$MOUNT_POINT_BACKUP/.write_test"
    log "Backup disk ready for writing"
else
    handle_final_result false "No write permission on backup disk. Check disk permissions."
fi

# --- Check 3: Verify Nextcloud data is accessible
if [ ! -d "$NEXTCLOUD_DATA_PATH" ]; then
    handle_final_result false "Nextcloud data not accessible. Please check data disk."
fi
log "Nextcloud data accessible"

# --- Find all users from data directory
log "Getting user list from $NEXTCLOUD_DATA_PATH ..."
USERS=$(find "$NEXTCLOUD_DATA_PATH" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; 2>/dev/null | sort)

if [ -z "$USERS" ]; then
    handle_final_result false "No users found in Nextcloud data directory"
fi

USERS_LOG=$(echo "$USERS" | paste -sd ', ' -)
log "Found users: $USERS_LOG"

# --- Backup each user with files/ directory
SUCCESS=true
for user in $USERS; do
    SRC="$NEXTCLOUD_DATA_PATH/$user/files/"
    DST="$MOUNT_POINT_BACKUP/$user/"

    # Skip if user doesn't have files directory
    if [ ! -d "$SRC" ]; then
        log "User '$user' has no files directory — skipping"
        continue
    fi

    # Create destination directory if it doesn't exist
    mkdir -p "$DST"

    log "Starting backup for user: $user..."

    if [ "$TEST_MODE" = "true" ]; then
        # --- Simulation for testing
        log_blue "TEST MODE: Simulating copy (5 sec)..."
        sleep 5
        # Симулируем успешное копирование
        log_blue "TEST MODE: User $user backup simulation completed"
        log_blue "TEST MODE: Would copy approximately $(find "$SRC" -type f 2>/dev/null | wc -l) files"
    else
        # --- Actual user files backup
        log "Copying from $SRC to $DST ..."
        if rsync $RSYNC_OPTIONS "$SRC" "$DST/"; then
            log_green "User $user backup completed successfully"
            
            # Additional info about copied data
            FILE_COUNT=$(find "$DST" -type f | wc -l)
            log "Files copied: $FILE_COUNT"
        else
            log_red "User $user backup failed"
            SUCCESS=false
        fi
    fi
done

# --- Unmount and power off logic
if [ "$ENABLE_POWER" = "true" ]; then
    # --- Unmount disk before power off
    log "Unmounting backup disk..."
    curl -s -X POST -H "Content-Type: application/json" \
        -H "Authorization: Bearer $HA_TOKEN" \
        -d "{\"device\": \"$MOUNT_POINT_BACKUP\"}" \
        "http://supervisor/host/umount" > /dev/null

    if [ $? -eq 0 ]; then
        log "Backup disk unmounted successfully"
    else
        log "Failed to unmount backup disk"
        # Не прерываем выполнение - это не критическая ошибка
    fi

    # --- Turn off power
    log "Turning off backup disk power..."
    ha_api_call "POST" "services/switch/turn_off" "$(jq -n --arg entity "$DISC_SWITCH_SELECT" '{entity_id: $entity}')" > /dev/null
    log "Backup disk power turned off"
else
    log "Power control disabled - leaving disk mounted"
fi

# --- Final result
if [ "$SUCCESS" = true ]; then
    handle_final_result true ""
else
    handle_final_result false ""
fi