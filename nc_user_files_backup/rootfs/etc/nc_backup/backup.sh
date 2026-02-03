#!/bin/bash
set -euo pipefail

# Load logging helpers
source /etc/nc_backup/logging.sh

# Runtime paths
# LOCKFILE  - prevents parallel or overlapping backup runs
LOCKFILE="/config/backup.lock"

# Lock handling (prevent parallel executions)
# If a lock exists:
# - remove it if older than 3 hours (stale run)
# - otherwise exit silently
if [ -e "$LOCKFILE" ]; then
    if [ "$(find "$LOCKFILE" -mmin +180 2>/dev/null)" ]; then
        log_yellow "Stale lock detected, removing"
        rm -f "$LOCKFILE"
    else
        log_yellow "Backup already running, exiting"
        exit 0
    fi
fi

# Create lock and ensure cleanup on exit
touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# Load validated configuration and environment
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

# Header / environment info
log_blue "-----------------------------------------------------------"
log_blue "Date $(_ts)"
log_blue "Starting backup of Nextcloud user files"
log_blue "-----------------------------------------------------------"

log "System: $(uname -s) $(uname -r)"
log "Architecture: $(uname -m)"
log "Timezone: $TIMEZONE"
log "Backup destination: $MOUNT_POINT_BACKUP"
log "Nextcloud data source: $NEXTCLOUD_DATA_PATH"
log "Backup disk power management enabled: $POWER_ENABLED"
log "Backup disk power switch entity: $DISC_SWITCH_SELECT"
log "Notifications enabled: $NOTIFICATIONS_ENABLED"
log "Home Assistant notify service: $NOTIFICATION_SERVICE_SELECT"
log "-----------------------------------------------------------"

# Home Assistant Supervisor API helper
ha_api_call() {
    local endpoint="$1"
    local payload="${2:-}"

    curl -s \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$payload" \
        "http://supervisor/core/api/$endpoint" \
        >/dev/null
}

# Unified final handler
handle_final_result() {
    local success="$1"
    local final_msg="$2"

    if [ "$success" != true ] && [ -z "$final_msg" ]; then
        final_msg="$ERROR_MESSAGE"
    fi

    if [ "$NOTIFICATIONS_ENABLED" = "true" ]; then
        PAYLOAD=$(jq -n --arg msg "$final_msg" '{"message":$msg}')
        ha_api_call "services/notify/$NOTIFICATION_SERVICE_SELECT" "$PAYLOAD" \
            && log_green "Notification sent via $NOTIFICATION_SERVICE_SELECT" \
            || log_red "Failed to send notification via $NOTIFICATION_SERVICE_SELECT"
    fi

    [ "$success" = true ] && log_green "$final_msg" || log_red "$final_msg"

    log_green "-----------------------------------------------------------"
    log_green "Backup scheduler started, waiting for scheduled time"

    exit $([ "$success" = "true" ] && echo 0 || echo 1)

}

log_green "Starting rsync file copy process"

# Power ON backup disk (optional)
if [ "$POWER_ENABLED" = "true" ]; then
    log "Turning ON backup disk power"
    ha_api_call "services/switch/turn_on" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')"

    STATE="unknown"
    for i in {1..30}; do
        STATE=$(curl -s \
            -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
            http://supervisor/core/api/states/$DISC_SWITCH_SELECT \
            | jq -r '.state // "unknown"' || echo "unknown")

        if [ "$STATE" = "on" ]; then
            log_green "Disk power is ON"
            break
        fi

        log "Waiting for disk power ($i/30), state=$STATE"
        sleep 2
    done

    [ "$STATE" != "on" ] && handle_final_result false "Backup disk power management failed"
    log "Waiting 40 seconds for disk initialization"
    sleep 40
fi

# Disk and source validation
[ ! -d "$MOUNT_POINT_BACKUP" ] && handle_final_result false "Backup destination disk is not mounted"

# Check write access
if touch "$MOUNT_POINT_BACKUP/.test" 2>/dev/null; then
    rm -f "$MOUNT_POINT_BACKUP/.test"
    log "Backup disk writable"
else
    handle_final_result false "Backup destination disk is not writable"
fi

[ ! -d "$NEXTCLOUD_DATA_PATH" ] && handle_final_result false "No Nextcloud users with files found"

# Detect Nextcloud users
log "Searching Nextcloud users..."

USERS=$(
    find "$NEXTCLOUD_DATA_PATH" \
        -mindepth 1 -maxdepth 1 \
        -type d \
        -exec bash -c '
            for d; do
                [ -d "$d/files" ] && basename "$d"
            done
        ' bash {} +
)

if [ -z "$USERS" ]; then
    handle_final_result false "No Nextcloud users with files directory found"
fi

log_yellow "Users found: $(echo "$USERS" | paste -sd ', ')"

# Backup loop (per user)
SUCCESS=true

for user in $USERS; do
    SRC="$NEXTCLOUD_DATA_PATH/$user/files/"
    DST="$MOUNT_POINT_BACKUP/$user/"

    [ ! -d "$SRC" ] && log_yellow "User $user has no files, skipping" && continue

    mkdir -p "$DST"
    log_blue "Copying files for user: $user"

    if [ "$TEST_MODE" = "true" ]; then
        sleep 5
        log_purple "TEST MODE: simulated backup for $user"
    else
        if rsync $RSYNC_OPTIONS "$SRC" "$DST/"; then
            FILES=$(find "$DST" -type f | wc -l)
            log_green "User $user files backed up ($FILES files)"
        else
            log_red "Failed to back up files for user $user"
            SUCCESS=false
        fi
    fi
done

# Unmount disk and power OFF (optional)
if [ "$POWER_ENABLED" = "true" ]; then
    log "Unmounting backup disk"
    curl -s -X POST \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"device\":\"$MOUNT_POINT_BACKUP\"}" \
        http://supervisor/host/umount >/dev/null || log_yellow "Unmount failed"

    log "Turning OFF backup disk power"
    ha_api_call "services/switch/turn_off" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')"
fi

# Final result
[ "$SUCCESS" = true ] \
    && handle_final_result true "$SUCCESS_MESSAGE" \
    || handle_final_result false ""
