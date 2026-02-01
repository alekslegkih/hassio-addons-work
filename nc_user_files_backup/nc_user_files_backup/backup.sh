#!/bin/bash
set -euo pipefail

LOG_FILE="/config/backup.log"
LOCKFILE="/data/backup.lock"

echo "==== CRON TRIGGER $(date) ====" >> "$LOG_FILE"

# -----------------------------------------------------------
# Lock to prevent parallel runs
# -----------------------------------------------------------
if [ -e "$LOCKFILE" ]; then
    if find "$LOCKFILE" -mmin +720 >/dev/null 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Stale lock detected, removing" >> "$LOG_FILE"
        rm -f "$LOCKFILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') Backup already running. Exiting." >> "$LOG_FILE"
        exit 0
    fi
fi

touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# -----------------------------------------------------------
# Load logging + config
# -----------------------------------------------------------
source /etc/nc_backup/logging.sh
source /etc/nc_backup/config.sh

# -----------------------------------------------------------
# Supervisor API helper
# -----------------------------------------------------------
ha_api_call() {
    local service="$1"
    local payload="$2"

    curl -s \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$payload" \
        "http://supervisor/core/api/services/$service"
}

# -----------------------------------------------------------
# Header
# -----------------------------------------------------------
print_header() {
    echo -e "${BLUE}-----------------------------------------------------${NC}"
    echo -e "${BLUE}Add-on:  Nextcloud User Files Backup${NC}"
    echo -e "${BLUE}      for Home Assistant${NC}"
    echo -e "${BLUE}-----------------------------------------------------${NC}"
    echo -e "${BLUE}System: $(uname -s) $(uname -r)${NC}"
    echo -e "${BLUE}Architecture: $(uname -m)${NC}"
    echo -e "${BLUE}Timezone: $TIMEZONE${NC}"
    echo -e "${BLUE}Backup disk: $MOUNT_POINT_BACKUP${NC}"
    echo -e "${BLUE}Data source: $NEXTCLOUD_DATA_PATH${NC}"
    echo -e "${BLUE}Power control: $ENABLE_POWER${NC}"
    echo -e "${BLUE}Switch: $DISC_SWITCH_SELECT${NC}"
    echo -e "${BLUE}Notifications: $ENABLE_NOTIFICATIONS${NC}"
    echo -e "${BLUE}Service: $NOTIFICATION_SERVICE${NC}"
    echo -e "${BLUE}-----------------------------------------------------${NC}"
}

print_header >> "$LOG_FILE"

log_green "Starting user files backup" >> "$LOG_FILE"

# -----------------------------------------------------------
# Power ON disk
# -----------------------------------------------------------
if [ "$ENABLE_POWER" = "true" ]; then
    log "Turning ON backup disk power" >> "$LOG_FILE"
    ha_api_call "switch/turn_on" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')" >/dev/null
    sleep 40
fi

# -----------------------------------------------------------
# Checks
# -----------------------------------------------------------
[ -d "$MOUNT_POINT_BACKUP" ] || handle_final_result false "Backup disk not mounted"
[ -d "$NEXTCLOUD_DATA_PATH" ] || handle_final_result false "Nextcloud data not accessible"

touch "$MOUNT_POINT_BACKUP/.write_test" 2>/dev/null \
    && rm -f "$MOUNT_POINT_BACKUP/.write_test" \
    || handle_final_result false "No write permission on backup disk"

# -----------------------------------------------------------
# Backup users
# -----------------------------------------------------------
USERS=$(find "$NEXTCLOUD_DATA_PATH" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; | sort)
[ -n "$USERS" ] || handle_final_result false "No users found"

SUCCESS=true

for user in $USERS; do
    SRC="$NEXTCLOUD_DATA_PATH/$user/files/"
    DST="$MOUNT_POINT_BACKUP/$user/"

    [ -d "$SRC" ] || continue
    mkdir -p "$DST"

    log "Backing up user: $user" >> "$LOG_FILE"

    if [ "$TEST_MODE" = "true" ]; then
        sleep 3
    else
        rsync $RSYNC_OPTIONS "$SRC" "$DST/" || SUCCESS=false
    fi
done

# -----------------------------------------------------------
# Unmount + Power OFF
# -----------------------------------------------------------
if [ "$ENABLE_POWER" = "true" ]; then
    log "Unmounting backup disk" >> "$LOG_FILE"
    curl -s \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "{\"device\":\"$MOUNT_POINT_BACKUP\"}" \
        http://supervisor/host/umount >/dev/null || true

    log "Turning OFF backup disk power" >> "$LOG_FILE"
    ha_api_call "switch/turn_off" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')" >/dev/null
fi

# -----------------------------------------------------------
# Notifications + exit
# -----------------------------------------------------------
if [ "$ENABLE_NOTIFICATIONS" = "true" ]; then
    MSG=$([ "$SUCCESS" = true ] && echo "$SUCCESS_MESSAGE" || echo "$ERROR_MESSAGE")
    ha_api_call "notify/$NOTIFICATION_SERVICE" \
        "$(jq -n --arg m "$MSG" '{message:$m}')" >/dev/null || true
fi

[ "$SUCCESS" = true ] && exit 0 || exit 1
