#!/bin/bash
set -euo pipefail

# ===================================================
# Paths
# ===================================================
LOG_FILE="/config/backup.log"
LOCKFILE="/data/backup.lock"

# ===================================================
# Load logging
# ===================================================
source /etc/nc_backup/logging.sh

# ===================================================
# Lock (prevent parallel runs)
# ===================================================
if [ -e "$LOCKFILE" ]; then
    if [ "$(find "$LOCKFILE" -mmin +720 2>/dev/null)" ]; then
        log_yellow "Stale lock detected, removing"
        rm -f "$LOCKFILE"
    else
        log_yellow "Backup already running, exiting"
        exit 0
    fi
fi

touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# ===================================================
# Load configuration
# ===================================================
source /etc/nc_backup/config.sh

# ===================================================
# Header
# ===================================================
log_section "Nextcloud User Files Backup"

log "System: $(uname -s) $(uname -r)"
log "Architecture: $(uname -m)"
log "Timezone: $TIMEZONE"
log "Backup disk: $MOUNT_POINT_BACKUP"
log "Data source: $NEXTCLOUD_DATA_PATH"
log "Power control: $ENABLE_POWER"
log "Switch: $DISC_SWITCH_SELECT"
log "Notifications: $ENABLE_NOTIFICATIONS"
log "Service: $NOTIFICATION_SERVICE"

# ===================================================
# HA API helper (Supervisor)
# ===================================================
ha_api_call() {
    local endpoint="$1"
    local payload="${2:-}"

    curl -s \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$payload" \
        "http://supervisor/core/api/$endpoint"
}

# ===================================================
# Final handler
# ===================================================
handle_final_result() {
    local success="$1"
    local msg="$2"

    if [ "$success" = true ]; then
        log_green "Backup completed successfully"
        FINAL_MSG="$SUCCESS_MESSAGE"
    else
        log_red "Backup failed: $msg"
        FINAL_MSG="$msg"
    fi

    if [ "$ENABLE_NOTIFICATIONS" = "true" ]; then
        log "Sending notification…"
        PAYLOAD=$(jq -n --arg msg "$FINAL_MSG" '{"message":$msg}')
        if ha_api_call "services/notify/$NOTIFICATION_SERVICE" "$PAYLOAD" >/dev/null; then
            log_green "Notification sent"
        else
            log_red "Failed to send notification"
        fi
    fi

    exit $([ "$success" = true ] && echo 0 || echo 1)
}

# ===================================================
# Start
# ===================================================
log_green "Starting user files backup"

# ===================================================
# Power ON
# ===================================================
if [ "$ENABLE_POWER" = "true" ]; then
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

    [ "$STATE" != "on" ] && handle_final_result false "Disk power did not turn on"
    log "Waiting 40 seconds for disk initialization"
    sleep 40
fi

# ===================================================
# Disk checks
# ===================================================
[ ! -d "$MOUNT_POINT_BACKUP" ] && handle_final_result false "Backup disk not mounted"

if touch "$MOUNT_POINT_BACKUP/.test" 2>/dev/null; then
    rm -f "$MOUNT_POINT_BACKUP/.test"
    log "Backup disk writable"
else
    handle_final_result false "Backup disk not writable"
fi

[ ! -d "$NEXTCLOUD_DATA_PATH" ] && handle_final_result false "Nextcloud data not found"

# ===================================================
# Users
# ===================================================
USERS=$(find "$NEXTCLOUD_DATA_PATH" -maxdepth 1 -mindepth 1 -type d -exec basename {} \; | sort)
[ -z "$USERS" ] && handle_final_result false "No users found"

log_yellow "Users: $(echo "$USERS" | paste -sd ', ')"

# ===================================================
# Backup loop
# ===================================================
SUCCESS=true

for user in $USERS; do
    SRC="$NEXTCLOUD_DATA_PATH/$user/files/"
    DST="$MOUNT_POINT_BACKUP/$user/"

    [ ! -d "$SRC" ] && log_yellow "User $user has no files, skipping" && continue

    mkdir -p "$DST"
    log_blue "Backing up user: $user"

    if [ "$TEST_MODE" = "true" ]; then
        sleep 5
        log_purple "TEST MODE: simulated backup for $user"
    else
        if rsync $RSYNC_OPTIONS "$SRC" "$DST/"; then
            FILES=$(find "$DST" -type f | wc -l)
            log_green "User $user done ($FILES files)"
        else
            log_red "User $user backup failed"
            SUCCESS=false
        fi
    fi
done

# ===================================================
# Unmount + Power OFF
# ===================================================
if [ "$ENABLE_POWER" = "true" ]; then
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

# ===================================================
# Finish
# ===================================================
[ "$SUCCESS" = true ] \
    && handle_final_result true "" \
    || handle_final_result false "One or more users failed"
