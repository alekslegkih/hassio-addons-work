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
# This provides all exported variables from settings.yaml
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

# Header / environment info
log_blue "Starting backup of Nextcloud user files"

log "System: $(uname -s) $(uname -r)"
log "Architecture: $(uname -m)"
log "Timezone: $TIMEZONE"
log "Backup destination: $MOUNT_POINT_BACKUP"
log "Nextcloud data source: $NEXTCLOUD_DATA_PATH"
log "Backup disk power management enabled: $ENABLE_POWER"
log "Backup disk power switch entity: $DISC_SWITCH_SELECT"
log "Notifications enabled: $ENABLE_NOTIFICATIONS"
log "Home Assistant notify service: $NOTIFICATION_SERVICE_SELECT"

# Home Assistant Supervisor API helper
# Used for:
# - switch control
# - notifications
# - disk unmount
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

# Unified final handler
# Handles:
# - final logging
# - optional notifications
# - correct exit code
handle_final_result() {
    local success="$1"
    local msg="$2"

    if [ "$success" = true ]; then
        log_green "Nextcloud user files backup completed successfully"
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

log_green "Starting rsync file copy process"

# Power ON backup disk (optional)
if [ "$ENABLE_POWER" = "true" ]; then
    log "Turning ON backup disk power"
    ha_api_call "services/switch/turn_on" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')"

    # Wait for switch to report ON state
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

        # Give the disk time to spin up and mount
        log "Waiting for disk power ($i/30), state=$STATE"
        sleep 2
    done

    [ "$STATE" != "on" ] && handle_final_result false "Backup disk power management failed"
    log "Waiting 40 seconds for disk initialization"
    sleep 40
fi

# Disk and source validation
[ ! -d "$MOUNT_POINT_BACKUP" ] && handle_final_result false"Backup destination dick is not mounted"

# Check write access
if touch "$MOUNT_POINT_BACKUP/.test" 2>/dev/null; then
    rm -f "$MOUNT_POINT_BACKUP/.test"
    log "Backup disk writable"
else
    handle_final_result false "Backup destination dick is not writable"
fi

[ ! -d "$NEXTCLOUD_DATA_PATH" ] && handle_final_result false "No Nextcloud users with files found"

# Detect Nextcloud users
log "Searching Nextcloud users..."

# A valid user directory must contain a 'files' subdirectory
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

# Final result
[ "$SUCCESS" = true ] \
    && handle_final_result true "" \
    || handle_final_result false "One or more user file backups failed"
